# Kiểm tra OpenRouter miễn phí — 08/11/2026

## Phạm vi và kết quả

Đã gọi thực tế 9 model text/JSON miễn phí trong danh mục công khai, qua bộ
chuyển đổi dịch đang dùng của HaizFlow. Mỗi mẫu có 2 câu; lượt mở rộng có 6 câu
Anh → Việt. Kiểm tra đủ ID, thứ tự, JSON và đọc đối chiếu bản dịch.
Không dùng phụ đề của người dùng, không sửa dự án, không gọi model tính phí.
Mỗi lần thử giới hạn một POST, không tự retry; định tuyến có `max_price=0`
cho prompt/completion/request. Không ghi key hoặc phản hồi lỗi thô vào báo cáo.

| Model giữ lại | Kết quả mẫu mở rộng | Quyền thu thập dữ liệu |
|---|---|---|
| dots-studio/dots-3-note-preview:free | 6/6 câu, ~2,0 giây | Không yêu cầu |
| nvidia/nemotron-3.5-super-vl:free | 6/6 câu, ~1,3 giây | Cần đồng ý |
| stealth/crouton-alpha | 6/6 câu, ~1,8 giây | Không yêu cầu |
| recursive/flint-v1.0:free | 6/6 câu, ~9,1 giây | Không yêu cầu |
| liquid/lfm-2.5-2.6b:free | 6/6 câu, ~5,4 giây | Cần đồng ý |
| liquid/lfm-3-1.7b:free | 6/6 câu, ~28,5 giây | Cần đồng ý |
| google/gemma-4-31b-it:free | 6/6 câu, ~9,1 giây; trước đó có 429 | Không yêu cầu |

Các thời gian là một lượt mẫu, không phải benchmark hay cam kết độ trễ.
`Crouton Alpha` được API công khai niêm yết giá bằng 0 dù ID không có `:free`.
Đúng JSON/đủ câu không đồng nghĩa chất lượng dịch hoàn hảo: các model nhỏ vẫn
có thể diễn đạt cứng hoặc hiểu sai quan hệ nhân vật. Liquid phải suy luận;
LFM3 dùng nhiều token suy luận và chậm rõ rệt trong mẫu này.

Tạm loại khỏi lựa chọn và cache:

- `google/gemma-4-26b-a4b-it:free`: cả 3 lượt đều trả HTTP 429 phía nhà cung cấp.
- `xingchen-agi/xing4.0-29b-a4b:free`: 2 lượt 429, lượt còn lại dịch “Mom” thành “cha”.

Không đánh dấu chúng đã bị ngừng vĩnh viễn. Không xóa biến thể trả phí.
Gemma 31B phục hồi ở lượt cuối nên vẫn được giữ, không gộp mọi Gemma vào cùng
một kết luận. Lỗi 429 phía upstream không chứng minh tài khoản đã hết quota.
Không thể bảo đảm model miễn phí luôn có công suất sau thời điểm kiểm tra.

## Thay đổi app

- Lọc hai route bất ổn trong danh sách mới, cache cũ và partial refresh.
- Dự án cũ đang lưu route bị loại được chặn trước khi gửi API và yêu cầu chọn
  lại model, không tự đổi sang model khác hoặc model tính phí.
- Bổ sung metadata LFM3 và Crouton Alpha vào danh mục có sẵn khi chưa tải lại.
- LFM3 yêu cầu cảnh báo/đồng ý riêng; không kế thừa quyền của LFM2.5 hoặc model khác.
- Đã làm mới cache danh mục công khai trên máy, không đổi lựa chọn trong dự án.

## Cách kiểm tra lại

Chạy bằng môi trường phát triển đã có kết nối OpenRouter. Đây là thao tác chủ
động sử dụng quota miễn phí; không chạy trong startup hay mỗi lần mở dropdown.

```powershell
.venv/Scripts/python.exe -X utf8 scripts/audit-openrouter-free.py --inference --extended --allow-synthetic-data-collection
```

`--probe-unavailable --model <id>` cho phép kiểm tra lại route tạm ẩn mà không
sửa danh mục app. Nếu thêm `--allow-synthetic-data-collection`, chỉ mẫu tổng hợp
được gửi với quyền allow để đối chứng lỗi chính sách; script không tự lưu quyền
đồng ý cho nội dung thật của người dùng.

Luồng dịch thật truyền tên đầy đủ `English`/`Vietnamese`; bài thử cũng dùng cùng
quy ước. Mẫu thăm dò đầu tiên dùng mã `en`/`vi` cho kết quả sai ngôn ngữ trên
Liquid; không dùng kết quả bài thử đó để kết luận app hoặc model không hoạt động.

Kết quả JSON cục bộ: `build/openrouter-free-audit-names-20261108.json` và
`build/openrouter-free-audit-extended-20261108.json`.

Nguồn công khai: [Danh mục model](https://openrouter.ai/api/v1/models),
[Giới hạn sử dụng](https://openrouter.ai/docs/api_reference/limits),
[Định tuyến và quyền dữ liệu](https://openrouter.ai/docs/guides/routing/provider-selection).
