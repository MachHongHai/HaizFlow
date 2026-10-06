# Tiêu chuẩn sẵn sàng phát hành

Giấy phép mã thuộc sở hữu hiện hành là HaizFlow Source-Available 1.0, được chủ
sở hữu duyệt ngày 01/10/2026. Điều khoản ứng dụng/CLA/branding còn dự thảo. [Rà soát giấy phép](licensing-review.md)
ghi hồ sơ kỹ thuật về phạm vi quyền sở hữu, OmniVoice phi thương
mại và mẫu giọng, source tương ứng FFmpeg, nghĩa vụ LGPL của Qt. Chạy
`scripts/verify-legal-state.py`; đóng gói công khai cần thêm `--public-release`
cùng bằng chứng phê duyệt. Không kích hoạt dự thảo qua bộ cài hoặc hạn chế
quyền được cấp độc lập.

[Tài liệu](README.vi.md) · [An toàn dependency](dependency-security.vi.md) · [English](release-readiness.md)

Rà soát gần nhất: **2026-10-06**. Chủ dự án đã chọn hướng phát hành miễn phí, không ký Authenticode. Hồ sơ kỹ thuật không phải chứng nhận pháp lý độc lập.

Đây là checklist có thẩm quyền cho bản Windows công khai. Source checkout đạt unit test chưa đồng nghĩa artifact được phép phát hành.

## Quy ước trạng thái

- **Hoàn tất:** đã triển khai và có bằng chứng tự động.
- **Chặn phát hành:** không được phân phối công khai trước khi đạt điều kiện.
- **Cần hoàn tất trước production:** có thể chưa bắt buộc cho engineering build nội bộ nhưng phải đạt trước khi dùng rộng.

## Danh sách kiểm soát

| ID | Hạng mục | Trạng thái | Điều kiện |
| --- | --- | --- | --- |
| 1 | Định danh và xóa project | Hoàn tất | UUID, registered root, giữ legacy, kiểm shared-root/path traversal và test xóa. |
| 2 | License và third-party | **Chặn phát hành** | Giấy phép source hiện hành, quyền đã cấp/thông báo thành phần, review checkpoint OmniVoice, nghĩa vụ FFmpeg/GPL và duyệt phát hành. |
| 3 | Artifact tái lập sạch | **Chặn đến clean build** | Worktree đã commit sạch, gate đầy đủ, frozen smoke cô lập, metadata và checksum. |
| 4 | Installer và phát hành unsigned | **Chặn đến nghiệm thu** | Artifact sạch, ma trận Windows, công khai trạng thái không ký/giới hạn chính sách Windows. Certificate tùy chọn. |
| 5 | Integrity model | Hoàn tất | Revision/size/SHA-256 cho HY-MT2, Whisper, OmniVoice, OCR, Demucs, VAD và alignment. |
| 6 | Single instance | Hoàn tất | Local server theo user, activation handoff, stale recovery và smoke isolation. |
| 7 | Phục hồi project index | Hoàn tất | Lock, atomic write, backup, quarantine, rebuild manifest và chặn ghi khi không phục hồi được. |
| 8 | Migration schema | Hoàn tất cho schema hiện tại | Migration tuần tự, backup, default, legacy root, từ chối future schema; version phải khớp source release. |
| 9 | Dependency tái lập | Hoàn tất | Lock có hash cho Windows/Python 3.13, CUDA variant, fingerprint và verify environment. |
| 10 | Disk và cache | Hoàn tất cho tooling | Preflight Core từ artifact, ước tính riêng từng gói, headroom, partial resume và cache Manual có giới hạn. |
| 11 | Offline/privacy claim | Hoàn tất | UI/tài liệu phân biệt xử lý trên máy với tải model, dịch Gemini, nhập URL và đăng mạng xã hội. |
| 12 | Chẩn đoán | Hoàn tất | Log xoay vòng, build ID, bắt lỗi Python/thread/Qt và diagnostic redact không chứa media. |
| 13 | Shutdown/phục hồi | Hoàn tất | Confirm, pause/cancel, chờ worker hữu hạn, child-process containment và phục hồi video gián đoạn. |
| 14 | Runtime containment | Hoàn tất | Frozen data mutable nằm dưới install root; source mode dùng `HAIZFLOW_HOME`. |
| 15 | Source hygiene | **Chặn đến clean build** | Không còn output/source cũ, tài liệu khớp kiến trúc và `git status --porcelain` rỗng. |
| 16 | Audit vulnerability | Hoàn tất với ngoại lệ | Chỉ còn ngoại lệ đã duyệt trong [dependency-security.vi.md](dependency-security.vi.md). |
| 17 | Zernio | Cần hoàn tất trước production | E2E bằng tài khoản thật cho từng nền tảng, quota, recovery, consent và điều khoản hiện hành. |
| 18 | Engine AI độc lập | **Chặn đến khi pin archive** | Archive CPU, CUDA 12.8, vision; URL/size/SHA-256 thật; profile smoke; nghiệm thu install/resume/rollback/remove. Có chế độ public unsigned. |

