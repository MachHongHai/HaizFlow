import sys
import unittest
from types import SimpleNamespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.models import ProjectGridModel, VideoListModel


class ModelUpdateTests(unittest.TestCase):
    def test_video_model_emits_only_the_changed_role(self):
        model = VideoListModel()
        current = SimpleNamespace(
            video_id="video-a", original_filename="a.mp4", status="pending", step="pending",
            updated_at="first", progress=0, files={}, project_name="Project", video_width=0,
            video_height=0, subtitle_override=False,
        )
        updated = SimpleNamespace(**{**current.__dict__, "status": "processing", "updated_at": "second"})
        model.set_videos([current])
        changed = []
        model.dataChanged.connect(lambda first, last, roles: changed.append((first.row(), last.row(), roles)))

        model.set_videos([updated])

        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0][:2], (0, 0))
        self.assertEqual(set(changed[0][2]), {VideoListModel.StatusRole, VideoListModel.UpdatedRole})

    def test_project_grid_emits_the_real_project_row_only(self):
        model = ProjectGridModel()
        current = {
            "key": "project-a", "project_name": "Project", "project_type": "batch",
            "video_count": 1, "status": "pending", "progress": 0, "thumbnail_source": "",
        }
        updated = {**current, "progress": 50}
        model.set_projects([current])
        changed = []
        model.dataChanged.connect(lambda first, last, roles: changed.append((first.row(), last.row(), roles)))

        model.set_projects([updated])

        self.assertEqual(changed, [(1, 1, [ProjectGridModel.ProgressRole])])

    def test_single_video_update_does_not_reset_the_model(self):
        first = SimpleNamespace(
            video_id="video-1", original_filename="one.mp4", status="pending", step="pending",
            updated_at="first", progress=0, files={}, project_name="One", video_width=0,
            video_height=0, subtitle_override=False,
        )
        updated = SimpleNamespace(**{**first.__dict__, "progress": 45, "updated_at": "second"})
        model = VideoListModel()
        model.set_videos([first])
        changed = []
        model.dataChanged.connect(lambda first_index, _last, roles: changed.append((first_index.row(), roles)))

        self.assertTrue(model.update_video(updated))
        self.assertEqual(changed, [(0, [VideoListModel.UpdatedRole, VideoListModel.ProgressRole])])


if __name__ == "__main__":
    unittest.main()
