from types import SimpleNamespace

import pytest

from hflow.desktop.models import VideoListModel, presentation_video_status
from hflow.desktop.presenters import build_project_summaries


@pytest.mark.parametrize("kind,tool,detail,expected", [
    ("manual", "export", "", "manual_ready"),
    ("manual", "", "Đã hủy lượt xuất.", "manual_ready"),
    ("manual", "translation", "", "cancelled"),
    ("single", "export", "Đã hủy lượt xuất.", "cancelled"),
])
def test_legacy_export_cancel_card_only_normalizes_manual_export(kind, tool, detail, expected):
    video = SimpleNamespace(status="cancelled", project_type=kind, manual_target_tool=tool, step_detail=detail,
        video_id="manual-old", project_name="ddkkk", project_directory="", project_key="p", updated_at="",
        created_at="", original_filename="old.mp4", files={}, video_width=1920, video_height=1080, progress=87)
    assert presentation_video_status(video) == expected
    assert build_project_summaries([video])[0]["status"] == expected
    assert video.status == "cancelled"  # Presentation does not mutate persisted projects.


def test_video_row_uses_effective_status_for_legacy_manual_export_cancel():
    import inspect

    assert "self.StatusRole: presentation_video_status(video)" in inspect.getsource(VideoListModel._role_values)
