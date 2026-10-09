# HaizFlow 0.1.8

**[Tải bộ cài Windows — HaizFlow-0.1.8-Setup.exe](https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.8/HaizFlow-0.1.8-Setup.exe)**

HaizFlow là ứng dụng miễn phí để tải video, dịch video, tạo phụ đề và lồng tiếng trên Windows. Bạn có thể xử lý tự động, chỉnh từng bước trong chế độ Thủ công hoặc chạy nhiều video theo hàng đợi.

## Chức năng chính

- Tải video lẻ, âm thanh và kênh được hỗ trợ, gồm YouTube, TikTok và Douyin. Douyin dùng phiên Chromium riêng, cài qua Gói tài nguyên.
- Nhận dạng bằng Whisper; dịch trên máy bằng HY-MT2 hoặc dùng Gemini; chỉnh nội dung, thời gian và phụ đề karaoke.
- Tạo giọng, dùng mẫu giọng bạn có quyền sử dụng và gán giọng cho nhiều người nói.
- OCR tìm phụ đề gốc; chỉnh vị trí, kích thước vùng che trên preview rồi Áp dụng làm mờ hoặc vá nền.
- Theo dõi tiến trình, tạm dừng, tiếp tục và tái sử dụng các kết quả đã xử lý.
- Chuẩn bị và đăng video qua tài khoản Zernio.

## Cài đặt và sử dụng

1. **[Bấm để tải bộ cài EXE](https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.8/HaizFlow-0.1.8-Setup.exe)**, mở tệp và làm theo hướng dẫn. Cài mới chỉ cần Setup.exe.
2. Vào **Cài đặt → Chung**, chọn CPU/GPU; mở **Gói tài nguyên** để cài công cụ cần dùng. Không cần cài Python hoặc CUDA Toolkit riêng.
3. Tạo dự án Thủ công, Tự động hoặc Hàng loạt; nhập video từ tệp hoặc liên kết.
4. Chọn ngôn ngữ, model và giọng đọc. Gemini cần key của bạn; HY-MT2 dịch trên máy, không cần key.
5. Xử lý, xem lại kết quả rồi bấm **Xuất**.

Đang dùng **0.1.6 hoặc 0.1.7**? Bấm **Phiên bản mới → Kiểm tra lại → Cập nhật**, rồi chọn **Khởi động lại**. Có thể nâng trực tiếp lên 0.1.8, không cần cài bản trung gian. Dự án, cài đặt và tệp model đã tải được giữ nguyên. Sau cập nhật, cài phiên bản bộ xử lý CPU/CUDA mới nếu app yêu cầu trong **Gói tài nguyên**; các bản sửa inference cần engine mới, không chỉ Core. Bản này cung cấp gói cập nhật từ 0.1.6 và 0.1.7 cùng gói Core đầy đủ dự phòng. Bản dưới 0.1.6 không nằm trong phạm vi kiểm chứng cập nhật này; hãy dùng bộ cài và chọn đúng thư mục HaizFlow hiện tại nếu cần nâng cấp.

[Hướng dẫn cài đặt](https://github.com/MachHongHai/HaizFlow/blob/v0.1.8/docs/install.vi.md) · [Hướng dẫn sử dụng](https://github.com/MachHongHai/HaizFlow/blob/v0.1.8/docs/user-guide.vi.md) · [Website](https://haizflow.pages.dev/) · [English guide](https://github.com/MachHongHai/HaizFlow/blob/v0.1.8/docs/user-guide.md)

## Cập nhật trong 0.1.8

- Sửa nhận diện RAM trên Windows: máy lắp 16 GB không bị từ chối chỉ vì RAM khả dụng cho hệ điều hành thấp hơn do phần cứng dành riêng bộ nhớ. Kiểm tra RAM trống và commit trước các bước AI nặng; giảm việc giữ đồng thời nhiều model trên CPU.
- Sửa tạm dừng tạo giọng trên video dài; ngắt worker đúng video, giữ các câu đã tạo để tiếp tục và không tự khởi chạy lại sau lệnh dừng.
- Chỉnh thời gian phụ đề không làm mất giọng đã tạo. Giảm lỗi giọng không hợp lệ khi đổi chế độ người nói, giữ các đoạn giọng hợp lệ khi thử lại.
- Cải thiện nhập clip dài, phát preview và đọc cache khi mở lại dự án; dùng lại nguồn phát được trực tiếp và cache âm thanh/phụ đề, tránh dựng lại không cần thiết.
- Cải thiện thời gian chuẩn bị preview sau OCR; vùng OCR không làm mất cache giọng, phụ đề và các bước khác.
- Đồng bộ nhịp karaoke với thời lượng giọng thực tế, vẫn giữ thời gian phụ đề đã chỉnh trên timeline.
- Lưu thao tác gần nhất trong Tải xuống: tab, liên kết đã xem trước, thiết lập quét kênh và danh sách video.
- Cải thiện quét kênh Douyin với phạm vi lớn: dùng lại phiên, tiếp tục từ trang đã quét và giữ kết quả một phần khi bị giới hạn. Sắp xếp áp dụng trong phạm vi đã quét, không phải toàn bộ lịch sử kênh.
- Sửa dừng tải trong ô nhập liên kết, thay nguồn và xóa dự án khi tác vụ đang dừng; tránh giữ tệp video gây lỗi khóa tệp trên Windows.
- Cải thiện xác minh chứng chỉ khi tải gói tài nguyên, giữ kiểm tra TLS; không tắt xác minh chứng chỉ.
- Tạm ẩn Gemini 3.8 khỏi danh sách chọn model. Tính năng thêm lớp OCR vẫn chưa ra mắt.
- Phát hành bộ xử lý CPU 10/CUDA 12/OCR 5 với mã xử lý mới. Các gói trong bản mới không phụ thuộc release dưới 0.1.5 đã được dọn; model và thư viện được khóa phiên bản không thay đổi.

## Cấu hình và điều kiện sử dụng

Windows 10 (1809 trở lên) hoặc Windows 11 x64; RAM lắp đặt từ **16 GB**. GPU NVIDIA không bắt buộc. Các lựa chọn GPU cần card tương thích từ **6 GB VRAM riêng**; model nặng cần nhiều bộ nhớ hơn. RAM trống và bộ nhớ commit cũng phải đủ tại thời điểm xử lý; đóng ứng dụng nặng và để Windows quản lý page file nếu được khuyến nghị. Đây không phải cam kết đã benchmark toàn bộ pipeline trên mọi máy 16 GB.

Checkpoint OmniVoice hiện tại **chỉ dành cho sử dụng phi thương mại**. Gemini, Zernio và các dịch vụ ngoài có hạn mức, chi phí và điều khoản riêng. Chỉ dùng video, nhạc và mẫu giọng bạn có quyền sử dụng. Website nguồn có thể yêu cầu xác minh hoặc giới hạn truy cập; không cam kết mọi liên kết đều tải được.

Bản Windows chưa có chữ ký Authenticode. Windows có thể cảnh báo nhà phát hành hoặc chặn tệp theo chính sách bảo mật. Tải từ repository chính thức; không cần tắt phần mềm bảo vệ.

Các tệp **Core** dành cho cập nhật trong app; **engine** do Gói tài nguyên tự tải; **ThirdPartySources** cung cấp nguồn thư viện theo giấy phép. Người dùng cài mới chỉ cần **Setup.exe**.
