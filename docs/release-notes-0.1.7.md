# HaizFlow 0.1.7

**[Tải bộ cài Windows — HaizFlow-0.1.7-Setup.exe](https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.7/HaizFlow-0.1.7-Setup.exe)**

HaizFlow là ứng dụng miễn phí để **tải video hàng loạt, dịch video, tạo phụ đề và lồng tiếng** trên Windows. Chọn xử lý tự động, chỉnh từng bước trong chế độ Thủ công hoặc xử lý nhiều video theo hàng đợi.

## Chức năng chính

- **Tải video hàng loạt:** tải video lẻ và kênh được hỗ trợ, gồm YouTube, TikTok và Douyin. Douyin dùng phiên Chromium riêng, cài qua Gói tài nguyên.
- **Dịch video và tạo phụ đề:** nhận dạng bằng Whisper, dịch trên máy bằng HY-MT2 hoặc dùng Gemini; chỉnh nội dung, thời gian và phụ đề karaoke.
- **Lồng tiếng:** chọn giọng có sẵn hoặc nhân bản mẫu giọng bạn có quyền sử dụng; nhận diện nhiều người nói để gán giọng riêng.
- **Che phụ đề gốc:** OCR tìm vùng chữ; kéo và chỉnh kích thước vùng trên preview, rồi làm mờ hoặc vá nền.
- **Xử lý tự động và hàng loạt:** chọn các bước, theo dõi tiến trình, tạm dừng và tiếp tục.
- **Đăng mạng xã hội:** chuẩn bị và đăng video qua tài khoản Zernio.

## Cài đặt và sử dụng

1. **[Bấm để tải bộ cài EXE](https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.7/HaizFlow-0.1.7-Setup.exe)**, mở tệp và làm theo hướng dẫn. Cài mới chỉ cần Setup.exe, không cần tải các tệp Core.
2. Mở **Cài đặt → Chung**, chọn CPU/GPU; vào **Gói tài nguyên** để cài công cụ cần dùng. Không cần cài Python hoặc CUDA Toolkit riêng.
3. Tạo dự án **Thủ công**, **Tự động** hoặc **Hàng loạt**, thêm video từ tệp hoặc liên kết.
4. Chọn model, ngôn ngữ và giọng đọc. Gemini cần key của bạn; HY-MT2 dịch trên máy, không cần key.
5. Chạy xử lý, xem lại kết quả rồi bấm **Xuất**. Có thể đăng video qua Zernio.

Đã cài HaizFlow **0.1.4, 0.1.5 hoặc 0.1.6**? Bấm **Phiên bản mới → Kiểm tra lại → Cập nhật**, rồi xác nhận **Khởi động lại**. Có thể nâng trực tiếp lên **0.1.7**, không cần cài từng bản trung gian. Dự án, cài đặt và gói tài nguyên được giữ nguyên. Bạn cũng có thể dùng bộ cài EXE và chọn đúng thư mục HaizFlow đang dùng để nâng cấp.

[Hướng dẫn cài đặt](https://github.com/MachHongHai/HaizFlow/blob/main/docs/install.vi.md) · [Hướng dẫn sử dụng](https://github.com/MachHongHai/HaizFlow/blob/main/docs/user-guide.vi.md) · [Website](https://haizflow.pages.dev/) · [English guide](https://github.com/MachHongHai/HaizFlow/blob/main/docs/user-guide.md)

## Cập nhật trong 0.1.7

- Sửa giọng và phụ đề trên preview không phát đúng sau khi dừng rồi phát lại, hoặc sau một bước xử lý.
- Phụ đề hiển thị hết thời gian trên timeline, không bị rút ngắn theo độ dài giọng đọc.
- Tái sử dụng cache phụ đề và giọng khi chỉnh vùng OCR hoặc cách trình bày phụ đề; không giải mã lại âm thanh chỉ vì thay đổi hình ảnh.
- Ưu tiên chuẩn bị các câu phụ đề tiếp theo để giảm khoảng trống khi chuyển câu trên preview.
- Nhận đúng thiết bị âm thanh khi phát lại hoặc đổi giữa loa và tai nghe.
- Giữ các tính năng và gói tài nguyên của 0.1.6. Bản vá không yêu cầu cài lại gói AI.

## Cấu hình và điều kiện sử dụng

Windows 10 (1809 trở lên) hoặc Windows 11 x64; RAM hệ thống từ **16 GB**. GPU NVIDIA không bắt buộc. Các lựa chọn GPU cần card tương thích từ **6 GB VRAM riêng**; model nặng cần nhiều bộ nhớ hơn. Bộ cài và trang Gói tài nguyên hiển thị dung lượng tương ứng.

Checkpoint OmniVoice hiện tại **chỉ dành cho sử dụng phi thương mại**. Gemini, Zernio và các dịch vụ ngoài có hạn mức, chi phí và điều khoản riêng. Chỉ dùng video, nhạc và mẫu giọng bạn có quyền sử dụng.

Bản Windows hiện chưa có chữ ký Authenticode. Windows có thể hiển thị cảnh báo nhà phát hành hoặc chặn tệp theo chính sách bảo mật. Tải từ repository chính thức và đọc hướng dẫn cài đặt; không cần tắt phần mềm bảo vệ.

Các tệp **Core** dành cho cập nhật trong app. **ThirdPartySources** cung cấp nguồn thư viện theo giấy phép. Người dùng cài mới chỉ cần **Setup.exe**.
