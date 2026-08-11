import sys
import unittest
from types import SimpleNamespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.models import ProjectGridModel, SocialPublishListModel, VideoListModel


class ModelUpdateTests(unittest.TestCase):
    def test_video_model_emits_only_the_changed_role(self):
        model = VideoListModel()
        current = SimpleNamespace(
            video_id="video-a", original_filename="a.mp4", status="pending", step="pending",
            updated_at="first", progress=0, files={}, project_name="Project", video_width=0,
            video_height=0,
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
            video_height=0,
        )
        updated = SimpleNamespace(**{**first.__dict__, "progress": 45, "updated_at": "second"})
        model = VideoListModel()
        model.set_videos([first])
        changed = []
        model.dataChanged.connect(lambda first_index, _last, roles: changed.append((first_index.row(), roles)))

        self.assertTrue(model.update_video(updated))
        self.assertEqual(changed, [(0, [VideoListModel.UpdatedRole, VideoListModel.ProgressRole])])

    def test_missing_video_dimensions_do_not_render_an_unknown_size_label(self):
        video = SimpleNamespace(video_width=0, video_height=0)

        self.assertEqual(VideoListModel._video_size(video), "")

    def test_social_publish_refresh_updates_rows_without_resetting_the_grid(self):
        model = SocialPublishListModel()
        current = {
            "id": "post-1", "file_name": "clip.mp4", "file_path": "D:/clip.mp4",
            "caption": "Caption", "hashtags": "#one", "post_text": "Caption\n#one",
            "status": "ready", "error": "", "thumbnail_source": "",
            "upload_progress": 0, "zernio_post_id": "", "platform_post_url": "",
            "target_platform": "tiktok",
        }
        model.set_items([current])
        resets = []
        changed = []
        model.modelReset.connect(lambda: resets.append(True))
        model.dataChanged.connect(
            lambda first, last, roles: changed.append((first.row(), last.row(), roles))
        )

        model.set_items([{**current, "target_platform": "youtube"}])

        self.assertEqual(resets, [])
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0][:2], (0, 0))
        self.assertEqual(changed[0][2], [SocialPublishListModel.TargetPlatformRole])


if __name__ == "__main__":
    unittest.main()
