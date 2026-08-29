pragma Singleton
import QtQuick

QtObject {
    property string language: "en"

    function stageLabel(stage) {
        const labels = {
            "queued": "Queued",
            "starting": "Preparing project",
            "loading_models": "Preparing translation model",
            "loading_alignment": "Preparing subtitle alignment",
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
        if (language !== "vi" || !source)
            return source

        const direct = fixedText(source)
        if (direct !== source)
            return direct

        let match = source.match(/^Translating subtitles (\d+)-(\d+) of (\d+)$/)
        if (match)
            return "Đang dịch phụ đề " + match[1] + "-" + match[2] + " / " + match[3]

        match = source.match(/^Translated (\d+) of (\d+) subtitles$/)
        if (match)
            return "Đã dịch " + match[1] + " / " + match[2] + " phụ đề"

        match = source.match(/^Paused during (.+)$/)
        if (match)
            return "Đã tạm dừng tại bước: " + stageLabel(match[1])

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

    // Only backend-generated runtime messages remain here. Static UI copy is
    // translated through qsTr() and the compiled Qt catalog.
    readonly property var fixedVietnamese: ({
        "Social publishing": "Đăng mạng xã hội",
        "YouTube Shorts": "YouTube Shorts",
        "Facebook Reels": "Facebook Reels",
        "Instagram Reels": "Instagram Reels",
        "posts": "bài đăng",
        "published": "đã đăng",
        "selected": "đã chọn",
        "HaizFlow": "HaizFlow",
        "Settings": "Cài đặt",
        "Checking installed models": "Đang kiểm tra các model đã cài",
        "Preparing the local model runtime": "Đang chuẩn bị môi trường model cục bộ",
        "Preparing the selected model runtime": "Đang chuẩn bị model cho thiết bị đã chọn",
        "Models are ready": "Các model đã sẵn sàng",
        "Verifying the complete model set": "Đang xác minh toàn bộ model",
        "Cancelling model download": "Đang dừng tải model",
        "Model download was cancelled. You can retry when ready.": "Đã dừng tải model. Bạn có thể thử lại khi sẵn sàng.",
        "Model download was cancelled. Retry to finish switching device.": "Đã dừng tải model. Hãy thử lại để hoàn tất chuyển thiết bị xử lý.",
        "Downloads": "Tải xuống",
        "Paste a public profile or channel link, not an individual video link.": "Hãy dán liên kết hồ sơ hoặc kênh công khai, không phải liên kết một video.",
        "Checking video link": "Đang kiểm tra liên kết video",
        "Video ready to download": "Video đã sẵn sàng để tải xuống",
        "Starting download": "Đang bắt đầu tải xuống",
        "Finalizing video": "Đang hoàn thiện video",
        "Download complete": "Đã tải xuống xong",
        "Cancelling download": "Đang hủy tải xuống",
        "Import cancelled": "Đã hủy nhập video",
        "Adding video to project": "Đang thêm video vào dự án",
        "Video added to project": "Đã thêm video vào dự án",
        "Paste a video link first.": "Hãy dán liên kết video trước.",
        "Enter a valid HTTP or HTTPS video link.": "Hãy nhập liên kết video HTTP hoặc HTTPS hợp lệ.",
        "Only public YouTube, TikTok, Douyin, Bilibili, Instagram, Facebook, X, Vimeo, Dailymotion, Twitch, Reddit, and VK profiles are supported.": "Chỉ hỗ trợ hồ sơ hoặc kênh công khai của YouTube, TikTok, Douyin, Bilibili, Instagram, Facebook, X, Vimeo, Dailymotion, Twitch, Reddit và VK.",
        "This link is not from a supported source. Use YouTube, TikTok, Douyin, Bilibili, Instagram, Facebook, X, Vimeo, Dailymotion, Twitch, Reddit, Streamable, or VK.": "Liên kết này không thuộc nguồn được hỗ trợ. Hãy dùng YouTube, TikTok, Douyin, Bilibili, Instagram, Facebook, X, Vimeo, Dailymotion, Twitch, Reddit, Streamable hoặc VK.",
        "Paste a link to one video, not a playlist or channel.": "Hãy dán liên kết của một video, không phải danh sách phát hoặc kênh.",
        "Live and upcoming streams are not supported.": "Chưa hỗ trợ video trực tiếp hoặc sắp phát.",
        "Open or create a project before downloading a video.": "Hãy mở hoặc tạo dự án trước khi tải video.",
        "Pause or finish the current video before replacing it.": "Hãy tạm dừng hoặc hoàn tất video hiện tại trước khi thay thế.",
        "Project name": "Tên dự án",
        "Project storage location": "Vị trí lưu dự án",
        "Queued": "Đang chờ",
        "In progress": "Đang thực hiện",
        "Complete": "Hoàn tất",
        "Failed": "Lỗi",
        "Cancelled": "Đã hủy",
        "Paused": "Đã tạm dừng",
        "done": "Hoàn tất",
        "pending": "Đang chờ",
        "processing": "Đang xử lý",
        "failed": "Lỗi",
        "cancelled": "Đã hủy",
        "paused": "Đã tạm dừng",
        "awaiting_review": "Cần duyệt bản dịch",
        "Batch queue": "Hàng đợi xử lý",
        "Choose cookies.txt": "Chọn cookies.txt",
        "Ready": "Sẵn sàng",
        "Reading channel": "Đang đọc kênh",
        "Reading channel videos": "Đang đọc danh sách video",
        "Starting isolated Douyin Beta inspector": "Đang khởi động bộ đọc Douyin Beta",
        "Previous import can be resumed": "Có thể tiếp tục phiên nhập trước",
        "Adding downloaded videos to the project": "Đang thêm video đã tải vào dự án",
        "Cancelling channel import": "Đang hủy nhập từ kênh",
        "Channel inspection cancelled": "Đã hủy quét kênh",
        "Import was interrupted. Retry this video.": "Phiên nhập đã bị gián đoạn. Hãy thử lại video này.",
        "Download cancelled": "Đã hủy tải xuống",
        "Channel import cancelled.": "Đã hủy nhập từ kênh.",
        "Paste a channel or profile link first.": "Hãy dán liên kết kênh hoặc trang cá nhân trước.",
        "Enter a valid HTTP or HTTPS channel link.": "Hãy nhập liên kết kênh HTTP hoặc HTTPS hợp lệ.",
        "Paste a YouTube channel link, not an individual video link.": "Hãy dán liên kết kênh YouTube, không phải liên kết một video.",
        "Paste a YouTube channel link.": "Hãy dán liên kết kênh YouTube.",
        "Paste a TikTok profile link, not an individual video link.": "Hãy dán liên kết trang cá nhân TikTok, không phải liên kết một video.",
        "Paste a Douyin profile link, not an individual video link.": "Hãy dán liên kết trang cá nhân Douyin, không phải liên kết một video.",
        "Paste a Douyin profile link.": "Hãy dán liên kết trang cá nhân Douyin.",
        "The channel returned no public videos.": "Kênh không trả về video công khai nào.",
        "Browser session or cookies could not be read. Close the browser or choose cookies.txt and try again.": "Không thể đọc phiên trình duyệt hoặc cookie. Hãy đóng trình duyệt hoặc chọn cookies.txt rồi thử lại.",
        "The destination project is no longer available.": "Dự án đích không còn khả dụng.",
        "The destination project was deleted.": "Dự án đích đã bị xóa.",
        "Videos": "Video",
        "videos": "video",
        "Mixed settings": "Thiết lập riêng theo video",
        "items": "mục",
        "Batch settings": "Cài đặt hàng loạt",
        "segments": "đoạn phụ đề",
        "Voice cloning": "Nhân bản giọng nói",
        "Speech recognition": "Nhận dạng giọng nói",
        "Background music": "Nhạc nền",
        "Choose background music": "Chọn nhạc nền",
        "Paste a background music link first.": "Hãy dán liên kết nhạc nền trước.",
        "Select a video before importing background music.": "Hãy chọn video trước khi nhập nhạc nền.",
        "Downloading background music": "Đang tải nhạc nền",
        "Cancelling background music download": "Đang hủy tải nhạc nền",
        "Background music imported": "Đã nhập nhạc nền",
        "No active video": "Không có video đang xử lý",
        "No video selected": "Chưa chọn video",
        "Settings applied": "Đã áp dụng cài đặt",
        "Settings reset to defaults": "Đã khôi phục cài đặt mặc định",
        "Switching processing device": "Đang chuyển thiết bị xử lý",
        "Preparing HY-MT2 translation model": "Đang chuẩn bị model dịch HY-MT2",
        "Preparing HY-MT2 translation": "Đang chuẩn bị dịch bằng HY-MT2",
        "Loading HY-MT2 translation model": "Đang tải model dịch HY-MT2",
        "Reusing HY-MT2 translation model": "Đang dùng lại model dịch HY-MT2",
        "Loading HY-MT2 tokenizer": "Đang tải bộ tách từ HY-MT2",
        "Loading HY-MT2 weights": "Đang tải trọng số HY-MT2",
        "HY-MT2 model is ready": "Model HY-MT2 đã sẵn sàng",
        "HY-MT2 Q4 CPU model is ready": "Model HY-MT2 Q4 cho CPU đã sẵn sàng",
        "Preparing video": "Đang chuẩn bị video",
        "Processing started": "Đã bắt đầu xử lý",
        "Queued to restart": "Đã đưa vào hàng đợi để chạy lại",
        "Queued to create dub": "Đã đưa vào hàng đợi để tạo lồng tiếng",
        "Queued for processing": "Đã đưa vào hàng đợi xử lý",
        "Translation ready for review": "Bản dịch đã sẵn sàng để duyệt",
        "Extracting source audio": "Đang trích xuất âm thanh nguồn",
        "Source audio ready": "Âm thanh nguồn đã sẵn sàng",
        "Separating speech from background audio": "Đang tách lời nói khỏi âm thanh nền",
        "Speech track ready": "Âm thanh lời nói đã sẵn sàng",
        "Preparing speech recognition": "Đang chuẩn bị nhận diện lời nói",
        "Starting HY-MT2 translation": "Đang bắt đầu dịch bằng HY-MT2",
        "Reusing subtitles checkpoint": "Đang dùng lại checkpoint phụ đề",
        "Formatting timed subtitles": "Đang định dạng phụ đề theo thời gian",
        "Scanning the full frame for original subtitles": "Đang quét toàn bộ khung hình để tìm phụ đề gốc",
        "Reusing generated voices": "Đang dùng lại giọng đọc đã tạo",
        "Starting voice synthesis": "Đang bắt đầu tạo giọng đọc",
        "Reusing mixed audio checkpoint": "Đang dùng lại checkpoint âm thanh",
        "Fitting voices to the video timeline": "Đang khớp giọng đọc với thời lượng video",
        "Reusing rendered video checkpoint": "Đang dùng lại checkpoint video đã kết xuất",
        "Rendering final video": "Đang kết xuất video đầu ra",
        "Preparing project": "Đang chuẩn bị dự án",
        "Extracting audio": "Đang trích xuất âm thanh",
        "Separating vocals": "Đang tách giọng",
        "Transcribing speech": "Đang nhận diện lời nói",
        "Translating": "Đang dịch",
        "Waiting for translation review": "Đang chờ duyệt bản dịch",
        "Creating subtitles": "Đang tạo phụ đề",
        "Generating voice": "Đang tạo giọng đọc",
        "Mixing audio": "Đang phối âm thanh",
        "Rendering video": "Đang kết xuất video",
        "Export complete": "Xuất video hoàn tất",
        "Final video ready": "Video đầu ra đã sẵn sàng",
        "Open input video": "Mở video nguồn",
        "Open export folder": "Mở thư mục video xuất",
        "Remove video": "Xóa video",
        "Delete project": "Xóa dự án",
        "English": "Tiếng Anh",
        "Vietnamese": "Tiếng Việt",
        "Processing device": "Thiết bị xử lý",
        "Manual": "Thủ công",
        "Translation ready": "Bản dịch đã sẵn sàng",
        "Subtitles ready": "Phụ đề đã sẵn sàng",
        "Voice ready": "Giọng đọc đã sẵn sàng",
        "Audio mix ready": "Bản phối âm đã sẵn sàng",
        "Source audio": "Âm thanh nguồn",
        "The link does not match the selected platform.": "Liên kết không khớp với nền tảng đã chọn.",
        "GPU accelerated": "Tăng tốc GPU",
        "GPU low memory": "GPU ít bộ nhớ",
        "CPU balanced": "CPU cân bằng",
        "CPU low memory": "CPU ít bộ nhớ",
        "CPU minimum memory": "CPU bộ nhớ tối thiểu",
        "GPU compute": "Xử lý bằng GPU",
        "Windows display adapter": "GPU hiển thị Windows",
        "Export diagnostics": "Xuất dữ liệu chẩn đoán"
    })

    function fixedText(source) {
        if (language !== "vi" || !source)
            return source
        return fixedVietnamese[source] || source
    }
}
