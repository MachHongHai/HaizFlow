# Kiểm tra tiếp tục tác vụ

## Hành vi

- Tạm dừng giữ kết quả đã hoàn tất. Tiếp tục không đổi cấu hình của lượt chạy.
- HY-MT2 và Gemini lưu kết quả từng lô trong tệp tiến độ riêng. Kết quả dở dang không thay thế phụ đề đã công bố.
- Tiếp tục chỉ gửi các câu còn thiếu; vẫn kiểm tra chất lượng toàn bộ kết quả trước khi công bố.
- Auto/Batch giữ phần nhận dạng đã hoàn tất khi tiếp tục dịch, tránh thay đổi đầu vào của lượt dịch dở dang.
- Editor có Chạy lại cạnh Tiếp tục. Chạy lại cần xác nhận và dùng cấu hình hiện tại; nó bỏ tiến độ dở dang của công cụ được chọn, không xóa kết quả đã công bố trước đó.
- Tiếp tục bị chặn nếu cài đặt hoặc đầu vào liên quan đã đổi, kể cả bản nháp chưa lưu và chế độ CPU/GPU của app. Đổi tên dự án hay thay cài đặt không liên quan đến công cụ đang dừng không bị chặn.
- Tác vụ tạm dừng từ bản cũ chưa lưu cấu hình cần Chạy lại một lần để tránh ghép kết quả sai.

## Bộ nhớ

Log thử nghiệm HY-MT2 GPU ghi nhận bộ nhớ cam kết Windows giảm từ khoảng 4,8 GiB xuống 0,7 GiB sau khi nạp model, rồi về 0 khi tạo câu đầu tiên. Đây không phải chỉ là thiếu VRAM.

Khâu bàn giao giải phóng cả quyền sở hữu nhận dạng/tách giọng/OCR của worker dùng chung và đóng worker OmniVoice không còn cần. Chuẩn bị model nền kiểm tra cả RAM và bộ nhớ cam kết; model nền được giải phóng khi bộ nhớ thấp. HY-MT2 GPU kiểm tra dự phòng trước khi nạp trọng số, không âm thầm đổi model người dùng chọn.

Đây là bảo vệ trong phạm vi app, không thể bảo đảm ứng dụng khác hoặc driver không tiêu thụ thêm bộ nhớ trong khi chạy.

## Thử bản đóng gói

1. Cài hoặc sửa gói bộ xử lý mới có runtime contract 5. Worker cũ không hỗ trợ lưu từng lô dịch.
2. Dịch video nhiều câu, tạm dừng sau vài lô, tiếp tục. Log phải ghi số câu giữ lại và lô tiếp theo không bắt đầu từ câu 1.
3. Tạm dừng, đổi ngôn ngữ/model hoặc CPU/GPU: Tiếp tục phải cảnh báo và không thêm tác vụ vào hàng đợi.
4. Khôi phục cấu hình cũ: Tiếp tục phải dùng lại tiến độ. Chạy lại phải hỏi xác nhận rồi bắt đầu lượt mới.
5. Với batch, nếu một video đổi cấu hình thì thao tác Tiếp tục không được chạy một phần batch trước khi cảnh báo.
6. Kiểm tra nút và thông báo ở cả tiếng Việt và tiếng Anh.

Kiểm thử tự động bao phủ lưu/khôi phục tiến độ, đầu vào thay đổi, cấu hình nháp, batch, khởi động hàng đợi, xác nhận chạy lại và giải phóng worker dùng chung. Các case tải/tạm dừng gói tài nguyên hiện có vẫn được giữ trong bộ kiểm thử toàn app.
