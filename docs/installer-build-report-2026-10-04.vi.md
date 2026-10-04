# Báo cáo installer và hướng phát hành unsigned — 04/10/2026

## Kết luận

Đã build và nghiệm thu installer **0.1.0 DEVELOPMENT, unsigned** trên máy Windows hiện tại. Chưa publish GitHub hoặc tạo tag release. Người dùng đã ủy quyền commit/push các thay đổi; trạng thái Git được báo riêng sau khi nghiệm thu.

Chủ dự án sau đó chọn hướng miễn phí: **không mua chứng chỉ và không ký Authenticode**. Source đã có `UnsignedRelease` riêng cho public Core/bootstrap/engine/installer. Chữ ký không còn là điều kiện bắt buộc; giấy phép, catalog engine, source sạch và nghiệm thu Windows vẫn bắt buộc.

**Chưa có installer public unsigned đã được duyệt.** Không đổi tên installer DEVELOPMENT rồi tải lên như bản chính thức.

## Rà soát bổ sung trước commit/push

Đã xác minh tài khoản GitHub có quyền push/admin trên `MachHongHai/HaizFlow`;
không đưa thông tin đăng nhập vào log, source hay artifact. Repository chưa
có release được công bố tại thời điểm rà soát.

Đã bổ sung metadata/checksum riêng cho launcher và updater, kiểm cùng commit,
phiên bản và chế độ engineering/public với Core khi assembly. Bản public có
chữ ký cũng phải qua legal/clean-source gate; không chỉ bản unsigned. Raw Core
và baseline delta nay từ chối cả root `runtime` lẫn `update-state`. Những
artifact engineering trong bảng dưới được tạo **trước** thay đổi tooling này;
không re-finalize chúng để giả nguồn sạch hoặc duyệt phát hành. Public candidate
phải được build lại từ commit sạch sau khi các điều kiện còn thiếu được xử lý.

Các điều kiện chưa đủ để publish binary: hồ sơ corresponding-source FFmpeg
và thư viện static, hồ sơ source/replacement Qt, ba URL engine public đã
kiểm tra bằng download thật, và nghiệm thu installer public trên máy sạch.
Đây không phải yêu cầu mua chứng chỉ Authenticode.

Kết quả source bổ sung: **1.315 test, 159 subtest qua, 1 bỏ qua**, 218,77
giây; compile/Python lint/QML lint qua (`build/source-pre-publish-2026-10-04.log`).
Sau đó bổ sung văn bản CC-BY-NC đầy đủ/thông tin publisher OmniVoice và test
notice: cả 14 test legal-state qua. Không coi tổng này là một lần chạy full
suite 1.316 test. Python correctness lint và `git diff --check` qua.

Bootstrap engineering mới ở `dist/bootstrap-provenance-engineering`:
metadata và checksum được tạo bằng builder thật; cả hai `--help`/import
smoke exit 0, không phát sinh root runtime/update-state, không có Qt/Torch.
Launcher/updater đều `NotSigned`. Log: `build/bootstrap-provenance-engineering.log`.
Đây vẫn là build working-tree engineering, không phải bootstrap public.

## Nghiệm thu cuối sau sửa mặc định ngôn ngữ và lưu tài nguyên

Thông số trong mục này là của bản hiện tại. Các mục lịch sử phía dưới giữ
bằng chứng của lượt trước; tên output installer được dùng lại khi build,
nên không dùng checksum lịch sử để kiểm tệp hiện tại.

