import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.core.diagnostics import export_diagnostics, redact_diagnostic_text


class DiagnosticsTest(unittest.TestCase):
    def test_redaction_removes_paths_urls_credentials_and_email(self):
        source = (
            r"C:\Users\Alice\Videos\private.mp4 "
            "https://example.test/watch?v=secret "
            "Authorization: bearer-value alice@example.test"
        )
        redacted = redact_diagnostic_text(source)

        self.assertNotIn("Alice", redacted)
        self.assertNotIn("example.test", redacted)
        self.assertNotIn("bearer-value", redacted)
        self.assertNotIn("alice@", redacted)
        self.assertIn("<path>", redacted)
        self.assertIn("<url>", redacted)
        self.assertIn("<redacted>", redacted)
        self.assertIn("<email>", redacted)

    def test_export_is_bounded_redacted_and_excludes_project_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs = root / "logs"
            workers = logs / "hymt2-workers"
            workers.mkdir(parents=True)
            (logs / "app.log").write_text(
                r"Failed C:\Users\Alice\project\secret.mp4 token=private-token" + "\n",
                encoding="utf-8",
            )
            (workers / "worker.log").write_text(
                "request=https://example.test/private?id=1\n",
                encoding="utf-8",
            )
            install = root / "app"
            install.mkdir()
            (install / "BUILD-INFO.json").write_text(
                json.dumps(
                    {
                        "application": "HaizFlow",
                        "version": "1.2.3",
                        "build_id": "1.2.3+abcdef",
                        "git_commit": "abcdef",
                        "unexpected_path": r"C:\Users\Alice",
                    }
                ),
                encoding="utf-8",
            )

            destination = export_diagnostics(
                root / "support",
                logs_directory=logs,
                install_directory=install,
            )

            self.assertEqual(destination.suffix, ".zip")
            with zipfile.ZipFile(destination) as archive:
                names = set(archive.namelist())
                self.assertIn("diagnostics.json", names)
                self.assertIn("logs/app-1.log", names)
                self.assertIn("logs/model-worker-1.log", names)
                self.assertFalse(any("project" in name for name in names))
                combined = "\n".join(
                    archive.read(name).decode("utf-8")
                    for name in names
                )
                summary = json.loads(archive.read("diagnostics.json").decode("utf-8"))
            self.assertNotIn("Alice", combined)
            self.assertNotIn("private-token", combined)
            self.assertNotIn("example.test", combined)
            self.assertEqual(summary["build_id"], "1.2.3+abcdef")
            self.assertTrue(summary["privacy"]["logs_redacted"])
            self.assertNotIn("unexpected_path", summary["build"])


if __name__ == "__main__":
    unittest.main()
