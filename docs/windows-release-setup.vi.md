# Cài đặt và phát hành HaizFlow miễn phí trên Windows

Phiên bản mục tiêu: **0.1.0**. Hướng dẫn cập nhật ngày 04/10/2026. Theo lựa chọn của chủ dự án: phát hành **unsigned**, không mua chứng chỉ Authenticode.

## 1. Bản hiện tại dùng vào việc gì?

Bản `HaizFlow-0.1.0-DEVELOPMENT-Setup.exe` dùng để nghiệm thu nội bộ, **chưa ký số và chưa phải bản phát hành công khai**. Không đổi tên nó thành bản chính thức. Development dùng AppId riêng để không ghi đè đăng ký cài đặt của bản public.

Các bằng chứng cuối đợt build được ghi trong `docs/installer-build-report-2026-10-04.vi.md`. Có thể xem log thô tại `build/installer-reports/` và `build/frozen-delta-reports/`.

Trước khi phát hành còn phải hoàn tất:

- Không yêu cầu chứng chỉ. Phải công khai trạng thái unsigned và kiểm thử khả năng chạy trên Windows sạch; không cam kết vượt SmartScreen/Smart App Control hay chính sách doanh nghiệp.
- Build, kiểm thử và pin URL/checksum thật cho ba engine CPU, CUDA và vision. Catalog hiện để trống URL/SHA-256; không coi pipeline AI của máy mới là đã nghiệm thu.
- Review bốn mục trong `legal/license-state.json`: quyền source/contributor; OmniVoice và mẫu giọng; FFmpeg corresponding source; Qt LGPL/relinking. Không xóa blocker chỉ để vượt build gate. Cần bằng chứng và người có thẩm quyền xác nhận; hướng dẫn này không thay tư vấn pháp lý.
- Source đã commit sạch, tag đúng commit, kiểm thử Windows/CPU/GPU thực tế. Không ship working tree dirty làm release chính thức.

## 2. Cài thử và vị trí dữ liệu

Chạy installer, chọn một thư mục local mà tài khoản Windows có quyền ghi, ví dụ `D:\Apps\HaizFlow-Test`. Không chọn gốc ổ đĩa, thư mục chứa dữ liệu khác, UNC/network drive hoặc junction. Không dùng thư mục của bản đang chạy. Bản cài không cần quyền administrator với thư mục phù hợp.

Bố cục dự kiến:

```text
D:\Apps\HaizFlow-Test\
  HaizFlow.exe                    launcher, mở app bằng tệp này
  _internal\                     runtime riêng của launcher
  updater\                       updater độc lập
  versions\0.1.0\                Core bất biến và phụ thuộc
  update-state\                  pointer, transaction, health IPC
  runtime\
    data\                        desktop-settings.json, index, logs
    cache\
    tmp\
    models\                      tài nguyên tải sau
    engines\
    packages\
```

Model nhận diện người nói nhỏ đi cùng Core; không cần tải gói nhận diện riêng. Nó luôn chạy CPU. Các engine/model lớn vẫn là tài nguyên tùy chọn. Nếu đổi vị trí lưu tài nguyên trong Cài đặt, `runtime/data/resource-storage.json` lưu pointer; payload tài nguyên đi tới vị trí mới, không phải tự động di chuyển toàn bộ dự án.

API key lưu bằng Windows Credential Manager của tài khoản Windows, **không nằm trong thư mục dự án hay installer**. Backup `runtime` không backup key; sang máy/tài khoản khác nhập lại key. Dự án/media/output ở thư mục do người dùng chọn bên ngoài app phải được backup riêng.

Cài lại cùng phiên bản giữ `runtime`. Nâng phiên bản giữ Core cũ để rollback theo trạng thái cập nhật; không sửa tệp dưới `versions` thủ công. Gỡ cài im lặng luôn giữ dữ liệu; gỡ tương tác chỉ xóa `runtime` nếu người dùng xác nhận. Không xóa thư mục dự án/tài nguyên đã đặt bên ngoài chỉ vì gỡ app.