| Hạng mục | Kết quả hiện tại |
| --- | --- |
| Installer | `dist/installer/HaizFlow-0.1.0-DEVELOPMENT-Setup.exe`, **194.794.242 byte**, `NotSigned` |
| SHA-256 | `2c714943755d389d841db43e5b15feacbd9a0cd80d0ff1910d5c2c895fb4d2cb` |
| Raw Core | `dist/HaizFlowCore`, 566.668.531 byte, 3.652 checksum entry |
| Assembly | `dist/HaizFlow-versioned-0.1.0-storage-safe`, **607.024.255 byte**, 3.795 checksum entry; không có root runtime/update-state |
| Full Core ZIP | `dist/release-assets-0.1.0-storage-safe-development/HaizFlow-Core-0.1.0-windows-x64-full.zip`, 252.994.454 byte |
| Source cuối | **1.303 qua, 1 bỏ qua, 157 subtest qua**, 106,29 giây; compile/Python correctness lint/QML lint qua |
| Cài mới/repair/gỡ/cài lại | Sáu kịch bản qua; bốn fixture dữ liệu giữ nguyên |
| Delta unsigned | `NotSigned` ở cả ba executable; inventory chính xác, real health, rollback và giữ dữ liệu qua; fixture cục bộ, không test mạng |
| Dung lượng đo sau cài | **607.024.255 = 607.024.255 byte** số embedded; uninstaller phát sinh 6.622.441 byte ghi riêng |
| Disk preflight | Cài mới tối thiểu 2.754.507.903 byte, upgrade 3.361.532.158 byte; khuyến nghị 4 GiB, reserve 2 GiB; engine/model/media tính riêng |

Log installer cuối:
`build/installer-reports/cc9ac850a086413cabc232941cde01f8/result.json`.
Test delta unsigned cuối chạy riêng và **qua**:
`build/frozen-delta-reports/8300c49d78f648898db149825b0b1012/result.json`.
Core/launcher/updater đều `NotSigned`; Core mới không tự sửa payload bất
biến khi chạy; data giữ nguyên. Delta fixture 153 byte chỉ thêm một file;
phiên bản 0.1.1/0.1.2 là giả lập, không phải release hoặc binary-upgrade
qua GitHub. Source suite kiểm thêm changed/deleted files và lỗi integrity.

Mặc định cài mới là **tiếng Việt**; lựa chọn tiếng Anh đã lưu được giữ.
Test bao gồm settings trống, JSON hỏng, ngôn ngữ không hợp lệ và cập nhật
một phần không làm mất lựa chọn trước đó.

Đã sửa thêm lỗi dọn tài nguyên: không suy ra thư mục hiện tại từ pointer
trống; từ chối gốc ổ, đường dẫn lồng nhau/reparse; giữ nguồn khi bản sao
không khớp; ghi pointer atomically. Nếu thay thế engine hoặc vùng lưu trữ
thất bại sau khi chuyển bản cũ sang backup, bản cũ được khôi phục. Hủy sau
smoke không tiếp tục promote engine. Regression test đã qua.

### Engine frozen và luồng cài bằng manager thật

| Engine | ZIP byte | Payload sau giải nén byte | Kết quả |
| --- | ---: | ---: | --- |
| CPU v1 | 359.974.008 | 870.977.872 | Cài từ cache, smoke, marker/status qua |
| Vision v1 | 94.878.501 | 232.391.799 | Cài từ cache, smoke, marker/status qua |
| CUDA v2 | 3.218.854.197 | 5.089.254.734 | Ghép hai part, hash từng part/toàn ZIP, cài/smoke/status qua |

Hai part CUDA v2 là 1.610.612.736 và 1.608.241.461 byte. Luồng này dùng
ZIP thật, không mock executable/smoke; chặn mọi truy cập mạng trong test,
không dùng dữ liệu người dùng. Report:
`build/resource-install-reports/d2152cd63bff4a6785eaa66cc4e67a4a/result.json`.
Không suy ra rằng download GitHub hoặc toàn bộ inference trên VM sạch đã qua.

### Dữ liệu phát sinh trong dist và dọn build

Người dùng xác nhận đã mở các EXE trong dist. Staging bị phát sinh runtime
đã bị loại khỏi luồng đóng gói; không sửa checksum để chấp nhận dữ liệu đó.
Đã sao lưu **180 tệp** runtime/update-state sang
`build/recovered-dist-launch-2026-10-04`, đối chiếu SHA-256 từng tệp; bản gốc
vẫn nguyên. Builder nay từ chối ghi đè artifact có runtime/update-state hoặc
reparse point, thay vì xóa chúng khi build lại.

