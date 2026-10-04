# Kiểm thử bản cài 0.1.0

Đây là bản kiểm thử nội bộ, chưa phải bản phát hành công khai.

Giữ nguyên cấu trúc thư mục:

    installer/
      HaizFlow-0.1.0-DEVELOPMENT-Setup.exe
      offline-resources/
        engine-cpu-py313-3.zip
        engine-cuda128-py313-4.zip
        engine-vision-onnx-3.zip
        RESOURCE-PACKS.json

1. Đóng HaizFlow đang chạy. Chạy **file Setup**, không chạy trực tiếp các EXE
   trong thư mục build hoặc engine.
2. Cài lại vào đúng thư mục hiện có, ví dụ `D:\HaizFlow-Test\HaizFlow`.
   Bộ cài giữ nguyên thư mục `runtime` chứa dữ liệu và dự án.
3. Mở app, vào **Cài đặt → Gói tài nguyên**, chọn gói cần dùng.
   App lấy engine từ thư mục đi kèm, kiểm tra SHA-256 rồi cài vào vị trí tài
   nguyên. Các model tùy chọn vẫn tải từ nguồn model qua Internet.
4. Giữ thư mục `offline-resources` trong thời gian kiểm thử. Nếu chuyển nó,
   chạy lại Setup từ thư mục mới để cập nhật vị trí; không cần xóa dự án.

Bộ cài hiển thị dung lượng Core và khoảng trống dự phòng, không cộng các engine
tùy chọn chưa cài. App kiểm tra riêng dung lượng cần cho từng gói trước khi cài.
Các ZIP engine được đọc tại chỗ, không nhân đôi vào cache của app.

Bản này không có chữ ký Windows. SmartScreen có thể hiện nhà phát hành không
xác định; chỉ tiếp tục khi bạn biết đúng nguồn và checksum bộ cài.

Khi phát hành công khai, thay catalog nội bộ bằng URL HTTPS bất biến cùng
checksum của các engine đã hoàn tất rà soát giấy phép. Catalog offline nội bộ
không được vượt qua cổng kiểm tra public release.
