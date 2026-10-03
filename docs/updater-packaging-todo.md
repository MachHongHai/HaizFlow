# Launcher/Updater packaging — chưa thực hiện

1. Đóng gói ba executable độc lập bằng Python runtime riêng của từng onedir:
   root HaizFlow.exe launcher, updater/HaizFlowUpdater.exe, versions/<version>/HaizFlowCore.exe.
   Không dựa vào Python có sẵn trong máy user hoặc import code từ Core đang hỏng.
2. Entry points source: scripts/haizflow-launcher.py, scripts/haizflow-updater.py;
   cần Windows GUI wrapper hiển thị friendly recovery error (source hiện stderr).
   Launcher frozen suy root từ executable; updater nhận root/request token từ Core.
3. Build Core bằng tooling riêng có tên HaizFlowCore; tạo full manifest/package
   với make-delta.py; stage initial Core bằng reconstruct; provision marker rồi
   Layout.seed chỉ sau verify. Không rename dist/HaizFlow đang có rồi giả vờ đã build.
4. Installer tương lai dùng shortcut vào launcher, không Core. Thay CloseApplications
   filter và ownership delete rules theo versions/updater, giữ runtime. Đánh giá
   explicit migration flat install sang versioned layout và quyền uninstall.
   Các Inno/release scripts cũ đang giữ nguyên signing gates; quyết định chính sách
   unsigned packaging và legal release review ở một change riêng, không xóa gate.
5. Tạo full + delta từ hai verified Core builds; thêm assets .zip/.manifest.json
   đúng tên vào release stable, chờ GitHub API có digest. Không publish từ script này.
6. Kiểm thử health PID thực PyInstaller, Python/PySide/QML initialization failure,
   chậm startup, normal quit/crash sau ack, old-launcher handoff, AV/permission locks,
   power-loss recovery, đĩa đầy, missing launcher/updater và concurrent instances.
7. Kiểm thử runtime/resource root cũ/mới và project ngoài install giữ nguyên.
   Kiểm chứng migration barriers trước mọi schema change. Fixture không thay kiểm
   thử user data copies trên frozen build.
8. Kiểm thử real GitHub downloads/redirects, offline/rate-limit/404, full fallback,
   missing digest fail-closed; cân nhắc bật Immutable Releases (không bắt buộc).
9. Bootstrap self-update không thuộc Core update; cần upgrade riêng/installer.
   Không overwrite launcher hoặc updater đang chạy. Giữ bootstrap recovery.
10. Hoàn tất review giấy phép thành phần, OmniVoice model NC, FFmpeg corresponding
    source và Qt LGPL evidence trước public release. Active app license không xóa
    các obligations này.

Chưa build installer, chưa tạo exe mới, chưa triển khai cập nhật máy thật.
