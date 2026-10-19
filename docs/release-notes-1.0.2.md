# HaizFlow 1.0.2

[Tải bộ cài Windows](https://github.com/MachHongHai/HaizFlow/releases/download/v1.0.2/HaizFlow-1.0.2-Setup.exe)

## Sửa lỗi và cải thiện

- Sửa lỗi tạo giọng nhiều người nói bị dừng khi lưu bản đồ người nói trên một số đường dẫn Windows dài. Giữ nguyên nhận diện, lựa chọn giọng và cache hợp lệ; không cần chuyển sang giọng đơn để né lỗi.
- Giảm nguy cơ hết bộ nhớ khi nạp HY-MT2: giải phóng các worker/model cũ, đo lại bộ nhớ hệ thống Windows và VRAM trước khi nạp. Nếu không đủ chỗ, app có thể dùng HY-MT2 CPU Q4 đã cài cho lượt chạy đó, vẫn kiểm tra RAM và không đổi cấu hình dự án. Nếu thiếu gói Q4, app hướng dẫn cài thay vì cố nạp bản GPU quá sức. Q4 có thể chậm hơn GPU và dùng độ chính xác của model lượng tử hóa hiện có; không cam kết hết OOM trên mọi máy.
- Cho thêm video vào dự án đăng mạng xã hội trong khi video khác đang đăng. Bấm Đăng riêng để xếp hàng tuần tự; chống xếp trùng, giữ đúng video khi danh sách đổi thứ tự và không tự đăng video mới nhập khi chưa được chọn.
- Giữ khả năng cấu hình/xếp hàng dự án khác khi một dự án đang xử lý hoặc xuất; mở khóa lựa chọn model dịch cho nhất quán.
- Cải thiện trạng thái Chromium cho phiên Douyin, giữ cơ chế app chủ động đóng trình duyệt sau bước xác minh để thu hồi tài nguyên.

## Cập nhật từ 1.0.0 và 1.0.1

Mở **Phiên bản mới → Cập nhật** để nâng trực tiếp từ **1.0.0** hoặc **1.0.1**. Release có Delta riêng cho từng bản, Core đầy đủ dự phòng và bộ cài mới. Dữ liệu dự án, thiết lập và model được giữ nguyên; các release cũ không bị xóa hay thay asset.

Các sửa lần này nằm trong Core; tiếp tục sử dụng bộ xử lý CPU 15/CUDA 17 và OCR 7 đã phát hành. Khi nâng từ 1.0.0, mở **Gói tài nguyên** và cập nhật bộ xử lý nếu app yêu cầu. HY-MT2 chỉ tự chuyển sang CPU Q4 khi gói model và bộ xử lý tương ứng đã cài; không tự tải model khi đang xử lý video.

Thư viện, model và codec không đổi. [Nguồn thư viện tương ứng](https://github.com/MachHongHai/HaizFlow/releases/download/v1.0.0/HaizFlow-1.0.0-ThirdPartySources.zip) và các gói tài nguyên tiếp tục được giữ tại URL phát hành bất biến.

Windows x64. Bản Windows **chưa ký Authenticode**; Windows có thể cảnh báo hoặc chặn theo chính sách. Không tắt phần mềm bảo vệ. Kiểm thử cục bộ/frozen không thay thế mọi cấu hình Windows, GPU hay điều kiện mạng thực tế. Các giới hạn giấy phép model, bao gồm checkpoint OmniVoice phi thương mại, vẫn áp dụng.
