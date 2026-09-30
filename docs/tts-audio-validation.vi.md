# Giọng đọc và chất lượng âm thanh

## Lựa chọn công cụ

Manual và auto dùng cùng hai lựa chọn: OmniVoice CPU và OmniVoice GPU. Lựa chọn được lưu trong dự án; không phụ thuộc công tắc thiết bị toàn ứng dụng cũ. Các công cụ giọng đọc đã ngừng hỗ trợ chuyển sang OmniVoice khi mở; output đã xuất không bị xóa.

OmniVoice dùng một gói model chung cho CPU/GPU và hỗ trợ nhân bản giọng. Chưa cài gói thì app báo thiếu trước khi chạy. Chọn GPU nhưng không nạp được CUDA phải báo lỗi, không âm thầm gọi CPU là GPU. Kho nghe thử đóng gói chỉ chứa giọng OmniVoice Anh, Việt, Trung.

## Voice cloning

Log clone của `testiengvietauto` ngày 30/09/2026 lỗi vì mẫu không có bản chép lời. OmniVoice tự tìm model ASR ngoài gói đã cài trong chế độ offline. Bản sửa nhận dạng mẫu bằng Whisper cục bộ trên CPU, cache theo SHA-256 mẫu, kết thúc process nhận dạng rồi mới nạp OmniVoice. Worker từ chối bản chép lời trống để không tải thêm model ngầm. Bản thử giọng thông thường sau đó thành công không chứng minh đường clone đã hoạt động.

Kiểm tra lại trên máy này còn phát hiện crash native trong bộ nạp safetensors song song của Transformers 5.3 trên Windows/CUDA. Worker đặt `HF_DEACTIVATE_ASYNC_LOAD=1` để nạp trọng số tuần tự; không sửa SDK đã cài. Mẫu thu của dự án đã tạo được giọng GPU với 32 bước mặc định sau thay đổi này. Kiểm tra thực tế này chưa thay thế nghiệm thu mọi mẫu/ngôn ngữ hoặc môi trường installer.

## Audio

ffprobe xác nhận video đã xuất của `testiengvietauto` trước bản sửa là AAC mono 16 kHz, khoảng 73 kbps. Tệp cũ được giữ nguyên; cần chạy xuất lại để áp dụng định dạng mới.

Nguồn được trích thành stereo 48 kHz PCM 24-bit. Chỉ đường nhận dạng lời nói tự đổi về mono 16 kHz bên trong WhisperX. Phối âm và cache preview dùng stereo 48 kHz; xuất MP4 dùng AAC stereo 48 kHz, mục tiêu 256 kbps. Cache nguồn/phối cũ có phiên bản khác để không tái dùng đường mono 16 kHz.

Giọng OmniVoice tạo ở 24 kHz. Đổi sang 48 kHz khi phối không tạo thêm chi tiết đã thiếu trong model. Track nhạc và âm thanh nguồn phải giữ hai kênh độc lập.

Chạy `scripts/check-audio-export.py` để kiểm trích nguồn, phối âm và xuất video bằng FFmpeg/ffprobe mà không sửa dự án người dùng. Không phải lệnh build installer.

## Kiểm tra hồi quy ngày 30/09/2026

Hai log auto mới nhất dừng ở nhận dạng/dịch, trước khi clone chạy. Lần dùng HY-MT2 GPU gặp lỗi CUDA allocation trong khi Windows commit còn khoảng 0,02 GiB; không phải kết luận RTX 4060 không hỗ trợ model. Sau đó đường phục hồi chuyển runtime toàn cục sang CPU nhưng vẫn yêu cầu model dịch `full`, làm lần chạy tiếp theo từ chối Whisper Turbo.

Bản sửa giữ nguyên lựa chọn của dự án: source Windows nhận dạng trong process riêng, kết thúc process trước bước dịch; phục hồi CPU chỉ áp dụng trong lần thử lại và trả thiết bị/model toàn cục về giá trị ban đầu. Trong lần phục hồi, HY-MT2 dùng Q4 và Whisper dùng Small nếu cần nhận dạng lại. Không tải thêm gói ngầm. Release không import WhisperX vào Core nếu model chỉ tồn tại trong process con. Khi engine không còn capability nào sử dụng, process kết thúc để giải phóng cả CUDA context và DLL commit; nếu còn capability khác dùng chung, engine được giữ nguyên.

Chạy thực tế bằng `scripts/check-clone-pipeline.py`, dùng video và mẫu thu của dự án làm đầu vào chỉ đọc:

- Whisper Turbo GPU → HY-MT2 GPU → OmniVoice GPU clone: hoàn tất, không phục hồi xuống CPU.
- Whisper Turbo GPU → HY-MT2 CPU Q4 → OmniVoice GPU clone: hoàn tất.
- Chạy lại cả hai sau khi sửa tái dùng stem Demucs: hoàn tất. Kết quả nằm trong `D:/HaizFlowData/tmp/clone-check-20260930T125214Z`; OCR được tắt trong lượt kiểm tra này.
- Chạy lại cả hai với `--warm-recognition`: engine Whisper đã nạp trước được giải phóng hoàn toàn trước foreground; cả hai chuỗi vẫn hoàn tất. Kết quả ở `D:/HaizFlowData/tmp/clone-check-20260930T130559Z`; OCR cũng được tắt.
- ffprobe xác nhận cả hai video là AAC stereo 48 kHz, khoảng 250 kbps. Stem Demucs 44,1 kHz không bị coi là bản nguồn legacy để trích/tách lại.

Kiểm thử hồi quy cuối: 927 bài Python và 85 subtest qua; Qt Quick có 20 mục qua, không fail/skip. Qt lint các QML thay đổi không báo lỗi. Có một cảnh báo TorchCodec trong môi trường source; đường kiểm tra thật đọc audio bằng FFmpeg/preloaded waveform, không dùng decoder TorchCodec.

Editor tách Che phụ đề/Watermark ở cấp UI, không đổi chỉ số các task backend. Auto đặt lặp/ducking dưới phần Nhạc nền; chưa có nhạc thì công tắc mờ và chỉ hiện nhắc nhập nhạc. Clone mở lại mẫu đã thu ở màn nghe thử; nút Áp dụng xác nhận mẫu và chọn giọng clone đồng bộ. Đóng cửa sổ không tự thay lựa chọn. Popup giọng giới hạn kích thước và vị trí theo cửa sổ.

Tác vụ manual đã tạm dừng không khóa các công cụ khác. Chỉ worker còn chạy hoặc đang trong hàng đợi mới giữ khóa. Chạy công cụ khác xóa yêu cầu pause cũ, thay mục tiêu tiếp tục; các artifact hoàn thành và đoạn giọng hợp lệ vẫn nằm trong cache theo chữ ký nội dung. Manifest giọng chỉ công bố khi toàn bộ đoạn hoàn tất.

## Trước phát hành

- Nghiệm thu clone cả CPU/GPU với mẫu thật 5–15 giây, ngôn ngữ đích Anh/Việt/Trung.
- Nghiệm thu gói tài nguyên tải/resume/repair/remove và môi trường Core đã đóng gói, không chỉ source Python.
- Hoàn thiện archive, URL bất biến, checksum và chữ ký engine trước khi build release; manifest engine hiện vẫn còn placeholder.

