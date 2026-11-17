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

Trong **Cài đặt → API Key**, kiểm tra key đã được dán đầy đủ và chọn **Sử dụng** ở tài khoản muốn dùng. Mỗi nhà cung cấp chọn key tại đây; model dịch chọn trong dự án. **Kiểm tra kết nối** liên hệ lại dịch vụ, nhưng thành công không bảo đảm model luôn sẵn sàng hoặc tài khoản còn tiền. Xem [hướng dẫn API](translation-api.vi.md).

Key nằm trong Windows Credential Manager của tài khoản Windows đang dùng. Khi đổi máy hoặc tài khoản Windows, thêm lại key. Không gửi key trong ảnh, log hoặc yêu cầu hỗ trợ.

## Âm thanh và xem trước

Kiểm tra các track nguồn, giọng đọc và nhạc nền trên timeline. Bật track cần nghe, điều chỉnh âm lượng và tránh phát đồng thời lời gốc với giọng lồng tiếng khi không cần.

Chọn font đi kèm qua mẫu xem trước; tiếng Trung, Nhật, Hàn có font dự phòng phù hợp. Xem lại vị trí, kích thước và vùng chữ ở vài thời điểm. Khi chỉ cần sửa một vài đoạn giọng, chọn các câu đó trong phạm vi tạo giọng của Thủ công, không cần tạo lại cả video.

## Bộ nhớ và dung lượng

Nếu model GPU không khả dụng, kiểm tra driver NVIDIA và gói tài nguyên tương ứng. Chọn model nhỏ hơn được hỗ trợ khi cần; có GPU tương thích không có nghĩa mọi model đều vừa bộ nhớ.

Với thông báo thiếu RAM/VRAM, đóng ứng dụng khác hoặc chọn model nhỏ hơn, phù hợp với máy. Có thể tắt **Giữ model sẵn sàng** để giải phóng model giữa các lượt xử lý; tùy chọn này giảm thời gian nạp lại, không làm tăng bộ nhớ máy.

Đủ RAM lắp đặt không có nghĩa luôn đủ bộ nhớ trống ở thời điểm chạy. Khi app yêu cầu thêm bộ nhớ, giải phóng tài nguyên hoặc chọn model nhỏ hơn rồi tiếp tục từ kết quả đã lưu còn hợp lệ.

OmniVoice CPU có thể mất vài phút cho một câu dài. Nếu thấy tiến trình đứng lâu, mở **Chi tiết** để xem log trước khi chạy lại. Muốn tạo giọng nhanh hơn, chọn GPU tương thích và bảo đảm đủ bộ nhớ trống.

Chuyển tài nguyên bằng **Chuyển vị trí** trong Gói tài nguyên. Đợi thao tác hoàn tất và giữ bản sao video nguồn, video xuất quan trọng. Không xóa thủ công thư mục dự án hoặc gói đang được dùng.

## Kết nối MCP

Giữ HaizFlow mở và bật **Cài đặt → MCP**. **Kiểm tra HaizFlow** kiểm tra phía app; sau đó gửi câu lệnh thử từ agent. Nếu vừa di chuyển hoặc cập nhật app, sao chép lại thông tin kết nối hiện tại. Không dùng lệnh mở giao diện thông thường làm lệnh máy chủ MCP. Xem [hướng dẫn MCP](mcp.vi.md).

## Thông báo lỗi

Đọc phần tóm tắt trước. **Chi tiết** mở log kỹ thuật; **Xác nhận** hoặc nút đóng sẽ bỏ thông báo. Menu **…** của dự án cũng có log kỹ thuật. Khi báo lỗi, chỉ gửi đoạn liên quan và che thông tin riêng tư.

## Bộ cài và Windows

Bộ cài hiện không ký số. Windows có thể hiển thị nhà phát hành không xác định hoặc áp dụng chính sách chặn ứng dụng chưa ký. Kiểm tra nguồn tải chính thức và SHA-256; không tắt antivirus hoặc thêm ngoại lệ rộng. Với máy do cơ quan quản lý, liên hệ người quản lý máy.

## Liên hệ hỗ trợ

Tạo yêu cầu tại [GitHub Issues](https://github.com/MachHongHai/HaizFlow/issues), kèm:

1. Phiên bản HaizFlow và Windows.
2. Các bước thực hiện và tên công cụ/model.
3. Ảnh thông báo hoặc log liên quan đã che thông tin riêng tư.
4. Chế độ CPU/GPU và tình trạng gói tài nguyên.

Không gửi API key, cookie, thông tin tài khoản hoặc video riêng tư. Chỉ chia sẻ media bạn có quyền cung cấp.
