# Kiểm tra lưu trữ, cập nhật và tạo giọng — 01/10/2026

## Các lỗi đã sửa

- Danh sách theo loại dự án: `ProjectGridModel.IsCreateCardRole` trùng `ProjectKeyRole` (UserRole + 10). Role `projectKey` bị ghi đè, khiến delegate có required property không khởi tạo. Đã tách mã role và kiểm thử dữ liệu khóa/roleNames. Đọc chỉ mục hiện có xác nhận 1 dự án download và 3 dự án publish; không sửa hay di chuyển dữ liệu dự án để khắc phục lỗi UI.
- Lưu video: `getSaveFileName` chưa dùng `_native_explorer_profile`, khác các dialog mở/chọn thư mục. Đã dùng cùng ngữ cảnh Windows gốc, giữ tên tệp dự án và bộ lọc MP4. Đã kiểm thử wrapper; chưa thao tác thủ công toàn bộ ổ đĩa trong dialog Windows.
- Preview giọng: cập nhật tiến trình phát `selectedVideoChanged` làm dialog gán lại model tương đương, khiến `VoicePicker.onModelChanged` dừng player. Dialog nay chỉ đổi model khi dữ liệu lựa chọn thực sự đổi. Sau yêu cầu preview luôn lên lịch phát, kể cả source/state đã là cùng giá trị từ lần nghe trước.
- Pause TTS: WAV từng câu đã xong nhưng MP3 chỉ được encode cuối lô. Tạm dừng xóa thư mục tạm trước khi câu đó được lưu. Nay MP3 được encode và công bố nguyên tử ngay khi worker xác nhận WAV hoàn tất; manual workflow giữ clip hoàn tất trước dọn staging. Test giả lập worker tạm dừng sau câu đầu xác nhận clip đầu còn và clip chưa tạo không xuất hiện.
- Tốc độ TTS: sử dụng mẫu preset có sẵn với bản chép lời tương ứng thay vì tạo narrator anchor lại. CPU mặc định 16 bước; GPU giữ 32 bước. Cache có phiên bản mới để không trộn chất giọng/phương thức suy luận mới với clip cũ. Cache cũ không bị xóa.
- Bản quyền: văn phong và giới hạn phân phối được làm rõ trong LICENSE, NOTICE, README và UI. Không còn nêu tên giấy phép cũ của ứng dụng trong các văn bản hiện hành. Thông báo bắt buộc của thành phần riêng vẫn được bảo toàn. Hash giấy phép và catalog Anh đã đồng bộ.

## Bằng chứng log và giới hạn của tối ưu

Log mới nhất tại `testnhe1` có 34 câu. Cả lượt nhiều người nói và lượt giọng thường đều ghi `device=cpu`, không phải GPU. Lượt giọng thường mất khoảng 41 giây cho `creating_voice_anchor`; câu đầu khoảng 48 giây. Lượt nhiều người nói mất khoảng 50 giây cho câu đầu, 34 giây cho câu tiếp theo. Không thấy exception ở các khoảng này; user tạm dừng tác vụ.

Chế độ nhiều người nói hiện dùng bản chép lời có timestamp để lấy mẫu giọng theo từng câu nguồn. Đây không phải hệ thống diarization gom/định danh người nói cho toàn video. Việc tạo prompt nguồn cho nhiều câu làm tăng chi phí xử lý. Không thêm pyannote/model nhận diện mới hoặc tải gói mới trong lượt này.

Tài liệu OmniVoice hỗ trợ 16 bước để suy luận nhanh hơn: <https://github.com/k2-fsa/OmniVoice#python-api>. Đây là đánh đổi chất lượng/tốc độ, không cam kết âm thanh hoàn toàn giống 32 bước. Không đổi lựa chọn CPU của user sang GPU. Tốc độ end-to-end mới cần kiểm thử lại trên video thực tế; chưa đo benchmark model thật trong lượt này (máy còn khoảng 5 GB RAM trống lúc kiểm tra).

## Kiểm tra chính sách lưu trữ

Chỉ mục và manifest có schema, khóa bất biến, backup/migration và cơ chế phục hồi. Tên hiển thị không được dùng thay khóa định danh. Render nội bộ và bản xuất cho người dùng được tách; đích xuất được kiểm tra để không ghi vào dữ liệu quản lý của dự án. Delta giữ runtime ngoài Core versioned. Các kiểm thử hiện có cho rename, artifact/cache, export, migration và bảo toàn dữ liệu đã qua.

Lỗi danh sách lần này là lỗi presentation role, không phải dự án bị mất sau migration. Không cần xóa chỉ mục, tạo lại dự án hay di chuyển thư mục. Các test filesystem không bảo đảm được mọi tình huống mất điện, ổ rời, mạng, antivirus hoặc thao tác bên ngoài app; phải kiểm thử bản đóng gói với dữ liệu mẫu sao lưu trước phát hành.

## Delta update: chưa đạt trạng thái sẵn sàng phát hành

| Mức độ | Phát hiện / việc còn thiếu |
| --- | --- |
| Chặn phát hành | `launch()` bỏ qua rollback khi `CoreStillRunningError` trong lần khởi động hiện tại, nhưng sau khi launcher thoát, `Layout.recover(launcher=True)` có thể rollback transaction `pending_health` có attempts=1 mà chưa kiểm tra Core còn sống. Cần lưu/kiểm chứng danh tính process khởi động qua crash/reopen và test orphan Core. |
| Chặn phát hành | Chưa có kiểm chứng launcher/updater/Core frozen, PID handshake của executable thực, layout/provisioning của installer và Windows file-lock/AV trên máy sạch. Installer/release scripts hiện chưa được nối đầy đủ với layout mới. |
| Trước phát hành | Cần thử interruption/mất điện thực; atomic JSON/fsync trên fixture không phải chứng minh độ bền trước mọi power loss trên Windows. |
| Hạn chế thiết kế | Không có chữ ký theo yêu cầu chủ sở hữu. HTTPS và SHA-256 kiểm tra nguồn/tính toàn vẹn theo trust của GitHub, không bảo vệ nếu tài khoản/kênh release bị chiếm quyền. |
| Hoàn thiện vận hành | Chưa có chính sách tự động cho GC package tải, IPC và Core cũ. Cleanup version hiện chỉ là thao tác rõ ràng có kiểm tra bảo vệ. |
| Pháp lý | Các nghĩa vụ model, FFmpeg, Qt và phạm vi tài sản vẫn cần bằng chứng rà soát; phê duyệt license app không thay thế việc này. |

Phần kiểm tra delta trong lượt này là chẩn đoán, không thay đổi giao thức updater hoặc build installer. Xem `updates.md` và `updater-packaging-todo.md` để tiếp tục xử lý.

## Xác minh

- 1.044 test Python, 121 subtest qua; còn 1 cảnh báo TorchCodec đã tồn tại từ trước.
- 60 test Qt Quick qua; QML lint và Python correctness lint qua.
- Sau xử lý lỗi encode, chạy lại 96 test TTS/manual artifacts/project grouping: qua.
- Render cửa sổ Bản quyền và kiểm tra ảnh: không chồng lấn; catalog Anh 999 mục, không unfinished.
- Các kiểm thử worker/partial output dùng fixture, không thay thế nghe đánh giá chất lượng model thật.
- Không cài dependency mới, không sửa/xóa dữ liệu người dùng, không build, commit hoặc push.
