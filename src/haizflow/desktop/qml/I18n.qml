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
    readonly property var fixedVietnamese: ({
        "Keeping original video subtitles unchanged": "Giữ nguyên phụ đề gốc",
        "Preparing original subtitle scan": "Đang chuẩn bị quét phụ đề gốc",
        "Scanning original subtitles": "Đang quét phụ đề gốc",
        "Restoring source audio": "Đang khôi phục âm thanh nguồn",
        "Restoring separated background audio": "Đang khôi phục nhạc nền đã tách",
        "Retrying translation on CPU": "Đang thử dịch lại bằng CPU",
        "Checking source video integrity": "Đang kiểm tra video nguồn",
        "Extracting the source audio": "Đang trích âm thanh nguồn",
        "Separating vocals and background music": "Đang tách giọng và nhạc nền",
        "Recognizing dialogue": "Đang nhận dạng lời thoại",
        "Translating subtitles": "Đang dịch phụ đề",
        "Analyzing original subtitle regions": "Đang phân tích vùng phụ đề gốc",
        "Regenerating the edited voice segment": "Đang tạo lại câu đã chỉnh",
        "Initializing voice libraries": "Đang khởi tạo thư viện giọng đọc",
        "Reusing the initialized voice runtime": "Đang dùng bộ tạo giọng đã khởi tạo",
        "Loading the voice model": "Đang nạp model giọng đọc",
        "Reusing the loaded voice model": "Đang dùng model giọng đọc đã nạp",
        "Stabilizing the voice": "Đang ổn định chất giọng",
        "Preparing the voice reference": "Đang chuẩn bị mẫu giọng",
        "Reusing the prepared voice reference": "Đang dùng mẫu giọng đã chuẩn bị",
        "Identifying speakers": "Đang nhận diện người nói",
        "Starting the voice runtime": "Đang khởi tạo bộ tạo giọng",
        "Restoring cached voice audio": "Đang khôi phục giọng đọc từ cache",
        "Updating audio layers": "Đang cập nhật các lớp âm thanh",
        "Subtitles updated": "Phụ đề đã cập nhật",
        "Video exported": "Video đã xuất",
        "Tool complete": "Đã hoàn tất công cụ",
        "Exporting video": "Đang xuất video",
        "Compositing visual layers": "Đang ghép các lớp hình ảnh",
        "Finishing video at the selected quality": "Đang hoàn thiện video theo chất lượng đã chọn",
        "Resuming saved translations": "Tiếp tục phần dịch đã lưu",
        "Reusing completed speech recognition": "Dùng lại phần nhận dạng đã hoàn tất",
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
        "The Douyin link contains an invalid video ID.": "Mã video trong liên kết Douyin không hợp lệ.",
        "Douyin did not provide playable video data. Check that the video is public and can be viewed on Douyin.": "Douyin không trả về dữ liệu video cho liên kết này. Kiểm tra video còn công khai và có thể xem trên Douyin.",
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
        "Preparing Whisper speech recognition": "Đang chuẩn bị nhận dạng bằng Whisper",
        "Loading WhisperX speech model": "Đang tải model nhận dạng WhisperX",
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
