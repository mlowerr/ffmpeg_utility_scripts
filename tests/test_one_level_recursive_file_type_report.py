"""Tests for the combined one-level recursive file type report CLI."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "cross-platform"
    / "one-level-recursive-file-type-report.py"
)


class OneLevelRecursiveReportTests(unittest.TestCase):
    def run_report(
        self, root: Path, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def touch(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    def test_default_filters_to_profile_video_types_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            child = root / "media"
            self.touch(child / "one.MP4")
            self.touch(child / "two.mKv")
            self.touch(child / "notes.txt")

            result = self.run_report(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            detailed = (root / "recursive-file-type-report.txt").read_text()
            summary = (root / "recursive-file-type-report-summary.txt").read_text()
            self.assertIn(".mp4", detailed)
            self.assertIn(".mkv", detailed)
            self.assertNotIn(".txt", detailed)
            self.assertIn("Total: 2", summary)
            self.assertIn("Remaining: 2", summary)

    def test_all_file_types_includes_unrelated_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.touch(root / "child" / "clip.avi")
            self.touch(root / "child" / "readme.TXT")

            result = self.run_report(root, "--all-file-types")

            self.assertEqual(result.returncode, 0, result.stderr)
            detailed = (root / "recursive-file-type-report.txt").read_text()
            summary = (root / "recursive-file-type-report-summary.txt").read_text()
            self.assertIn(".txt", detailed)
            self.assertIn("Total: 2", summary)
            self.assertIn("Remaining: 2", summary)

    def test_aggregates_statuses_and_lists_zero_remaining_folders(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.touch(root / "first" / "movie.mp4")
            self.touch(root / "first" / "done_REDU.avi")
            self.touch(root / "first" / "work.tmp.mov")
            self.touch(root / "first" / "movie_REDU.tmp.mp4")
            (root / "first" / "empty").mkdir()
            self.touch(root / "second" / "done_REDU.mkv")
            self.touch(root / "second" / "ignored.txt")

            result = self.run_report(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            summary = (root / "recursive-file-type-report-summary.txt").read_text()
            self.assertIn("Total: 5", summary)
            self.assertIn("Temporary: 2", summary)
            self.assertIn("Transcoded: 2", summary)
            self.assertIn("Remaining: 1", summary)
            self.assertIn(str(root / "second"), summary)
            self.assertNotIn(f"\n{root / 'first'}\n", summary)
            self.assertNotIn(str(root / "first" / "empty"), summary)

    def test_aggregates_each_direct_child_tree_into_one_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for child in ("a", "b", "c", "d"):
                for descendant in ("x", "y", "z"):
                    (root / child / descendant).mkdir(parents=True)

            self.touch(root / "a" / "direct.mp4")
            self.touch(root / "a" / "x" / "nested.avi")
            self.touch(root / "a" / "x" / "deep" / "deeper.mkv")
            self.touch(root / "b" / "direct.mov")
            self.touch(root / "b" / "y" / "nested.flv")
            self.touch(root / "c" / "z" / "deep" / "done_REDU.wmv")

            result = self.run_report(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            detailed = (root / "recursive-file-type-report.txt").read_text()
            expected_totals = {"a": 3, "b": 2, "c": 1, "d": 0}
            self.assertEqual(detailed.count("Child folder report for:"), 4)
            self.assertEqual(detailed.count("File type report for:"), 4)
            for child, expected_total in expected_totals.items():
                heading = f"File type report for: {root / child}"
                section = detailed.split(heading, maxsplit=1)[1].split(
                    "Child folder report for:", maxsplit=1
                )[0]
                self.assertIn("Scan mode: recursive", section)
                self.assertIn(f"Total files: {expected_total}", section)

            for child in ("a", "b", "c", "d"):
                for descendant in ("x", "y", "z"):
                    self.assertNotIn(
                        f"File type report for: {root / child / descendant}", detailed
                    )
            self.assertNotIn(
                "File type report for: " + str(root / "a" / "x" / "deep"), detailed
            )

            summary = (root / "recursive-file-type-report-summary.txt").read_text()
            self.assertIn("Total: 6", summary)
            self.assertIn(str(root / "d"), summary)
            self.assertNotIn(str(root / "d" / "x"), summary)

    def test_empty_tree_writes_zero_totals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            result = self.run_report(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            detailed = (root / "recursive-file-type-report.txt").read_text()
            summary = (root / "recursive-file-type-report-summary.txt").read_text()
            self.assertIn("No direct child folders found.", detailed)
            self.assertIn("Total: 0", summary)
            self.assertIn("Remaining: 0", summary)

    def test_custom_outputs_are_excluded_on_subsequent_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            child = root / "child"
            self.touch(child / "movie.mp4")
            detailed_path = child / "reports" / "details.txt"
            summary_path = child / "reports" / "status.txt"
            arguments = (
                "--all-file-types",
                "--output",
                str(detailed_path),
                "--summary-output",
                str(summary_path),
            )

            first = self.run_report(root, *arguments)
            second = self.run_report(root, *arguments)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            summary = summary_path.read_text()
            self.assertIn("Total: 1", summary)
            self.assertIn(f"Wrote combined report: {detailed_path}", second.stdout)
            self.assertIn(f"Wrote summary report: {summary_path}", second.stdout)

    def test_rejects_matching_output_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "same.txt"

            result = self.run_report(
                root, "--output", str(output), "--summary-output", str(output)
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "Error: detailed and summary output paths must be different",
                result.stderr,
            )
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