Bảy output/probe cũ đã được xóa ở lượt trước (993.830.844 byte). Lệnh dọn
đợt cuối, kể cả ZIP CUDA v1 và part cũ, bị môi trường thực thi chặn trước
khi chạy; **chưa xóa các mục này**, không đổi công cụ để vượt chặn. Các
thư mục staging/assets `*-final`, `*-audited`, `*-vietnamese` và CUDA v1
không phải bộ đóng gói cuối. Cần giữ backup runtime trước khi dọn thủ công.

Catalog source vẫn **0/3 URL engine public**. Build/source và installer
engineering không thay cho review corresponding source FFmpeg, Qt LGPL
và nghiệm thu đường tải trên máy sạch. Không đưa file DEVELOPMENT lên Latest.

## Artifact đã build — lịch sử trước đợt sửa cuối

| Artifact | Vị trí / kết quả |
| --- | --- |
| Installer nội bộ | `dist/installer/HaizFlow-0.1.0-DEVELOPMENT-Setup.exe` |
| Kích thước installer | 196.984.156 byte, khoảng 187,86 MiB |
| Authenticode | `NotSigned`, đúng phạm vi kiểm thử unsigned |
| Checksum | `.exe.sha256` nằm cạnh installer, đã đối chiếu hash của file thực |
| Core | `dist/HaizFlowCore/HaizFlowCore.exe`; payload 572.452.212 byte, 3.743 tệp trong checksum manifest |
| Assembly versioned | `dist/HaizFlow-versioned-0.1.0-final`; 612.847.499 byte, 3.886 tệp trong root checksum manifest |
| Full Core ZIP nội bộ | `dist/release-assets-0.1.0-final-development/HaizFlow-Core-0.1.0-windows-x64-full.zip`; 256.162.842 byte |
| Provenance | Commit nền `b99c1c0713b299d036bafd0bdfd302b70ec8d271`, build ID `0.1.0+b99c1c0713b2`, **git_dirty: true** |

SHA-256 của installer nghiệm thu:

```text
448e67c530ce341588ff81f23a319990693dc48bfaf699d904165e619e628b5c
```

Assembly không đóng gói root `runtime` hoặc `update-state`. Model nhận diện người nói khoảng 26,5 MB đi cùng Core, xác minh theo hash pinned; các engine/model lớn không đi cùng installer. `INSTALL-REQUIREMENTS.json` ghi yêu cầu trống khi upgrade 3.373.178.646 byte và khuyến nghị 4 GiB. Các số này không gồm engine, media, output hay cache của người dùng.

## Kết quả kiểm thử

| Hạng mục | Bằng chứng / phạm vi |
| --- | --- |
| Source trước build và sau thay đổi unsigned | 1.264 test qua, 1 bỏ qua, 150 subtest qua; Python lint/compile và QML lint qua; lượt cuối 184,64 giây |
| Qt Quick Test | 77 qua, 0 lỗi; `build/qml-test-installer-audit.txt` |
| Chỉnh nội dung phụ đề | Suite GUI cô lập qua; không chỉnh dự án người dùng |
| Packaging/delta/model sau thay đổi unsigned | 59 test và 28 subtest qua |
| PowerShell | Sáu script packaging/sign/smoke parse thành công |
| Guard public unsigned | Cả bốn entrypoint từ chối kết hợp `UnsignedRelease` với flag engineering trước khi build |
| Frozen native/Core UI | FFmpeg/ffprobe và Qt/QML startup qua trong artifact thực |
| Speaker frozen | Inference CPU thực, 2 segment từ sample đi kèm; không cần engine ngoài, model trong Core không bị ghi lại |
| Installer cuối | Cài mới → chạy app thực → repair → gỡ giữ data → cài lại trên data cũ → gỡ lần cuối: qua |
| Repair | Cố tình làm hỏng `Main.qml` và thêm tệp Core thừa; repair khôi phục UI và loại tệp thừa |
| Dữ liệu installer | Bốn fixture data/model/project/internal-external có hash không đổi sau chuỗi gỡ/cài lại |
| Delta frozen cuối | Inventory target chính xác, kích hoạt Core mới, real health ack, rollback khi Core kế tiếp lỗi startup, data không đổi |

