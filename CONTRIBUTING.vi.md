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

Người đóng góp giữ quyền tác giả; gửi pull request không phải chuyển nhượng
bản quyền. Giấy phép hạn chế mới chưa có hiệu lực. Trước khi đưa đóng góp vào
bản phát hành theo giấy phép mới, maintainer phải có quyền phù hợp cho đúng
phạm vi hoặc giữ phần đó theo giấy phép riêng. [Thỏa thuận đóng góp dự thảo](legal/CONTRIBUTOR-PERMISSION-DRAFT.md)
chỉ áp dụng khi đã được duyệt và người đóng góp đồng ý rõ ràng, không ràng buộc
người đóng góp trước đây. Hãy khai báo mã bên thứ ba và giữ thông báo của họ.
Báo lỗi cần bước tái hiện; đề xuất tính năng nên thống nhất phạm vi trước khi
sửa rộng. Review bao gồm hành vi, kiểm thử, quyền riêng tư, dữ liệu và giấy phép.
