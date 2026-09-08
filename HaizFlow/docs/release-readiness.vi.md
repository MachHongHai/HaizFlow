# Tiêu chuẩn sẵn sàng phát hành

[Tài liệu](README.vi.md) · [An toàn dependency](dependency-security.vi.md) · [English](release-readiness.md)

Rà soát gần nhất: **2026-09-08**

Đây là checklist có thẩm quyền cho bản Windows công khai. Source checkout đạt unit test chưa đồng nghĩa artifact được phép phát hành.

## Quy ước trạng thái

- **Hoàn tất:** đã triển khai và có bằng chứng tự động.
- **Chặn phát hành:** không được phân phối công khai trước khi đạt điều kiện.
- **Cần hoàn tất trước production:** có thể chưa bắt buộc cho engineering build nội bộ nhưng phải đạt trước khi dùng rộng.

## Danh sách kiểm soát

| ID | Hạng mục | Trạng thái | Điều kiện |
| --- | --- | --- | --- |
| 1 | Định danh và xóa project | Hoàn tất | UUID, registered root, giữ legacy, kiểm shared-root/path traversal và test xóa. |
| 2 | License và third-party | **Chặn phát hành** | Notice Apache, license bên thứ ba, review checkpoint OmniVoice, nghĩa vụ FFmpeg/GPL và duyệt pháp lý. |
| 3 | Artifact tái lập sạch | **Chặn đến clean build** | Worktree đã commit sạch, gate đầy đủ, frozen smoke cô lập, metadata và checksum. |
| 4 | Installer và ký số | **Chặn bản công khai** | Artifact sạch, ma trận Windows, certificate Authenticode thật và verify chữ ký. |
| 5 | Integrity model | Hoàn tất | Revision/size/SHA-256 cho HY-MT2, Whisper, OmniVoice, OCR, Demucs, VAD và alignment. |
| 6 | Single instance | Hoàn tất | Local server theo user, activation handoff, stale recovery và smoke isolation. |
| 7 | Phục hồi project index | Hoàn tất | Lock, atomic write, backup, quarantine, rebuild manifest và chặn ghi khi không phục hồi được. |
| 8 | Migration schema | Hoàn tất cho schema hiện tại | Migration tuần tự, backup, default, legacy root, từ chối future schema; version phải khớp source release. |
| 9 | Dependency tái lập | Hoàn tất | Lock có hash cho Windows/Python 3.13, CUDA variant, fingerprint và verify environment. |
| 10 | Disk và cache | Hoàn tất cho tooling | Preflight từ artifact, dự trù model, headroom, partial resume và cache Manual có giới hạn. |
| 11 | Offline/privacy claim | Hoàn tất | UI/tài liệu phân biệt local với tải model, Edge TTS, URL import và social publishing. |
| 12 | Chẩn đoán | Hoàn tất | Log xoay vòng, build ID, bắt lỗi Python/thread/Qt và diagnostic redact không chứa media. |
| 13 | Shutdown/phục hồi | Hoàn tất | Confirm, pause/cancel, chờ worker hữu hạn, child-process containment và phục hồi video gián đoạn. |
| 14 | Runtime containment | Hoàn tất | Frozen data mutable nằm dưới install root; source mode dùng `HAIZFLOW_HOME`. |
| 15 | Source hygiene | **Chặn đến clean build** | Không còn output/source cũ, tài liệu khớp kiến trúc và `git status --porcelain` rỗng. |
| 16 | Audit vulnerability | Hoàn tất với ngoại lệ | Chỉ còn ngoại lệ đã duyệt trong [dependency-security.vi.md](dependency-security.vi.md). |
| 17 | Zernio | Cần hoàn tất trước production | E2E bằng tài khoản thật cho từng nền tảng, quota, recovery, consent và điều khoản hiện hành. |

## License gate

