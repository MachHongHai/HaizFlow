# Trợ giúp HaizFlow

[Trang chính](../README.vi.md) · [Cài đặt](install.vi.md) · [Sử dụng](user-guide.vi.md) · [English](support.md)

## Gói tài nguyên

Chọn **Cài đặt → Gói tài nguyên** để cài, kiểm tra hoặc gỡ gói. Chế độ CPU/GPU trong **Cài đặt → Chung** quyết định gói dùng khi xử lý.

- Với thông báo thiếu gói, cài gói được nêu trong thông báo, rồi chạy lại công cụ.
- Với gói đã cài, dùng **… → Kiểm tra và sửa** để kiểm tra các tệp và môi trường xử lý.
- Dùng **Tạm dừng/Tiếp tục** để quản lý lượt tải. Phần tải hợp lệ được giữ lại.
- Để cài lại từ đầu, chọn **Gỡ gói**, sau đó **Cài đặt**.

Tài nguyên dùng chung có thể đã được cung cấp bởi gói khác. **Đã cài** thể hiện tài nguyên đang sẵn sàng, không phải số lần bạn tải riêng một gói. Không tự xóa tệp bên trong các gói.

## API key

Trong **Cài đặt → API Key**, kiểm tra key đã được dán đầy đủ và chọn đúng tài khoản. Với Zernio, chấm đỏ nghĩa là kiểm tra chưa thành công: xem lại key, quyền truy cập và kết nối mạng, rồi kiểm tra lại.

Key nằm trong Windows Credential Manager của tài khoản Windows đang dùng. Khi đổi máy hoặc tài khoản Windows, thêm lại key. Không gửi key trong ảnh, log hoặc yêu cầu hỗ trợ.

## Âm thanh và xem trước

Kiểm tra các track nguồn, giọng đọc và nhạc nền trên timeline. Bật track cần nghe, điều chỉnh âm lượng và tránh phát đồng thời lời gốc với giọng lồng tiếng khi không cần.

Phụ đề dùng Bangers đi kèm ứng dụng. Xem lại vị trí, kích thước và vùng hiển thị ở vài thời điểm trong video.

## Bộ nhớ và dung lượng

Whisper tự chọn kiểu tính toán theo khả năng CTranslate2 của GPU: GPU hỗ trợ FP16 vẫn dùng FP16; GPU đời cũ như GTX 1070 dùng INT8/FP32 khi backend hỗ trợ. Không đổi checkpoint hoặc ép toàn bộ máy sang CPU. Kiểu tính toán thực tế được ghi trong log nhận dạng. Driver và môi trường GPU vẫn cần tương thích; chế độ tương thích không bảo đảm mọi model đều vừa VRAM.

Với thông báo thiếu RAM/VRAM, đóng ứng dụng khác hoặc chọn model nhỏ hơn, phù hợp với máy. Có thể tắt **Giữ model sẵn sàng** để giải phóng model giữa các lượt xử lý; tùy chọn này giảm thời gian nạp lại, không làm tăng bộ nhớ máy.

RAM lắp đặt quyết định máy có đạt cấu hình CPU tối thiểu; RAM còn trống và bộ nhớ Windows còn cấp phát được quyết định có thể nạp model ngay lúc đó hay không. Khi chuyển sang HY-MT2 CPU, ứng dụng giải phóng các runtime warm-up không còn cần và đo lại bộ nhớ trong tối đa 2 giây nếu thiếu tài nguyên. Nếu vẫn thiếu, ứng dụng giữ kết quả đã hoàn thành và dừng an toàn, không bỏ kiểm tra bộ nhớ.

OmniVoice CPU có thể mất vài phút cho một câu dài; phần trăm hoàn thành chỉ tăng khi đã có âm thanh hợp lệ. Log `decoder_forwards` ghi nhận lượt suy luận thực để phân biệt đang tính toán với worker không tiến triển. Không giảm precision hay số bước suy luận để tăng tốc. Phục hồi GPU → CPU chỉ thay backend cho lượt đang phục hồi; không ghi đè lựa chọn model đã lưu hoặc bỏ checkpoint còn hợp lệ.

Chuyển tài nguyên bằng **Chuyển vị trí** trong Gói tài nguyên. Đợi thao tác hoàn tất và giữ bản sao video nguồn, video xuất quan trọng. Không xóa thủ công thư mục dự án hoặc gói đang được dùng.

## Bộ cài và Windows

Bộ cài hiện không ký số. Windows có thể hiển thị nhà phát hành không xác định hoặc áp dụng chính sách chặn ứng dụng chưa ký. Kiểm tra nguồn tải chính thức và SHA-256; không tắt antivirus hoặc thêm ngoại lệ rộng. Với máy do cơ quan quản lý, liên hệ người quản lý máy.

## Liên hệ hỗ trợ

Tạo yêu cầu tại [GitHub Issues](https://github.com/MachHongHai/HaizFlow/issues), kèm:

1. Phiên bản HaizFlow và Windows.
2. Các bước thực hiện và tên công cụ/model.
3. Ảnh thông báo hoặc log liên quan đã che thông tin riêng tư.
4. Chế độ CPU/GPU và tình trạng gói tài nguyên.

Không gửi API key, cookie, thông tin tài khoản hoặc video riêng tư. Chỉ chia sẻ media bạn có quyền cung cấp.
