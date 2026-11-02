# Ngôn ngữ phụ đề và công cụ giọng đọc

Manual phân biệt `target_language` (lựa chọn cho lần dịch tiếp theo) và
`subtitle_language` (ngôn ngữ của kết quả phụ đề đã xuất bản thành công).
Đổi ô Dịch sang không tự đổi công cụ giọng của các phụ đề đang có.
Các dự án cũ chưa có trường mới được kiểm tra nội dung phụ đề khi cần.

VieNeu vẫn cho phép phụ đề Việt/Anh; không cam kết chất lượng tiếng Anh
bằng tiếng Việt. Nếu kết quả mới là Trung, Hàn, Nhật hoặc Tây Ban Nha và đang dùng VieNeu, Manual
chuyển sang OmniVoice cùng CPU/GPU, bỏ override VieNeu không tương thích.
Việc chuyển chỉ xảy ra sau khi dịch thành công, không khi đổi ô ngôn ngữ
hay khi dịch thất bại. Chọn lại VieNeu với phụ đề không hỗ trợ bị chặn và cảnh báo
mỗi lần thử, không dùng cơ chế thông báo một lần mỗi phiên.

Auto/Batch kiểm tra ngôn ngữ đích trước khi chạy. Hai chiều chọn ngôn ngữ không hỗ trợ
khi dùng VieNeu hoặc chọn VieNeu khi đích không hỗ trợ đều bị chặn; lựa chọn
hợp lệ trước đó được giữ lại. Backend cũng kiểm tra trước khi tạo giọng.

Nhập SRT hỗ trợ chọn Việt/Anh/Trung/Hàn/Nhật/Tây Ban Nha. Chữ kana và Hangul
được nhận diện từ nội dung; tiếng Tây Ban Nha dùng lựa chọn người dùng vì chữ
Latin không đủ để phân biệt chắc chắn. SRT tiếng Nhật chỉ có kanji vẫn giữ nhãn
Nhật đã chọn. Mốc thời gian và Unicode được giữ khi nhập/xuất SRT gốc/kết quả.
VieNeu kiểm tra cả nội dung thực tế: chữ Hán/kana/Hangul trong câu tiếng Việt
cũng bị chặn, thông báo chỉ rõ câu để sửa/phiên âm hoặc chọn OmniVoice/Edge TTS.

Nhận dạng giọng nói vẫn tự phát hiện ngôn ngữ. Tiếng Tây Ban Nha dùng aligner
đã xác minh. Nhật/Hàn tách đoạn dài theo khoảng nghỉ thực, rồi lấy mốc từ decoder
Whisper đang nạp khi toàn bộ chữ nhận lại khớp transcript và các mốc hợp lệ;
không tải thêm aligner tùy ý. Nếu đối chiếu không đạt, giữ timing ASR thay vì đổi
nội dung hay nhận mốc không đáng tin cậy. Không cam kết nhận dạng đúng mọi audio.

Xuất SRT bị khóa khi đang xử lý, có tác vụ trong hàng đợi, đang xuất video
hoặc nhập nguồn. Hàm xuất kiểm tra trước khi đọc tài liệu và mở hộp chọn tệp.