Với bản cũ dạng flat chưa có `update-layout.json`: không tự chuyển dữ liệu tại chỗ. Đóng app, backup `runtime` và mọi thư mục dự án; cài vào thư mục mới, rồi khôi phục/đăng ký lại dữ liệu theo phiên bản được hỗ trợ. Không chép `_internal` hoặc executable cũ vào bản mới.

### Thiết lập lần đầu cho người dùng

1. Mở `HaizFlow.exe`. Cài mới mặc định tiếng Việt; lựa chọn tiếng Anh đã lưu được giữ khi cài lại. Kiểm tra CPU/GPU trong Cài đặt. GPU chỉ dùng khi máy/driver và engine tương thích. Nhận diện nhiều người nói vẫn CPU.
2. Chọn thư mục lưu tài nguyên trước khi tải gói lớn; kiểm tra dung lượng trống.
3. Cài engine/model cần dùng trong Gói tài nguyên. Ba engine frozen đã qua cài cache thực bằng manager của app (GPU qua ghép multipart), kiểm executable và dung lượng. Bản engineering vẫn thiếu địa chỉ engine phát hành, nên tải từ GitHub và pipeline đầy đủ trên máy mới chưa được nghiệm thu.
4. Chỉ thêm Gemini key nếu dùng dịch Gemini; chỉ thêm Zernio key nếu đăng mạng xã hội. Đặt tên từng key, chọn key đang dùng và kiểm tra kết nối. Dấu chấm của Zernio thể hiện kết quả các API đọc được kiểm tra, không chứng minh đã đăng thành công hay mọi quyền ghi.
5. Tạo dự án thử bằng media ngắn, kiểm tra nhận dạng/dịch/giọng/preview/xuất trước khi chạy batch. Cấu hình tài khoản, caption, hàng đợi thuộc từng project; key thuộc Cài đặt app.

Người dùng cuối **không cần cài Python, Qt, FFmpeg hoặc CUDA Toolkit** để mở Core. Không hướng dẫn tắt Defender/SmartScreen; khi Windows chặn, trước hết xác minh đúng repository, tag, file và hash. Bản unsigned không có publisher được Windows xác thực. Có máy/chính sách sẽ không cho chạy dù nguồn hợp lệ.

## 3. Phát hành unsigned, không tốn phí chứng chỉ

Không cần đăng ký CA/Authenticode, Windows SDK Signing Tools, token, HSM hay PFX cho workflow này. GitHub Releases là nơi phát hành được chọn; không mua chứng chỉ và không tạo chứng chỉ self-signed để bắt người dùng cài trusted root.

Windows có thể hiện “Unknown publisher”, “Windows protected your PC” hoặc chặn chạy. File unsigned không kế thừa reputation từ phiên bản trước. Smart App Control và chính sách máy doanh nghiệp có thể không có lựa chọn tiếp tục. Đây là giới hạn phải ghi trong release notes, không phải lỗi installer có thể sửa bằng đổi tên. Xem [tài liệu SmartScreen của Microsoft](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation).

Chỉ khi chính bạn đã tải từ repository chính thức, hash khớp và Windows cho phép quyết định riêng cho file, bạn mới cân nhắc “More info → Run anyway”. Không tắt bảo vệ toàn máy, không thêm exclusion rộng, không hứa cách này dùng được trên mọi máy. Nếu Defender báo malware cụ thể, dừng để kiểm tra; không bỏ qua như cảnh báo reputation thông thường.

Các script có hai chế độ không ký khác nhau:

- `-UnsignedRelease`: ứng viên công khai unsigned; vẫn bắt buộc source sạch, giấy phép được duyệt, catalog tài nguyên đầy đủ và các kiểm thử.
- `-AllowUnsigned`: chỉ kiểm thử nội bộ. Installer phải dùng thêm `-EngineeringBuild`, AppId và tên DEVELOPMENT riêng. Không đổi tên file để giả thành release.

`-UnsignedRelease` không được kết hợp với signing identity, `-AllowUnsigned`, `-AllowDirtyBuild` hay `-EngineeringBuild`. Tên installer công khai sẽ là `HaizFlow-0.1.0-UNSIGNED-Setup.exe`. Hỗ trợ ký trong source vẫn được giữ như một lựa chọn tương lai, không phải điều kiện của hướng miễn phí.

