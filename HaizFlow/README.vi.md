# HaizFlow

**Công cụ mã nguồn mở xử lí và reup video hàng loạt, chạy local — không tốn phí API.**

[English](README.md) · [Repository](https://github.com/MachHongHai/HaizFlow) · [Báo lỗi](https://github.com/MachHongHai/HaizFlow/issues) · [Giấy phép](LICENSE)

HaizFlow là ứng dụng desktop giúp tải media công khai, dịch và lồng tiếng video, xử lí phụ đề và xuất video hoàn chỉnh trong cùng một quy trình. Ứng dụng được thiết kế để dễ dùng: tạo dự án, chọn nguồn và thiết lập, sau đó theo dõi tiến độ rõ ràng ngay trên giao diện.

> [!NOTE]
> HaizFlow đang được phát triển tích cực. Hãy tuân thủ điều khoản của từng nền tảng nguồn và chỉ tải, xử lí, xuất bản nội dung mà bạn có quyền sử dụng.

## Điểm nổi bật

- **Giao diện desktop dễ sử dụng** — có không gian riêng cho dự án đơn lẻ, hàng loạt và tải xuống; điều hướng nhất quán, thao tác rõ ràng, tiến độ trực tiếp và khả năng khôi phục công việc.
- **Quản lí theo dự án** — video nguồn, thiết lập, đầu ra, log và dữ liệu khôi phục được đặt cùng một nơi, tách biệt giữa các dự án.
- **Sẵn sàng cho hàng loạt** — xếp hàng và quản lí nhiều video; trạng thái dự án vẫn được giữ khi quay lại ứng dụng.
- **Tải media** — tải video công khai hoặc video từ kênh, đồng thời tải hay trích âm thanh vào thư mục đầu ra bạn chọn.
- **Dịch, lồng tiếng và phụ đề** — nhận dạng giọng nói, dịch, tổng hợp giọng đọc, chèn phụ đề và xuất video trong một pipeline.
- **Thay phụ đề gốc tốt hơn** — tự nhận diện vùng phụ đề cứng có độ tin cậy cao, làm mờ vùng đó trước khi đặt phụ đề mới. Video không có phụ đề gốc sẽ dùng bố cục phụ đề mặc định.
- **Kiểm soát phối âm** — giữ âm thanh gốc hoặc tách giọng, thêm nhạc nền từ tệp/liên kết và nghe thử trước khi xử lí.
- **Local-first** — xử lí media, nhận dạng, model dịch, tách giọng và render chạy trên máy. Model chỉ được tải và kiểm tra ở lần mở đầu tiên cần dùng, sau đó được tái sử dụng.

## Phần nào chạy local?

HaizFlow dùng các thành phần local như WhisperX, HY-MT2, Demucs, OCR và FFmpeg trong pipeline. Việc nhập liên kết công khai cần kết nối đến nền tảng tương ứng. Edge TTS mặc định là dịch vụ trực tuyến, nên văn bản được gửi đến dịch vụ này khi tổng hợp giọng nói.

## Cài đặt

### Installer Windows

Khi đã có bản phát hành, tải installer ở [Releases](https://github.com/MachHongHai/HaizFlow/releases), chọn thư mục cài đặt và mở HaizFlow. Installer không nhúng các model lớn. Ở lần mở đầu tiên cần model, ứng dụng sẽ hiển thị tiến độ tải và kiểm tra file trước khi dùng.

### Chạy từ source

Yêu cầu: Windows 10 (1809+) trở lên, Python 3.11–3.13 x64, Git và `uv`.

```powershell
git clone https://github.com/MachHongHai/HaizFlow.git
cd HaizFlow
.\scripts\install-desktop-env.ps1
.\scripts\run-desktop.ps1
```

Mặc định source mode lưu dữ liệu runtime tại `runtime\`. Đặt `HAIZFLOW_HOME` trong `.env` nếu muốn chuyển toàn bộ model, project, cache và log sang thư mục khác; xem [.env.example](.env.example).

## Quy trình cơ bản

1. Tạo dự án **Đơn lẻ**, **Hàng loạt** hoặc **Tải xuống**.
2. Thêm tệp từ máy, dán liên kết công khai hoặc chọn kênh/hồ sơ công khai.
3. Chọn ngôn ngữ đích, giọng đọc, cách xử lí âm thanh, nhạc nền (nếu cần) và thư mục đầu ra.
4. Bắt đầu xử lí, theo dõi trạng thái, log và đầu ra trong trang dự án.
5. Mở video xuất hoặc thư mục đầu ra khi hoàn tất.

## Phát triển

Chạy các kiểm tra chất lượng trước khi gửi thay đổi:

```powershell
.\scripts\test.ps1
.venv\Scripts\python.exe .\scripts\verify-runtime.py --for-build
.\scripts\audit-dependencies.ps1
```

Build EXE và installer Windows tại máy:

```powershell
.\scripts\build-exe.ps1
.\scripts\build-installer.ps1
```

Release build kiểm tra test, QML, runtime dependency, compliance, frozen-app smoke test và checksum artifact. Xem [release readiness](docs/release-readiness.md) để biết checklist phát hành hiện tại.

## Cấu trúc dự án

```text
src/haizflow/core/       đường dẫn, diagnostics, integrity và phần cứng
src/haizflow/desktop/    controller PySide6 và lớp trình bày desktop
src/haizflow/desktop/qml giao diện Qt Quick
src/haizflow/pipeline/   nhận dạng, dịch, lồng tiếng, phụ đề và render
src/haizflow/services/   project, import/tải media, queue và lưu trữ
src/haizflow/schemas/    schema metadata có version và migration
scripts/                 setup, test, xác minh và build tooling
installer/               định nghĩa installer Windows
test/                    test unit, integration, UI và regression release
```

Chi tiết kiến trúc: [docs/architecture.md](docs/architecture.md).

## Đóng góp

Mọi đóng góp, báo lỗi và góp ý UX đều được chào đón. Với thay đổi lớn, hãy mở [issue](https://github.com/MachHongHai/HaizFlow/issues) trước để cùng trao đổi hướng triển khai.

## Tác giả và liên hệ

Dự án được tạo bởi **Mạch Hồng Hải**.

- GitHub: [MachHongHai](https://github.com/MachHongHai)
- Email: machhonghaipr@gmail.com

## Giấy phép

Source HaizFlow dùng [Apache License 2.0](LICENSE). Dependency, model và binary bên thứ ba giữ giấy phép riêng; xem [NOTICE](NOTICE) và `licenses/`.
