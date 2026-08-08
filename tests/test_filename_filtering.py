"""Regression tests for candidate and report filename classification."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cross-platform"))
import profiles  # noqa: E402


def load_report_module():
    spec = importlib.util.spec_from_file_location(
        "file_type_report_for_tests", ROOT / "cross-platform" / "file-type-report.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


report = load_report_module()


class FilenameFilteringTests(unittest.TestCase):
    def test_temporary_candidate_marker_must_precede_final_extension(self):
        self.assertTrue(profiles.is_temporary_transcode_path(Path("movie_REDU.tmp.mp4")))
        self.assertFalse(profiles.is_temporary_transcode_path(Path("family.tmp.archive.mp4")))

    def test_report_uses_exact_temporary_shape(self):
        self.assertTrue(report.is_temporary_file(Path("work.tmp.mov")))
        self.assertFalse(report.is_temporary_file(Path("attempt.tmparchive.mp4")))
        self.assertFalse(report.is_temporary_file(Path("family.tmp.archive.mp4")))

    def test_report_recognizes_all_canonical_completed_video_suffixes(self):
        for name in (
            "movie_REDU.mp4",
            "movie_REDU.m4v",
            "movie_REDU.mpeg",
            "movie_REDU.mpg",
            "movie_HEVC_REDU.mp4",
            "movie_HEVC_REDU.mkv",
            "movie_HEVC.mkv",
            "movie_small.mp4",
        ):
            with self.subTest(name=name):
                self.assertTrue(report.is_transcoded_file(Path(name)))

    def test_report_does_not_use_redu_substrings(self):
        self.assertFalse(report.is_transcoded_file(Path("document_reduction.mp4")))
        self.assertFalse(report.is_transcoded_file(Path("movie_REDU_notes.mp4")))

    def test_cli_rejects_newline_filename_without_running_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "unsafe\nname.mp4").touch()
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "cross-platform" / "transcode_cli.py"),
                    "--profile",
                    "h264_mp4",
                    "--path",
                    str(root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("filename contains a newline or carriage return", result.stderr)
        self.assertIn("\\n", result.stderr)

    def test_newline_filename_keeps_failure_status_when_valid_file_succeeds(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            unsafe = root / "unsafe\nname.mp4"
            valid = root / "valid.mp4"
            unsafe.touch()
            valid.touch()
            argv = ["transcode_cli.py", "--profile", "h264_mp4", "--path", str(root)]
            spec = importlib.util.spec_from_file_location(
                "transcode_cli_filename_test", ROOT / "cross-platform" / "transcode_cli.py"
            )
            cli = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cli)

            def transcode(command, *_args):
                Path(command[-1]).write_bytes(b"encoded")
                return 0, ""

            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(cli.ffmpeg, "run_ffmpeg_with_progress", side_effect=transcode), \
                    mock.patch.object(cli.ffmpeg, "detect_dimensions", return_value=(1920, 1080)), \
                    mock.patch.object(cli.ffmpeg, "ffprobe_ok", return_value=True), \
                    mock.patch.object(cli.ffmpeg, "probe_audio_streams", return_value=[]):
                status = cli.main()

            self.assertEqual(status, 1)
            self.assertTrue((root / "valid_REDU.mp4").exists())
            self.assertTrue(unsafe.exists())


if __name__ == "__main__":
    unittest.main()
