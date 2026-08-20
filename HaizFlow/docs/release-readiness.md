# Tiêu chuẩn sẵn sàng phát hành

Tài liệu này là nguồn duy nhất theo dõi các rủi ro phát hành của ứng dụng Windows. Mỗi bản release phải cập nhật trạng thái, chạy toàn bộ release gate và lưu `BUILD-INFO.json` cùng `SHA256SUMS.txt` trong artifact.

Ngày rà soát: 2026-08-20

## Quy ước trạng thái

- **Hoàn tất:** đã có implementation và kiểm thử tự động.
- **Chặn phát hành:** chưa được phép phát hành công khai cho đến khi điều kiện được đáp ứng.
- **Còn lại:** chưa phải blocker của beta nội bộ nhưng phải xử lý trước production rộng.

## Danh sách kiểm soát

| ID | Hạng mục | Trạng thái | Điều kiện nghiệm thu |
| --- | --- | --- | --- |
| 1 | Định danh và xóa project an toàn | **Hoàn tất** | Project mới dùng UUID; project đơn/batch cùng tên có root riêng; legacy root được giữ; manifest, shared-root và path traversal được kiểm tra trước khi xóa. |
| 2 | License và third-party compliance | **Runtime đã nâng cấp, còn legal gate** | Source code dùng Apache-2.0; FFmpeg đã nâng lên 8.1.2 Essentials, pin SHA-256 và kèm source archive có chữ ký. Build sinh notices từ đúng `.venv`. OmniVoice SDK dùng Apache-2.0 nhưng checkpoint dùng CC-BY-NC-4.0, vì vậy phải được duyệt riêng trước mọi phát hành hoặc mục đích thương mại. Trước khi công khai vẫn phải cung cấp corresponding source/build material của các thư viện GPL liên kết tĩnh và được người chịu trách nhiệm pháp lý duyệt. |
| 3 | Frozen acceptance và artifact mới | **Chặn phát hành cho đến khi source sạch** | Build xóa artifact cũ có kiểm soát, chạy dependency/native-tool check và Qt/QML smoke trong một home/model/cache/temp cô lập; sau smoke mới tạo metadata/checksum. Release gate từ chối mọi model bị nhúng nhầm dưới `_internal/models`. `dist/` không được commit, nên mỗi revision phát hành phải được commit trước, rồi build và nghiệm thu artifact mới. Artifact ngày 2026-07-16 chỉ là bằng chứng lịch sử, không thay thế nghiệm thu revision hiện tại. |
| 4 | Installer, nâng cấp và code signing | **Chờ certificate và artifact sạch** | Có định nghĩa Inno Setup, kiểm tra dung lượng theo artifact thật, version resource/icon và cơ chế ký Authenticode. Cần certificate thật, artifact từ worktree sạch và nghiệm thu trên Windows sạch trước khi ký EXE/installer. |
| 5 | Khóa revision và checksum model | **Hoàn tất** | HY-MT2 GPU/CPU, Whisper small, Whisper large-v3-turbo, OmniVoice, OCR, Demucs và năm model alignment đều khóa immutable revision, kích thước và full SHA-256. Pipeline không chấp nhận model Whisper từ biến môi trường hoặc tự tải vào cache. Installer không chứa model; bootstrap lần chạy đầu tải atomic vào `runtime\models`, có progress/cancel/retry và xác minh trước khi nạp. |
| 6 | Single-instance ứng dụng | **Hoàn tất** | `QLocalServer` tạo named pipe theo user. Instance thứ hai gửi yêu cầu activate rồi thoát; instance chính khôi phục cửa sổ. Stale server được xử lý và smoke mode không chiếm khóa. Khóa file/index là phạm vi riêng của ID 7. |
| 7 | Phục hồi project index | **Hoàn tất** | `projects.json` được khóa liên tiến trình, ghi atomic, giữ last-known-good `.bak`, sao chép bản hỏng sang quarantine và rebuild từ manifest trong các project root đã đăng ký. Backup được hợp nhất với manifest mới hơn; lỗi không thể phục hồi chặn ghi thay vì tạo index rỗng. |
| 8 | Schema migration | **Hoàn tất** | Project metadata dùng schema v4, video metadata dùng schema v13. Migration tuần tự giữ backup, chuyển định danh `job` cũ, bổ sung checkpoint/settings mới, giữ project root legacy và từ chối schema tương lai. |
| 9 | Dependency lock tái lập | **Hoàn tất** | `requirements-lock-py313-win64.txt` khóa toàn bộ dependency trực tiếp/gián tiếp bằng SHA-256 cho Windows x64/Python 3.13; Torch khóa đúng biến thể cu128. Manifest fingerprint phát hiện source/lock lệch, installer dùng `--require-hashes`, build gate đối chiếu toàn bộ `.venv`. |
| 10 | Disk preflight và cache policy | **Hoàn tất cho build/installer** | Bootstrap tính đúng số byte model còn thiếu cộng 1 GiB headroom và tính cả phần `.part` có thể resume. Installer tính từ artifact thật, giữ hai bản khi upgrade, cộng 2 GiB workspace và dự trù bộ model CPU/GPU lần đầu lớn hơn theo chính manifest checksum. Với artifact dev hiện tại khoảng 5,66 GiB, preflight yêu cầu khoảng 19,36 GiB cho cài mới và 25,02 GiB cho upgrade. Model vẫn không nằm trong installer; chúng được tải sau lần mở đầu vào chính `{app}\runtime\models`. |
| 11 | Mô tả offline và quyền riêng tư | **Hoàn tất** | Lần chạy đầu nói rõ cần Internet để tải model; sau khi checksum hợp lệ, Whisper/HY-MT2/OmniVoice/Demucs/media xử lý local. Settings nói rõ Edge TTS nhận văn bản phụ đề, nhập URL/kênh kết nối nền tảng tương ứng và hành vi khi offline. README và UI nói rõ đăng mạng xã hội là tùy chọn cloud: video được tải qua Zernio tới nền tảng đã chọn và API key nằm trong Windows Credential Manager. |
| 12 | Chẩn đoán production | **Hoàn tất** | App log xoay vòng 5 MiB × 4 file; bắt lỗi main thread, Python worker, unraisable exception và Qt message. Artifact có build ID. Settings xuất ZIP diagnostics đã redaction, giới hạn kích thước và không lấy tên/media/log project. |
| 13 | Shutdown và phục hồi video gián đoạn | **Hoàn tất** | Close event hỏi xác nhận khi còn xử lý/tải; active video được pause, subprocess tree bị dừng, queue từ chối việc mới và chờ worker. Windows Job Object dọn process con khi app crash; lần mở sau chuyển metadata `processing` còn sót thành `paused` có thể resume. Smoke mode luôn dùng data tạm thay vì `.env` thật. |
| 14 | Portable storage theo thư mục cài đặt | **Hoàn tất** | Trong frozen build, thư mục được chọn ở wizard là hard boundary: model tải sau cài đặt, Qt/QML, Torch, Hugging Face, pip/uv, CUDA/Numba, temp, log và settings đều nằm dưới `{app}\runtime`. User có thể chọn ổ C, D, E hoặc ổ khác miễn có quyền ghi. Source mode vẫn có thể dùng `HAIZFLOW_HOME`; smoke xác nhận không thoát khỏi boundary được cấu hình. |
| 15 | Hygiene source và cấu trúc desktop | **Chặn release build** | Hai utility không dùng đã bị xóa; thư mục `build/` phải rỗng trước clean build. Chín desktop controller sau refactor, QML facade và tài liệu kiến trúc phải cùng nằm trong một commit; `git status --porcelain` phải rỗng trước khi chạy build release. |
| 16 | Audit lỗ hổng dependency | **Hoàn tất với ngoại lệ có kiểm soát** | `pip` đã nâng 26.1.2; `scripts/audit-dependencies.ps1` dùng pip-audit pin version và fail với mọi advisory mới. Wheel CUDA `+cu128` được quét thêm bằng version PyTorch canonical. Ngoại lệ Transformers/DiskCache/PyTorch bị giới hạn đúng ID, có threat model, biện pháp giảm thiểu và hạn rà soát trong `docs/dependency-security.md`; alignment checkpoint không pin đã bị vô hiệu hóa. |
| 17 | Đăng mạng xã hội qua Zernio | **Còn lại trước production** | Source dùng REST API/OAuth của Zernio, upload tuần tự, idempotency key ổn định, consent rõ ràng và không còn Playwright/cookie/DOM automation. Unit test phải đạt; trước release công khai vẫn phải nghiệm thu end-to-end với tài khoản thật trên từng nền tảng được hỗ trợ, quota/gói dịch vụ hiện hành và điều khoản của các bên. |

