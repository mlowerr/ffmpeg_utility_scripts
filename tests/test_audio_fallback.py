import importlib.util
import unittest
from pathlib import Path
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "transcode_cli_audio_fallback",
    Path(__file__).parents[1] / "cross-platform" / "transcode_cli.py",
)
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class AudioFallbackCommandTests(unittest.TestCase):
    def fallback_command(self, profile_name, audio_streams=None):
        with mock.patch.object(cli, "detect_dimensions", return_value=(1920, 1080)):
            return cli.build_video_cmd(
                Path(f"input{cli.PROFILES[profile_name]['ext']}"),
                Path(f"output{cli.PROFILES[profile_name]['out_ext']}"),
                cli.PROFILES[profile_name],
                "software",
                0,
                force_audio_fallback=True,
                audio_streams=audio_streams,
            )

    def fallback_audio_options(self, profile_name):
        command = self.fallback_command(profile_name)
        codec_index = command.index("-c:a")
        bitrate_index = command.index("-b:a", codec_index)
        return command[codec_index + 1], command[bitrate_index + 1]

    def test_rm_and_rmvb_mpg_fallbacks_use_mp2_at_192k(self):
        for profile_name in ("h264_rm", "h264_rmvb"):
            with self.subTest(profile=profile_name):
                self.assertEqual(self.fallback_audio_options(profile_name), ("mp2", "192k"))

    def test_mp4_oriented_legacy_fallback_still_uses_aac(self):
        for profile_name in ("h264_avi", "h264_mov", "h264_mpg", "h264_flv", "h264_wmv"):
            with self.subTest(profile=profile_name):
                self.assertEqual(self.fallback_audio_options(profile_name), ("aac", "192k"))

    def test_flv_fallback_sets_only_ambiguous_mono_stream_layout(self):
        streams = [
            {"index": 1, "channels": 1, "channel_layout": "unknown"},
            {"index": 2, "channels": 1, "channel_layout": "mono"},
        ]
        command = self.fallback_command("h264_flv", streams)

        self.assertIn("-channel_layout:a:0", command)
        self.assertEqual(command[command.index("-channel_layout:a:0") + 1], "mono")
        self.assertNotIn("-channel_layout:a:1", command)
        self.assertNotIn("-channel_layout", command)

    def test_ffprobe_one_channels_layout_is_treated_as_unspecified(self):
        streams = [{"index": 1, "channels": 1, "channel_layout": "1 channels"}]
        command = self.fallback_command("h264_flv", streams)

        self.assertIn("-channel_layout:a:0", command)
        self.assertEqual(command[command.index("-channel_layout:a:0") + 1], "mono")

    def test_valid_stereo_and_multichannel_layouts_are_not_forced(self):
        streams = [
            {"index": 1, "channels": 2, "channel_layout": "stereo"},
            {"index": 2, "channels": 6, "channel_layout": "5.1"},
        ]
        command = self.fallback_command("h264_flv", streams)

        self.assertFalse(any(option.startswith("-channel_layout") for option in command))

    def test_mp2_fallback_does_not_add_layout_options(self):
        streams = [{"index": 1, "channels": 1, "channel_layout": "unknown"}]
        command = self.fallback_command("h264_rm", streams)

        self.assertEqual(self.fallback_audio_options("h264_rm"), ("mp2", "192k"))
        self.assertFalse(any(option.startswith("-channel_layout") for option in command))


class AudioCopyCompatibilityTests(unittest.TestCase):
    def test_unsupported_audio_codec_muxer_diagnostic_triggers_fallback(self):
        diagnostic = "[mp4 @ 0x1234] Unsupported audio codec: pcm_s16le"
        self.assertTrue(cli.is_audio_copy_compat_failure(diagnostic))


if __name__ == "__main__":
    unittest.main()
