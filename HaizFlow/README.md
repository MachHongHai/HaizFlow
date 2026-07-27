# HaizFlow

HaizFlow là ứng dụng Windows local-first để tạo phụ đề, dịch và lồng tiếng video. Giao diện dùng PySide6/QML; pipeline chạy WhisperX, HY-MT2, Edge TTS, Demucs và FFmpeg.

## Đặc tính chính

- Project đơn và batch, nhập video local hoặc từ URL/kênh được hỗ trợ.
- Nhận dạng giọng nói và dịch chạy local bằng model đã khóa revision/checksum.
- Cho phép duyệt bản dịch, chỉnh khung phụ đề, chọn giọng đọc và giữ/xóa background.
- Pause, resume, recovery và shutdown có kiểm soát.
- Installer cho phép chọn thư mục trên ổ local. Trong frozen build, toàn bộ dữ liệu mutable nằm dưới `<thư-mục-cài>\runtime`. Model không nằm trong installer: lần chạy đầu có giao diện tải model đã khóa checksum vào `<thư-mục-cài>\runtime\models`.
- Khi model đã tải và xác minh xong, các lần mở sau bỏ qua màn hình cài model và chỉ load/warm model local ở nền. Màn hình tải chỉ xuất hiện lại nếu user đổi sang backend CPU/GPU chưa có hoặc file model bị thiếu/hỏng.

Edge TTS là dịch vụ mạng: văn bản phụ đề đã dịch được gửi tới dịch vụ để tổng hợp giọng nói. Nhập URL/kênh cũng kết nối tới nền tảng tương ứng. Media, WhisperX, HY-MT2, Demucs và FFmpeg chạy local.

## Chạy source trên Windows

Yêu cầu: Windows 10 1809 trở lên, Python 3.13 x64, Git và `uv`.

```powershell
.\scripts\install-desktop-env.ps1
.\scripts\run-desktop.ps1
```

Mặc định source mode lưu dữ liệu dưới `runtime\`. Có thể đặt `HAIZFLOW_HOME` trong `.env` để chuyển toàn bộ runtime/model/cache sang một thư mục khác. Xem [.env.example](.env.example).

## Kiểm thử

```powershell
.\scripts\test.ps1
.venv\Scripts\python.exe .\scripts\verify-runtime.py --for-build
.\scripts\audit-dependencies.ps1
```

`test.ps1` chạy compile, unit/integration test và `qmllint`. Runtime gate kiểm đúng dependency lock, model, CUDA/CPU, Qt và FFmpeg. Dependency audit chỉ bỏ qua các advisory có threat model cụ thể trong [docs/dependency-security.md](docs/dependency-security.md); advisory mới sẽ làm gate thất bại.

## Build EXE và installer

Build frozen artifact không chứa model:

```powershell
.\scripts\build-exe.ps1
```

Build installer bằng Inno Setup 6:

```powershell
.\scripts\build-installer.ps1
```

Release build chỉ được chạy từ worktree sạch. `build-exe.ps1` chạy test, QML lint, runtime/dependency/compliance gate, frozen smoke test, sau đó mới tạo `BUILD-INFO.json` và `SHA256SUMS.txt`. `build-installer.ps1` xác minh lại commit, build ID, checksum và xác nhận artifact không vô tình chứa model trước khi đóng gói.

Không dùng `-AllowDirtyBuild` hoặc `-SkipFrozenSmokeTest` cho artifact phát hành. Bản public cần ký Authenticode và hoàn thành các gate pháp lý/phần cứng ghi tại [docs/release-readiness.md](docs/release-readiness.md).

## Cấu trúc

```text
src/haizflow/core/       đường dẫn, phần cứng, log, integrity và diagnostics
src/haizflow/desktop/    QML facade, controller theo workflow và list model
src/haizflow/pipeline/   các stage media/subtitle/TTS/render
src/haizflow/services/   project/video store, queue, import và translation worker
src/haizflow/schemas/    schema metadata có version/migration
src/haizflow/desktop/qml giao diện Qt Quick
scripts/                 test, runtime verification và release tooling
installer/               định nghĩa Inno Setup
test/                    unit/integration/release regression
```

Thiết kế chi tiết nằm trong [docs/architecture.md](docs/architecture.md).

## License

Source HaizFlow dùng Apache License 2.0. Dependency, model và binary đi kèm giữ license riêng; xem [NOTICE](NOTICE), `licenses/` và third-party notices được sinh trong artifact.
