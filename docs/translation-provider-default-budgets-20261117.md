# Mặc định ngân sách đầu ra theo nhà cung cấp — 17/11/2026

Theo yêu cầu người dùng, không ước lượng một trần đầu ra chung cho các model.
Chính sách này thay thế việc tăng ngân sách ERNIE/Flint trong lượt đối chứng
trước đó; không thay đổi các lựa chọn suy luận trong dự án.

## Hành vi

| Kết nối | Tham số không gửi trong yêu cầu dịch |
|---|---|
| Gemini | `generationConfig.maxOutputTokens` |
| OpenAI Responses | `max_output_tokens` |
| DeepSeek Chat Completions | `max_tokens` |
| OpenRouter Chat Completions | `max_tokens` |
| API tùy chỉnh tương thích OpenAI Chat Completions | `max_tokens` |

Các giao thức trên cho phép bỏ tham số. App dùng mặc định server, không gửi
`null`, `0` hoặc một số rất lớn để giả lập vô hạn. Chưa thêm UI giới hạn token
thủ công; không đoán một giá trị khi server tùy chỉnh không đúng hợp đồng này.

Vẫn chia lô phụ đề, thu nhỏ lô theo dung lượng endpoint thấp, kiểm tra JSON/ID/
đủ câu và lưu checkpoint. OpenRouter vẫn kiểm tra endpoint, định dạng JSON,
quyền dữ liệu và chặn giá khác 0 cho model đã xác minh miễn phí. Không còn bắt
endpoint phải có hỗ trợ `max_tokens` vì app không gửi tham số đó nữa.

Giữ thời gian chờ và chính sách lỗi HTTP hiện có. Nếu server trả kết quả bị cắt
do giới hạn riêng, không ghi lô thiếu và không tự gửi lại để nâng trần. Gemini
cũng không còn tự retry token exhaustion với cùng ngân sách mặc định. Các loại
retry Gemini khác ngoài phạm vi này giữ nguyên.

Mặc định nhà cung cấp vẫn hữu hạn, khác nhau theo model/endpoint; bỏ trần app
không bảo đảm hết lỗi token. Có thể tốn nhiều thời gian/token hơn khi suy luận
bật hoặc bắt buộc. Không thay đổi key, dự án, quyền dữ liệu hay tự chuyển model.

## Kiểm chứng

Kiểm tra payload của cả năm loại kết nối, toàn bộ mức suy luận, endpoint không
hỗ trợ điều chỉnh cap nhưng hỗ trợ JSON, lô tiếp theo có ID khác 0, giới hạn
context nhỏ, kết quả bị cắt/thiếu/sai ID, checkpoint và lỗi sau HTTP 200.
HTTP server cục bộ kiểm tra thực sự dữ liệu gửi trên wire; không gọi inference
trả phí hoặc dùng nội dung dự án cho thay đổi chính sách này.

Nguồn chính thức:
[Gemini GenerationConfig](https://ai.google.dev/api/generate-content),
[OpenAI Responses](https://developers.openai.com/api/reference/resources/responses/methods/create),
[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/),
[OpenRouter Parameters](https://openrouter.ai/docs/api_reference/parameters).
