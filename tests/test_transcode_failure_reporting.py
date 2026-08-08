import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "transcode_cli_failure_reporting",
    Path(__file__).parents[1] / "cross-platform" / "transcode_cli.py",
)
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class AudioProbeTests(unittest.TestCase):
    def test_probe_audio_streams_returns_diagnostic_fields(self):
        payload = {"streams": [{"index": 1, "codec_name": "aac", "channels": 1,
                                "channel_layout": "unknown", "tags": {"language": "eng"}}]}
        completed = subprocess.CompletedProcess([], 0, json.dumps(payload), "")
        with mock.patch.object(cli.subprocess, "run", return_value=completed):
            self.assertEqual(cli.probe_audio_streams("movie.mp4"), payload["streams"])
            command = cli.subprocess.run.call_args.args[0]
            fields = command[command.index("-show_entries") + 1]
            self.assertIn("channels", fields)
            self.assertIn("channel_layout", fields)

    def test_audio_diagnostic_includes_channel_fields(self):
        diagnostic = cli.format_audio_streams([
            {"index": 1, "codec_name": "speex", "channels": 1, "channel_layout": "unknown"},
        ])

        self.assertIn("channels=1", diagnostic)
        self.assertIn("channel_layout=unknown", diagnostic)

    def test_probe_audio_streams_preserves_ffprobe_failure(self):
        completed = subprocess.CompletedProcess([], 1, "", "access denied")
        with mock.patch.object(cli.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "access denied"):
                cli.probe_audio_streams("movie.mp4")


class ContinuedProcessingTests(unittest.TestCase):
    def test_fallback_probe_failure_is_reported_and_batch_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            failed = root / "a.flv"
            successful = root / "b.flv"
            failed.write_bytes(b"source")
            successful.write_bytes(b"source")

            def run_transcode(command, *_args):
                if Path(command[-1]).name == "a_REDU.tmp.mp4":
                    return 1, "Unsupported audio codec: speex"
                Path(command[-1]).write_bytes(b"encoded")
                return 0, ""

            def audio_streams(path):
                if Path(path) == failed:
                    raise RuntimeError("ffprobe returned invalid audio stream data")
                return []

            stderr = io.StringIO()
            argv = ["transcode_cli.py", "--profile", "h264_flv", "--path", str(root)]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(cli.ffmpeg, "run_ffmpeg_with_progress", side_effect=run_transcode), \
                    mock.patch.object(cli.ffmpeg, "detect_dimensions", return_value=(1920, 1080)), \
                    mock.patch.object(cli.ffmpeg, "ffprobe_ok", return_value=True), \
                    mock.patch.object(cli.ffmpeg, "probe_audio_streams", side_effect=audio_streams), \
                    contextlib.redirect_stderr(stderr):
                status = cli.main()

            self.assertEqual(status, 1)
            self.assertIn("audio fallback probe", stderr.getvalue())
            self.assertIn("processing continued", stderr.getvalue())
            self.assertFalse((root / "a_REDU.tmp.mp4").exists())
            self.assertTrue((root / "b_REDU.mp4").exists())

    def test_audio_mismatch_is_summarized_and_later_file_completes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            failed = root / "a.mp4"
            successful = root / "b.mp4"
            failed.write_bytes(b"source")
            successful.write_bytes(b"source")

            def run_transcode(command, *_args):
                Path(command[-1]).write_bytes(b"encoded")
                return 0, ""

            def audio_streams(path):
                path = Path(path)
                one = [{"index": 1, "codec_name": "aac", "tags": {}, "disposition": {}}]
                two = one + [{"index": 2, "codec_name": "ac3", "tags": {}, "disposition": {}}]
                if path == failed:
                    return two
                return one

            stderr = io.StringIO()
            argv = ["transcode_cli.py", "--profile", "h264_mp4", "--path", str(root)]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(cli.ffmpeg, "run_ffmpeg_with_progress", side_effect=run_transcode), \
                    mock.patch.object(cli.ffmpeg, "detect_dimensions", return_value=(1920, 1080)), \
                    mock.patch.object(cli.ffmpeg, "ffprobe_ok", return_value=True), \
                    mock.patch.object(cli.ffmpeg, "probe_audio_streams", side_effect=audio_streams), \
                    contextlib.redirect_stderr(stderr):
                status = cli.main()

            self.assertEqual(status, 1)
            self.assertIn("Failure summary: 1 file operation(s) failed; processing continued", stderr.getvalue())
            self.assertIn(str(failed), stderr.getvalue())
            self.assertIn("input audio streams: 2; output audio streams: 1", stderr.getvalue())
            self.assertTrue(failed.exists())
            self.assertFalse(successful.exists())
            self.assertTrue((root / "b_REDU.mp4").exists())

    def test_interrupt_summary_does_not_claim_processing_continued(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.mp4"
            remaining = root / "b.mp4"
            first.write_bytes(b"source")
            remaining.write_bytes(b"source")

            stderr = io.StringIO()
            argv = ["transcode_cli.py", "--profile", "h264_mp4", "--path", str(root)]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(cli.ffmpeg, "run_ffmpeg_with_progress", side_effect=KeyboardInterrupt), \
                    mock.patch.object(cli.ffmpeg, "detect_dimensions", return_value=(1920, 1080)), \
                    contextlib.redirect_stderr(stderr):
                status = cli.main()

            self.assertEqual(status, 1)
            self.assertIn(
                "processing was interrupted; remaining files were not attempted",
                stderr.getvalue(),
            )
            self.assertNotIn("processing continued", stderr.getvalue())
            self.assertTrue(first.exists())
            self.assertTrue(remaining.exists())


if __name__ == "__main__":
    unittest.main()
