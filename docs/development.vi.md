# Hướng dẫn phát triển HaizFlow

[Tài liệu](README.vi.md) · [Kiến trúc](architecture.vi.md) · [English](development.md)

Tài liệu này quy định quy trình đóng góp cho ứng dụng Windows. Đây là phần bổ sung cho đặc tả kiến trúc, không thay thế test của từng subsystem hoặc release gate.

## 1. Môi trường hỗ trợ

- Windows 10 phiên bản 1809 trở lên hoặc Windows 11 x64;
- CPython 3.13 x64;
- PowerShell và Git;
- môi trường NVIDIA CUDA nếu cần kiểm chứng đường GPU.

Không cài dependency production tùy ý vào Python toàn cục. Repository dùng bộ dependency Windows khóa hash và kiểm tra environment thực tế.

## 2. Clone và cài đặt

```powershell
git clone https://github.com/MachHongHai/HaizFlow.git
cd HaizFlow
powershell -ExecutionPolicy Bypass -File .\scripts\install-desktop-env.ps1
```

Script kiểm tra Python, tạo `.venv`, chuyển package cache/temp vào runtime boundary, đồng bộ lock, cài editable và verify dependency/runtime.

Chỉ dùng `-Recreate` khi cần environment sạch:

```powershell
.\scripts\install-desktop-env.ps1 -Recreate
```

Script chỉ xóa `.venv` thuộc repository sau khi kiểm tra absolute path.

## 3. Giới hạn runtime

Chỉ sao chép `.env.example` thành `.env` khi cần override. Ví dụ đặt data root phát triển:

```dotenv
HAIZFLOW_HOME=D:\HaizFlowData
```

Khi có `HAIZFLOW_HOME`, model, data, cache bên thứ ba và temp đều nằm dưới root đó. Không commit `.env`, credential, model tải về, media dự án, `runtime`, `build` hoặc `dist`.

## 4. Chạy ứng dụng

```powershell
.\.venv\Scripts\python.exe .\haizflow_desktop.py
```

Launcher cấu hình đường dẫn cache/model/temp trước khi import Qt hoặc Torch. Các cờ worker nội bộ là process contract, không phải CLI cho người dùng.

Smoke test UI có giới hạn thời gian:

```powershell
.\.venv\Scripts\python.exe .\haizflow_desktop.py --ui-smoke-test
```

## 5. Cấu trúc source

```text
src/haizflow/
  core/           runtime, hardware, logging, integrity
  desktop/        Qt bootstrap, facade, controller, model, presenter
    qml/          shell, page, workspace, control, dialog
    assets/       branding và voice sample dựng sẵn
    translations/ catalog dịch Qt
  pipeline/       biến đổi media/model xác định
  schemas/        contract lưu trữ và liên tầng
  services/       use case, storage, queue, cache, integration
  utils/          helper media/process không trạng thái
  vendor/         mã tương thích đã audit
test/             unit, integration, QML creation, regression
scripts/          môi trường, audit, verify, build, release
installer/        định nghĩa Inno Setup
licenses/         notice và license bên thứ ba
docs/             tài liệu user, architecture, security, release
```

Dependency đi theo presentation → controller → service/pipeline → schema/core. Service và pipeline không được import QML.

## 6. Quy trình thay đổi

1. Xác lập hành vi hiện tại bằng test hoặc ca tái hiện.
2. Xác định đúng layer sở hữu; không vá invariant của service trong delegate QML.
3. Thêm regression test trước khi refactor rộng.
4. Thực hiện thay đổi coherent nhỏ nhất và bảo toàn dữ liệu dự án.
5. Chạy focused test khi phát triển.
6. Chạy toàn bộ gate trước review.
7. Cập nhật tài liệu khi hành vi, dữ liệu, mạng hoặc giả định release đổi.

Không trộn redesign UI, migration schema và thay thuật toán media trong một thay đổi khó review.

## 7. Quy ước Python

- Dùng type rõ cho dữ liệu lưu trữ và dữ liệu đi qua layer.
- Không chạy công việc dài trên Qt GUI thread.
- Chuyển kết quả worker về QObject thread bằng signal hoặc event queue hiện có.
- Tác vụ có cancel phải kiểm tra primitive ở khoảng thời gian hữu hạn.
- Chỉ publish file sau validation, từ staging thuộc dự án, bằng thao tác atomic.
- Giữ exception context nội bộ và hiển thị lỗi ngắn, có hành động phục hồi.
- Không thêm network fallback ngầm cho đường model local.

`qml_controller.py` là facade. Logic mới nên nằm trong controller/service chuyên trách và chỉ expose API hẹp.

## 8. Quy ước QML

- Dùng design token và Studio control chung; không tạo bảng màu hoặc nút riêng cho từng trang.
- QML sở hữu layout, focus, direct manipulation và trạng thái UI tạm; không sở hữu inference hoặc mutation filesystem.
- Khai báo type cho property khi biết type.
- Không gán vào property cần giữ binding.
- Delegate có lifecycle tái sử dụng; không phụ thuộc `Component.onCompleted` để xác định row.
- Load page nặng bằng `Loader` có guard và giải phóng media khi đóng workspace.
- Có `Accessible.name`, focus ring, tab order và Escape hợp lý.
- Giữ đúng luồng Windows IME; lưu text đã commit và không trim nội dung người dùng.
- Chuỗi hiển thị dùng `qsTr()` và catalog.