## License gate

Các nguồn chính thức dùng để xác định nghĩa vụ:

- Qt for Python licensing: https://doc.qt.io/qtforpython-6/licenses.html
- FFmpeg legal checklist: https://ffmpeg.org/legal.html
- FFmpeg license: https://ffmpeg.org/doxygen/trunk/md_LICENSE.html
- HY-MT2 model card: https://huggingface.co/tencent/Hy-MT2-1.8B
- Whisper large-v3-turbo model card: https://huggingface.co/openai/whisper-large-v3-turbo
- OmniVoice source và language table: https://github.com/k2-fsa/OmniVoice
- OmniVoice checkpoint/license: https://huggingface.co/k2-fsa/OmniVoice
- Edge TTS repository và mô tả online service: https://github.com/rany2/edge-tts

Mỗi artifact phải chứa:

```text
LICENSE.txt
NOTICE.txt
THIRD_PARTY_NOTICES.md
licenses/
BUILD-INFO.json
SHA256SUMS.txt
```

`scripts/generate-third-party-notices.py --strict` phải thành công. Runtime hiện dùng `8.1.2-essentials_build-www.gyan.dev`, được pin bằng binary SHA-256 và manifest. Artifact kèm source archive chính thức `ffmpeg-8.1.2.tar.xz`, chữ ký PGP, license và README của binary package. Người phát hành vẫn phải cung cấp complete corresponding source/build material của các thư viện GPL được liên kết tĩnh; riêng tarball FFmpeg upstream chưa đủ để tự khẳng định hoàn tất toàn bộ nghĩa vụ này.

