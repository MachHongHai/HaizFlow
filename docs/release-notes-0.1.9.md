# HaizFlow 0.1.9

**[Tải bộ cài Windows — HaizFlow-0.1.9-Setup.exe](https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.9/HaizFlow-0.1.9-Setup.exe)**

HaizFlow là ứng dụng miễn phí để tải video, dịch, tạo phụ đề và lồng tiếng trên Windows. Bạn có thể xử lý tự động, chỉnh từng bước trong chế độ Thủ công hoặc chạy nhiều video theo hàng đợi.

## Chức năng chính

- Tải video, âm thanh và kênh được hỗ trợ. Douyin dùng phiên Chromium riêng, cài qua Gói tài nguyên.
- Nhận dạng bằng Whisper; dịch trên máy bằng HY-MT2 hoặc dùng Gemini; chỉnh nội dung, thời gian và phụ đề karaoke.
- Tạo giọng, dùng mẫu giọng bạn có quyền sử dụng và gán giọng cho nhiều người nói.
- OCR tìm phụ đề gốc; chỉnh vùng nhận diện và thêm các lớp làm mờ/vá nền độc lập.
- Cắt timeline Kết quả thành các đoạn; xuất toàn bộ video hoặc đoạn đã chọn.
- Theo dõi tiến trình, tạm dừng, tiếp tục và tái sử dụng kết quả đã xử lý.
- Chuẩn bị và đăng video qua tài khoản Zernio.

## Cài đặt và sử dụng

1. **[Bấm để tải bộ cài EXE](https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.9/HaizFlow-0.1.9-Setup.exe)**, mở tệp và làm theo hướng dẫn. Cài mới chỉ cần Setup.exe.
2. Vào **Cài đặt → Chung**, chọn CPU/GPU; mở **Gói tài nguyên** để cài công cụ cần dùng. Không cần cài Python hoặc CUDA Toolkit riêng.
3. Tạo dự án Thủ công, Tự động hoặc Hàng loạt; nhập video từ tệp hoặc liên kết.
4. Chọn ngôn ngữ, model và giọng đọc. HY-MT2 dịch trên máy không cần key; Gemini cần key của bạn.
5. Xử lý, xem lại kết quả rồi bấm **Xuất**. Khi xuất một đoạn, chọn đoạn Kết quả cần xuất trong hộp thoại.

Đang dùng **0.1.6, 0.1.7 hoặc 0.1.8**? Bấm **Phiên bản mới → Kiểm tra lại → Cập nhật**, rồi chọn **Khởi động lại**. Có thể nâng trực tiếp lên 0.1.9, không cần cài bản trung gian. Dự án, cài đặt và tệp model đã tải được giữ nguyên. Sau cập nhật, cài bộ xử lý CPU/CUDA mới nếu app yêu cầu trong **Gói tài nguyên**; sửa inference cần engine mới, không chỉ Core. Bản này cung cấp delta từ từng bản 0.1.6–0.1.8 và gói Core đầy đủ dự phòng. Bản dưới 0.1.6 không nằm trong phạm vi kiểm chứng cập nhật này.

[Hướng dẫn sử dụng](https://github.com/MachHongHai/HaizFlow/blob/v0.1.9/docs/user-guide.vi.md) · [Trợ giúp](https://github.com/MachHongHai/HaizFlow/blob/v0.1.9/docs/support.vi.md) · [Website](https://haizflow.pages.dev/)

## Cập nhật trong 0.1.9

- Sửa chuyển vị trí gói tài nguyên: có tiến trình sao chép/xác minh, xử lý hủy và chuyển sang vị trí mới sau khi dữ liệu đã được kiểm tra.
- Thêm nút tua trước/sau 15 và 30 giây bằng icon bên cạnh nút So sánh và zoom.
- Khôi phục lớp che độc lập: thêm, chỉnh vị trí/kích thước, chọn làm mờ hoặc vá nền rồi Áp dụng; chỉnh thời gian bằng kéo timeline, không có ô bắt đầu/kết thúc trong panel.
- Thêm track **Kết quả** trên cùng timeline, hỗ trợ chia/cắt đoạn và chọn xuất một đoạn. Không cắt phá hủy nguồn hoặc xóa cache AI.
- Xuất một đoạn chỉ chuẩn bị và render phạm vi đã chọn, không render toàn bộ video rồi mới cắt. Cải thiện tiến trình xuất video dài.
- Sửa xuất bản cache khi thư mục cũ bị khóa hoặc chưa hoàn chỉnh; xác minh output trước khi kích hoạt và giữ bản cũ nếu thay thế thất bại.
- Checkpoint dịch và tài liệu editor retry hữu hạn khi Windows khóa tệp tạm thời; không ghi đè bản hợp lệ khi ghi thất bại.
- Whisper chọn precision theo khả năng thực tế của CTranslate2. GPU hỗ trợ FP16 vẫn dùng FP16; GPU đời cũ như GTX 1070 dùng kiểu tương thích mà backend hỗ trợ.
- Không nhầm lỗi khóa tệp, hết dung lượng hoặc thiếu Windows commit thành lỗi GPU chỉ vì thông báo chứa GPU/CUDA.
- Phục hồi GPU → CPU dùng đúng lựa chọn CPU cho nhận dạng, dịch và tạo giọng trong lượt phục hồi, không đổi cấu hình đã lưu; tái sử dụng checkpoint và các câu giọng còn hợp lệ.
- Trước HY-MT2 CPU, giải phóng thêm runtime warm-up không cần thiết và đo lại bộ nhớ trong tối đa 2 giây nếu thiếu tài nguyên. Vẫn giữ kiểm tra an toàn RAM/commit.
- OmniVoice CPU chọn số luồng trước khi nạp model; theo dõi lượt suy luận thực để phân biệt đang tính toán với worker không tiến triển. Không thay checkpoint, precision hoặc số bước suy luận.
- Bộ xử lý CPU 11/CUDA 13/OCR 6 được build lại với mã mới; model và dependency khóa phiên bản không thay đổi.

## Cấu hình và lưu ý

Windows 10 (1809 trở lên) hoặc Windows 11 x64; RAM lắp đặt từ **16 GB**. GPU NVIDIA không bắt buộc. Các lựa chọn GPU cần card tương thích từ **6 GB VRAM riêng**; model nặng cần nhiều bộ nhớ hơn. RAM trống và Windows commit phải đủ tại thời điểm xử lý. OmniVoice CPU có thể mất vài phút cho một câu dài; phần trăm hoàn thành chỉ tăng khi đã có âm thanh hợp lệ. Không cam kết đã benchmark toàn bộ pipeline trên mọi máy 16 GB hoặc GTX 1070.

Checkpoint OmniVoice hiện tại **chỉ dành cho sử dụng phi thương mại**. Gemini, Zernio và dịch vụ ngoài có hạn mức, chi phí và điều khoản riêng. Chỉ dùng media và mẫu giọng bạn có quyền sử dụng. Nguồn mạng xã hội có thể yêu cầu xác minh hoặc giới hạn truy cập; không cam kết mọi liên kết đều tải được.

Bản Windows chưa có chữ ký Authenticode. Windows có thể cảnh báo hoặc chặn theo chính sách bảo mật. Tải từ repository chính thức; không tắt phần mềm bảo vệ.

Các tệp **Core** dành cho cập nhật trong app; **engine** do Gói tài nguyên tự tải; **ThirdPartySources** cung cấp nguồn thư viện theo giấy phép. Người dùng cài mới chỉ cần **Setup.exe**.