## 9. Persistence và migration

ID project/video là bất biến; display name không phải filesystem identity. Thay schema cần version mới, migration xác định, backup, default/validation, chặn schema tương lai và test trạng thái hợp lệ/hỏng/gián đoạn.

Không xóa path chỉ được suy ra từ text hiển thị. Luôn resolve và kiểm tra project ownership trước thao tác destructive.

## 10. Artifact và cache Manual

Artifact Manual được định danh theo content và config liên quan. Loại artifact mới cần signature ổn định, input/output rõ, staging và publish atomic, validation, invalidation đúng descendant, cancel, LRU/pinning và test cache hit/partial/corrupt.

Đổi setting có thể chọn variant cũ nhưng không được xóa toàn bộ lịch sử. Input và output của người dùng không phải cache disposable.

## 11. Model và provider

Model local phải khóa repository/revision, filename, size và full SHA-256. Loader chỉ nhận đường local đã verify và không tự gọi network loader không pin.

Provider online phải hiển thị rõ network use, có retry/timeout hữu hạn, phân biệt lỗi tạm với lỗi access, hỗ trợ cancel khi có thể, lưu secret bằng Windows Credential Manager và không log credential/link private.

Hành vi và license provider là một phần của integration contract.

## 12. Test

```powershell
.\scripts\test.ps1
```

Gate chạy compile Python, Ruff correctness, unit/integration và `qmllint`.

Focused test:

```powershell
$env:PYTHONPATH=(Resolve-Path .\src).Path
.\.venv\Scripts\python.exe -m unittest discover -s test -p "test_video_download.py"
```

Thay đổi hành vi cần test cả success và failure. Test concurrency phải bao gồm stale callback, cancel, shutdown và thao tác lặp. Chỉ dùng media thật khi codec behavior là đối tượng cần kiểm chứng.

## 13. Dịch và tài liệu

Tiếng Anh là bản canonical và được hiển thị trước; tiếng Việt dùng tên `.vi.md`. UI dùng catalog Qt `.ts/.qm`.

Tài liệu user nói rõ thao tác, kết quả và cách phục hồi. Tài liệu engineering nêu ownership, invariant, failure semantics và evidence. Không coi plan, số test hoặc dev artifact là tính năng sản phẩm vĩnh viễn.

## 14. Checklist an toàn

- Thay đổi có mở rộng network không?
- Có parse media, URL, archive, JSON hoặc model không tin cậy không?
- Path có thể thoát project/runtime boundary không?
- Worker cũ có thể ghi đè state mới không?
- Partial output có thể bị nhận nhầm là cache hit không?
- Log có lộ credential hoặc path riêng tư không?
- Binary/model/library mới có cần notice hoặc điều khoản phân phối khác không?

Đổi dependency/model phải đọc [an toàn dependency](dependency-security.vi.md).

## 15. Checklist pull request

- [ ] Thay đổi có một mục đích rõ.
- [ ] Dữ liệu user và thay đổi ngoài phạm vi được giữ nguyên.
- [ ] Hành vi mới có regression test.
- [ ] QML responsive và accessible.
- [ ] Dữ liệu cũ vẫn đọc được hoặc có migration đã test.
- [ ] Ảnh hưởng mạng, privacy, license và cache đã được ghi lại.
- [ ] `scripts/test.ps1` đạt.
- [ ] Không commit model, media, cache, credential hoặc build output.

Mở issue tại [MachHongHai/HaizFlow](https://github.com/MachHongHai/HaizFlow/issues) nếu cần thống nhất quyết định kiến trúc trước khi code.

## 16. Kiểm chứng đóng gói

Build chưa ký chỉ là artifact kỹ thuật nội bộ, không phải bản phát hành công khai:

```powershell
.\scripts\build-exe.ps1 -AllowDirtyBuild -AllowUnsigned
```

Bản công khai phải được tạo từ checkout đã commit sạch và ký Authenticode:

```powershell
$env:HAIZFLOW_SIGN_CERT_PASSWORD = "<mật-khẩu-certificate>"
.\scripts\build-exe.ps1 -SignCertificatePath C:\secure\haizflow-signing.pfx
.\scripts\build-installer.ps1 -SignCertificatePath C:\secure\haizflow-signing.pfx
```

Installer gate kiểm frozen artifact, tính dung lượng thật, build Inno Setup, verify checksum/chữ ký rồi thực hiện chu kỳ cài đặt, khởi động và gỡ cài đặt trong thư mục cô lập. Bỏ qua frozen smoke hoặc installer smoke chỉ dành cho chẩn đoán. Đọc [tiêu chuẩn sẵn sàng phát hành](release-readiness.vi.md) để biết điều kiện pháp lý, source sạch và ma trận nghiệm thu Windows.
