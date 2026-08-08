import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHARED_LAUNCHER = ROOT / "cross-platform" / "transcode-cli.sh"
THIN_WRAPPERS = sorted((ROOT / "unix" / "video").glob("*-transcode.sh"))
THIN_WRAPPERS += sorted((ROOT / "unix" / "audio").glob("*-to-mp3.sh"))
THIN_WRAPPERS.append(ROOT / "unix" / "mkv-shrink")


class UnixLauncherTests(unittest.TestCase):
    def test_shared_launcher_is_executable(self):
        self.assertTrue(os.access(SHARED_LAUNCHER, os.X_OK))

    def test_wrappers_work_through_external_symlinks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for index, wrapper in enumerate(THIN_WRAPPERS):
                link = Path(temp_dir) / f"wrapper-{index}"
                link.symlink_to(wrapper)
                result = subprocess.run(
                    [link, "--help"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"{wrapper.relative_to(ROOT)} failed: {result.stderr}",
                )
                self.assertIn("Usage:", result.stdout)

    def test_shared_launcher_rejects_multiple_search_directories(self):
        result = subprocess.run(
            [SHARED_LAUNCHER, "h264_mp4", "first", "second"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "Error: only one search directory may be specified.", result.stderr
        )


if __name__ == "__main__":
    unittest.main()
