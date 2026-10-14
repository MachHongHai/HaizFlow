"""Cheap, read-only batch summaries; never invalidate pipeline artifacts."""


def results(videos, jobs=()):
    exports = {job["videoId"]: job for job in jobs}
    rows = []
    for video in videos:
        if video is None:
            continue
        job = exports.get(video.video_id)
        status = job["status"] if job else video.status
        error = str((job.get("error") if job else video.error) or "")
        rows.append({"videoId": video.video_id, "fileName": video.original_filename,
                     "status": status, "error": error, "step": str(video.step or "")})
    return {"rows": rows, "total": len(rows),
            "succeeded": sum(row["status"] == "done" for row in rows),
            "failed": sum(row["status"] == "failed" for row in rows),
            "cancelled": sum(row["status"] == "cancelled" for row in rows),
            "waiting": sum(row["status"] not in {"done", "failed", "cancelled"} for row in rows)}


def completion_notice(summary, language="vi"):
    """Keep notifications compact; the UI retains every per-video error."""
    if language == "vi":
        title = "Đã hoàn tất hàng loạt"
        message = (f"{summary['succeeded']} thành công · {summary['failed']} lỗi"
                   f" · {summary['cancelled']} đã hủy. Xem Chi tiết trong dự án.")
    else:
        title = "Batch finished"
        message = (f"{summary['succeeded']} succeeded · {summary['failed']} failed"
                   f" · {summary['cancelled']} cancelled. See Details in the project.")
    return title, message, "warning" if summary["failed"] else "info"
