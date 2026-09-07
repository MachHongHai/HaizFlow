# Manual Editor: tình trạng triển khai

## Đã tích hợp

- `ManualSubtitleModel`: ID ổn định, revision, giữ nguyên nội dung nhập, lưu working document bằng atomic rename và công bố artifact trong executor tuần tự.
- `SubtitleTextEditor`: vùng nhập lớn, autosave 500 ms, commit khi rời ô, trạng thái lưu và thử lại. Manual không dùng `approveTranslationReview` để lưu từng lần nhập.
- `SubtitleOverlayRenderer`: dùng ASS writer và font của export để tạo sprite trắng/vàng trong suốt. Khung chọn lấy alpha bounds của sprite. Video nền Manual không burn-in phụ đề.
- Một scrub controller cho transport, fullscreen và timeline; gộp seek 75 ms, giữ đích mới nhất khi đổi nguồn.
- Một `QAudioSink` cho âm thanh kết quả. MediaPlayer kết quả chỉ phát hình. Volume điều chỉnh trực tiếp; câu đã đổi text không phát clip cũ.
- Tự yêu cầu tạo lại giọng sau 800 ms nếu tài liệu trước khi sửa có giọng; dùng hàng đợi xử lý hiện có và cache từng clip.
- OmniVoice giữ worker ấm, có timer nghỉ 90 giây và kiểm tra danh tính timer để callback cũ không đóng worker đang được dùng lại.
- Menu `Chỉnh sửa` dùng lịch sử theo đúng phạm vi tài liệu: từng video, từng project hoặc Cài đặt. Auto, Manual và video con trong Batch ghi toàn bộ `VideoConfig`; Batch ghi một lệnh nguyên tử cho cả nhóm; Đăng mạng xã hội ghi nội dung và tùy chọn bài; Cài đặt ghi ngôn ngữ và thiết bị xử lý. Text/timing phụ đề, nhạc nền và mẫu giọng cũng có snapshot phục hồi riêng. Lịch sử vẫn tách tuyệt đối khỏi Back/Forward của điều hướng.
- Voice manifest chỉ được kích hoạt nếu chữ ký tài liệu vẫn khớp sau khi tác vụ kết thúc.
- Khôi phục project `kkk` từ artifact `3513e4f955dbce481e45f5696e685bbe43cc1904fa4c9ab88b56cb83e695acb5`. Metadata và phụ đề trước phục hồi nằm tại thư mục `cache/manual/recovery/20260905T113848915039Z` của video. Không tự gọi model trong thao tác phục hồi.

## Kiểm thử đã chạy

- 662 unit/integration tests: đạt.
- Test text tiếng Việt dài, phản hồi revision cũ, commit một lần khi rời ô, click chọn và bỏ chọn trên video.
- Test alpha bounds hai sprite libass; chưa phải phép so sánh pixel toàn bộ frame với export.
- 100 lần seek với audio sink giả: tái sử dụng một output, giải phóng đúng một lần.
- Khởi tạo cả bảy inspector bằng controller thật trong runtime cô lập: không có cảnh báo QML.
- Ruff kiểm tra lỗi Python, compileall và qmllint các component sửa đổi: đạt.

## Chưa hoàn tất nghiệm thu kế hoạch

- So sánh karaoke từng từ và từng pixel với video xuất trên media thật. Hiện mặt chữ dùng libass nhưng phép clip vàng còn nội suy theo thời lượng phrase; chưa chứng minh tương đương sweep từng từ của libass.
- Pin revision lịch sử và phục hồi working document chưa được công bố sau khi ứng dụng bị ngắt.
- Voice state theo từng segment và UI thử lại lỗi mạng; ưu tiên/ngắt tác vụ tự cập nhật ở ranh giới câu. Hiện chỉ tuần tự hóa trên hàng đợi có sẵn.
- Khi đóng ứng dụng, executor lưu tài liệu, overlay và audio được đóng theo thứ tự; tác vụ lưu chưa bắt đầu bị hủy và tác vụ đang giữ file atomic được chờ hoàn tất. Việc hủy riêng tác vụ tự cập nhật giọng đang chạy và đóng warm worker theo quyền sở hữu workspace vẫn cần hoàn thiện.
- Giới hạn cache sprite trên đĩa và decode audio dài theo cửa sổ/memmap. Cache PCM đã có giới hạn LRU 128 MB nhưng một track rất dài có thể vượt giới hạn đó.
- Smoke test MP4 với thiết bị âm thanh Windows thật, source swap liên tục và kiểm tra không rè/lặp. Test sink giả không thay thế bước này.

Không coi tài liệu này là xác nhận toàn bộ kế hoạch đã hoàn thành. Auto/Batch tiếp tục dùng nhánh preview và pipeline cũ.
