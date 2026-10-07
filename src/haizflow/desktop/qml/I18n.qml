pragma Singleton
import QtQuick
import "RuntimeMessages.js" as RuntimeMessages

QtObject {
    property string language: "en"

    function stageLabel(stage) {
        const labels = {
            "queued": "Queued",
            "starting": "Preparing project",
            "loading_models": "Preparing translation model",
            "loading_alignment": "Preparing subtitle alignment",
            "validating_source": "Checking source video integrity",
            "detecting_original_subtitles": "Scanning original subtitles",
            "extracting_audio": "Extracting audio",
            "separating_audio": "Separating vocals",
            "transcribing": "Transcribing speech",
            "translating": "Translating",
            "review_translation": "Waiting for translation review",
            "creating_subtitle": "Creating subtitles",
            "creating_voice": "Generating voice",
            "building_audio_timeline": "Mixing audio",
            "rendering": "Rendering video",
            "paused": "Paused",
            "done": "Export complete",
            "manual_translation": "Translation ready",
            "manual_source": "Extracting audio",
            "manual_separation": "Separating vocals",
            "manual_recognition": "Transcribing speech",
            "manual_image": "Scanning original subtitles",
            "manual_audio": "Mixing audio",
            "manual_export": "Rendering video",
            "manual_subtitles": "Subtitles ready",
            "manual_voice": "Voice ready",
            "manual_timeline": "Audio mix ready",
            "failed": "Failed"
        }
        return fixedText(labels[stage] || stage)
    }

    function taskStateLabel(state) {
        const labels = {
            "active": "In progress",
            "pending": "Queued",
            "done": "Complete",
            "failed": "Failed",
            "cancelled": "Cancelled"
        }
        return fixedText(labels[state] || state)
    }

    function runtimeStatus(source) {
        if (language !== "vi" || !source)
            return source

        const direct = fixedText(source)
        if (direct !== source)
            return direct

        if (source.indexOf("_") >= 0)
            return stageLabel(source)

        let match = source.match(/^(.+?) ready - GPU acceleration - (.+)$/)
        if (match)
            return match[1] + " đã sẵn sàng - Tăng tốc GPU: " + match[2]

        match = source.match(/^(.+?) ready - CPU mode - (.+)$/)
        if (match)
            return match[1] + " đã sẵn sàng - Chế độ CPU: " + match[2].replace(/threads$/, "luồng")

        match = source.match(/^Ready - GPU acceleration - (.+)$/)
        if (match)
            return "Sẵn sàng - Tăng tốc GPU: " + match[1]

        match = source.match(/^Ready - CPU mode - (.+)$/)
        if (match)
            return "Sẵn sàng - Chế độ CPU: " + match[1].replace(/threads$/, "luồng")

        match = source.match(/^Model warm-up unavailable: (.+)$/)
        if (match)
            return "Không thể khởi tạo model: " + match[1]

        match = source.match(/^Processing device switch failed: (.+)$/)
        if (match)
            return "Không thể chuyển thiết bị xử lý: " + match[1]

        match = source.match(/^Saved processing device unavailable: (.+) Using automatic mode\.$/)
        if (match)
            return "Thiết bị xử lý đã lưu không khả dụng: " + match[1] + " Đã chuyển sang chế độ tự động."

        match = source.match(/^Organized (\d+) video workspace\(s\) into their projects\.$/)
        if (match)
            return "Đã sắp xếp " + match[1] + " video vào dự án tương ứng."

        return source
    }

    function progressDetail(source) {
        if (!source)
            return source

        // The controller can append a separate item counter to a status.
        const parts = source.split(" | ")
        if (parts.length > 1)
            return parts.map(part => progressDetail(part)).join(" | ")

        const direct = fixedText(source)
        if (direct !== source)
            return direct

        let match
        match = source.match(/^Lớp che (\d+)$/)
        if (match)
            return language === "vi" ? source : "Cover layer " + match[1]
        match = source.match(/^Preparing voice: (.+)$/)
        if (match)
            return voiceStageLabel(match[1])
        if (language !== "vi") {
            match = source.match(/^Đang xuất video (\d+)%$/)
            if (match)
                return "Exporting video " + match[1] + "%"
            match = source.match(/^Đang phân tích khung hình (\d+)\/(\d+)$/)
            if (match)
                return "Scanning original subtitles (" + match[1] + "/" + match[2] + ")"
            match = source.match(/^Đang tạo (\d+) câu đã thay đổi$/)
            if (match)
                return "Generating " + match[1] + " changed voice segments"
            match = source.match(/^Đã tạo (\d+)\/(\d+) câu$/)
            if (match)
                return "Generated " + match[1] + " of " + match[2] + " voice segments"
            match = source.match(/^Đã tạm dừng (.+)$/)
            if (match)
                return "Paused during " + manualToolLabel(match[1])
            return source
        }

        match = source.match(/^Scanning original subtitles \((\d+)\/(\d+)\)$/)
        if (match)
            return "Đang quét phụ đề gốc (" + match[1] + "/" + match[2] + ")"

        match = source.match(/^Verified voice audio (\d+) of (\d+)$/)
        if (match)
            return "Đã kiểm tra " + match[1] + " / " + match[2] + " đoạn giọng đọc"

        match = source.match(/^Identifying speakers (\d+) of (\d+)$/)
        if (match)
            return "Đang nhận diện người nói (" + match[1] + "/" + match[2] + ")"

        match = source.match(/^Manual stage ready: (.+)$/)
        if (match)
            return "Đã hoàn tất bước: " + manualToolLabel(match[1])

        match = source.match(/^Starting (.+) translation$/)
        if (match)
            return "Đang bắt đầu dịch bằng " + match[1]

        match = source.match(/^Sending Gemini translation batch: sentences (\d+)-(\d+) of (\d+)\.$/)
        if (match)
            return "Đang dịch bằng Gemini: câu " + match[1] + "-" + match[2] + " / " + match[3]

        match = source.match(/^Rendering final video \((\d+)%\)$/)
        if (match)
            return "Đang xuất video (" + match[1] + "%)"

        match = source.match(/^Loading subtitle alignment for (.+)$/)
        if (match)
            return "Đang nạp model căn thời gian phụ đề (" + match[1] + ")"

        match = source.match(/^Aligning (.+) subtitles$/)
        if (match)
            return "Đang căn thời gian phụ đề (" + match[1] + ")"

        match = source.match(/^Detected (.+) speech$/)
        if (match)
            return "Đã nhận dạng ngôn ngữ lời nói: " + (match[1] === "unknown" ? "chưa xác định" : match[1])

        match = source.match(/^Prepared (\d+) complete sentences$/)
        if (match)
            return "Đã chia " + match[1] + " câu hoàn chỉnh"

        match = source.match(/^Validated (\d+) timed sentences$/)
        if (match)
            return "Đã kiểm tra thời gian của " + match[1] + " câu"

        match = source.match(/^Prepared (\d+) timestamp-locked sentences$/)
        if (match)
            return "Đã chuẩn bị " + match[1] + " câu theo mốc thời gian"

        match = source.match(/^GPU unavailable during (.+)\. Switching this project to CPU and retrying that stage\.$/)
        if (match)
            return "GPU không khả dụng tại bước " + stageLabel(match[1]) + ". Đang chuyển sang CPU để thử lại."

        match = source.match(/^Translating subtitles (\d+)-(\d+) of (\d+)$/)
        if (match)
            return "Đang dịch phụ đề " + match[1] + "-" + match[2] + " / " + match[3]

        match = source.match(/^Translated (\d+) of (\d+) subtitles$/)
        if (match)
            return "Đã dịch " + match[1] + " / " + match[2] + " phụ đề"

        match = source.match(/^Paused during (.+)$/)
        if (match)
            return "Đã tạm dừng tại bước: " + stageLabel(match[1])

        match = source.match(/^Đã tạm dừng (.+)$/)
        if (match)
            return "Đã tạm dừng tại bước: " + manualToolLabel(match[1])

        match = source.match(/^Queued: position (\d+)$/)
        if (match)
            return "Đang chờ ở vị trí " + match[1]

        match = source.match(/^Loading HY-MT2 Q4 CPU model with (\d+) threads$/)
        if (match)
            return "Đang tải model HY-MT2 Q4 cho CPU với " + match[1] + " luồng"

        match = source.match(/^HY-MT2 weights loaded; moving model to (.+)$/)
        if (match)
            return "Đã tải trọng số HY-MT2; đang chuyển model sang " + match[1]

        return source
    }

    function manualToolLabel(tool) {
        const labels = {
            "source": "Extracting audio",
            "separation": "Separating vocals",
            "transcription": "Transcribing speech",
            "translation": "Translating",
            "subtitles": "Creating subtitles",
            "subtitle": "Creating subtitles",
            "image": "Scanning original subtitles",
            "audio": "Mixing audio",
            "ocr": "Scanning original subtitles",
            "voice": "Generating voice",
            "timeline": "Mixing audio",
            "export": "Rendering video"
        }
        return fixedText(labels[tool] || tool)
    }

    function voiceStageLabel(stage) {
        const labels = {
            "importing_runtime": "Initializing voice libraries",
            "reusing_runtime": "Reusing the initialized voice runtime",
            "loading_model": "Loading the voice model",
            "reusing_model": "Reusing the loaded voice model",
            "creating_voice_anchor": "Stabilizing the voice",
            "loading_voice_reference": "Preparing the voice reference",
            "reusing_voice_anchor": "Reusing the prepared voice reference",
            "identifying_speakers": "Identifying speakers",
            "launching_worker": "Starting the voice runtime"
        }
        return fixedText(labels[stage] || "Starting voice synthesis")
    }

    function channelImportStatus(source) {
        if (language !== "vi" || !source)
            return source

        const direct = fixedText(source)
        if (direct !== source)
            return direct

        let match = source.match(/^Reading video details (\d+)\/(\d+)$/)
        if (match)
            return "Đang đọc thông tin video " + match[1] + "/" + match[2]

        match = source.match(/^Found (\d+) videos$/)
        if (match)
            return "Đã tìm thấy " + match[1] + " video"

        match = source.match(/^(\d+) videos ready to review$/)
        if (match)
            return match[1] + " video sẵn sàng để xem lại"

        match = source.match(/^Downloading (\d+) videos$/)
        if (match)
            return "Đang tải " + match[1] + " video"

        match = source.match(/^Imported (\d+) videos; (\d+) need attention$/)
        if (match)
            return "Đã nhập " + match[1] + " video; " + match[2] + " video cần kiểm tra"

        match = source.match(/^Imported (\d+) videos$/)
        if (match)
            return "Đã nhập " + match[1] + " video"

        return source
    }

    function downloadStatus(source) {
        if (language !== "vi" || !source)
            return source
        const direct = fixedText(source)
        if (direct !== source)
            return direct
        let match = source.match(/^Saved to (.+)$/)
        if (match)
            return "Đã lưu tại " + match[1]
        match = source.match(/^Queued (.+)$/)
        if (match)
            return "Đang chờ tải: " + match[1]
        match = source.match(/^Preparing (.+)$/)
        if (match)
            return "Đang chuẩn bị: " + match[1]
        if (source === "Refreshing video stream and retrying")
            return "Đang làm mới luồng video để thử lại"
        return source
    }

    // Only backend-generated runtime messages remain here. Static UI copy is
    // translated through qsTr() and the compiled Qt catalog.
    readonly property var fixedVietnamese: RuntimeMessages.vietnamese

    readonly property var fixedEnglish: {
        const result = {}
        // Keep the first human-readable label where several states share text.
        Object.keys(fixedVietnamese).forEach(key => {
            if (!result[fixedVietnamese[key]])
                result[fixedVietnamese[key]] = key
        })
        return result
    }

    function fixedText(source) {
        if (!source)
            return source
        return (language === "vi" ? fixedVietnamese[source] : fixedEnglish[source]) || source
    }
}
