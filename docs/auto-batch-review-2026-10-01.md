# Auto, Batch và hộp Giới thiệu — 01/10/2026

## Luồng Auto

- Xử lý và Chạy lại mở cùng hộp cấu hình chất lượng/vị trí xuất; chưa xác nhận thì không đưa tác vụ vào hàng đợi.
- Xác nhận lưu preset vào video, kiểm tra chủ sở hữu cài đặt và gói tài nguyên, chạy đồ thị xử lý đầy đủ rồi xuất bản sao thành phẩm.
- Checkpoint được dùng lại khi chữ ký cấu hình và đầu ra còn hợp lệ. Đổi preset chỉ làm mất tính hợp lệ của bản dựng; không xóa toàn bộ kết quả nhận dạng/giọng đọc.
- Pause hoặc chờ duyệt phụ đề giữ yêu cầu xuất ở trạng thái chờ. Không lấy bản dựng cũ để báo lần xử lý mới đã xuất thành công.
- Hủy xuất không hủy quá trình xử lý dự án. Người dùng vẫn có thể tiếp tục hoặc xuất lại.
- Chọn chất lượng khác không nhận nhầm bản dựng legacy là bản có chất lượng mới.

## Batch

Đã kiểm tra nhập file/thư mục, thứ tự nhập lưu bền, cài đặt chung và từng video, hàng đợi tuần tự, tạm dừng/tiếp tục, checkpoint và xuất thành phẩm.

Các lỗi được sửa:

- Xuất hàng loạt chỉ chọn video đã hoàn tất, có bản dựng phù hợp và không đang chạy. Video chưa xong hoặc cấu hình đã đổi được bỏ qua, có thông báo số lượng.
- Thay đổi cài đặt video đã hoàn tất đưa video đó về hàng chờ; giữ checkpoint để pipeline kiểm tra và dùng lại.
- Khi chỉnh thuộc tính phụ đề được cung cấp, giữ các thuộc tính khác thay vì thay toàn bộ bằng mặc định.
- Kiểm tra Gemini key và mẫu giọng nhân bản trước khi thêm cả nhóm vào hàng đợi, tránh chạy một phần nhóm rồi báo thiếu cấu hình nhiều lần.
- Sự kiện sao chép chưa được đọc phải hoàn tất trước khi bắt đầu yêu cầu xuất mới; tránh sự kiện cũ ghi nhầm trạng thái cho lần xuất tiếp theo.
- Chỉ một worker sao chép được khởi chạy tại một thời điểm khi chờ các bản dựng.
- Thử lại yêu cầu xuất bị lỗi có thể yêu cầu dựng nếu bản dựng chưa có; trạng thái xuất vẫn độc lập với trạng thái pipeline.

Hàng đợi xử lý hiện tại đã tuần tự hóa video; kiểm thử xác nhận không chạy song song nhiều pipeline, tiếp tục video sau lỗi ở video trước và tháo các mục đang chờ trước khi pause.

## Giới thiệu

Chiều cao theo nội dung, không đặt cố định 840 px. Ở cửa sổ thấp, giảm khoảng cách, kích thước logo và QR vừa đủ để nội dung còn nguyên. Không hiển thị thanh cuộn dọc; vẫn có thể cuộn nội dung nếu cửa sổ quá nhỏ.

Đã kiểm tra ảnh thực tế ở cửa sổ 1120×900 và 1120×720. Ảnh nhỏ hiển thị đầy đủ QR và nút Đóng, không chồng lên các nút sao chép.

## Kiểm chứng và giới hạn

- Bộ Python: 1.056 test và 121 subtest qua. Sau chỉnh cuối của About, chạy lại 65 test UI, tất cả qua.
- Qt Quick Test: 60 qua, không lỗi hoặc bỏ qua.
- QML lint, Ruff kiểm tra lỗi Python và kiểm tra tính nhất quán giấy phép đều qua.
- Có cảnh báo TorchCodec có sẵn trong môi trường phát triển; chưa sửa hoặc đổi dependency trong đợt này.
- Kiểm thử bằng fixture và mô phỏng worker, không chạy lại video dài bằng model GPU trên dữ liệu dự án người dùng. Đây không phải chứng nhận hoàn hảo cho mọi cấu hình hay installer.
- Không build installer/executable, commit, push, thay đổi hoặc xóa dữ liệu dự án người dùng.

Các giới hạn delta update được ghi riêng trong báo cáo cập nhật trước đó; đợt này không thay đổi cơ chế cập nhật.
