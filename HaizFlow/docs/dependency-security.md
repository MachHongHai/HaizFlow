# Chính sách an toàn dependency

Ngày rà soát: 2026-07-27

Mỗi release phải chạy:

```powershell
.\scripts\audit-dependencies.ps1
```

Script dùng `pip-audit==2.10.1`, quét trực tiếp environment sẽ được đóng gói và chỉ bỏ qua đúng các advisory đã được đánh giá bên dưới. Advisory mới luôn làm release gate thất bại. Danh sách ngoại lệ phải được rà soát lại trước mỗi release và chậm nhất ngày 2026-08-27.

## Đã khắc phục

- `pip` đã nâng từ 25.1.1 lên 26.1.2 và dependency lock đã được sinh lại bằng `uv==0.11.19`.
- HY-MT2 chỉ đọc model đã pin revision và kiểm tra SHA-256, dùng `local_files_only=True`, `use_safetensors=True` và `trust_remote_code=False`.

## Ngoại lệ có kiểm soát

### transformers 4.57.6

Advisory được chấp nhận tạm thời:

- [`PYSEC-2025-217`](https://osv.dev/vulnerability/PYSEC-2025-217)
- [`PYSEC-2026-2288`](https://osv.dev/vulnerability/PYSEC-2026-2288)
- [`PYSEC-2026-2289`](https://osv.dev/vulnerability/PYSEC-2026-2289)
- [`PYSEC-2026-2290`](https://osv.dev/vulnerability/PYSEC-2026-2290)

Các advisory liên quan tới việc nạp checkpoint/config không đáng tin hoặc các đường `Trainer`/conversion mà HaizFlow không cho người dùng gọi. HaizFlow chỉ nạp checkpoint HY-MT2 cố định, đã kiểm tra từng file bằng SHA-256, không chạy remote code và không dùng `Trainer`.

Không nâng thẳng lên Transformers 5 trong RC này: thử nghiệm 5.14.1 cho thấy cấu hình RoPE của checkpoint HY-MT2 4.57.6 có khóa không còn được nhận diện (`beta_fast`, `alpha`, `beta_slow`, `mscale_all_dim`, `mscale`). Đóng gói bản đó có thể âm thầm thay đổi chất lượng dịch. Ngoại lệ chỉ được gỡ sau khi có bản model/config tương thích và bộ nghiệm thu chất lượng dịch đạt.

### diskcache 5.6.3

Advisory được chấp nhận tạm thời:

- [`PYSEC-2026-2447`](https://osv.dev/vulnerability/PYSEC-2026-2447)

Đây là dependency gián tiếp của `llama-cpp-python` và upstream chưa có phiên bản sửa. Lỗi yêu cầu kẻ tấn công ghi được dữ liệu pickle vào cache rồi làm ứng dụng đọc cache đó. HaizFlow không gọi `Llama.from_pretrained`, không dùng DiskCache và chỉ mở file GGUF local đã pin SHA-256. Runtime/cache nằm dưới thư mục cài đặt do người dùng chọn; người đã có quyền thay đổi thư mục này cũng có thể thay EXE/DLL/model của ứng dụng. Ngoại lệ phải được xóa ngay khi upstream phát hành bản sửa hoặc `llama-cpp-python` bỏ dependency này.

### torch 2.8.0+cu128

`pip-audit` không ánh xạ được hậu tố wheel CUDA `+cu128` về PyPI. Release gate vì vậy quét thêm version canonical của `torch`, `torchaudio` và `torchvision`; các advisory mới vẫn làm build thất bại. Các ngoại lệ tạm thời:

- [`PYSEC-2025-203`](https://osv.dev/vulnerability/PYSEC-2025-203)
- [`PYSEC-2025-204`](https://osv.dev/vulnerability/PYSEC-2025-204)
- [`PYSEC-2025-206`](https://osv.dev/vulnerability/PYSEC-2025-206)
- [`PYSEC-2026-139`](https://osv.dev/vulnerability/PYSEC-2026-139)
- [`PYSEC-2026-2286`](https://osv.dev/vulnerability/PYSEC-2026-2286)
- [`PYSEC-2025-194`](https://osv.dev/vulnerability/PYSEC-2025-194)
- [`CVE-2025-2999`](https://osv.dev/vulnerability/CVE-2025-2999)
- [`CVE-2025-3001`](https://osv.dev/vulnerability/CVE-2025-3001)

WhisperX 3.8.6 mới nhất yêu cầu `torch~=2.8.0`, `torchaudio~=2.8.0`, `torchvision~=0.23.0` và `torchcodec<0.8`; nâng cưỡng bức lên Torch 2.10 làm runtime nằm ngoài compatibility contract upstream. HaizFlow không nhận checkpoint Torch từ người dùng, không dùng PT2/JIT/Trainer và không gọi các operator được nêu trong nhóm lỗi tensor DoS/memory-corruption. HY-MT2 dùng safetensors đã pin SHA-256; Whisper dùng CTranslate2 model đã pin.

WhisperX mặc định còn có thể tải alignment checkpoint pickle không pin. HaizFlow đã vô hiệu hóa đường đó: chỉ năm torchaudio alignment asset chính thức cho `en/fr/de/es/it` được cho phép, mỗi file có size/SHA-256 cố định, URL HTTPS cố định, được bootstrap lần chạy đầu tải atomic với progress/cancel/retry, kiểm lại trước mỗi lần nạp và dùng `weights_only=True`. Pipeline frozen/source chỉ dùng repository local đã xác minh và không tự tải alignment model từ mạng. Ngôn ngữ khác giữ timestamp Whisper và chia câu theo tỷ lệ thay vì tải Hugging Face checkpoint không pin. VAD pickle của WhisperX cũng bị loại khỏi PyInstaller; bootstrap tải nó từ URL khóa theo commit, kiểm size/SHA-256 và pipeline truyền explicit local path khi nạp. HaizFlow dùng sentence splitter nội bộ cho từng span nên WhisperX không còn tự tải `punkt_tab` của NLTK. Đây là giảm thiểu bắt buộc cho đến khi WhisperX hỗ trợ Torch đã sửa và alignment safetensors/revision pin.

Demucs 4.0.1 upstream nạp checkpoint bằng `torch.load`, nên HaizFlow không cho tên model mặc định tự truy cập remote repository. Checkpoint `htdemucs` chính thức được khóa bằng URL HTTPS/host cố định, kích thước chính xác và full SHA-256 `8726e21a…`; bootstrap model tải file đó vào runtime và release gate cấm nhúng model trong artifact. Runtime chỉ truyền local repository đã xác minh cho subprocess và từ chối chạy nếu payload thiếu/hỏng. Do PyTorch 2.6+ đổi mặc định `torch.load` sang `weights_only=True` trong khi package Demucs chứa cả class model, riêng subprocess Demucs nhận `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` sau bước xác minh; biến này không được đặt cho process chính hay worker khác. Vì checkpoint pickle vẫn là định dạng có thể thực thi khi nạp, full checksum là trust boundary bắt buộc và không được thay bằng file do người dùng cung cấp.

## Phạm vi dữ liệu

WhisperX, HY-MT2, Demucs và FFmpeg chạy local. Edge TTS nhận văn bản phụ đề đã dịch để tổng hợp giọng nói. Nhập video bằng URL/kênh kết nối tới nền tảng tương ứng. Chức năng xuất chẩn đoán chỉ lấy log ứng dụng/model đã giới hạn kích thước và redaction; không lấy video, tên project hoặc log project.
