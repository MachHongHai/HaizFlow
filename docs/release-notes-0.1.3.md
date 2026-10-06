# HaizFlow 0.1.3

Tải **HaizFlow-0.1.3-Setup.exe** để cài ứng dụng. Các tệp Core và bộ xử lý được ứng dụng tải khi cần; không cần mở hoặc giải nén chúng.

- Hỗ trợ chế độ GPU trên card NVIDIA 6 GB VRAM, với RAM hệ thống từ 16 GB.
- Demucs trên GPU 6 GB xử lý theo đoạn ngắn để giảm bộ nhớ sử dụng. Whisper dùng batch nhỏ và không nạp model trước khi bắt đầu tác vụ.
- Thông báo cập nhật không tự mở cửa sổ. Bấm **Phiên bản mới** để xem và xác nhận cập nhật.
- Trang Gói tài nguyên phân biệt Windows chặn tệp với gói thiếu hoặc hỏng. Gói chưa xác minh thành công không được đánh dấu là đã cài.
- Preview hiển thị tiến trình chuẩn bị âm thanh sau khi tạo giọng và tạm dừng phát kết quả đến khi âm thanh sẵn sàng. Âm thanh video dài dùng cache trên đĩa thay vì giữ toàn bộ dữ liệu giải mã trong RAM.

## Cập nhật

Trong HaizFlow, chọn **Phiên bản mới → Kiểm tra lại → Cập nhật**, xác nhận rồi khởi động lại khi ứng dụng yêu cầu. Dự án, API key và dữ liệu được giữ nguyên. Nếu dùng Demucs GPU hoặc Whisper GPU, kiểm tra và cập nhật bộ xử lý NVIDIA trong **Cài đặt → Gói tài nguyên** sau khi cập nhật ứng dụng.

## Cấu hình và Windows

Windows 10 1809 trở lên hoặc Windows 11 x64; RAM hệ thống từ 16 GB. Chế độ GPU cần GPU NVIDIA tương thích CUDA với ít nhất 5 GiB VRAM khả dụng (card 6 GB). Với GPU 6 GB, ưu tiên Demucs, Whisper Small và Gemini; dùng HY-MT2 CPU Q4 thay cho model GPU đầy đủ. Mức bộ nhớ thực tế còn phụ thuộc video, model và ứng dụng khác đang mở.

Bản này chưa có chữ ký số. Windows Smart App Control hoặc chính sách Application Control của tổ chức có thể chặn EXE/DLL chưa được tin cậy. Cập nhật ứng dụng không thể thay đổi chính sách Windows này. Không cần tắt bảo mật hoặc thêm ngoại lệ toàn ổ đĩa; máy được tổ chức quản lý cần quản trị viên kiểm tra nhật ký CodeIntegrity và chính sách cho phép ứng dụng.

[Hướng dẫn cài đặt](https://github.com/MachHongHai/HaizFlow/blob/main/docs/install.vi.md) · [Hướng dẫn sử dụng](https://github.com/MachHongHai/HaizFlow/blob/main/docs/user-guide.vi.md) · [Thông tin ứng dụng](https://haizflow.pages.dev/)

OmniVoice có giới hạn sử dụng phi thương mại theo giấy phép checkpoint. Xem các điều khoản đi kèm ứng dụng trước khi sử dụng.
