# Tài liệu HaizFlow

[English](README.md) · [Tiếng Việt](README.vi.md) · [Trang chính repository](../README.vi.md)

Tài liệu được chia theo đối tượng đọc. Hướng dẫn người dùng tập trung vào thao tác và kết quả nhìn thấy; tài liệu kỹ thuật xác định invariant, ranh giới và yêu cầu kiểm chứng.

| Bắt đầu tại đây | Dành cho | Phạm vi |
| --- | --- | --- |
| [Hướng dẫn sử dụng](user-guide.vi.md) | Người dùng và tester | Cài đặt, các loại dự án, chỉnh sửa, lưu trữ và xử lý lỗi. |
| [Kiến trúc](architecture.vi.md) | Kỹ sư | Component, mô hình dữ liệu, dependency, worker, cache và ranh giới an toàn. |
| [Hướng dẫn phát triển](development.vi.md) | Người đóng góp | Môi trường tái lập, test, quy ước QML/Python và pull request. |
| [Trạng thái kỹ thuật Manual editor](manual-editor-stabilization.vi.md) | Maintainer | Phần đã triển khai, nghiệm thu còn lại và trọng tâm regression. |
| [An toàn dependency](dependency-security.vi.md) | Người duyệt security | Chính sách audit, dependency đã khóa, ngoại lệ và giảm thiểu. |
| [Sẵn sàng phát hành](release-readiness.vi.md) | Người phát hành | Điều kiện pháp lý, build, installer và production. |

## Quy ước tài liệu

- Tiếng Anh là bản canonical được hiển thị trước; mỗi tài liệu có bản `.vi.md` tương ứng.
- Không dịch command, path, option, schema field và mã lỗi.
- Hướng dẫn người dùng dùng câu trực tiếp, nói rõ thao tác và kết quả.
- Tài liệu kỹ thuật dùng thuật ngữ chính xác, tách biệt hành vi đã kiểm chứng với giả định hoặc công việc dự kiến.
- Số lượng test và kích thước artifact không được coi là thông tin sản phẩm vĩnh viễn; bằng chứng release nằm trong build metadata.
- Ranh giới mạng, quyền riêng tư, giấy phép model và giới hạn tương thích phải xuất hiện tại nơi chúng ảnh hưởng tới quyết định.

Nếu thấy tài liệu sai hoặc thiếu, hãy mở [GitHub issue](https://github.com/MachHongHai/HaizFlow/issues).
