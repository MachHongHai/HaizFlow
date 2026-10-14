# HFlow 1.0.0

[Tải bộ cài Windows](https://github.com/MachHongHai/HaizFlow/releases/download/v1.0.0/HaizFlow-1.0.0-Setup.exe)

## Thay đổi

- Thêm chuẩn hóa khung hình 9:16 nền mờ hoặc đầy khung trong Manual, Auto và Hàng loạt; video đã là 9:16 được giữ nguyên.
- Phụ đề tự căn theo OCR lớn hơn khoảng 25%; chữ có thể vượt chiều cao box OCR để giữ độ dễ đọc, không đổi vùng vá/che nguồn.
- Thêm tốc độ phát preview, zoom timeline và cải thiện điều khiển xuất/tiến trình; khóa Xuất khi tác vụ khác đang xử lý.
- Đưa Edge TTS trở lại lựa chọn giọng đọc; tăng độ bền khi kết nối lỗi, có thử lại giới hạn.
- Thêm VieNeu CPU/GPU, mẫu nghe thử và nhân bản giọng; ưu tiên VieNeu GPU cho tiếng Việt. Phụ đề tiếng Trung dùng backend tương thích thay vì VieNeu.
- Nhập SRT hiển thị ngay trên preview/timeline, có thể dịch hoặc tạo giọng trực tiếp; Xóa SRT trả phụ đề/giọng về trạng thái trống. Xuất SRT gốc, kết quả hoặc cả hai; khóa thao tác khi đang xử lý.
- Cải thiện nhiều người nói: câu ngắn, giọng cao/trẻ em và các câu chứa nhiều lượt nói; không lấy lựa chọn nữ mặc định làm kết quả nhận diện. Những lượt thiếu bằng chứng vẫn được đánh dấu chưa chắc chắn và dùng Nữ dịu dàng khi cần fallback. Không cam kết chính xác mọi giọng biến đổi/hoạt hình.
- Sửa xử lý âm cuối của câu TTS ngắn, đặt fade mặc định bằng 0 và tránh ép thời lượng sinh giọng. Không cam kết mọi model đọc chính xác mọi ngôn ngữ/từ mượn.
- Tạo lại giọng sau khi sửa phụ đề chỉ sinh lại câu thay đổi, giữ cache hợp lệ và mapping người nói của các câu còn lại. Chạy lại toàn bộ khi chủ động tạo lại không sửa nội dung hoặc đổi cấu hình giọng.
- Cải thiện nhập tiếng Việt Windows Telex, dropdown đóng khi bấm lần hai và giao diện focus.
- Cảnh báo sửa phụ đề/Gemini một lần theo phiên; undo đúng nội dung cũ khôi phục trạng thái khớp giọng.
- Sửa play tự bật khi mở project và cải thiện thao tác timeline/preview.
- Danh sách đăng hiển thị mới nhất lên đầu; Đăng tất cả vẫn xử lý từ cũ tới mới.
- Đồng bộ tiến trình xuất giữa cửa sổ và thanh trạng thái; chỉ đạt 100% khi hoàn tất. Xuất đoạn đúng thời gian khi tốc độ đầu ra khác 1x; tối ưu các lượt encode và OCR khi xuất.
- Sửa đóng hộp thoại xác nhận bằng dấu X bị kẹt Đang chuẩn bị; cải thiện phản hồi các nút tiếp tục/chạy lại/tách giọng. Hủy chỉ dọn kết quả của lượt bị hủy, giữ kết quả trước đó; tạm dừng giữ phần đã hoàn thành.

## Cập nhật và tài nguyên

Hỗ trợ nâng trực tiếp từ **0.1.8, 0.1.9 và 0.1.10** qua **Phiên bản mới → Cập nhật**. Có delta riêng cho từng bản và Core đầy đủ dự phòng. Giữ dữ liệu dự án, thiết lập và model; không xóa release cũ.

Cài mới chỉ cần Setup.exe. Sau cập nhật, mở **Gói tài nguyên** và cập nhật bộ xử lý CPU/CUDA khi app yêu cầu: các sửa tạo giọng cần cả bộ xử lý mới, không chỉ Core. Gói OCR không đổi trong bản này. Giọng đã lưu trước đó không tự bị ghi đè; tạo lại giọng để áp dụng bản sửa âm thanh.

Windows x64, RAM lắp đặt từ 16 GB; RAM trống/Windows commit phải đủ khi xử lý. GPU 4 GB được hỗ trợ theo khả năng từng model; không cam kết tốc độ hay khả năng chạy mọi model trên mọi GPU.

OmniVoice checkpoint vẫn giới hạn phi thương mại. Chỉ dùng media/mẫu giọng có quyền sử dụng. Model phân loại âm sắc ECAPA q8 đi kèm Core theo MIT; đó là dự đoán âm sắc, không phải xác định giới tính cá nhân.

Bản Windows **chưa ký Authenticode**; Windows có thể cảnh báo hoặc chặn theo chính sách. Không tắt phần mềm bảo vệ. ThirdPartySources cung cấp nguồn thư viện tương ứng. Kiểm thử cục bộ/frozen không thay thế ma trận mọi máy Windows hoặc điều kiện mạng thực tế.
