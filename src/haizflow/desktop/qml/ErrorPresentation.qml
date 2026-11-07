pragma Singleton
import QtQuick
QtObject {
    function isIssue(tone) { return ["error", "critical", "danger", "failed", "warning"].indexOf(String(tone).toLowerCase()) >= 0; }
    function technical(value) {
        return /Traceback|File "[^"]+", line|\b(?:[A-Za-z]+Error|Exception|WinError|errno|HTTPError|failed|unsupported)\b|No module named|Could not|Unable to|https?:\/\/|[A-Z]:[\\/]|\[[A-Z][A-Z_]+\]|^\s*\{|^['"][A-Za-z_][\w. -]*['"]$|\b(?:0x[0-9a-f]{6,}|status[_ ]code|stack trace)\b/i.test(String(value || ""));
    }
    function summary(value, fallback) {
        const raw = String(value || "").trim();
        if (/GPU thiếu bộ nhớ|cuda out of memory|cublas_status_alloc_failed|cudnn_status_alloc_failed/i.test(raw)) return qsTr("GPU thiếu bộ nhớ. Giải phóng VRAM hoặc chọn CPU rồi chạy lại.");
        if (/GPU không khả dụng|cuda is unavailable|no cuda|cuda driver|GPU became unavailable/i.test(raw)) return qsTr("GPU không khả dụng. Kiểm tra GPU hoặc chọn CPU rồi chạy lại.");
        if (/out of memory|cuda.*memory|\bOOM\b/i.test(raw)) return qsTr("Không đủ bộ nhớ. Hãy chọn model nhẹ hơn.");
        if (/disk full|no space left|not enough space|WinError 112/i.test(raw)) return qsTr("Ổ đĩa đã đầy. Hãy dọn dung lượng rồi thử lại.");
        if (/429|rate.limit|quota/i.test(raw)) return qsTr("Dịch vụ giới hạn lượt dùng. Hãy thử lại sau.");
        if (/503|502|504|service unavailable/i.test(raw)) return qsTr("Máy chủ tạm thời không đáp ứng. Hãy thử lại sau.");
        if (/connection.*(?:reset|failed)|network|DNS/i.test(raw)) return qsTr("Kết nối bị gián đoạn. Hãy kiểm tra mạng rồi thử lại.");
        if (/timed? ?out|timeout/i.test(raw)) return qsTr("Tác vụ chưa phản hồi kịp. Hãy thử lại.");
        if (/permission denied|access.*denied|WinError (?:5|32)|being used by another process/i.test(raw)) return qsTr("Không truy cập được tệp. Hãy đóng ứng dụng đang dùng tệp.");
        if (!raw || technical(raw) || raw.length > 180 || raw.indexOf("\n") >= 0)
            return fallback || qsTr("Không thể hoàn tất thao tác. Mở Chi tiết để xem nguyên nhân.");
        return raw;
    }
    function status(value, failed) {
        const raw = String(value || "");
        if (failed || /^\s*(?:Traceback|[\w.]+(?:Error|Exception)\s*:|\[(?:ERROR|CRITICAL)\]|No module named)/i.test(raw))
            return summary(raw);
        return raw;
    }
}
