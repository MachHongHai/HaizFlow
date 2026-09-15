import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.services import manual_artifacts


class AdaptiveCachePolicyTests(unittest.TestCase):
    def test_large_disk_uses_normal_soft_limits(self):
        usage = type("Usage", (), {"free": 200 * 1024**3})()
        with patch("haizflow.services.manual_artifacts.shutil.disk_usage", return_value=usage):
            self.assertEqual(
                manual_artifacts.adaptive_project_limit(Path.cwd(), 0),
                manual_artifacts.PROJECT_SOFT_LIMIT_BYTES,
            )
            self.assertEqual(
                manual_artifacts.adaptive_global_limit(Path.cwd(), 0),
                manual_artifacts.GLOBAL_SOFT_LIMIT_BYTES,
            )

    def test_low_disk_reduces_limits_and_preserves_operational_reserve(self):
        usage = type("Usage", (), {"free": manual_artifacts.MINIMUM_FREE_BYTES})()
        with patch("haizflow.services.manual_artifacts.shutil.disk_usage", return_value=usage):
            self.assertEqual(manual_artifacts.adaptive_project_limit(Path.cwd(), 0), 0)
            self.assertEqual(manual_artifacts.adaptive_global_limit(Path.cwd(), 0), 0)


if __name__ == "__main__":
    unittest.main()
