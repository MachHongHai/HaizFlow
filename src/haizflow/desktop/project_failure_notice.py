"""Notify new failures, never replay persisted errors just by opening a project."""


class ProjectFailureNotice:
    def __init__(self):
        self.video_id = ""
        self.status = ""
        self.revision = 0
        self._eligible = False

    def observe(self, video):
        video_id = str(getattr(video, "video_id", "") or "")
        status = str(getattr(video, "status", "") or "")
        if video_id != self.video_id:
            self._eligible = False
            self.revision += 1
        elif status == "failed" and self.status != "failed":
            self._eligible = True
            self.revision += 1
        elif status != "failed":
            self._eligible = False
        self.video_id, self.status = video_id, status

    def started(self, video_id):
        if str(video_id or "") == self.video_id:
            # Even a very short retry can fail between two UI metadata polls.
            self.status = "processing"
            self._eligible = False

    def claim(self, video_id):
        if self._eligible and self.status == "failed" and str(video_id or "") == self.video_id:
            self._eligible = False
            return True
        return False
