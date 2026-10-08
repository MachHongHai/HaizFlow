# HaizFlow 0.1.5

**[Tải bộ cài Windows — HaizFlow-0.1.5-Setup.exe](https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.5/HaizFlow-0.1.5-Setup.exe)**

HaizFlow là ứng dụng miễn phí để **tải video hàng loạt, dịch video, tạo phụ đề và lồng tiếng** trên Windows. Bạn có thể xử lý tự động, chỉnh từng bước trong trình sửa Thủ công hoặc xử lý nhiều video theo hàng đợi.

## Chức năng chính

- **Tải video hàng loạt:** tải từ video, kênh hoặc trang cá nhân công khai được hỗ trợ, gồm YouTube, TikTok và Douyin.
- **Dịch video và tạo phụ đề:** nhận dạng lời nói bằng Whisper, dịch trên máy bằng HY-MT2 hoặc dùng Gemini; chỉnh nội dung, thời gian và phụ đề karaoke.
- **Lồng tiếng:** chọn giọng có sẵn hoặc dùng mẫu giọng bạn có quyền sử dụng. Nhận diện nhiều người nói để gán giọng riêng cho từng nhóm.
- **Che phụ đề gốc:** dùng OCR tìm vùng chữ, chỉnh vùng trên preview rồi làm mờ hoặc vá nền.
- **Xử lý tự động và hàng loạt:** chọn các bước cần chạy, theo dõi tiến trình, tạm dừng và tiếp tục.
- **Đăng mạng xã hội:** chuẩn bị và đăng video qua tài khoản Zernio.

## Cài đặt và sử dụng

1. **[Bấm để tải bộ cài EXE](https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.5/HaizFlow-0.1.5-Setup.exe)**, mở tệp và làm theo hướng dẫn. Bạn chỉ cần bộ cài này, không cần tải các tệp Core hay mã nguồn ở danh sách Assets.
2. Mở HaizFlow, chọn **Cài đặt → Chung → CPU/GPU**, rồi vào **Gói tài nguyên** để cài các công cụ cần dùng. Không cần cài Python hay CUDA Toolkit riêng.
3. Chọn **Dự án mới → Thủ công, Tự động hoặc Hàng loạt**, thêm video từ tệp hoặc liên kết.
4. Chọn model và ngôn ngữ. Khi dùng Gemini, thêm key của bạn trong **Cài đặt → API Key**. HY-MT2 dịch trên máy, không cần key.
5. Chạy các bước cần dùng, xem lại phụ đề và giọng đọc, rồi bấm **Xuất**. Có thể đăng kết quả qua Zernio.

Đã cài HaizFlow? Bấm **Phiên bản mới**, kiểm tra thông tin rồi xác nhận **Cập nhật**. Bản này có tệp cập nhật đầy đủ và cập nhật chênh lệch từ 0.1.4; không cần tải lại gói tài nguyên đã cài. Bạn cũng có thể dùng bộ cài EXE để nâng cấp.