Log nghiệm thu cuối:

- Installer: `build/installer-reports/bec5bbb5083e4524861737a499188641/result.json` cùng các log Inno/frozen UI trong thư mục đó.
- Delta: `build/frozen-delta-reports/5565d14a2bd740c7b575d78cf52addff/result.json`.
- Speaker: `build/frozen-speaker-report.json`.

Delta dùng phiên bản **giả lập cục bộ** 0.1.1/0.1.2, không đổi version app 0.1.0. Chưa nghiệm thu download/update từ GitHub release thật. Speaker test xác nhận inference/đóng gói, không phải benchmark chất lượng phân biệt nhiều người nói.

Không gọi đây là kiểm chứng mọi chức năng trên mọi máy. Chưa có ma trận máy Windows 10/CPU-only/GPU driver khác, test Smart App Control từ file download hoặc nghiệm thu cả ba engine frozen trên VM sạch. Dependency audit qua **với ngoại lệ đã ghi nhận**, không có nghĩa không có advisory. Suite dev có cảnh báo torchcodec/pyannote của môi trường AI cũ và API Qt deprecated; các package AI cũ đó không được gom vào Core.

## Các lỗi packaging đã sửa

- Cho phép đúng model speaker pinned đi kèm Core; không nhầm nó với payload model lớn bị cấm.
- Xác minh model đi kèm theo cách chỉ đọc, không tạo/đổi integrity-cache marker trong Core bất biến.
- Sửa assembly gọi delta reconstruction thiếu tham số `base`.
- Sửa bool Inno preprocessor: giá trị chuỗi `"0"` không còn bị coi là bật mode engineering/versioned/signed.
- Installer/launcher kiểm lock app/updater/update, pending transaction, downgrade và reparse-point trước thao tác thay/xóa.
- Repair thay riêng Core đích để không giữ tệp dư; giữ Core rollback khác và mutable runtime.
- Uninstall kiểm Core trước xóa, không xóa project hoặc resource ngoài app; silent uninstall giữ runtime.
- Smoke cleanup chờ helper tạm của Inno giải phóng file, không báo thất bại chức năng chỉ vì helper vừa gỡ chưa thoát.
- Tách public `UnsignedRelease` khỏi `AllowUnsigned` nội bộ; giữ nguyên legal/resource/provenance gate và công khai giới hạn Windows của file chưa ký.

Các thay đổi mới về policy chỉ nằm trong build scripts/tests/docs; installer DEVELOPMENT đã nghiệm thu không được chỉnh bytes sau khi tạo hash.

## Những điều còn chặn public release, không liên quan phí chữ ký

1. **Catalog 0/3 engine sẵn sàng:** CPU/CUDA/vision chưa có URL và SHA-256 artifact thật. Máy mới chưa được chứng minh tải/cài/chạy pipeline AI đầy đủ.
2. **Hồ sơ giấy phép:** `legal/license-state.json` còn bốn clearance chưa duyệt: phạm vi source/contributor; OmniVoice và mẫu giọng; corresponding source FFmpeg; nghĩa vụ Qt LGPL/relinking. Chưa có `public_release_review` và evidence được duyệt. Không tự điền approval hoặc bỏ gate.
3. **Provenance binary engineering:** artifact đã nghiệm thu được tạo từ snapshot `git_dirty: true`. Commit source sau đó không đổi provenance của binary cũ; ứng viên public phải build lại từ commit sạch sau khi các gate khác hoàn tất.
4. **Nghiệm thu thật:** VM/máy sạch và đường tải GitHub, engine inference, Windows security policy, upgrade qua release thực chưa hoàn tất.

