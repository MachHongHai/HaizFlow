# Hướng dẫn dịch Gemini

Trong Manual, Auto và cấu hình chung Batch, chọn một model Gemini để hiện nút
**Văn phong & hướng dẫn**. Chọn một văn phong rồi nhập hướng dẫn riêng nếu cần;
các lựa chọn được lưu cùng cấu hình video/dự án:

- **Cân bằng** (mặc định): rõ nghĩa, trung tính, cân bằng độ sát và dễ đọc.
- **Sát nghĩa**: bám sát cách diễn đạt gốc, hạn chế diễn đạt lại, không dịch máy móc.
- **Tự nhiên**: ưu tiên lời thoại tự nhiên trong ngôn ngữ đích.
- **Linh hoạt**: chuyển thành ngữ, hài hước và cảm xúc cho phù hợp đối tượng xem;
  không thêm tình tiết, đổi số liệu hay tăng sắc thái quá mức so với nguồn.

Hai ô tùy chọn:

- **Bối cảnh và cách dịch**: bối cảnh, sắc thái, phong cách dịch.
- **Tên nhân vật và xưng hô**: quy ước tên, vai vế và cách gọi giữa từng cặp nhân vật.

Ví dụ:

```text
王明 → Vương Minh
Minh và Lan là bạn cùng tuổi: tôi – cậu.
Lan nói với bố: con – bố.
Giữ nhất quán tên nhân vật, không tự suy diễn quan hệ tình cảm.
```

Mỗi ô tối đa 4000 ký tự. Để trống vẫn dùng các quy tắc nhất quán mặc định.
Quy ước có thể áp dụng chung cho Batch hoặc chỉnh riêng từng video. Hủy hộp thoại
không lưu; đổi dự án đóng bản nháp để tránh ghi nhầm vào video khác.

## Ngữ cảnh và cache

Mỗi nhóm dịch nhận thêm một lượng giới hạn các cặp câu gốc/bản dịch đã được
chấp nhận ở đầu video và gần nhóm hiện tại, cùng một vài câu gốc lân cận.
Ngữ cảnh được dựng lại từ kết quả từng nhóm đã lưu khi tiếp tục sau khi dừng.
Thử lại HTTP hoặc sửa riêng câu dịch lỗi vẫn nhận cùng hướng dẫn và ngữ cảnh.
Không chia sẻ ngữ cảnh giữa các video, không thêm một lượt gọi model để phân
tích toàn phim và không thay thế đại từ hàng loạt sau dịch. Có thêm token ngữ
cảnh trong các yêu cầu dịch hiện có.

Gemini dùng cấu hình lấy mẫu mặc định của Google, không ép temperature thấp.
Với Flash-Lite, khi nhập hướng dẫn riêng hoặc chọn văn phong khác Cân bằng, mức suy luận tăng từ `minimal` lên
`low` để xử lý quy ước/quan hệ; lượt dịch có thể chậm và dùng nhiều token suy
luận hơn một chút. Không thêm lượt gọi kiểm tra toàn bộ bản dịch. Prompt yêu
cầu soát chính tả và không sao chép lỗi từ bản dịch trước; không tự sửa tên
riêng bằng từ điển hoặc bảng thay thế chữ cố định.

Đổi văn phong/hướng dẫn làm mất hiệu lực cache dịch Gemini liên quan, không buộc Whisper
nhận dạng lại chỉ vì thay hướng dẫn. Phụ đề và giọng đã xuất bản trong editor
vẫn giữ nguyên đến khi người dùng chủ động chạy lại. Các model HY-MT2 không dùng
hai trường này. Hướng dẫn và phụ đề được gửi tới Google khi chạy Gemini;
không ghi nội dung hướng dẫn hay API key vào log kỹ thuật.

## Giới hạn

Đây là hướng dẫn cho model, không phải bộ xác minh danh tính nhân vật. Câu
thoại thiếu ngữ cảnh vẫn có thể bị suy luận sai. Xưng hô có thể đổi hợp lý theo
người nói, người nghe hoặc cảnh; không ép mọi nhân vật dùng một đại từ duy
nhất. Các ví dụ dịch trước giúp giữ nhất quán nhưng không chứng minh chúng đúng.
Quy ước do người dùng nhập được ưu tiên khi có bằng chứng rõ ràng hơn.

Kiểm thử offline bao phủ chia nhóm, tiếp tục, retry, sửa câu riêng, cache,
Batch, quyền sở hữu hộp thoại và giao diện Qt. Không dùng API trả phí trong
kiểm thử; chưa có đánh giá chất lượng trên tập video có nhãn nhân vật.
