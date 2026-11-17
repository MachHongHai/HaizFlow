# Clone OmniVoice/VieNeu và kiểm tra API — 17/11/2026

## Lỗi trong ảnh 1.0.5

Stack kết thúc tại `omnivoice.utils.audio.load_waveform`: bộ đọc soundfile lỗi,
sau đó nhánh dự phòng import `librosa` không có trong engine đóng gói. Ảnh không
đủ để xác định định dạng/tính hợp lệ của tệp mẫu gốc. Đã tái hiện cùng đường lỗi
với mẫu M4A/AAC hợp lệ; đây không phải lỗi suy luận tạo giọng thông thường.

## Thay đổi

- OmniVoice chuẩn hóa mỗi mẫu người dùng một lần trong mỗi yêu cầu bằng FFmpeg
  có sẵn: WAV PCM16 mono 24 kHz. Không cắt mẫu để tránh lệch bản chép lời.
- SDK nhận `(waveform, sample_rate)`, đọc qua Python file handle có hỗ trợ đường
  dẫn Unicode; không đi qua nhánh giải mã đường dẫn dự phòng `librosa`.
- Tệp tạm sống đến khi worker hoàn tất. Dùng fingerprint tệp gốc để giữ khả năng
  tái dùng prompt giữa các yêu cầu dù đường dẫn WAV tạm khác nhau; cache vẫn có
  giới hạn. Không đổi giọng dự phòng khi mẫu hỏng/mất.
- VieNeu vốn đã giải mã mẫu bằng FFmpeg, không xác nhận cùng lỗi thiếu decoder.
  Dùng chung bước chuẩn hóa có kiểm tra header PCM; giữ 48 kHz/8 giây như trước.
  SDK VieNeu có fallback trim khi không có librosa; đã chạy trực tiếp phương
  thức preclean của SDK đang cài với import librosa bị chặn và thành công.
- Không thêm librosa/numba vào engine, không đổi model hoặc tham số chất lượng.

## Thử thật trên dev

Dùng một mẫu giọng có sẵn của app, chuyển thành M4A tên có dấu, không dùng mẫu
của người dùng hoặc ghi vào dự án. Chạy hai model GPU tuần tự trên RTX 4060;
không tự chuyển CPU. Câu đích: “Xin chào, đây là mẫu kiểm tra nhân bản giọng.”

| Lượt | Kết quả |
|---|---|
| OmniVoice GPU clone | MP3 hợp lệ 20.925 byte; ~47,5 giây, gồm nạp model lạnh |
| VieNeu GPU clone | MP3 hợp lệ 26.973 byte; ~16,9 giây, gồm nạp model lạnh |
| Gemini 3.5 Flash-Lite | 6/6 câu mẫu, 1 POST, ~1,5 giây |
| ERNIE 5.5 Flash Preview free | 12/12 câu mẫu, 1 POST, ~7,4 giây |
| Flint v1.0 free | 12/12 câu mẫu, 1 POST, ~28,5 giây |

Ba lượt dịch kiểm tra payload thật: không gửi giới hạn đầu ra của app. Hai lượt
OpenRouter xác minh metadata/endpoint hiện tại, không cho thu thập dữ liệu,
khóa giá prompt/completion/request ở 0. Không retry POST trong probe, không thay
key hay lựa chọn dự án. Đây là mẫu đối chứng, không phải cam kết độ trễ/chất
lượng cho mọi mẫu hoặc đảm bảo server không bao giờ cắt kết quả.

Bộ kiểm thử liên quan: 1.254 tests và 22 subtests đạt. MP3 cuối cùng của cả hai
model được giải mã lại và qua kiểm tra waveform: OmniVoice 24 kHz/~2,6 giây,
VieNeu 48 kHz/~2,8 giây. Không khẳng định đã nghe đối chứng độ giống giọng.

Các probe đầu tiên dừng do thiếu video ID trong harness không có dự án; Gemini
chưa gửi POST, OmniVoice chưa nạp model. Đã sửa harness chuyển log vào báo cáo
riêng và chạy lại thành công; đây không phải lỗi app có project ID hợp lệ.

Không build/phát hành hay sửa EXE 1.0.5. Bản sửa cần được đóng gói vào bản cập
nhật; việc sửa source không tự sửa binary đã cài của người dùng.

Hợp đồng SDK tham khảo:
[OmniVoice waveform clone prompt](https://github.com/k2-fsa/OmniVoice/blob/master/omnivoice/models/omnivoice.py),
[VieNeu v3 Turbo](https://github.com/pnnbao97/VieNeu-TTS/blob/main/src/vieneu/v3turbo.py).
