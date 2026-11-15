# HaizFlow 1.0.5

[Tải bộ cài Windows](https://github.com/MachHongHai/HaizFlow/releases/download/v1.0.5/HaizFlow-1.0.5-Setup.exe)

## Điểm mới

- Thêm API dịch OpenAI, DeepSeek, OpenRouter và API tùy chỉnh tương thích OpenAI. Chọn model, văn phong và mức suy luận theo từng dự án; Cài đặt API chỉ quản lý kết nối/key.
- Cập nhật 9 model Gemini, thêm nhãn miễn phí/tính phí và mức suy luận đúng từng model. Nhãn miễn phí chỉ khả năng dùng free tier; key bật thanh toán vẫn có thể tính phí.
- OpenRouter dùng danh sách có cache và làm mới nền, lọc model phù hợp cho dịch, kiểm tra endpoint và giới hạn đầu ra; sửa xử lý JSON và thông báo quota. Giữ bản dịch đã hoàn thành để tiếp tục phần còn thiếu.
- Thêm MCP điều khiển dự án, xử lý, phụ đề, xuất và đăng video theo quyền được bật. Hướng dẫn kết nối Codex, Claude và Antigravity gọn theo từng bước; trả kết quả có phân trang và chế độ công cụ gọn để giảm ngữ cảnh agent.
- Sửa trạng thái xuất và phụ đề/preview bị lẫn giữa các dự án; cải thiện áp dụng thiết lập, chọn phạm vi chạy lại và xóa video trong batch.
- Tạo lại giọng cho một hoặc nhiều câu trong dự án thủ công, tái dùng worker để giảm thời gian nạp model. Cải thiện câu ngắn, ngôn ngữ Nhật/Hàn/Tây Ban Nha, âm lượng và mẫu tham chiếu OmniVoice.
- Tối ưu OCR và tải preview, tránh khởi tạo và đọc tệp lặp; sửa vô hiệu hóa cache khi thay nguồn nhưng giữ cache hợp lệ khi mở lại dự án. OCR có hỗ trợ GPU DirectML trên máy tương thích.
- Bổ sung font phụ đề phù hợp cho Trung/Nhật/Hàn; cải thiện watermark, hộp thoại lỗi và phản hồi khi đổi dự án.

## Cập nhật từ 1.0.2

Các bản **1.0.2, 1.0.3 và 1.0.4** có thể cập nhật trực tiếp lên **1.0.5** trong app: có Delta riêng và Full Core dự phòng. Cài mới dùng **Setup.exe**, không dùng ZIP Core thay bộ cài.

Sau cập nhật, vào **Cài đặt → Gói tài nguyên** để cập nhật **CPU 18 / GPU CUDA 20 / OCR 10**. Không phải tải lại model; dự án và dữ liệu hiện có được giữ nguyên. Bộ Setup chứa launcher/updater mới; cập nhật Core trong app không tự thay launcher/updater cũ.

Windows 10/11 x64. Bản phát hành **chưa ký Authenticode**; Windows có thể cảnh báo hoặc chặn theo chính sách. Không tắt phần mềm bảo vệ. Các giấy phép độc lập và giới hạn checkpoint OmniVoice phi thương mại vẫn áp dụng. MCP tắt khi thoát app; khi bật, hãy xem và tắt những quyền không muốn cấp cho agent.
