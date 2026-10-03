# Báo cáo triển khai — 01/10/2026

Trạng thái: nền tảng source đã triển khai và kiểm thử; **chưa sẵn sàng phát hành updater dạng frozen**. Không build installer, không ký, không tạo release, không commit hoặc push.

## 24 điểm bàn giao

1. Giấy phép chính tại `LICENSE` đã chuyển sang `LicenseRef-HaizFlow-Source-Available-1.0`, tiếng Việt trước tiếng Anh theo phê duyệt chủ sở hữu.
2. `NOTICE` ghi Mạch Hồng Hải là tác giả HaizFlow; thông báo độc lập của thành phần bên thứ ba vẫn được bảo toàn.
3. README, metadata, hồ sơ pháp lý và kiểm tra hash giấy phép đã đồng bộ; các bản dự thảo được giữ với trạng thái lịch sử, không có hiệu lực.
4. About không còn đoạn khởi tạo, giấy phép và bên thứ ba; cửa sổ Bản quyền riêng có trong Cài đặt và menu `?`.
5. Bootstrap chỉ dùng thư viện chuẩn Python; không import Qt hoặc thư viện AI.
6. Core đặt trong `versions/<version>`; runtime được giữ ngoài Core, tại `runtime`. Không tự chuyển bản cài cũ sang layout mới.
7. Marker layout bắt buộc, tránh nhận nhầm thư mục hoặc cập nhật nhầm runtime.
8. Nguồn tải cố định là public release của `MachHongHai/HaizFlow`; không PAT hoặc cấu hình nguồn tùy ý.
9. HTTPS, redirect và đường dẫn asset được giới hạn; digest và kích thước được kiểm tra trước sử dụng.
10. Không Authenticode, Ed25519, RSA hoặc key ký. SHA-256 bảo vệ tính toàn vẹn, **không chứng minh danh tính nhà phát hành** nếu nguồn phát hành bị chiếm quyền.
11. Manifest schema nghiêm ngặt: sản phẩm, phiên bản, nền tảng, kiến trúc, inventory, added/changed/removed, hash, kích thước và tương thích dữ liệu.
12. Delta ở mức tệp: chỉ đóng gói tệp mới/thay đổi, dựng Core mới bằng tệp không đổi từ base đã xác minh. Không hard-link hoặc sửa Core đang chạy.
13. Full fallback dùng khi không có delta phù hợp, delta quá lớn hoặc base không hợp lệ. Metadata hỏng không được bỏ qua để hạ mức kiểm tra.
14. Staging được dựng, kiểm tra toàn cây rồi mới promote sang thư mục version hoàn chỉnh; tệp completion marker không thay thế kiểm tra hash.
15. Chặn traversal, Windows device names, drive/UNC, đường dẫn xung đột, symlink/junction/reparse point và ZIP entry ngoài inventory.
16. Preflight dung lượng và giới hạn manifest/ZIP/inventory giúp chặn dữ liệu quá lớn; ghi JSON và package có fsync/replace.
17. Kernel lock tách launcher/update/updater; journal lưu trạng thái chuyển tiếp để phục hồi sau gián đoạn, không đoán version bằng cách quét thư mục.
18. Chỉ chuyển active pointer sau khi user đồng ý khởi động lại và Core cũ thực sự thoát. Không kill Core cũ hoặc tác vụ của user.
19. Health acknowledgment có nonce, version và PID; chỉ gửi sau khi Python/PySide/QML đã sẵn sàng. Tạo process thành công không được coi là healthy.
20. Core mới không healthy được rollback tối đa một lần về known-good. Nếu Core chưa đóng được, không rollback hoặc mở thêm Core. Crash sau confirmation không tự rollback.
21. Runtime/models/settings và dự án bên ngoài không bị thay thế; cleanup version chỉ thực hiện rõ ràng, giữ active/previous/known-good/pending/running.
22. UI có preparing/ready/restarting/updated/rolled-back; download có thể chuẩn bị riêng, nhưng restart bị chặn khi còn công việc. Bản cài legacy giữ cơ chế installer cũ.
23. Kiểm thử dùng Core giả chạy bằng Python, fixture ZIP và mạng mock; bao phủ healthy/failure/timeout, corruption, gián đoạn, recovery, concurrency, path attacks và bảo toàn dữ liệu. Chưa kiểm chứng exe frozen, antivirus/file lock thực tế hoặc nâng cấp trên máy sạch.
24. Các bước đóng gói, provisioning, kiểm thử frozen và giới hạn phát hành được ghi riêng trong `updater-packaging-todo.md`. Nghĩa vụ model OmniVoice, FFmpeg, Qt và phạm vi quyền nguồn vẫn cần rà soát trước phát hành công khai.

## Tệp tạo mới

- `src/haizflow/update/`: `__init__.py`, `filesystem.py`, `manifest.py`, `packages.py`, `state.py`, `network.py`, `launcher.py`, `updater.py`.
- `scripts/`: `make-delta.py`, `haizflow-launcher.py`, `haizflow-updater.py`.
- `src/haizflow/desktop/qml/CopyrightDialog.qml`.
- `tests/test_delta_update.py`, `tests/qml/tst_AppUpdatePopup_2.qml`, `tests/qml/tst_CopyrightDialog.qml`.
- `docs/updater-packaging-todo.md` và báo cáo này.

## Nhóm tệp đã sửa

- Pháp lý/metadata: LICENSE, NOTICE, CONTRIBUTING (Anh/Việt), README (Anh/Việt), pyproject.toml, dependency-lock-manifest.json, legal/license-state.json, legal/rights-inventory.json, hai bản dự thảo, scripts/verify-legal-state.py.
- Tài liệu: docs/licensing-review.md, docs/release-readiness.md và bản Việt, docs/updates.md.
- Runtime/UI: core/paths.py, desktop/main.py, desktop/app_update_controller.py, AboutDialog.qml, AppMenuBar.qml, AppUpdatePopup.qml, Main.qml và catalog Anh TS/QM.
- Test hiện có: test_legal_state.py, test_portable_paths.py, test_qml_menu.py, test_ui_foundation.py, tst_AppUpdatePopup.qml.

## Kết quả xác minh

- Lượt cuối sau kiểm tra an toàn: 1.041 test Python và 121 subtest qua (155,43 giây); 60 test Qt Quick qua, không fail/skip. Test riêng delta có 37 test và 25 subtest qua.
- Python correctness lint, QML lint, dependency lock và giấy phép nội bộ qua; catalog Anh có 999 bản dịch, không còn mục unfinished.
- About/Bản quyền được render và kiểm tra bố cục bằng ảnh. Có cảnh báo TorchCodec đã tồn tại từ trước.
- Public release gate còn chặn có chủ đích bởi các mục quyền nguồn/model/FFmpeg/Qt; phê duyệt giấy phép app không tự hoàn thành các nghĩa vụ này.
- Git snapshot trước báo cáo và test an toàn cuối: 31 tệp tracked thay đổi (896 dòng thêm, 482 dòng xóa), các tệp mới chưa tracked; không staged. Các con số diff này không tính nội dung tệp mới.

Xem `updates.md` để biết giao thức chi tiết. Không coi các test fixture là chứng nhận sẵn sàng production.
