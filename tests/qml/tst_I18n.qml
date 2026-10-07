import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 200
    height: 200

    TestCase {
        name: "I18n"
        when: windowShown

        function test_vietnameseProgress_data() {
            return [
                {tag: "ocr", source: "Scanning original subtitles (21/36)", expected: "Đang quét phụ đề gốc (21/36)"},
                {tag: "ocrWithCounter", source: "Scanning original subtitles (21/36) | 21/36", expected: "Đang quét phụ đề gốc (21/36) | 21/36"},
                {tag: "translation", source: "Translated 48 of 307 subtitles | 48/307", expected: "Đã dịch 48 / 307 phụ đề | 48/307"},
                {tag: "gemini", source: "Starting Gemini translation", expected: "Đang bắt đầu dịch bằng Gemini"},
                {tag: "voice", source: "Verified voice audio 3 of 20", expected: "Đã kiểm tra 3 / 20 đoạn giọng đọc"},
                {tag: "speakers", source: "Identifying speakers 1 of 3", expected: "Đang nhận diện người nói (1/3)"},
                {tag: "voicePreparation", source: "Preparing voice: loading_voice_reference", expected: "Đang chuẩn bị mẫu giọng"},
                {tag: "pausedManual", source: "Đã tạm dừng image", expected: "Đã tạm dừng tại bước: Đang quét phụ đề gốc"},
                {tag: "cpuRecovery", source: "GPU unavailable during translating. Switching this project to CPU and retrying that stage.", expected: "GPU không khả dụng tại bước Đang dịch. Đang chuyển sang CPU để thử lại."},
                {tag: "unknownPreserved", source: "D:/video/test.mp4", expected: "D:/video/test.mp4"}
            ]
        }

        function test_vietnameseProgress(data) {
            const original = I18n.language
            try {
                I18n.language = "vi"
                compare(I18n.progressDetail(data.source), data.expected)
            } finally {
                I18n.language = original
            }
        }

        function test_englishProgress_data() {
            return [
                {tag: "manualOcr", source: "Đang phân tích khung hình 21/36 | 21/36", expected: "Scanning original subtitles (21/36) | 21/36"},
                {tag: "manualVoice", source: "Đã tạo 3/20 câu", expected: "Generated 3 of 20 voice segments"},
                {tag: "manualVoiceChange", source: "Đang tạo 4 câu đã thay đổi", expected: "Generating 4 changed voice segments"},
                {tag: "manualLibrary", source: "Đang khởi tạo thư viện giọng đọc", expected: "Initializing voice libraries"},
                {tag: "manualTranslation", source: "Đang dịch phụ đề", expected: "Translating subtitles"},
                {tag: "pausedManual", source: "Đã tạm dừng translation", expected: "Paused during Translating"},
                {tag: "englishUnchanged", source: "Translated 48 of 307 subtitles", expected: "Translated 48 of 307 subtitles"}
            ]
        }

        function test_englishProgress(data) {
            const original = I18n.language
            try {
                I18n.language = "en"
                compare(I18n.progressDetail(data.source), data.expected)
            } finally {
                I18n.language = original
            }
        }
    }
}