## Frozen release gate

Artifact frozen dev đã được build lại và nghiệm thu ngày 2026-07-27. Vì worktree cố ý còn dirty trên nhánh test và installer chưa có Authenticode certificate, artifact này chỉ dùng để kiểm chứng kỹ thuật, không phải release candidate công khai.

Kết quả kiểm chứng source hiện tại (2026-08-20):

- Bộ `scripts/test.ps1` phải đạt hoàn toàn ở commit phát hành; không ghi cố định số test trong tài liệu để tránh số liệu cũ.
- Qt/QML source smoke test thành công.
- Runtime gate xác nhận Whisper small/large-v3-turbo, OmniVoice, HY-MT2 CPU/GPU, OCR, Demucs và cả năm model alignment, CPU/GPU native runtime và FFmpeg.
- Integration test liên tiến trình xác nhận instance thứ hai kích hoạt instance chính rồi thoát.

Mốc frozen dev hiện tại:

- Artifact: `dist\HaizFlow`, PyInstaller onedir, không nhúng model.
- Quy mô: 11.497 file, 5,373 GiB.
- Đã đối chiếu thành công toàn bộ 11.497 SHA-256 trong `SHA256SUMS.txt`.
- Bộ unit/integration test và `qmllint` tại thời điểm đóng băng artifact đã thành công; frozen self-test, FFmpeg/FFprobe, CPU/GPU runtime gate và Qt/QML startup đều thành công.
- Installer Inno Setup dev r2 có kích thước 2.240.951.379 byte. Smoke cài trên ổ D xác minh đủ 11.497 checksum, đủ 13 file `torch\_inductor\runtime`, không có checkpoint model; frozen QML startup từ thư mục đã cài exit 0.
- Silent uninstall xóa EXE/payload nhưng giữ duy nhất `runtime\` và marker dữ liệu thử nghiệm.
- `BUILD-INFO.json` ghi rõ commit, branch, dirty state, Python, `model_delivery=first-run-download` và xác nhận mọi cờ `bundled_*_model` là `false`.

Build chuẩn:

```powershell
.\scripts\build-exe.ps1
```

Artifact phát hành luôn được build không kèm model bằng `.\scripts\build-exe.ps1`. `prepare-offline-models.ps1` chỉ dùng trên máy phát triển để chạy các probe chất lượng runtime, không phải đầu vào đóng gói.

Quy trình bắt buộc của script:

1. Chạy compile, toàn bộ unit/integration test và `qmllint`; mọi diagnostic QML đều chặn build.
2. Kiểm tra source runtime, package version và audit dependency.
3. Sinh third-party notices ở strict mode.
4. Xóa riêng artifact `dist\HaizFlow` cũ sau khi xác thực đường dẫn.
5. Build PyInstaller `--onedir`.
6. Chép application license, notices và license texts.
7. Tính dung lượng cài đặt từ artifact thực tế; build bị chặn nếu ổ đích không đủ không gian an toàn.
8. Chạy frozen self-test, FFmpeg/FFprobe và xác nhận `_internal/models` không chứa payload.
9. Kiểm tra manifest bootstrap model đã pin URL, size và SHA-256.
10. Khởi tạo Qt/QML/Multimedia bằng data tạm, không tải/warm model, rồi tự thoát.
11. Sau smoke mới tạo `BUILD-INFO.json`, SHA-256, rồi tự xác minh lại toàn bộ manifest.

`BUILD-INFO.json` chứa `build_id` theo dạng `<version>+<12 ký tự commit>`; installer eligibility đối chiếu build ID, version và toàn bộ commit trước khi đóng gói.

`HaizFlow.spec` không còn là entrypoint build để tránh hai cấu hình PyInstaller khác nhau. Chỉ dùng `scripts\build-exe.ps1`; script cố định `cwd`, `distpath`, `workpath` và `specpath` dưới repository. Version resource và icon được sinh từ source trước khi chạy PyInstaller.

## Installer

`scripts\build-installer.ps1` chỉ nhận artifact đã có `SHA256SUMS.txt` hợp lệ, rồi gọi `installer\HaizFlow.iss`. Wizard mặc định dùng `{localappdata}\Programs\HaizFlow`, ghi nhớ đường dẫn cài trước và cho user chọn bất kỳ thư mục writable nào trên ổ local C, D, E hoặc ổ local khác; UNC và mapped network drive bị chặn vì model/runtime cần semantics filesystem local. Thư mục đích của cài mới phải rỗng hoặc chỉ chứa `runtime\` được giữ lại; upgrade phải có đủ EXE, `BUILD-INFO.json` và payload `_internal`, tránh xóa nhầm nội dung của thư mục không phải HaizFlow. Frozen app lấy chính `{app}` làm install root; không có drive hardcode. Release eligibility cấm root `runtime\` xuất hiện trong artifact; installer tạo thư mục này riêng và không dùng wildcard `Excludes`, vì wildcard đó có thể làm mất dependency như `torch\_inductor\runtime`. `[InstallDelete]` và uninstall mặc định không xóa dữ liệu mutable. Uninstaller chỉ xóa runtime sau câu hỏi xác nhận riêng; silent uninstall luôn giữ dữ liệu. Script tính riêng dung lượng cài mới/nâng cấp từ artifact thật, sinh icon `.ico` đa kích thước và có thể ký EXE/installer khi được cấp certificate qua `-SignCertificatePath` cùng biến môi trường `HAIZFLOW_SIGN_CERT_PASSWORD`; không có certificate thì artifact vẫn chỉ là unsigned RC.

`-SkipFrozenSmokeTest` chỉ dành cho chẩn đoán build, không được dùng để tạo artifact phát hành.

Audit dependency bắt buộc trước release:

```powershell
.\scripts\audit-dependencies.ps1
```

## Ma trận nghiệm thu trước production

- Windows 10 và Windows 11 x64 sạch.
- Máy CPU-only Intel và AMD với 8 GB, 16 GB và 32 GB RAM.
- NVIDIA 6 GB, 8 GB và lớn hơn; GPU không hỗ trợ BF16; driver cũ hoặc thiếu driver.
- Không mạng, mạng chậm, Edge TTS gián đoạn và URL extractor thay đổi.
- Tài khoản Windows và đường dẫn project có Unicode.
- Ổ gần đầy, project trên ổ rời, sleep/hibernate và mất nguồn GPU giữa pipeline.
- Mở app hai lần, nâng cấp từ dữ liệu legacy, pause/resume/restart và batch queue dài.

## Quyết định phát hành

Beta nội bộ được phép khi ID 1 và ID 3 đã qua release gate. Phát hành công khai bị chặn cho đến khi hoàn tất tối thiểu ID 2, 4, 5, 9 và 11. Tài liệu này không thay thế tư vấn pháp lý chuyên môn.
