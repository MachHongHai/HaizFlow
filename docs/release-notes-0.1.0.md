<!-- Prepared release copy. Publication status and approvals are tracked in release-readiness.vi.md and legal/license-state.json. -->

# HaizFlow 0.1.0

Ứng dụng miễn phí để tải, dịch, tạo phụ đề và lồng tiếng video trên Windows.

## Chức năng

- **Tải video hàng loạt:** chọn video từ kênh hoặc trang cá nhân công khai được hỗ trợ và tải theo hàng đợi.
- **Dịch video:** nhận dạng bằng Whisper, dịch trên máy bằng HY-MT2 hoặc dùng Gemini.
- **Tạo phụ đề:** dùng font Bangers; chỉnh nội dung, thời gian, kích thước, màu và hiệu ứng karaoke.
- **Lồng tiếng:** dùng giọng có sẵn hoặc mẫu giọng bạn có quyền sử dụng.
- **Xử lý tự động:** chọn các bước xử lý và ngôn ngữ trước khi chạy.
- **Xử lý hàng loạt:** dùng thiết lập chung cho nhiều video và theo dõi từng kết quả.
- **Che phụ đề gốc:** tìm vùng chữ bằng OCR, làm mờ hoặc vá nền.
- **Nhận diện nhiều người nói:** phân nhóm và chọn giọng đọc riêng cho từng nhóm.
- **Đăng mạng xã hội:** chuẩn bị nội dung và đăng video qua Zernio.

Máy không có GPU NVIDIA vẫn dùng được các công cụ CPU. Whisper và HY-MT2 xử lý trên máy, không cần API key hay phí dịch theo lượt. Gemini và Zernio là dịch vụ ngoài với điều khoản và chi phí riêng.

## Cài đặt

1. Trong **Assets**, tải bộ cài Windows `HaizFlow-0.1.0-UNSIGNED-Setup.exe` và tệp SHA-256 đi kèm.
2. Mở bộ cài, chọn ngôn ngữ và thư mục cài trên ổ còn đủ dung lượng.
3. Mở HaizFlow; giao diện mặc định là tiếng Việt. Chọn CPU/GPU trong **Cài đặt → Chung**.
4. Cài các gói cần dùng trong **Gói tài nguyên**. Thêm Gemini/Zernio key khi dùng các dịch vụ này.
5. Tạo dự án, thêm video, chọn công cụ và xem trước kết quả trước khi xuất.

Windows 10 phiên bản 1809 trở lên hoặc Windows 11 x64; RAM từ 16 GiB. Không cần cài Python hoặc CUDA Toolkit riêng. Dung lượng của gói tài nguyên, video và tệp xuất được tính riêng với ứng dụng.

Bộ cài không ký số. Windows có thể hiện nhà phát hành không xác định hoặc chặn ứng dụng chưa ký theo chính sách máy. Kiểm tra nguồn tải và SHA-256; không tắt bảo vệ Windows.

[Cài đặt chi tiết](https://github.com/MachHongHai/HaizFlow/blob/test/docs/install.vi.md) · [Hướng dẫn sử dụng](https://github.com/MachHongHai/HaizFlow/blob/test/docs/user-guide.vi.md) · [Trợ giúp](https://github.com/MachHongHai/HaizFlow/blob/test/docs/support.vi.md)

## Giấy phép

HaizFlow miễn phí sử dụng theo HaizFlow Source-Available 1.0. **Model OmniVoice hiện tại chỉ được cấp phép cho mục đích phi thương mại.** Giấy phép ứng dụng không thay thế điều kiện của model, video hoặc mẫu giọng.

---

## English

HaizFlow is a free Windows app for batch video downloads, translation, subtitle creation and dubbing. It includes automatic and batch processing, OCR-based original-caption coverage, multiple-speaker detection and social publishing through Zernio.

Whisper and HY-MT2 run locally without API keys or per-call translation charges. CPU options work without an NVIDIA GPU. Gemini and Zernio are optional external services with their own terms and charges.

### Installation

1. Download `HaizFlow-0.1.0-UNSIGNED-Setup.exe` and its SHA-256 file from **Assets**.
2. Run Setup and choose a language and installation folder with sufficient free space.
3. Open HaizFlow and select CPU/GPU in **Settings → General**. Vietnamese is the default; English is available in Settings.
4. Install the resources you need and add Gemini/Zernio keys when using those services.
5. Create a project, add videos, process and preview before export.

Requires Windows 10 version 1809 or later, or Windows 11 x64, and at least 16 GiB RAM. No separate Python or CUDA Toolkit installation is needed. Resource packs and media require additional storage.

The installer is unsigned. Windows may show an unknown publisher or block execution under device policy. Verify the download source and SHA-256; do not disable Windows protection.

[Installation](https://github.com/MachHongHai/HaizFlow/blob/test/docs/install.md) · [User guide](https://github.com/MachHongHai/HaizFlow/blob/test/docs/user-guide.md) · [Help](https://github.com/MachHongHai/HaizFlow/blob/test/docs/support.md)

HaizFlow is free to use under HaizFlow Source-Available 1.0. **The current OmniVoice model is for noncommercial use only.** Application terms do not replace model or imported-content licenses.
