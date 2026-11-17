# OpenRouter: hai lượt lỗi của dự án c — 17/11/2026

> Cập nhật tiếp theo theo yêu cầu người dùng: chính sách tăng trần trong báo cáo
> này là kết quả đối chứng lịch sử, đã được thay bằng bỏ tham số giới hạn đầu ra
> tùy chọn để dùng mặc định nhà cung cấp. Các lượt live trong bảng bên dưới được
> chạy trước thay đổi đó, không phải phép thử live của chế độ tự động mới.

## Nguyên nhân xác nhận được

- ERNIE `baidu/ernie-5.5-flash-preview:free`, câu 25–36: phản hồi
  `finish_reason=length`, dùng đủ 10.240 token đầu ra cho suy luận, không còn
  nội dung bản dịch. Đây là giới hạn đầu ra của yêu cầu, không phải quota tài khoản.
  Metadata yêu cầu suy luận High nhưng ngân sách cũ chưa tính mức mặc định này.
- Flint `recursive/flint-v1.0:free`, câu 37–48: sau khoảng 127 giây, body HTTP
  không đọc được thành JSON. Log cũ không có loại/kích thước body nên chưa đủ
  bằng chứng phân biệt phản hồi rỗng, ngắt giữa chừng hay phản hồi lỗi khác.
  Không phải bằng chứng rằng JSON phụ đề sai ID. Khi phát lại đoạn này, một lượt
  khác hết 10.240 token suy luận; lỗi transport cũ không được tái hiện chính xác.

## Sửa trong app

- Tính ngân sách theo mức suy luận bắt buộc thực sự gửi, kể cả mặc định High.
- Model bắt buộc suy luận nhưng không có mức điều chỉnh được dành tối thiểu
  16.384 token tổng; vẫn giới hạn bởi endpoint/context và trần 32.768.
  Model cho phép tắt suy luận vẫn giữ ngân sách thấp khi tắt; mức Low có thể chọn
  không tự nhận mức sàn của model không điều khiển được suy luận.
- Không thêm vòng gửi lại, không đổi model, không tự bật suy luận tùy chọn.
  Tăng trần không có nghĩa luôn dùng hết trần, nhưng có thể cho phép model suy
  luận lâu hơn và tốn thêm token nếu đó là model tính phí.
- Phân biệt phản hồi rỗng, không đúng định dạng và quá lớn. Log kỹ thuật chỉ ghi
  mã nguyên nhân, số byte và MIME allowlist; không ghi body, key hoặc phụ đề.
- Nhận diện lỗi dịch vụ nằm trong `choices[0].error` dù HTTP 200, bao gồm loại
  lỗi chuẩn trong metadata. Không tự gửi lại POST không rõ kết quả hoặc lỗi
  sau khi đã bắt đầu sinh. Giữ nguyên quy tắc HTTP retry hiện có cho lỗi HTTP
  tạm thời; không tự retry HTTP 429.
- Giữ kiểm tra đủ câu/ID duy nhất, chặn kết quả bị cắt và giữ các lô đã lưu.

## Thử thực tế, giá định tuyến bằng 0

Mỗi lượt chỉ một POST, khóa giá prompt/completion/request bằng 0; không dùng
model trả phí. Các lượt kiểm tra tổng hợp dùng 12 câu Anh → Việt, ID bắt đầu
khác 0. Quyền thu thập dữ liệu cho Nemotron/LFM/Particle chỉ dùng tạm cho câu
mẫu theo sự đồng ý của người dùng, không lưu quyền vào app, không gửi phụ đề dự
án tới ba model này.

| Model | Kết quả trong lượt thử |
|---|---|
| ERNIE 5.5 Flash Preview | 12/12 câu mẫu, ~10,4 giây |
| Flint v1.0 | 12/12 câu mẫu, ~29 giây |
| Particle-1 | 12/12 câu mẫu, ~2,5 giây |
| Nemotron 3.5 Super VL | 12/12 câu mẫu, ~2,4 giây |
| Dots 3 Note Preview | Đúng JSON/ID; một câu lẫn chữ Hán, chất lượng chưa ổn định |
| LFM3 1.7B | HTTP 429 phía nhà cung cấp |
| Ling 3.2 Flash | HTTP 429 phía nhà cung cấp |
| Gemma 4 31B | HTTP 429 phía nhà cung cấp |

Phát lại đúng cửa sổ phụ đề từng lỗi của c qua code production, không ghi vào
dự án, không cho phép thu thập dữ liệu:

- ERNIE câu 25–36: trần 16.384; 12/12 câu, `stop`, ~7,1 giây.
- Flint câu 37–48: trần cũ 10.240 bị cắt; trần mới 16.384 trả 12/12 câu,
  `stop`, ~31,3 giây, sử dụng 4.371 token đầu ra trong lượt này.

Đây là các lượt đối chứng, không bảo đảm model sẽ không bao giờ hết ngân sách
hay server không bao giờ lỗi. Prompt phát lại có ngữ cảnh nguồn, không có bộ nhớ
bản dịch đã hoàn thành từ lượt cũ. HTTP 429 tạm thời không đủ để kết luận model
đã ngừng hoạt động hoặc tài khoản hết quota; không loại model chỉ vì lượt này.

## Kiểm tra không phát sinh phí cho đường dẫn trả phí

Kiểm thử giả lập và HTTP server cục bộ: OpenRouter miễn phí/trả phí, OpenAI,
DeepSeek, API tùy chỉnh; body rỗng/HTML/SSE/UTF-8 lỗi/quá lớn, lỗi HTTP-200,
lỗi nested choice, token/context ceiling, từ chối/truncated output, ID thiếu/
trùng/sai, checkpoint, quyền dữ liệu, key đang chọn và không tự chuyển model.
Không chạy inference model trả phí; không khẳng định đã kiểm chứng mọi endpoint
trả phí thực tế. Không build hoặc thay đổi dữ liệu dự án.

Nguồn giao thức:
[Reasoning tokens](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens),
[Errors and debugging](https://openrouter.ai/docs/api_reference/errors-and-debugging).