[Hướng dẫn cài đặt](https://github.com/MachHongHai/HaizFlow/blob/main/docs/install.vi.md) · [Hướng dẫn sử dụng](https://github.com/MachHongHai/HaizFlow/blob/main/docs/user-guide.vi.md) · [Website](https://haizflow.pages.dev/) · [English guide](https://github.com/MachHongHai/HaizFlow/blob/main/docs/user-guide.md)

## Có gì mới trong 0.1.5?

- **Tải Douyin bằng phiên riêng:** cài **Trình duyệt Douyin (Chromium)** trong Gói tài nguyên, rồi bấm **Tạo phiên Douyin**. Phiên dùng chung cho Video, Kênh và Âm thanh; trình duyệt tự đóng sau khi xác minh thành công. Chưa cài gói thì app thông báo, không tự tải.
- **Sửa trạng thái tải xuống:** xóa thông báo lỗi cũ khi kiểm tra liên kết mới thành công; cải thiện tải kênh TikTok, Facebook và X. Tải kênh Instagram và Reddit tạm chưa mở; video Instagram lẻ vẫn được hỗ trợ.
- **Chỉnh vùng OCR trực tiếp trên preview:** bấm vào vùng chữ, kéo hoặc đổi kích thước, rồi bấm **Áp dụng**. **Khôi phục vùng nhận diện** áp dụng ngay vùng OCR đã quét ban đầu.
- **Phóng to/thu nhỏ preview:** dùng hai nút kính lúp hoặc con lăn chuột. Kéo chuột trái trên nền để dịch chuyển hình; kéo trên vùng OCR, phụ đề hoặc watermark để chỉnh đối tượng.
- **Nhớ bước đang chỉnh của từng dự án** khi thoát ra và mở lại.
- **Hàng đợi gói tài nguyên:** có thể chọn cài hoặc gỡ nhiều gói liên tiếp. Gói đang tạm dừng có thể tiếp tục hoặc hủy để về trạng thái ban đầu.
- **Thông báo tiến trình đúng ngôn ngữ:** sửa các câu còn lẫn Anh/Việt ở OCR, dịch, tạo giọng và tạm dừng, kể cả khi kèm số đếm.
- **Sửa bước dịch dừng vì nghi ngờ câu trùng:** vẫn thử dịch lại những câu cần kiểm tra; một bản dịch hợp lệ không còn bị chặn chỉ vì giống câu khác. Bản dịch rỗng hoặc sai định dạng vẫn được kiểm tra.
- **Cảnh báo bản dịch trong chế độ Thủ công:** kết quả vẫn được áp dụng; câu cần kiểm tra có box cảnh báo vàng trong phần Phụ đề. Chế độ Tự động chỉ dừng khi bản dịch còn ký tự lỗi hoặc nội dung không hợp lệ sau khi thử lại.
- **Giữ phụ đề và giọng đọc khi chỉnh vùng OCR:** các bản xem trước không còn ghi đè dữ liệu của bước khác. Tối ưu việc mở dự án và chuẩn bị preview sau khi áp dụng vùng che.
- **Âm thanh preview theo thiết bị mặc định:** đồng bộ đầu ra khi chuyển giữa Nguồn và Kết quả hoặc thay tai nghe.
- **Sửa thiếu thư viện khi hoàn tất tạo giọng trong chế độ Tự động.**
- **Các bước Thủ công chạy độc lập:** che phụ đề, tách giọng và các bước không dùng Gemini không yêu cầu Gemini key.
- **Sửa thay nguồn video sau khi xử lý**, và khôi phục preview đã lưu của dự án khác trong lúc một video đang chạy.
- **Liên kết bên ngoài mở bằng trình duyệt mặc định** của Windows.

## Cấu hình và điều kiện sử dụng

Windows 10 (1809 trở lên) hoặc Windows 11 x64; RAM hệ thống từ **16 GB**. GPU NVIDIA không bắt buộc. Các lựa chọn GPU cần card tương thích từ **6 GB VRAM riêng**; model nặng cần nhiều bộ nhớ hơn. Dung lượng ứng dụng hiển thị trong bộ cài, dung lượng tài nguyên hiển thị theo từng gói.

Checkpoint OmniVoice hiện tại **chỉ dành cho sử dụng phi thương mại**. Gemini, Zernio và các dịch vụ bên ngoài có hạn mức, chi phí và điều khoản riêng. Chỉ dùng video, nhạc và mẫu giọng bạn có quyền sử dụng.

Bản Windows hiện chưa có chữ ký Authenticode. Windows có thể hiển thị cảnh báo nhà phát hành hoặc chặn tệp theo chính sách bảo mật. Tải từ repository chính thức và đọc [hướng dẫn cài đặt](https://github.com/MachHongHai/HaizFlow/blob/main/docs/install.vi.md); không cần tắt phần mềm bảo vệ.

Tệp **ThirdPartySources** cung cấp nguồn thư viện theo giấy phép; các tệp **Core** dành cho cập nhật trong ứng dụng. Người dùng cài mới chỉ tải **Setup.exe**.
