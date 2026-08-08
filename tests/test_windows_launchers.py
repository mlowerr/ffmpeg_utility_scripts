"""Static regression tests for the PowerShell launcher error contracts."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / "windows"
SHARED_LAUNCHER = ROOT / "cross-platform" / "transcode-cli.ps1"


class WindowsLauncherTests(unittest.TestCase):
    def test_thin_wrappers_validate_launcher_and_propagate_status(self) -> None:
        wrappers = [
            *sorted((WINDOWS / "video").glob("*-transcode.ps1")),
            *sorted((WINDOWS / "audio").glob("*-to-mp3.ps1")),
            WINDOWS / "mkv-shrink.ps1",
        ]
        self.assertTrue(wrappers)
        for wrapper in wrappers:
            with self.subTest(wrapper=wrapper.relative_to(ROOT)):
                text = wrapper.read_text(encoding="utf-8")
                self.assertIn("Test-Path -LiteralPath $generic -PathType Leaf", text)
                self.assertIn("$invocationSucceeded = $?", text)
                self.assertIn("$status = $LASTEXITCODE", text)
                self.assertIn("$null -eq $status", text)
                self.assertIn("exit $status", text)

    def test_shared_launcher_rejects_conflicting_hardware_encoders(self) -> None:
        text = SHARED_LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("$hardwareSelectionCount", text)
        self.assertIn("$hardwareSelectionCount -gt 1", text)
        self.assertIn("mutually exclusive", text)

    def test_aggregate_drivers_require_launcher_and_reject_missing_status(self) -> None:
        for driver in (
            WINDOWS / "video" / "transcode_all_video.ps1",
            WINDOWS / "audio" / "transcode_all_audio.ps1",
        ):
            with self.subTest(driver=driver.relative_to(ROOT)):
                text = driver.read_text(encoding="utf-8")
                self.assertIn("$null -eq $powerShellCommand", text)
                self.assertIn("$invocationSucceeded = $?", text)
                self.assertIn("$null -eq $status", text)
                self.assertNotIn("$null -eq $LASTEXITCODE) { 0 }", text)


if __name__ == "__main__":
    unittest.main()