Nguồn chính thức: [Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html), [FFmpeg legal](https://ffmpeg.org/legal.html), [FFmpeg license](https://ffmpeg.org/doxygen/trunk/md_LICENSE.html), [HY-MT2](https://huggingface.co/tencent/Hy-MT2-1.8B), [Whisper](https://huggingface.co/openai/whisper-large-v3-turbo), [OmniVoice source](https://github.com/k2-fsa/OmniVoice), [OmniVoice model](https://huggingface.co/k2-fsa/OmniVoice), [Edge TTS](https://github.com/rany2/edge-tts).

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
$env:HAIZFLOW_SIGN_CERT_PASSWORD = "<mật-khẩu-certificate>"
.\scripts\build-exe.ps1 -SignCertificatePath C:\secure\haizflow-signing.pfx
```

Build phải kiểm source/dependency/native tool/notice, xóa đúng target artifact cũ, tạo PyInstaller `onedir`, chép license, chứng minh không nhúng model, chạy frozen/FFmpeg/QML smoke cô lập, sau đó mới tạo và verify `BUILD-INFO.json` cùng `SHA256SUMS.txt`.

Chỉ khi kiểm thử nội bộ trên working tree đang phát triển mới dùng:

```powershell
.\scripts\build-exe.ps1 -AllowDirtyBuild -AllowUnsigned
```

`-AllowUnsigned` không tạo release candidate công khai. `-AllowDirtyBuild` ghi rõ provenance chưa sạch và artifact đó không đủ điều kiện đi qua public installer gate.

Model là download lần đầu, không phải payload installer. `prepare-offline-models.ps1` chỉ phục vụ probe phát triển.

## Gate installer

```powershell
.\scripts\build-installer.ps1 -SignCertificatePath C:\secure\haizflow-signing.pfx
```

Installer phải tính disk từ artifact, cho chọn ổ local writable, chặn network path, giữ runtime data khi upgrade và chỉ xóa data sau lựa chọn uninstall riêng. Silent uninstall luôn giữ data.

Bản công khai cần certificate thật qua `-SignCertificatePath` và `HAIZFLOW_SIGN_CERT_PASSWORD`, rồi verify chữ ký. Build installer tự cài im lặng vào thư mục cô lập, chạy installed-layout smoke, gỡ cài đặt, kiểm dữ liệu runtime được giữ lại và verify checksum. `-SkipFrozenSmokeTest` và `-SkipInstallerSmokeTest` chỉ dùng chẩn đoán và làm artifact mất tư cách release candidate.

Chỉ để kiểm thử kỹ thuật cục bộ, có thể tạo installer chưa ký từ artifact đủ điều kiện:

```powershell
.\scripts\build-installer.ps1 -AllowUnsigned
```

Tên file luôn có `UNSIGNED`. Có thể chạy lại installer smoke riêng:

```powershell
.\scripts\test-installer.ps1 -InstallerPath .\dist\installer\HaizFlow-<version>-Setup.exe -RequireSignature
```

## Ma trận Windows

- Windows 10 phiên bản 1809 trở lên và Windows 11 x64 sạch.
- CPU-only Intel/AMD với RAM đại diện 8/16/32 GB.
- NVIDIA 6/8 GB và lớn hơn; không hỗ trợ BF16; driver thiếu/cũ.
- Offline lần đầu, mạng chậm, download model gián đoạn, Edge TTS lỗi.
- URL công khai, extractor đổi, cookie, rate limit và cancel.
- Tài khoản/path/file Unicode và nhập tiếng Việt bằng IME.
- Ổ gần đầy, ổ local khác, removable drive, sleep/hibernate, GPU gián đoạn.
- Seek/source swap lặp, shutdown audio, pause/resume/restart, batch dài.
- Upgrade mọi schema được hỗ trợ và phục hồi index hỏng.
- Tài khoản Zernio test cho từng nền tảng trước production.

## Quyết định

Engineering build nội bộ có thể dùng để kiểm chứng nếu ghi rõ phạm vi và trạng thái unsigned. Phát hành công khai vẫn bị chặn cho tới khi hoàn tất review pháp lý/license, clean artifact tái lập, source hygiene, nghiệm thu Windows và Authenticode. Tài liệu này ghi bằng chứng kỹ thuật, không thay tư vấn pháp lý chuyên môn.
