# HaizFlow 1.0.4

[Tải bộ cài Windows](https://github.com/MachHongHai/HaizFlow/releases/download/v1.0.4/HaizFlow-1.0.4-Setup.exe)

## Sửa lỗi và cải tiến

- Sửa lỗi `'impersonate'` khi tải video Douyin hoặc tải video trong kênh. Bước tải media dùng cùng cấu hình mạng tương thích với phiên Douyin; không đổi UA/cookie hay chỉnh cấu hình mạng toàn cục sau khi yt-dlp khởi tạo. Thêm kiểm tra cấu hình tải vào kiểm định bản đóng gói.
- Tối ưu xác minh Core lúc mở app: bỏ lượt kiểm tra trùng và đọc song song có giới hạn, vẫn kiểm tra đầy đủ SHA-256, file thừa/thiếu và junction. Launcher mới nằm trong bộ Setup; cập nhật Core trong app không tự thay launcher cũ.
- Cải tiến trình chỉnh sửa phụ đề và vùng theo dõi nội dung; sửa thao tác sửa/gộp/xóa câu làm mất giọng các câu không bị ảnh hưởng trong một số dự án cũ.
- Sửa cache preview OCR khi thay đổi và khôi phục cấu hình khung hình; giảm xử lý lại không cần thiết khi mở dự án.
- Cải thiện phản hồi và giao dịch xóa dự án, giữ hộp thoại trong trạng thái đang xóa cho tới khi hoàn tất.
- VieNeu không còn chặn câu ngắn chỉ dựa trên thời lượng so với văn bản; vẫn kiểm tra waveform lỗi, im lặng và tín hiệu không hợp lệ. Chỉ thử lại có giới hạn khi audio thực sự không hợp lệ.
- OmniVoice/VieNeu dùng theo dõi thời gian không có tiến triển thay vì giới hạn cố định cho toàn bộ video dài. Khi GPU gặp lỗi và chuyển CPU, tái sử dụng các câu đã hoàn thành thay vì tạo lại toàn bộ.

## Cập nhật trực tiếp từ 1.0.1

Các bản **1.0.1, 1.0.2 và 1.0.3** có thể cập nhật trực tiếp lên **1.0.4** trong app. Release có Delta riêng cho từng bản và Full Core dự phòng. Người cài mới dùng **Setup.exe**, không giải nén ZIP Core cập nhật thay bộ cài.

Sau cập nhật, mở **Gói tài nguyên** và cập nhật bộ xử lý **CPU 17 / GPU CUDA 19** để nhận các sửa lỗi TTS. Không phải tải lại model; OCR 8 vẫn dùng gói đã phát hành. Giữ nguyên release cũ, dự án và cache hợp lệ.

Để nhận tối ưu launcher, lưu công việc, đóng HaizFlow rồi cài **Setup 1.0.4** vào đúng thư mục cài hiện tại. Không xóa `runtime` hoặc dự án. Việc kiểm tra đầy đủ Core vẫn được giữ, nên tốc độ mở còn phụ thuộc ổ đĩa và phần mềm bảo vệ trên từng máy.

Windows 10/11 x64. Bản phát hành **chưa ký Authenticode**; Windows có thể cảnh báo hoặc chặn theo chính sách. Không tắt phần mềm bảo vệ. Giới hạn giấy phép, gồm checkpoint OmniVoice phi thương mại, vẫn áp dụng. Không thêm nhà cung cấp API dịch/TTS mới trong bản này.
