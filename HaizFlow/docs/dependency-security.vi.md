# Chính sách an toàn dependency và model

[Tài liệu](README.vi.md) · [Sẵn sàng phát hành](release-readiness.vi.md) · [English](dependency-security.md)

Rà soát gần nhất: **2026-09-08**  
Rà soát tiếp theo: **trước mọi release và không muộn hơn 2026-10-08**

Tài liệu xác định trust boundary cho Python package, native tool và model artifact. Ngoại lệ được liệt kê chỉ có hiệu lực tạm thời và không cho phép bỏ qua advisory mới.

## Audit bắt buộc

```powershell
.\scripts\audit-dependencies.ps1
```

Script audit chính environment sẽ đóng gói bằng `pip-audit` đã pin. Advisory mới làm release gate thất bại nếu chưa có định danh, threat model, biện pháp giảm thiểu, thời hạn và ghi nhận tại đây. Production phải khớp `pyproject.toml`, `requirements-lock-py313-win64.txt` có SHA-256 và `dependency-lock-manifest.json`.

## Kiểm soát nền

- Lock Windows cố định version và SHA-256. Khi đồng bộ environment, uv chỉ dùng `unsafe-first-match` để tìm đúng version đã khóa qua các index riêng của PyTorch, llama.cpp và PyPI; không dùng best-match không ràng buộc.
- Repository, revision bất biến, filename, size và full SHA-256 của model được khóa trong bootstrap manifest.
- Download được staging và chỉ promote atomic sau khi verify.
- HY-MT2 dùng `local_files_only=True`, `use_safetensors=True`, `trust_remote_code=False`.
- Loader nhận đường local đã verify và không fallback sang model download không pin.
- Release artifact không được nhúng nhầm model.
- Checkpoint tùy ý của người dùng không được coi là production model đáng tin.

## Ngoại lệ có kiểm soát

### Transformers 4.57.6

Ngoại lệ tạm: [PYSEC-2025-217](https://osv.dev/vulnerability/PYSEC-2025-217), [PYSEC-2026-2288](https://osv.dev/vulnerability/PYSEC-2026-2288), [PYSEC-2026-2289](https://osv.dev/vulnerability/PYSEC-2026-2289), [PYSEC-2026-2290](https://osv.dev/vulnerability/PYSEC-2026-2290), [CVE-2026-9856](https://github.com/advisories/GHSA-xrqw-3rrv-vx5w).

Các lỗi nằm ở đường nạp checkpoint/config không tin cậy, Trainer/conversion hoặc ghi `chat_template` do caller kiểm soát qua `save_pretrained()`. Ứng dụng chỉ nạp HY-MT2 cố định đã verify, bắt buộc safetensors, chặn remote code và không gọi `save_pretrained()` của tokenizer/processor. Chỉ nâng Transformers 5 sau khi cách diễn giải cấu hình RoPE của HY-MT2 qua compatibility và translation-quality gate.

### NLTK 3.10.3

Ngoại lệ tạm: [PYSEC-2026-3740 / CVE-2026-81726](https://github.com/advisories/GHSA-8mgp-746c-j5xp).

NLTK 3.10.3 đã sửa các advisory trước đó về parser, corpus reader, recursion và từ chối dịch vụ. Finding còn lại liên quan path do caller kiểm soát trong API đọc/ghi model artifact. HaizFlow không expose các API này: wrapper alignment của WhisperX thay resource loader NLTK bằng bộ tách câu nội bộ, không tải NLTK data và không nhận đường model NLTK từ user. Xóa ngoại lệ khi có bản NLTK vá tương thích.

### DiskCache 5.6.3

Ngoại lệ tạm: [PYSEC-2026-2447](https://osv.dev/vulnerability/PYSEC-2026-2447). Đây là dependency gián tiếp của `llama-cpp-python`; HaizFlow không dùng DiskCache để lấy model hoặc gọi `Llama.from_pretrained`. CPU path chỉ mở GGUF đã verify size/SHA-256.

### Lightning 2.6.5

Ngoại lệ tạm: [PYSEC-2026-3624 / CVE-2026-58659](https://osv.dev/vulnerability/PYSEC-2026-3624). Trong khi chờ bản tương thích đã sửa, `haizflow.core.dependency_security` chặn `_instantiator` ngoài CLI path chính thức ở cả hai namespace. Guard có regression test và tự tắt sau khi phát hiện bản upstream đã sửa.

### Torch 2.8.0+cu128

Do `pip-audit` không ánh xạ trực tiếp hậu tố CUDA, gate quét thêm version canonical. Ngoại lệ tạm: [PYSEC-2025-203](https://osv.dev/vulnerability/PYSEC-2025-203), [PYSEC-2025-204](https://osv.dev/vulnerability/PYSEC-2025-204), [PYSEC-2025-206](https://osv.dev/vulnerability/PYSEC-2025-206), [PYSEC-2026-139](https://osv.dev/vulnerability/PYSEC-2026-139), [PYSEC-2026-2286](https://osv.dev/vulnerability/PYSEC-2026-2286), [PYSEC-2025-194](https://osv.dev/vulnerability/PYSEC-2025-194), [CVE-2025-2999](https://osv.dev/vulnerability/CVE-2025-2999), [CVE-2025-3001](https://osv.dev/vulnerability/CVE-2025-3001).

WhisperX 3.8.6 khóa compatibility family Torch 2.8. HaizFlow không nhận checkpoint Torch của user hoặc expose PT2/JIT/Trainer. HY-MT2 dùng safetensors, Whisper dùng CTranslate2. Chỉ năm alignment asset `en/fr/de/es/it` đã pin được phép; VAD được khóa commit/size/checksum.

### Checkpoint Demucs

HaizFlow khóa host/URL/size/full SHA-256 của `htdemucs` và không cho resolve repository tùy ý. Chỉ subprocess Demucs nhận `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` sau verify; main process và worker khác không nhận override này.

## Mạng và dữ liệu

| Tính năng | Dữ liệu ra khỏi máy |
| --- | --- |
| Tải model | Request file cố định và transport metadata |
| Nhập URL/kênh | URL công khai, cookie đã cấu hình và provider response |
| Edge TTS | Text phụ đề cần để tổng hợp giọng |
| Đăng mạng xã hội | Media/nội dung đã chọn và credential provider |
| Xuất chẩn đoán | Log giới hạn và redact; không có media/metadata dự án |

WhisperX, HY-MT2, OmniVoice, Demucs, OCR, FFmpeg và project storage chạy local khi đủ asset.

## Yêu cầu thay đổi

Đổi package, model, host, deserializer, binary hoặc provider cần bằng chứng tương thích, review license, audit vulnerability, integrity metadata bất biến, test failure/corrupt/cancel và cập nhật threat model. Ngoại lệ hết hiệu lực khi mitigation không còn khớp implementation hoặc đã có bản sửa tương thích.
