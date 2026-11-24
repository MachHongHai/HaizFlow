pragma Singleton
import QtQuick
import "."

QtObject {
    function label(state) {
        switch (state) {
        case "pending": return qsTr("Chưa chạy");
        case "queued": return qsTr("Đang chờ lượt");
        case "preparing": return qsTr("Đang chuẩn bị");
        case "processing": case "active": return qsTr("Đang xử lý");
        case "rendering": return qsTr("Đang dựng video");
        case "exporting": return qsTr("Đang xuất");
        case "awaiting_review": return qsTr("Cần duyệt phụ đề");
        case "paused": return qsTr("Đã tạm dừng");
        case "done": case "success": return qsTr("Hoàn tất");
        case "failed": case "error": return qsTr("Có lỗi");
        case "cancelled": return qsTr("Đã hủy");
        default: return qsTr("Sẵn sàng");
        }
    }

    function tone(state) {
        if (["done", "success"].includes(state)) return "success";
        if (["failed", "error"].includes(state)) return "danger";
        if (["queued", "preparing", "processing", "active", "rendering", "exporting", "paused", "awaiting_review"].includes(state))
            return "warning";
        return "neutral";
    }

    function foreground(state) {
        const value = tone(state);
        return value === "success" ? Theme.success : value === "danger" ? Theme.danger
            : value === "warning" ? Theme.warning : Theme.textMuted;
    }

    function background(state) {
        const value = tone(state);
        return value === "success" ? Theme.successMuted : value === "danger" ? Theme.dangerMuted
            : value === "warning" ? Theme.warningMuted : Theme.surfaceMuted;
    }

    function exportState(status, queued) {
        return status === "pending" || (status === "rendering" && queued) ? "queued" : status;
    }
}