Đã chạy `build-exe.ps1 -UnsignedRelease`: script không yêu cầu certificate; dừng đúng ở legal review trước PyInstaller/ghi đè Core hiện có. Đã chạy strict resource verifier: từ chối catalog thiếu URL/hash. Đây là gate đang hoạt động, **không phải lỗi phát sinh vì thiếu chữ ký**.

Catalog source còn ước lượng CUDA 4,5 GB. ZIP engineering thực đầu tiên đo
3.218.852.746 byte, vượt giới hạn mỗi asset của GitHub. Packaging/downloader
hiện đã hỗ trợ multipart với hash từng phần và toàn ZIP; preflight tính cả
chỗ trống để ghép. Test integrity/cancel/resume và cài fixture đã qua. Chưa
coi catalog có URL thật hoặc download GitHub đã được nghiệm thu. Bản engine
  sạch v2 đã qua cài thực ở mục nghiệm thu cuối; số của lượt đầu không thay metadata release.

## Bổ sung: tài sản, dung lượng và dọn build

- Chủ dự án xác nhận quyền phân phối branding/voice preview và chọn giữ
  OmniVoice kèm công khai giới hạn phi thương mại. Ghi nhận trong
  `legal/reviews/owner-assets-and-omnivoice-2026-10-04.md`; public gate vẫn
  chặn hồ sơ chưa hoàn tất, không tự duyệt corresponding source FFmpeg/Qt.
- CPU build dùng wheel llama.cpp Windows chính thức cùng version/hash;
  hook thu DLL ctypes vào đúng thư mục. Vision giữ YAML/dictionary cần thiết
  của RapidOCR, không gom ONNX mặc định chưa pin. Cả hai EXE frozen đã qua
  profile smoke. GPU v2 đã qua smoke cô lập và ghép multipart/cài thực.
- Prune Virtual Keyboard/Quick Timeline mà app không import, kèm plugin
  input-context tương ứng. Không xóa Windows native IME. Core mới đã qua
  native/Qt/QML smoke; không coi pruning là đủ duyệt LGPL toàn gói.
- Lượt source mới: **1.281 qua, 1 bỏ qua, 150 subtest qua**, 217,65 giây;
  dependency audit/codec/lint qua theo các ngoại lệ đã ghi nhận.
- Installer từ chối artifact có `INSTALL-REQUIREMENTS.json` lệch dung lượng
  đo thực. Smoke mới so tổng byte đúng file set đã cài với số embedded,
  ghi riêng overhead uninstaller; engine/model/media không bị lẫn vào Core.
- Đã xóa 7 output/probe cũ trong `dist`, giải phóng **993.830.844 byte**.
  Không xóa project, resource người dùng, baseline nghiệm thu cuối hoặc log.
  Xóa trực tiếp, không có bản sao thùng rác; có thể dựng lại từ source.
  Chi tiết tại `build/obsolete-build-cleanup-2026-10-04.json`.

Lượt retest delta khi build engine chạy đồng thời đã timeout outer process
100 giây trong lúc xác minh Core trước startup, không được tính là đạt.
Test helper tách outer bound 300 giây (bao gồm inventory I/O) khỏi health
timeout 30 giây. Lượt cuối đã chạy lại serial và qua, theo report trong
mục nghiệm thu cuối; lượt timeout cũ vẫn không được tính là đạt.

## Trình tự phát hành tiếp theo

Theo [hướng dẫn miễn phí đầy đủ](windows-release-setup.vi.md): review quyền phân phối → build/test engine unsigned → pin URL/hash thật → source sạch → build Core/bootstrap/assembly/installer bằng `UnsignedRelease` → nghiệm thu đúng installer trên VM → tạo draft GitHub với đủ assets → tải lại/đối chiếu → publish stable.

Release đầu 0.1.0 dùng Full Core; chưa có baseline public thì không phát hành delta giả. Lưu raw finalized Core để tạo delta cho release thực kế tiếp. Chữ ký là lựa chọn tương lai, không cần mua để thực hiện hướng này.
