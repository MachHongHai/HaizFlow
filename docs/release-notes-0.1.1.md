# HaizFlow 0.1.1

Tải, dịch, tạo phụ đề và lồng tiếng video trên Windows. Hỗ trợ tải video hàng loạt, xử lý tự động, che phụ đề gốc, nhận diện nhiều người nói và đăng mạng xã hội.

## Cài đặt

**Chỉ tải và mở [HaizFlow-0.1.1-Setup.exe](https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.1/HaizFlow-0.1.1-Setup.exe).** Không cần tải hoặc giải nén các tệp Core bên dưới; chúng dành cho tính năng cập nhật trong ứng dụng.

1. Chọn thư mục cài trên ổ còn đủ dung lượng.
2. Mở HaizFlow; giao diện mặc định là tiếng Việt. Chọn CPU hoặc GPU NVIDIA trong **Cài đặt → Chung**.
3. Cài các gói cần dùng trong **Cài đặt → Gói tài nguyên**. Không cần cài Python hay CUDA Toolkit riêng.
4. Tạo dự án, thêm video, chọn công cụ và xem trước trước khi xuất.

Người đang dùng 0.1.0 có thể cập nhật trong ứng dụng. Bạn cũng có thể đóng HaizFlow và cài đè bằng bộ cài mới; dữ liệu hiện có được giữ lại. Không cần gỡ ứng dụng trước.

Gói CPU/GPU/OCR được ứng dụng tải khi bạn chọn cài; không nhúng vào bộ cài để tránh tải những gói không dùng. Bộ xử lý NVIDIA là gói lớn và dùng chung cho các công cụ GPU.

[Cài đặt chi tiết](https://github.com/MachHongHai/HaizFlow/blob/v0.1.1/docs/install.vi.md) · [Hướng dẫn sử dụng](https://github.com/MachHongHai/HaizFlow/blob/v0.1.1/docs/user-guide.vi.md)

## Gói tài nguyên

Tiến trình phân biệt rõ tải, xác minh và cài đặt. Tệp tải dở được giữ khi tạm dừng; bấm **Tiếp tục** để tiếp tục cài. Bộ xử lý dùng chung chỉ cần cài một lần. **Kiểm tra và sửa** dành cho gói đã cài.

## Hệ thống và giấy phép

Windows 10 1809 trở lên hoặc Windows 11 x64; RAM từ 16 GiB. Máy không có GPU NVIDIA vẫn dùng được các công cụ CPU. Gemini và Zernio là dịch vụ ngoài, có điều khoản và chi phí riêng.

Bộ cài không ký số. Windows có thể hiện nhà phát hành không xác định; kiểm tra nguồn tải và mã SHA-256 trong thông tin phát hành, không tắt bảo vệ Windows.

HaizFlow miễn phí theo HaizFlow Source-Available 1.0. **Model OmniVoice hiện tại chỉ dành cho mục đích phi thương mại.** Bạn cần quyền sử dụng video, âm nhạc và mẫu giọng nhập vào ứng dụng.

Các thư viện không đổi so với 0.1.0. [Nguồn thư viện tương ứng](https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.0/HaizFlow-0.1.0-ThirdPartySources.zip) · [Thông báo và giấy phép](https://github.com/MachHongHai/HaizFlow/blob/v0.1.1/THIRD_PARTY_NOTICES.md).

## English

**Download and run [HaizFlow-0.1.1-Setup.exe](https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.1/HaizFlow-0.1.1-Setup.exe) only.** Core files below are for in-app updates, not manual installation. Existing 0.1.0 users can update in the app or close HaizFlow and run Setup over their installation; existing data is retained.

Choose CPU/NVIDIA GPU in Settings, then install the resources you need. Downloads, verification and installation have separate status feedback. Pause retains partial downloads; Resume continues the installation. Shared runtimes are installed once.

Requires Windows 10 1809 or later / Windows 11 x64 and at least 16 GiB RAM. No separate Python or CUDA Toolkit is required. The installer is unsigned; verify the source and SHA-256 without disabling Windows protection. **The current OmniVoice model is noncommercial only.** Gemini and Zernio have separate terms and charges.