SHA-256 giúp kiểm toàn vẹn file, **không thay chữ ký danh tính**. Bảo vệ tài khoản GitHub bằng 2FA/passkey, review quyền write/release, bảo vệ tag, dùng draft để nghiệm thu đủ assets rồi mới publish. Nếu tài khoản phát hành bị chiếm, checksum đăng trên cùng tài khoản không đủ bảo vệ.

## 4. Chuẩn bị máy build

Máy build cần Windows x64, Git, Python 3.13 x64, uv theo lock tooling và Inno Setup 6.5+. Không cần Windows SDK để ký. Máy hiện dùng Inno 6.7.3 có dòng “Non-commercial use only”; hãy kiểm tra [điều kiện Inno Setup](https://jrsoftware.org/isinfo.php) nếu workflow/phân phối của bạn là thương mại. App tải miễn phí không tự động đồng nghĩa mọi công cụ/thư viện được dùng thương mại miễn phí.

Đặt repo, temp và cache trên ổ đủ chỗ. Build Core đã dùng môi trường độc lập `build/core-env`, không gom mọi package AI của `.venv` vào installer. Không tự nâng phiên bản dependency lúc build release.

```powershell
Set-Location D:\Du-an\HaizFlow
New-Item -ItemType Directory -Force -Path build\tool-temp, build\cache\uv | Out-Null
$env:TEMP = (Resolve-Path build\tool-temp).Path
$env:TMP = $env:TEMP
$env:UV_CACHE_DIR = (Resolve-Path build\cache\uv).Path
uv venv build\core-env --python 3.13
uv pip sync --python build\core-env\Scripts\python.exe --require-hashes requirements-lock-py313-win64.txt
```

Lệnh tạo env dành cho máy mới/thư mục chưa có; nếu đã có env đang dùng, không tạo đè. `.venv` có tooling kiểm thử của project phải được chuẩn bị theo README/script cài môi trường; release gate chạy `scripts/test.ps1` từ đó. Khi chạy build thật, dùng PowerShell có fail-fast (`$ErrorActionPreference='Stop'`) và dừng ngay khi lệnh trả nonzero.

## 5. Hoàn tất gói AI trước khi build public Core

Các script tạo một ZIP nguyên vẹn làm baseline cho mỗi engine, rồi tự chia
gói lớn thành các phần đã pin checksum. Dùng index do script tạo và catalog
multipart; không ghép/cắt file thủ công hoặc bỏ kiểm hash toàn gói.

Catalog CUDA đang ước lượng 4,5 GB download. Đó chưa phải kích thước build thật, nhưng có nguy cơ vượt giới hạn dưới 2 GiB mỗi asset của [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

Chọn một trong các cách trước khi pin URL:

- Nếu ZIP thực tế dưới 2 GiB, đưa lên release tài nguyên bất biến, ví dụ tag `resources-v1`, không đặt release tài nguyên làm Latest của app.
- Nếu vượt giới hạn, không upload ZIP đó như một GitHub asset. Hướng không trả phí cần kiểm tra một dịch vụ hosting miễn phí phù hợp cả dung lượng, băng thông, điều khoản và URL bất biến; chưa có dịch vụ nào được chọn/nghiệm thu ở đây. Không cam kết free-tier dùng lâu dài hoặc tự động chuyển sang storage trả phí.
- Packaging/downloader đã hỗ trợ nhiều phần: mỗi phần dưới 2 GiB, hash riêng và hash toàn ZIP, ghép streaming vào tệp tạm rồi publish atomic. Chỗ trống tính cả các phần tải và ZIP ghép. Gói lớn được build script tự chia; không cần mua hosting để vượt giới hạn mỗi asset.

Ví dụ build unsigned công khai sau khi các gate pháp lý và source sạch đã qua:

```powershell
.\scripts\build-resource-engine.ps1 -Profile cpu -Version 1 -UnsignedRelease
.\scripts\build-resource-engine.ps1 -Profile cuda128 -Version 2 -UnsignedRelease
.\scripts\build-resource-engine.ps1 -Profile vision -Version 1 -UnsignedRelease
```

ZIP nằm dưới `build/resource-engines/<pack-id>/`. Kiểm thử inference thật, cancel, CPU-only/driver tương thích và chạy trên máy sạch không có dev Python. Upload ZIP tới nơi được chọn chỉ khi quyền phân phối đã được duyệt. Ghi catalog bằng file thật, không nhập số ước lượng:

```powershell
.venv\Scripts\python.exe scripts\finalize-resource-pack.py `
  --pack-id engine-cpu-py313 --version 1 `
  --archive build\resource-engines\engine-cpu-py313\engine-cpu-py313-1.zip `
  --url 'URL_HTTPS_BAT_BIEN_CUA_FILE_THAT'
```

Vision (`engine-vision-onnx`) cũng dùng ZIP đơn. Với CUDA lớn, upload toàn bộ
`*.zip.001`, `*.zip.002`, ... trong thư mục `multipart-*` do build script báo,
không upload ZIP quá 2 GiB. `parts.json` là index/checksum local, không thay
catalog của Core. Sau khi các URL public thật đã tải lại/kiểm tra được:

```powershell
.venv\Scripts\python.exe scripts\finalize-resource-pack.py `
  --pack-id engine-cuda128-py313 --version 2 `
  --archive build\resource-engines\engine-cuda128-py313\engine-cuda128-py313-2.zip `
  --parts-manifest 'THU_MUC_MULTIPART_THUC\parts.json' `
  --parts-url-prefix 'URL_HTTPS_RELEASE_RESOURCES_THUC'
```

`--parts-url-prefix` là URL thư mục chứa asset, không phải trang GitHub
`/releases/tag/...`. Ví dụ cấu trúc `/releases/download/resources-v1/`;
chỉ điền khi đúng release/asset tồn tại. Finalizer kiểm file từng phần và
hash của phép nối so với ZIP gốc. Giữ source ZIP cùng index làm baseline;
chạy verifier sau khi pin cả ba engine:

```powershell
.venv\Scripts\python.exe scripts\verify-resource-pack-manifest.py --strict
.venv\Scripts\python.exe scripts\verify-legal-state.py --public-release
```

Các placeholder trong hướng dẫn phải thay bằng dữ liệu thật. Commit catalog đã review trước khi build Core; không sửa catalog sau khi đã đóng gói Core và cho rằng app sẽ tự biết URL mới.

## 6. Build release unsigned đúng thứ tự

Chỉ thực hiện khi source sạch, legal/resource gate đạt và version còn là 0.1.0. Các thư mục output assembly/bootstrap/assets phải **chưa tồn tại**. Tên ở dưới là ví dụ cho một lượt build mới, không xóa output cũ để vượt gate.

```powershell
git status --short
.\scripts\build-exe.ps1 -CoreLayout `
  -PythonExecutable D:\Du-an\HaizFlow\build\core-env\Scripts\python.exe `
  -UnsignedRelease

.\scripts\build-bootstrap.ps1 -OutputDirectory D:\Du-an\HaizFlow\dist\bootstrap-public `
  -PythonExecutable D:\Du-an\HaizFlow\build\core-env\Scripts\python.exe `
  -UnsignedRelease

.venv\Scripts\python.exe scripts\assemble-versioned.py `
  --core dist\HaizFlowCore --launcher dist\bootstrap-public\HaizFlow `
  --updater dist\bootstrap-public\HaizFlowUpdater `
  --output dist\HaizFlow-public --assets dist\release-assets-0.1.0

.\scripts\build-installer.ps1 -ArtifactPath D:\Du-an\HaizFlow\dist\HaizFlow-public `
  -UnsignedRelease -SkipInstallerSmokeTest
```

Ở máy build dùng `SkipInstallerSmokeTest` để tránh đăng ký AppId public vào máy đang có app thật. **Chưa được nghiệm thu/publish chỉ vì compile đã xong**. Copy đúng installer và `.sha256` sang VM sạch, cùng repository/tooling cần cho smoke; chạy:

```powershell
.\scripts\test-installer.ps1 `
  -InstallerPath D:\Release\HaizFlow-0.1.0-UNSIGNED-Setup.exe `
  -AllowRegisteredInstall
```

`AllowRegisteredInstall` chỉ dùng trong VM sạch; không dùng trên máy có HaizFlow production. Test tự cài vào đường dẫn có khoảng trắng, không tạo shortcut, chạy UI frozen, repair, gỡ, cài lại trên dữ liệu giữ lại và kiểm hash fixture. Vẫn cần test tương tác wizard/IME/DPI, cảnh báo từ file tải qua browser và pipeline với engine thật. Không truyền `RequireSignature` cho bản unsigned.

Cả Core, launcher, updater, engine, setup và uninstaller của HaizFlow sẽ không ký trong hướng này. Manifest/Full Core được tạo sau khi executable hoàn chỉnh; bất kỳ thay đổi bytes nào sau đó đều cần build lại metadata/hash/package/installer tương ứng. Không thay version hay bytes của một release đã công khai.

Launcher/updater mới có `BOOTSTRAP-INFO.json` và checksum riêng; assembly
kiểm chúng cùng commit/phiên bản/chế độ build với Core. Không tái dùng thư mục
bootstrap cũ thiếu metadata hoặc metadata thuộc commit khác, không sửa metadata
bằng tay để vượt kiểm tra. Build lại bootstrap từ cùng source sạch khi cần.

## 7. Delta update và lưu baseline

Release đầu **0.1.0 chỉ có Full Core**. Chưa có phiên bản public trước đó thì không tạo delta giả để phát hành. Các bản 0.1.1/0.1.2 trong test frozen chỉ là fixture cục bộ, không đổi version app và không đưa lên release.

Lưu nguyên `dist/HaizFlowCore` đã finalized của mỗi release ở archive nội bộ; gồm `BUILD-INFO.json`, `SHA256SUMS.txt`, licenses và mọi tệp. Không dùng thư mục `runtime`, không dùng Core đã chỉnh tay và không bỏ thư viện “ít dùng” khỏi baseline.

Khi release thực kế tiếp là 0.1.1, sau khi build Core 0.1.1 sạch/unsigned:

```powershell
.venv\Scripts\python.exe scripts\build-core-update.py `
  --base D:\ReleaseArchive\0.1.0\HaizFlowCore `
  --target dist\HaizFlowCore --output dist\delta-assets-0.1.1
```

Assembly tạo Full; lệnh trên tạo delta cùng manifest. Tên updater yêu cầu:

```text
HaizFlow-Core-0.1.1-windows-x64-full.zip
HaizFlow-Core-0.1.1-windows-x64-full.manifest.json
HaizFlow-Core-0.1.1-windows-x64-from-0.1.0.zip
HaizFlow-Core-0.1.1-windows-x64-from-0.1.0.manifest.json
```

Giữ Full trong mọi release để fallback. Delta chỉ cập nhật Core, **không cập nhật root launcher/updater hoặc engine/model**. Khi cần đổi protocol/bootstrap/layout, phát hành installer đầy đủ và kế hoạch tương thích riêng. Core mới có migration không rollback-safe không được lách manifest compatibility.

Updater kiểm nguồn GitHub repo cố định, metadata digest, SHA-256 package/từng tệp và inventory; staging riêng, không patch Core đang chạy; health xác nhận rồi mới chấp nhận phiên bản. Đây là kiểm toàn vẹn + nguồn HTTPS/repository, **không phải chữ ký detached của manifest hoặc hệ thống TUF**. Bảo vệ GitHub bằng 2FA/passkey, hạn chế quyền release, bảo vệ tag và runner/signing identity.

Kiểm thử delta local:

```powershell
.venv\Scripts\python.exe scripts\test-frozen-delta.py --artifact dist\HaizFlow-public --require-unsigned
```

Còn phải thử download qua GitHub release thật, gián đoạn/mạng yếu/ổ gần đầy và upgrade từ installer cũ trên VM. Kết quả fixture local không chứng minh toàn bộ hành trình mạng đã qua.

## 8. Phát hành GitHub Releases

Repo updater cố định: `MachHongHai/HaizFlow`. Repo khác cần sửa source và rebuild; không chỉ upload sang repo mới.

Chỉ sau khi tất cả gate và VM acceptance qua, bạn tự review/commit source, tag **đúng commit đã build**, push tag. Không dùng `git add .` nếu có tệp secret hoặc thay đổi không thuộc release. Không retag/thay bytes của phiên bản đã phát hành.

Assets release v0.1.0 gồm:

- `HaizFlow-0.1.0-UNSIGNED-Setup.exe` và `.exe.sha256`.
- Full Core ZIP và `.manifest.json` đúng tên.
- Changelog/release notes: yêu cầu máy, resource downloads, vị trí dữ liệu, trạng thái unsigned/caveat SmartScreen và Smart App Control, giấy phép/limitations.
- Có thể kèm checksum tổng, SBOM và evidence build; không kèm `.env`, API key, PFX, runtime, test fixtures hay installer DEVELOPMENT.

Các lệnh dưới **tạo/publish release bên ngoài**, chỉ chạy khi bạn chủ động phát hành. Đăng nhập bằng browser/token có quyền tối thiểu; không paste token vào chat hoặc repo.

```powershell
gh auth login
gh auth status
gh release create v0.1.0 --repo MachHongHai/HaizFlow --verify-tag --draft `
  --title 'HaizFlow 0.1.0' --notes-file docs\release-notes-0.1.0.md `
  dist\installer\HaizFlow-0.1.0-UNSIGNED-Setup.exe `
  dist\installer\HaizFlow-0.1.0-UNSIGNED-Setup.exe.sha256 `
  dist\release-assets-0.1.0\HaizFlow-Core-0.1.0-windows-x64-full.zip `
  dist\release-assets-0.1.0\HaizFlow-Core-0.1.0-windows-x64-full.manifest.json
```

`docs/release-notes-0.1.0.md` phải viết theo kết quả nghiệm thu thực, không có sẵn chứng nhận production. Kiểm tra draft có đủ asset, tải lại trên VM, verify hash và tên; trạng thái Authenticode của các executable HaizFlow sẽ là `NotSigned`. Nếu bật immutable releases, tải đủ assets **trước** publish; GitHub không cho thay assets/tag sau đó. Xem [quản lý release](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository) và [CLI create](https://cli.github.com/manual/gh_release_create).

Khi đã chốt stable:

```powershell
gh release edit v0.1.0 --repo MachHongHai/HaizFlow --draft=false --latest
```

Updater hiện lấy stable Latest, bỏ draft/prerelease. Không đặt release engine `resources-v1` hoặc bản DEVELOPMENT/test làm Latest. Bản unsigned stable đã qua các gate có thể làm Latest theo lựa chọn của chủ dự án. Giữ release assets public tải được không cần token người dùng. Sau publish, test metadata/digest/download bằng tài khoản/máy mới; release sau test delta từ bản đang public, không từ baseline tự dựng.

## 9. Khi có lỗi

- Installer từ chối upgrade: đóng app, hoàn tất cập nhật chờ; không xóa lock/pointer thủ công khi process còn chạy. Bộ cài thấp hơn bản active không được hạ phiên bản.
- Checksum sai: dừng; tải lại từ nguồn chính thức. Không regenerate hash trên file lỗi để “sửa”.
- Core lỗi startup: dùng rollback/repair có kiểm chứng; backup runtime trước mọi thao tác phục hồi, không đoán active version từ tên thư mục.
- Download engine không có URL: cần hoàn tất catalog phát hành; không phải lỗi key Gemini/Zernio.
- GPU không có model tương thích: kiểm tra app setting và engine/driver; CPU fallback phải phản ánh model thực tế. Không tự cài CUDA Toolkit để che lỗi đóng gói.
- Build yêu cầu chứng chỉ: dùng `UnsignedRelease` cho ứng viên công khai. Không dùng `AllowUnsigned`/`EngineeringBuild` để vượt gate public.
- Cảnh báo hoặc chặn bởi Windows: đối chiếu nguồn/hash và loại cảnh báo. Không tắt cơ chế bảo vệ hoặc bảo user cài certificate self-signed làm trusted root; một số máy sẽ không hỗ trợ chạy unsigned.

Chỉ kết luận release đạt khi có bằng chứng cho **đúng các bytes đã upload**, không chỉ khi source test qua.
