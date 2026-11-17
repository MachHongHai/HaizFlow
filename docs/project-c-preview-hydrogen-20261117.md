# Dự án c: preview OCR và thời gian chờ Hydrogen — 17/11/2026

## 1. Preview OCR: đã sửa

Không xóa cache. Cùng nguồn và cùng lớp che OCR nhưng có hai khóa base:

- Trước nhận dạng: `1bafe011410d43ff01c3`.
- Sau khi công bố 89 câu nguồn: `99589a349ece5346edef`.

Lý do: `original_subtitle_intervals` (các mốc lời nói vừa nhận dạng) nằm trong
khóa preview, dù lớp che Manual đã có khoảng thời gian riêng và renderer không
dùng mốc ASR để vẽ lớp đó. Khi video đang trong queue, request preview chỉ được
khôi phục cache khớp khóa, không chạy render mới. Khóa khác khiến khả năng khôi
phục preview OCR bị mất tạm thời. Sau pause, app được ráp lại proxy; log lúc
14:36:29 ghi 14 mask chunks, render=0/reused=14, phù hợp cache vẫn còn.

Sửa riêng khóa base của Manual có `treatment_layers`: không phụ thuộc mốc ASR.
Giữ nguyên vùng/mode/thời gian lớp che, nguồn/source generation, sequence, crop
và các yếu tố thực sự ảnh hưởng hình ảnh. Thêm đọc tương thích khóa cũ có mốc
ASR; không chọn tùy tiện proxy mới nhất, không nới kiểm tra file hoàn chỉnh.

Đã đọc lại dữ liệu thật của c bằng host chẩn đoán, đặt trạng thái `processing`
trong bộ nhớ và request `cache_only=True`: trả `ready`, `busy=False`, đúng base
`1bafe...`, không FFmpeg/FFprobe và không ghi manifest/pin hoặc dữ liệu dự án.
Không chạy lại OCR/nhận dạng/dịch trong phép thử.

Kiểm thử preview/OCR: 382 tests và 277 subtests đạt; có ca nhận dạng → đang
xử lý → pause, đọc khóa cũ, đổi nguồn/vùng/mode/thời gian che và cache hỏng.

## 2. Hydrogen: chỉ chẩn đoán, chưa đổi code Gemini

Log theo giờ Việt Nam:

- 14:32:07.858: lưu xong 89 câu nguồn.
- 14:32:08.600: gửi lô Gemini đầu tiên, câu 1–24.
- 14:35:53.223: yêu cầu pause, sau khoảng 224,6 giây.
- Không có log nhận phản hồi, usage, lỗi HTTP hay số lần timeout ở khoảng này.

Tái dựng request cục bộ từ cấu hình dự án: model `gemini-4-hydrogen`,
`thinkingLevel=low`, không `maxOutputTokens`, JSON/schema, 24 câu với 1.136 ký
tự nguồn. Payload chẩn đoán khoảng 3.766 byte (không tính bổ sung timing nếu
caller cung cấp). Không phải input khổng lồ hay app tự gửi mức High.

Xác nhận từ code và mô phỏng không mạng: adapter có vòng tối đa ba lần gửi lại
khi `URLError`/`TimeoutError`, mỗi lần `urlopen(timeout=90)`; không ghi log riêng
cho các lần timeout này. Ba lần chờ danh nghĩa và backoff có thể thành khoảng
4 phút 33 giây. Đây là khả năng có thật trong code, **không chứng minh lượt thật
đã xảy ra ba lần gửi**. Timeout của urllib áp dụng cho thao tác blocking, không
phải deadline tổng; đọc body có thể chờ lâu hơn nếu dữ liệu tiếp tục tới. Pause
không trực tiếp đóng socket HTTP như đối với subprocess.

Bỏ trần cho phép server dùng ngân sách mặc định lớn hơn trước, nên có thể góp
phần tăng thời gian suy luận; log không có phản hồi/token usage để kết luận đây
là nguyên nhân chính của lượt Hydrogen này. Không có đối chứng A/B trên cùng
request. Chưa gọi thêm API, chưa thay token/reasoning/retry hoặc dữ liệu dự án.

Hướng kiểm chứng/sửa tiếp: log an toàn theo từng attempt và thời gian chờ, deadline
tổng có hủy thực sự, xem lại việc retry một POST timeout có thể đã được tính phí;
sau đó đối chứng có/không cap nếu người dùng muốn. Không tự khôi phục trần chung.

Nguồn:
[Python urllib timeout](https://docs.python.org/3.13/library/urllib.request.html),
[Hydrogen và các mức thinking được hỗ trợ](https://aistudio.google.com/docs/models/gemini-4-hydrogen).
