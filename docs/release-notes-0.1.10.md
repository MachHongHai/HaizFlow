# HFlow 0.1.10

[Tải bộ cài Windows](https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.10/HaizFlow-0.1.10-Setup.exe)

## Thay đổi

- Sửa hàng cuối của danh sách đăng bị che; cho phép mở bài đã đăng và xóa video khác trong khi một video đang đăng. Video đang xử lý vẫn được bảo vệ.
- Cải thiện chế độ GPU ít VRAM: OmniVoice dùng chế độ quản lý bộ nhớ phù hợp; cảnh báo/chặn model vượt khả năng GPU, không thay checkpoint hoặc giảm chất lượng suy luận. Không cam kết tốc độ trên mọi GPU 4 GB.
- Sửa bảo toàn giọng đọc khi thêm nhạc nền, thay nguồn reset các lớp của nguồn cũ, bảo toàn mapping nhiều người nói khi tạo lại các câu đã sửa.
- Sửa vẽ timeline dài và tái sử dụng cache OCR/vá nền cũ mà không làm mất kết quả đã áp dụng.
- Thêm Xuất SRT trong workspace, chặn khi chưa có phụ đề.
- Cải thiện dự án Hàng loạt: lựa chọn video xem trước, cảnh báo thiết lập riêng vẫn cho xử lý, tiếp tục sau lỗi từng video và báo cáo kết quả/chi tiết lỗi.
- Cập nhật ảnh Trang chủ và trình sửa Thủ công trong README.

## Cập nhật

Hỗ trợ nâng trực tiếp từ **0.1.8 và 0.1.9** qua **Phiên bản mới → Cập nhật**. Có gói delta cho từng bản và gói Core đầy đủ dự phòng. Dự án, cài đặt và model được giữ nguyên. Các phiên bản dưới 0.1.8 không nằm trong phạm vi kiểm chứng của bản này.

Cài mới chỉ cần Setup.exe. Sau cập nhật, mở Gói tài nguyên để cập nhật bộ xử lý CPU/CUDA nếu được yêu cầu; sửa inference cần engine mới, không chỉ Core.

Windows x64; RAM lắp đặt từ 16 GB, RAM trống và Windows commit phải đủ khi xử lý. Lựa chọn GPU phụ thuộc model và khả năng thực tế của card; không phải mọi model đều chạy được trên GPU 4 GB. Không có benchmark toàn pipeline trên mọi máy 16 GB/4 GB VRAM.

Checkpoint OmniVoice chỉ dành cho sử dụng phi thương mại. Chỉ dùng media/mẫu giọng có quyền sử dụng. Dịch vụ ngoài có điều khoản và giới hạn riêng.

Bản Windows chưa có chữ ký Authenticode; Windows có thể cảnh báo hoặc chặn theo chính sách. Không tắt phần mềm bảo vệ. ThirdPartySources cung cấp nguồn thư viện theo giấy phép.
