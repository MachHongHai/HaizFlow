# Cập nhật Core vi sai

## Trạng thái

Đã có file-level delta/full builder, manifest validation, downloader GitHub,
staging, journal/pointer, independent launcher/updater Python entrypoints,
health acknowledgment sau khi QML sẵn sàng, rollback và tích hợp controller/UI.
Đã đóng gói Launcher/Updater/Core frozen và tích hợp installer engineering.
Kiểm thử delta cục bộ bằng Core/launcher thật xác nhận dựng inventory đúng,
health và rollback khi Core mới không khởi động; dữ liệu fixture được giữ nguyên.
Phiên bản trong kiểm thử là giả lập, chưa thử download/update qua release public.
**Chưa production-ready:** còn tài nguyên AI, review giấy phép và Windows
acceptance. Chủ dự án đã chọn phát hành unsigned, không cần chứng chỉ. Xem [phát hành miễn phí](windows-release-setup.vi.md) và
[báo cáo installer](installer-build-report-2026-10-04.vi.md).

Legacy flat install tiếp tục cơ chế bộ cài đã có. Chế độ public unsigned phải chọn rõ `UnsignedRelease`; không bỏ gate giấy phép/tài nguyên/provenance.
Chỉ installation được provision rõ bằng update-layout.json dùng delta; không
tự chuyển một bản cài hoặc dữ liệu người dùng sang layout mới.

## Kiến trúc và vùng sở hữu

```text
HaizFlow/
  HaizFlow.exe                   launcher độc lập
  updater/HaizFlowUpdater.exe     updater độc lập
  update-layout.json             marker schema/product/layout cố định
  versions/
    0.1.0/HaizFlowCore.exe
    0.1.0/_internal/...
    0.1.0/core-manifest.json
    0.1.0/core-complete.json
    0.2.0/...
  runtime/                       dữ liệu bền vững KHÔNG thuộc updater
  update-state/
    active-version.json          active, previous, known_good
    last-confirmed.json          pointer xác nhận cho phục hồi JSON hỏng
    transaction.json             journal có state/schema/transaction ID
    staging/<transaction ID>/
    downloads/
    ipc/                         yêu cầu/status/permission/health nonce
    update.lock, updater.lock, launcher.lock
```

Install root suy ra từ đường dẫn executable versions/<semver>/HaizFlowCore.exe
và marker được kiểm tra; không tin biến môi trường install-root ở frozen mode.
Core root là version folder; bundle root là _MEIPASS; runtime là install/runtime.
Resource root ngoài ổ đĩa do user chọn tiếp tục qua runtime/data/resource-storage.json.
User vẫn chọn nơi lưu từng project. Updater không đọc/sửa project index, settings,
accounts, media, checkpoints, models, engines hay exports; không tự migrate dữ liệu.

## Luồng

```text
Core: kiểm tra stable release → user chọn Cập nhật
Updater độc lập: official metadata → tải manifest/package → kiểm tra SHA/size
→ dựng staging bằng copy file base đã verify + file mới → verify toàn bộ cây
→ completion marker → rename staging sang versions → ready (90%, chưa hoàn tất)
Core: user có thể đóng popup để hoãn → chọn Khởi động lại khi hết job
Updater: permission nonce + chờ Core thực sự thoát (không terminate job)
→ journal activating → atomic pointer replacement → pending_health
Launcher: kiểm tra Core hoàn chỉnh → start → QML-ready ack có nonce/version/PID
→ confirmed + last-confirmed snapshot (hoặc rollback 1 lần sang known-good)
```

Health không yêu cầu load AI. Process creation không đủ; crash/exit trước ack,
timeout, QML failure hoặc missing executable là startup failure. Quit/crash sau
ack không gây rollback. Chỉ Core mới chưa xác nhận được dừng khi timeout; Core
đang dùng không bị updater terminate. Launcher lock giữ đến khi Core thoát để
ngăn chạy đồng thời; updater chờ old launcher nhả lock trước mở launcher mới.

IPC là JSON trong vùng riêng, token ngẫu nhiên, tên request cố định và schema
strict. Network metadata không tạo shell command; không có shell=True. Giới hạn:
cùng một Windows user có quyền ghi installation có thể sửa IPC/launcher; đây
không phải sandbox chống một local attacker có cùng quyền.

## Manifest và package

Schema 1, product HaizFlow, stable, windows, x64; strict MAJOR.MINOR.PATCH.
Có target_version/base_version/package_type (full|delta), package_name/size/SHA,
target_files/base_files, added_files/changed_files/removed_files,
data_compatibility (project_schema/video_schema/rollback_safe/migration_before_health).
Mỗi file: relative path, size, sha256. Manifest không chứa lệnh hoặc URL thực thi.

Tên assets:
- HaizFlow-Core-0.2.0-windows-x64-full.zip (+ .manifest.json thay .zip).
- HaizFlow-Core-0.2.0-windows-x64-from-0.1.0.zip (+ .manifest.json).

Tệp không đổi vẫn copy, không hardlink, chỉ reuse sau hash verification. Không
patch Core đang chạy. ZIP chỉ được chứa chính xác added+changed; kiểm tra cả
package digest/size rồi file digest/size sau extract. Base/target inventory
không được có reparse points, traversal, UNC/device/absolute paths, tên Windows
dành riêng, path collision case-insensitive, tệp/thư mục xung đột, entry trùng,
root-level runtime/update-state/versions. Có giới hạn file, bytes và metadata.

