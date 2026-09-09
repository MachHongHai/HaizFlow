# Đóng góp cho HaizFlow

[English](CONTRIBUTING.md) · [Hướng dẫn phát triển](docs/development.vi.md) · [Kiến trúc](docs/architecture.vi.md)

HaizFlow chào đón issue rõ ràng và pull request có phạm vi cụ thể. Trước khi sửa, hãy tìm issue hiện có rồi mô tả lỗi người dùng nhìn thấy, kết quả mong muốn và phạm vi thay đổi.

## Quy trình phát triển

1. Tạo branch từ default branch hiện tại.
2. Cài đúng môi trường Windows bằng `scripts/install-desktop-env.ps1`.
3. Thêm regression test nếu thay đổi hành vi.
4. Giữ network access, dữ liệu bền vững, cache signature và thao tác xóa ở trạng thái tường minh.
5. Chạy `scripts/test.ps1` trước khi mở pull request.
6. Cập nhật cả tài liệu tiếng Anh và tiếng Việt nếu hành vi người dùng thay đổi.

Không commit model, media dự án, runtime data, credential, build output hoặc log riêng tư. Khi gửi đóng góp, bạn đồng ý nội dung có thể được phân phối theo giấy phép Apache-2.0 của repository.

Đọc [hướng dẫn phát triển](docs/development.vi.md) và [tiêu chuẩn phát hành](docs/release-readiness.vi.md) để biết quy ước triển khai và gate kiểm tra.
