# Publishing HaizFlow updates

HaizFlow checks the latest stable release published in the official GitHub repository. The check runs after the Home screen is responsive and can also be started from **Settings → Update HaizFlow**. It never downloads or runs an installer without the user's action.

## Publish a version

1. Update the version in `pyproject.toml` using `MAJOR.MINOR.PATCH` format.
2. Run the release checks and build the signed Core installer.
3. Create a Git tag with the same version, prefixed with `v` (for example, `v0.2.0`).
4. Create a draft GitHub Release from that tag.
5. Attach the Authenticode-signed installer, its SHA-256 checksum and the release manifest.
6. Write short release notes describing user-visible changes and known limitations.
7. Publish the release after every asset has been uploaded and verified.

The app uses GitHub's `releases/latest` endpoint, which ignores drafts and pre-releases. Publishing a stable release therefore makes it visible to installed copies of HaizFlow. Users are taken to the release page and choose the installer themselves.

Do not add silent self-installation until the updater can validate a signed manifest, the installer checksum and its Authenticode signature in a separate updater process. Opening the official release page is the safer first release path and works without a background update service.

## Phát hành bản cập nhật HaizFlow

HaizFlow kiểm tra bản stable mới nhất trên repository GitHub chính thức. Việc kiểm tra diễn ra sau khi màn hình Trang chủ đã phản hồi ổn định; người dùng cũng có thể chủ động kiểm tra tại **Cài đặt → Cập nhật HaizFlow**. Ứng dụng không tự tải hoặc chạy bộ cài.

1. Tăng version trong `pyproject.toml` theo dạng `MAJOR.MINOR.PATCH`.
2. Chạy kiểm tra phát hành và tạo bộ cài Core đã ký.
3. Tạo Git tag cùng version, thêm tiền tố `v`, ví dụ `v0.2.0`.
4. Tạo GitHub Release ở trạng thái draft từ tag đó.
5. Đính kèm bộ cài đã ký Authenticode, checksum SHA-256 và release manifest.
6. Viết release notes ngắn, tập trung vào thay đổi người dùng nhìn thấy và giới hạn còn lại.
7. Chỉ publish sau khi toàn bộ asset đã được tải lên và kiểm tra.

Endpoint `releases/latest` không trả về draft hoặc pre-release. Vì vậy, chỉ bản stable đã publish mới xuất hiện trong ứng dụng. Người dùng được đưa tới đúng trang phát hành và tự quyết định tải bộ cài.
