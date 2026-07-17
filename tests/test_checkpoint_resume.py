import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location("transcode_cli", Path(__file__).parents[1] / "cross-platform" / "transcode_cli.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "movie.mkv"
        self.source.write_bytes(b"source")
        self.profile = cli.PROFILES["hevc_mkv"]

    def tearDown(self):
        self.temp.cleanup()

    def test_source_specific_same_directory_checkpoint(self):
        checkpoint = cli.checkpoint_path(self.source)
        self.assertEqual(checkpoint.parent, self.source.parent)
        self.assertIn(self.source.name, checkpoint.name)

    def test_signature_detects_source_and_encoding_changes(self):
        command = cli.build_video_cmd(self.source, Path("segment.mkv"), self.profile, "software", 2, 24)
        first = cli.checkpoint_signature(self.source, "hevc_mkv", self.profile, "software", 2, 24, 30, command)
        self.source.write_bytes(b"changed source")
        second = cli.checkpoint_signature(self.source, "hevc_mkv", self.profile, "software", 2, 24, 30, command)
        changed_command = cli.build_video_cmd(self.source, Path("segment.mkv"), self.profile, "nvenc", 4, 20)
        changed_options = cli.checkpoint_signature(self.source, "hevc_mkv", self.profile, "nvenc", 4, 20, 10, changed_command)
        self.assertNotEqual(first["source_size"], second["source_size"])
        self.assertNotEqual(second["command_options"], changed_options["command_options"])

    def test_atomic_manifest_survives_replacement(self):
        manifest = self.root / "manifest.json"
        cli.atomic_json_write(manifest, {"completed": [0, 1, 2]})
        self.assertEqual(json.loads(manifest.read_text())["completed"], [0, 1, 2])
        self.assertEqual(list(self.root.glob("*.pending")), [])

    def test_incomplete_segment_is_never_valid(self):
        segment = self.root / "segment-00000003.writing.mkv"
        segment.write_bytes(b"")
        with mock.patch.object(cli, "probe_media", side_effect=ValueError("corrupt")):
            self.assertFalse(cli.validate_segment(segment, {"audio": 1, "subtitle": 0}))

    def test_segment_duration_must_match_manifest_entry(self):
        segment = self.root / "segment.mkv"
        segment.write_bytes(b"ok")
        streams = {"duration": 3.0, "video": 1, "audio": 0, "subtitle": 0}
        with mock.patch.object(cli, "probe_media", return_value=streams):
            self.assertTrue(cli.validate_segment(segment, {"audio": 0, "subtitle": 0}, 3.0))
            self.assertFalse(cli.validate_segment(segment, {"audio": 0, "subtitle": 0}, 1.0))

    def test_crash_retains_completed_segments_and_discards_only_trailing_corruption(self):
        manifest_path = self.root / "manifest.json"
        manifest = {"completed": []}
        for number in range(3):
            segment = self.root / f"segment-{number:08d}.mkv"
            segment.write_bytes(b"complete")
            manifest["completed"].append({"index": number, "file": segment.name})
        manifest["completed"][-1]["file"] = "segment-00000002.writing.mkv"
        (self.root / manifest["completed"][-1]["file"]).write_bytes(b"partial")
        with mock.patch.object(cli, "validate_segment", side_effect=[True, True, False]):
            retained = cli.validate_completed_segments(
                self.root, manifest, {"audio": 1, "subtitle": 0}, manifest_path
            )
        self.assertEqual([entry["index"] for entry in retained], [0, 1])
        self.assertTrue((self.root / "segment-00000000.mkv").exists())
        self.assertFalse((self.root / "segment-00000002.writing.mkv").exists())

    def test_corrupt_non_trailing_segment_rejects_whole_resume(self):
        manifest = {"completed": [{"file": "bad.mkv"}, {"file": "good.mkv"}]}
        with mock.patch.object(cli, "validate_segment", return_value=False):
            with self.assertRaisesRegex(ValueError, "non-trailing"):
                cli.validate_completed_segments(self.root, manifest, {"audio": 0, "subtitle": 0}, self.root / "manifest.json")

    def test_video_without_audio_and_multiple_audio(self):
        segment = self.root / "segment.mkv"
        segment.write_bytes(b"ok")
        with mock.patch.object(cli, "probe_media", return_value={"video": 1, "audio": 0, "subtitle": 0}):
            self.assertTrue(cli.validate_segment(segment, {"audio": 0, "subtitle": 0}))
        with mock.patch.object(cli, "probe_media", return_value={"video": 1, "audio": 2, "subtitle": 1}):
            self.assertTrue(cli.validate_segment(segment, {"audio": 2, "subtitle": 1}))
            self.assertFalse(cli.validate_segment(segment, {"audio": 1, "subtitle": 1}))

    def test_concurrent_lock_and_exact_owner_release(self):
        work = cli.checkpoint_path(self.source)
        first = cli.CheckpointLock(work)
        first.acquire()
        second = cli.CheckpointLock(work)
        with self.assertRaises(FileExistsError):
            second.acquire()
        second.release()  # must not release somebody else's token
        self.assertTrue(first.directory.exists())
        first.release()
        self.assertFalse(first.directory.exists())

    def test_stale_lock_requires_expired_lease_and_dead_identity(self):
        work = cli.checkpoint_path(self.source)
        lock_dir = work / "lock"
        lock_dir.mkdir(parents=True)
        cli.atomic_json_write(lock_dir / "owner.json", {
            "pid": 99999999, "boot_id": "not-this-boot", "process_start": "0",
            "token": "old", "claimed_at": time.time() - cli.CHECKPOINT_LOCK_STALE_SECONDS - 1,
        })
        recovered = cli.CheckpointLock(work)
        recovered.acquire()
        self.assertTrue(lock_dir.exists())
        recovered.release()

    def test_uninitialized_new_lock_is_not_reclaimed(self):
        work = cli.checkpoint_path(self.source)
        (work / "lock").mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            cli.CheckpointLock(work).acquire()

    def test_segment_command_normalizes_timestamps_and_boundaries(self):
        base = cli.build_video_cmd(self.source, Path("unused.mkv"), cli.PROFILES["mkv_shrink"], "software", 0, 26)
        command = cli.build_segment_cmd(base, self.source, self.root / "part.writing.mkv", 60, 30, True)
        rendered = " ".join(map(str, command))
        self.assertIn("setpts=PTS-STARTPTS", rendered)
        self.assertIn("asetpts=PTS-STARTPTS", rendered)
        self.assertIn("-force_key_frames expr:gte(t,0)", rendered)
        self.assertIn("-ss 60.000000", rendered)
        input_index = command.index("-i")
        self.assertEqual(command[input_index + 1], str(self.source))
        self.assertGreater(command.index("-t"), input_index + 1)

    def test_audio_timestamp_filter_is_not_combined_with_streamcopy(self):
        copy_base = cli.build_video_cmd(self.source, Path("unused.mkv"), self.profile, "software", 0, 26)
        copy_command = cli.build_segment_cmd(copy_base, self.source, self.root / "copy.mkv", 0, 30, True)
        self.assertNotIn("-af", copy_command)
        encoded_profile = cli.PROFILES["mkv_shrink"]
        encoded_base = cli.build_video_cmd(self.source, Path("unused.mp4"), encoded_profile, "software", 0, 28)
        encoded_command = cli.build_segment_cmd(encoded_base, self.source, self.root / "encoded.mkv", 0, 30, True)
        self.assertIn("-af", encoded_command)

    def test_mkv_shrink_preserves_source_and_legacy_profiles_support_fallback(self):
        self.assertTrue(cli.PROFILES["mkv_shrink"]["preserve_source"])
        with mock.patch.object(cli, "detect_dimensions", return_value=(1280, 720)):
            fallback = cli.build_video_cmd(
                self.source, Path("segment.mkv"), cli.PROFILES["h264_avi"], "software", 0, 26,
                force_audio_fallback=True,
            )
        self.assertEqual(fallback[fallback.index("-c:a") + 1], "aac")

    def test_successful_cleanup_removes_entire_checkpoint(self):
        work = cli.checkpoint_path(self.source)
        work.mkdir()
        (work / "segment-00000000.mkv").write_bytes(b"final")
        import shutil
        shutil.rmtree(work)
        self.assertFalse(work.exists())


if __name__ == "__main__":
    unittest.main()
