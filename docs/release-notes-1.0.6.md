# HaizFlow 1.0.6

[Tải bộ cài Windows](https://github.com/MachHongHai/HaizFlow/releases/download/v1.0.6/HaizFlow-1.0.6-Setup.exe)

## Điểm mới

- Sửa bộ chọn tệp/thư mục Windows: vị trí quen thuộc, DPI rõ nét và trả focus về app.
- Sửa áp dụng cài đặt batch, vị trí phụ đề và trạng thái xuất khi chuyển dự án.
- Làm gọn trang batch, thẻ video và hàng thao tác; tiến độ dùng thanh trạng thái chung.
- Kiểm tra API key thực tế cho Gemini, OpenAI, DeepSeek, OpenRouter, API tùy chỉnh và Zernio;
  chọn API sử dụng trong Cài đặt. Cải thiện xử lý phản hồi và tiếp tục bản dịch.
- Tạm dừng dịch API không phải chờ hết timeout; giữ các câu đã hoàn thành và không
  tự gửi lại yêu cầu đã dừng. Giữ cấu hình model, suy luận và giới hạn mặc định của nhà cung cấp.
- Sửa đọc mẫu clone OmniVoice/VieNeu, giữ các cải tiến OCR, giọng đọc và preview.
- Cập nhật hướng dẫn MCP, phiên Douyin, mẫu giọng nghe thử và font đa ngôn ngữ.

## Cập nhật từ 1.0.2

Các bản **1.0.2–1.0.5** có thể cập nhật trong app; có Delta riêng và Full Core dự
phòng. Core mới chứa cả launcher/updater mới với runtime riêng đã kiểm checksum.
Sau lần thoát bình thường đầu tiên của 1.0.6, bộ khởi động được thay an toàn;
**lần mở tiếp theo dùng launcher mới**, không cần tự cài lại hay thay shortcut.
Bản cũ được giữ để khôi phục; dự án, API key, model và thư mục xuất không bị xóa.

Vào **Cài đặt → Gói tài nguyên** cập nhật **CPU 19 / GPU CUDA 21** để nhận đầy đủ
các sửa lỗi worker. OCR giữ phiên bản 10; không cần tải lại model đã có.

Windows 10/11 x64. Bản phát hành **chưa ký Authenticode**; Windows có thể cảnh báo
hoặc chặn theo chính sách. Không tắt phần mềm bảo vệ. Giữ các giấy phép độc lập và
giới hạn checkpoint OmniVoice phi thương mại. Không dùng ZIP Core thay bộ cài mới.
