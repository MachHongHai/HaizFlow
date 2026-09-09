import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.url_import import VideoUrlImportCoordinator


class UrlImportCoordinatorTests(unittest.TestCase):
    def test_download_failure_keeps_inspected_metadata_available_for_direct_retry(self):
        coordinator = VideoUrlImportCoordinator()
        coordinator._metadata = {"url": "https://www.tiktok.com/@creator/video/123", "title": "Clip"}

        coordinator._handle_rejection(coordinator._generation, "Requested format is not available", False)

        self.assertEqual(coordinator.state, "retry")
        self.assertEqual(coordinator.title, "Clip")


if __name__ == "__main__":
    unittest.main()