Công cụ local (không build/upload):
```powershell
.venv/Scripts/python.exe scripts/make-delta.py --base dist/core-0.1.0 --target dist/core-0.2.0 --output dist/updates
# Có thể chỉ --target --output để tạo Full Core.
# --base-version / --target-version nếu tên thư mục khác.
```
Công cụ tạo full + delta, verify ZIP sau tạo, in bytes/percent tiết kiệm. Đầu ra
đã tồn tại không bị ghi đè. Core fixture nhỏ chỉ cần HaizFlowCore.exe giả.

Full fallback dùng cùng downloader và validation: không có delta cho base, base
thiếu/sai hash, không có delta ZIP hoặc delta >=85% full. Full Core không phải
Inno Setup wizard. Base metadata hỏng vẫn yêu cầu sửa installation có kiểm soát;
không đoán schema để vượt qua kiểm tra. Package/manifest integrity mismatch là
lỗi, không hạ tiêu chuẩn kiểm tra. Binary diff và bootstrap self-update chưa có.

## Journal, recovery và disk

downloaded → verified → staged → ready → activating → pending_health → confirmed.
Nhánh lỗi: failed hoặc rolled_back. Dùng tempfile cùng thư mục, flush/fsync,
os.replace pointer/journal; staging/versions cùng installation filesystem.
Không tuyên bố toàn bộ transaction atomic trên mọi filesystem/volume hoặc
chống mọi mất điện. Locked DLL/exe, AV lock, permission error làm activation
dừng và giữ old pointer; không yêu cầu admin cho per-user writable install.

Recovery đọc journal, không đoán từ thư mục:
- downloaded/verified bị ngắt: bỏ staging có ownership validation, giữ Core cũ.
- staged: verify/promote hoặc failed.
- ready: giữ để resume request mới; không tự restart đang có job.
- activating bị ngắt: restore prior pointer đã kiểm chứng.
- pending_health đã attempt: rollback một lần, trừ confirmed snapshot đã được
  flush trước khi crash ở bước ghi journal cuối.
- active JSON hỏng: chỉ restore last-confirmed snapshot có Core đã verify.
- journal hỏng/no runnable Core: dừng với lỗi rõ; runtime không bị xóa.

Preflight staging cần tổng bytes target +64 MiB; download preflight cần package
size +64 MiB. Do download/staging dùng chung volume nhưng checks ở hai thời điểm,
không bảo đảm chống một process khác tiêu thụ disk sau preflight. Disk-full errors
được báo và old Core giữ nguyên. Cleanup_versions là thao tác explicit, chỉ xóa
direct version children có marker/tree verify, giữ active/previous/known-good,
pending và running_versions do caller cung cấp. **Không gọi GC tự động** cho tới
khi packaging có kiểm chứng process discovery. Không dọn runtime/projects/models.
Downloads/IPC retention còn cần chính sách giới hạn được kiểm chứng trước release.

## Schema/migration barrier

Update tự động chỉ nhận cùng project/video schema với base và rollback_safe=true,
migration_before_health=false. Thay schema bị chặn trước staging. Không rollback
dữ liệu. Muốn schema upgrade sau này phải có preflight toàn bộ selected/offline
projects, backup migration có khả năng restore, khóa việc migration đến sau health,
compatibility window và recovery UX được kiểm thử riêng. Metadata không tự chứng
minh executable tuân thủ cam kết schema: tác giả release phải kiểm chứng nó.

## GitHub và giới hạn không ký

Nguồn duy nhất là public releases/latest của MachHongHai/HaizFlow. Không PAT,
đăng nhập, API key, Authenticode hay Ed25519. Release phải stable/published/tag
hợp lệ và đúng URL repo. Tải đúng tên asset, uploaded, size và API sha256 digest;
digest package phải đồng nhất manifest. Redirect kiểm tra trước connection:
HTTPS official GitHub asset path hoặc release-assets/objects CDN, không foreign
host/repo/API redirects. Release notes chỉ là nội dung, không chạy lệnh.

SHA-256 chứng minh bytes khớp digest, **không chứng minh tác giả** khi cả asset
và digest từ nguồn bị chiếm. Trust dựa HTTPS + official repo + kiểm tra nguồn và
toàn vẹn; không tương đương signed updates. Immutable Releases là biện pháp
GitHub tùy chọn giảm thay asset sau publish, không giả định đã bật, không tự
đổi repo settings. Nguồn: [GitHub Releases REST](https://docs.github.com/en/rest/releases/releases),
[Immutable Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#immutable-releases).

## Kiểm thử và phần chưa kiểm chứng

tests/test_delta_update.py: Core fixtures, full/delta/hash/inventory/path/ZIP,
Windows junction/locks, crash giữa staging/activation/confirmation, thiếu disk,
busy activation, healthy Core giả, failed startup/timeout và bounded rollback,
full fallback, independent updater defer/activation, data-preservation.
tests/test_portable_paths.py: source/legacy paths và versioned install fixtures.
tests/test_app_update_controller.py: controller/legacy updater regressions.
tests/qml/tst_AppUpdatePopup_2.qml: ready/restart/busy/preparing/error/defer.
tests/qml/tst_CopyrightDialog.qml: open/escape/reopen.

Chưa thử frozen onedir, real downloaded delta GitHub, interrupted power loss,
Windows Defender quarantines, locked running frozen DLL, multiple desktop
processes thực, installer upgrade/uninstall. Không tự build, tag, commit,
push hay publish. Xem [packaging todo](updater-packaging-todo.md).