## License gate

Nguồn chính thức: [Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html), [FFmpeg legal](https://ffmpeg.org/legal.html), [FFmpeg license](https://ffmpeg.org/doxygen/trunk/md_LICENSE.html), [HY-MT2](https://huggingface.co/tencent/Hy-MT2-1.8B), [Whisper](https://huggingface.co/openai/whisper-large-v3-turbo), [OmniVoice source](https://github.com/k2-fsa/OmniVoice), [OmniVoice model](https://huggingface.co/k2-fsa/OmniVoice).

Artifact phải có:

```text
LICENSE.txt
NOTICE.txt
THIRD_PARTY_NOTICES.md
licenses/
BUILD-INFO.json
SHA256SUMS.txt
```

`scripts/generate-third-party-notices.py --strict` phải đạt. License source HaizFlow không thay license của model/font/codec/dependency. SDK và checkpoint OmniVoice cần phân tích riêng; chỉ kèm source archive FFmpeg upstream chưa đủ chứng minh hoàn tất mọi nghĩa vụ corresponding source của thành phần GPL liên kết tĩnh.

## Gate source

Chạy từ checkout đã commit sạch:

```powershell
.\scripts\test.ps1
.\scripts\audit-dependencies.ps1
```

Gate compile Python, correctness lint, unit/integration và yêu cầu `qmllint` sạch. Không ghi số test cố định trong tài liệu; output của release commit là bằng chứng có thẩm quyền.

## Gate frozen artifact

Entrypoint duy nhất:

```powershell
.\scripts\build-exe.ps1 -CoreLayout -UnsignedRelease
```

Build phải kiểm source/dependency/native tool/notice, xóa đúng target artifact cũ, tạo PyInstaller `onedir`, chép license, chứng minh không nhúng engine/model lớn hoặc chưa pin (ngoại lệ duy nhất là model speaker CPU tích hợp có hash), chạy frozen/FFmpeg/QML smoke cô lập, sau đó mới tạo và verify `BUILD-INFO.json` cùng `SHA256SUMS.txt`.

Chỉ khi kiểm thử nội bộ trên working tree đang phát triển mới dùng:

```powershell
.\scripts\build-exe.ps1 -AllowDirtyBuild -AllowUnsigned
```

`-AllowUnsigned` chỉ dùng nội bộ. `-UnsignedRelease` là lựa chọn phát hành không ký của chủ dự án; vẫn bắt buộc giấy phép, tài nguyên và source sạch. `-AllowDirtyBuild` ghi rõ provenance chưa sạch và artifact không đủ điều kiện public. Không kết hợp các chế độ này. Xem [hướng dẫn đầy đủ](windows-release-setup.vi.md).

Engine AI và model lớn là các gói tài nguyên tùy chọn, không thuộc payload Core. Model speaker CPU nhỏ tích hợp là ngoại lệ pinned. Trình quản lý chỉ cài gói người dùng xác nhận, kiểm checksum bất biến và chỉ kích hoạt engine sau smoke test. `prepare-offline-models.ps1` chỉ phục vụ probe phát triển.

## Gate installer

```powershell
.\scripts\build-installer.ps1 -ArtifactPath .\dist\HaizFlow-public -UnsignedRelease -SkipInstallerSmokeTest
```

Installer phải tính disk từ artifact, cho chọn ổ local writable, chặn network path, giữ runtime data khi upgrade và chỉ xóa data sau lựa chọn uninstall riêng. Silent uninstall luôn giữ data.

Các con số dung lượng có ý nghĩa khác nhau. Setup tính yêu cầu Core từ artifact hoàn tất, staging thực tế, bản sao tạm khi nâng cấp và 2 GiB dự phòng vận hành. Con số đó không gồm gói AI tùy chọn, media dự án, output hoặc cache. Gate từ chối Core lớn hơn 1,25 GiB, yêu cầu cài mới lớn hơn 4 GiB hoặc mức khuyến nghị lớn hơn 8 GiB. Trình quản lý gói chạy preflight riêng cho từng lượt cài đã xác nhận: byte còn phải tải, dung lượng cài, bản rollback và 2 GiB dự phòng. Export có ước tính riêng theo thời lượng, codec, bitrate và render tạm. Manifest sinh từ artifact cùng số Setup hiển thị là nguồn chính xác; tài liệu không được dùng lại số đo của một candidate cũ.

Bản công khai có thể dùng `UnsignedRelease`, không cần certificate. Phải thông báo Unknown publisher, cảnh báo/chặn SmartScreen hoặc Smart App Control và chính sách doanh nghiệp; không tắt bảo vệ Windows. Builder kiểm cài, mở app, repair, gỡ/cài lại, giữ dữ liệu và hash bằng fixture có cùng payload và logic public nhưng AppId riêng, tránh đụng bản user đã cài. Đây không phải nghiệm thu trên mọi cấu hình Windows. Kiểm chính installer public trên VM sạch bằng `AllowRegisteredInstall` vẫn là kiểm bổ sung được khuyến nghị; phải ghi rõ máy và artifact đã kiểm, không suy ra Windows 10 từ Windows 11. Bỏ toàn bộ smoke làm mất tư cách release candidate.

Chỉ để kiểm thử kỹ thuật cục bộ, có thể tạo installer chưa ký từ artifact đủ điều kiện:

```powershell
.\scripts\build-installer.ps1 -ArtifactPath .\dist\HaizFlow-development -AllowUnsigned -EngineeringBuild
```

Tên file nội bộ có `DEVELOPMENT`. Bộ cài công khai có tên `HaizFlow-<version>-Setup.exe`; trạng thái chữ ký được ghi riêng trong tài liệu. Với ứng viên public không ký, chỉ chạy lệnh sau trong VM sạch:

```powershell
.\scripts\test-installer.ps1 -InstallerPath .\dist\installer\HaizFlow-<version>-Setup.exe -AllowRegisteredInstall
```

## Ma trận Windows

- Windows 10 phiên bản 1809 trở lên và Windows 11 x64 sạch.
- CPU-only Intel/AMD với RAM đại diện 16/24/32 GB.
- NVIDIA 7/8/12 GB VRAM và lớn hơn; không hỗ trợ BF16; driver thiếu/cũ.
- Mở Core khi offline, mạng chậm và tải gói gián đoạn.
- URL công khai, extractor đổi, cookie, rate limit và cancel.
- Tài khoản/path/file Unicode và nhập tiếng Việt bằng IME.
- Ổ gần đầy, ổ local khác, removable drive, sleep/hibernate, GPU gián đoạn.
- Seek/source swap lặp, shutdown audio, pause/resume/restart, batch dài.
- Upgrade mọi schema được hỗ trợ và phục hồi index hỏng.
- Tài khoản Zernio test cho từng nền tảng trước production.

## Gate gói engine

Core và engine là các release unit riêng. Trước khi build Core công khai, phải build từng engine từ lock hash đã review với `UnsignedRelease`, chạy profile smoke, tải ZIP lên URL bất biến rồi dùng `finalize-resource-pack.py` ghi URL, dung lượng nén, dung lượng cài và SHA-256 thật. `verify-resource-pack-manifest.py --strict` phải đạt; metadata ước lượng hoặc để trống là blocker. Không cần certificate trong hướng unsigned đã chọn.

Nghiệm thu gồm tải gián đoạn/resume, từ chối checksum sai, active atomic, rollback khi smoke lỗi, gỡ an toàn, chuyển resource sang ổ local khác và chặn gỡ engine đang dùng. Máy chỉ cài Core vẫn phải mở Home và chỉnh media mà không import package suy luận.

## Quyết định

Engineering build nội bộ có thể dùng để kiểm chứng nếu ghi rõ phạm vi và trạng thái unsigned. Phát hành công khai vẫn bị chặn cho tới khi hoàn tất review pháp lý/license, pin archive engine, clean artifact tái lập, source hygiene và nghiệm thu Windows. Chữ ký không còn là điều kiện của hướng miễn phí. Tài liệu này ghi bằng chứng kỹ thuật, không thay tư vấn pháp lý chuyên môn.
