# Đối chiếu EXE 1.0.4 và dev trên cùng file — 13/11/2026

## Kết luận

Trên file kiểm thử này, dev có hồi quy nhẹ ở bước OCR. Trung vị hai lượt mỗi bản:

- Xử lý OCR: 13,885 → 15,051 giây, tăng 1,166 giây (8,4%).
- Chờ preview sau OCR: 10,030 → 9,384 giây, giảm 0,646 giây.
- Cộng OCR và chờ preview: 23,915 → 24,434 giây, tăng 0,520 giây (2,2%).

Không thấy hồi quy tạo giọng trong bốn lượt này. Thời gian nạp model dao động mạnh; không được quy toàn bộ chênh lệch tổng hợp giọng cho tối ưu code. Riêng chờ preview sau tạo giọng, cả hai lượt dev đều thấp hơn hai lượt EXE.

## Kiểm soát đầu vào

- Dùng đúng `input/video.mp4` của dự án `w3`, không tải lại link TikTok.
- 1080×1920, HEVC, 30 FPS, thời lượng 88,566667 giây.
- SHA-256 đầu vào giống nhau ở cả bốn lượt và file gốc không đổi:
  `b8a9c9740a8395b1ef312071bde38643c6c5557a36ac3902477b49a0d9fdf2b0`.
- Cùng 52 câu dịch, thời gian và ID câu. Hash của danh sách chuẩn hóa
  `(start, end, text, segment_id)`:
  `c8b4b199a13c4782334ea2d1309200da8e4a4a5cd5193c59d5d417dbda4a711a`.
- Dùng lại cùng dữ liệu nhận dạng/dịch/tách giọng đã có trong bản sao riêng; không gọi Whisper, Gemini hoặc API dịch. Phạm vi đo là OCR, TTS và UI hoàn tất, không phải chạy toàn pipeline từ nguồn trống.
- Mỗi lượt có runtime/dự án riêng. Cache OCR, visual, voice, export, PCM và waveform được bỏ khỏi bản sao trước khi chạy. Log cả bốn lượt xác nhận `Cache miss` ở image và voice, không có `Cache hit`.
- Mỗi lượt thực sự tạo đủ 52 câu VieNeu GPU nhiều người nói.
- Giữ tỷ lệ gốc, tốc độ 1×, tự nhận diện vùng che và vá nền; cùng cài đặt phụ đề/âm thanh từ dự án đã sao chép. Giữ model trong RAM tắt.

## Bản app và môi trường

- EXE Core chính thức 1.0.4, commit `b5b28cca015d10e49324eb3d50b960e69c1a8198`.
- Binary SHA-256 không thay đổi:
  `9b3dc4c4e386c900f0992a1434ba4182d214f43d22eb7503dd53458055eb7526`.
- Dev là bản sao source hiện tại, chưa build, từ worktree dirty tại HEAD
  `c42ad9367de6145cd10db1b97cf16b8188bc24be`.
- Cùng tài nguyên đã cài ở `E:/HaizFlow-App/HaizFlowResources` (GPU engine 19, vision engine 9), cùng model. OCR chạy trên CPU; TTS chạy trên GPU.
- FFmpeg và FFprobe của hai bản có SHA-256 giống nhau:
  - FFmpeg: `4e5244d41e98a3d85667c21ddfd8428574b740f45ec0a07b38ce0b35e77fc270`.
  - FFprobe: `a57f27ed3574ee23d08a89946f32e1aa87fd072b3665607d36af44cfcbad04b6`.
- Chỉ thêm bộ đo vào QML của bản sao riêng; binary và bản cài người dùng không sửa. Hai bên cùng Qt offscreen/software, nên đây không phải đo độ trễ tương tác cửa sổ GPU thông thường.
- Thứ tự ABBA: EXE → dev → dev → EXE. RAM trống trước mỗi lượt khoảng 4,7–5,2 GiB. Không xóa cache hệ điều hành; cache trang/DLL có thể ảnh hưởng thời gian nạp model.

## Số đo từng lượt

Đơn vị giây. Processing tính từ ngay trước gọi tool bình thường đến log hoàn tất tool; preview tính tiếp đến khi có yêu cầu preview mới, media/audio hết busy, đủ narration timing và frame UI được trình bày. OCR phải đổi visual source, không được dùng frame cũ để kết thúc phép đo.

| Lượt | Bản | OCR | Preview sau OCR | Tạo giọng | Preview sau giọng |
|---|---|---:|---:|---:|---:|
| 1 | EXE 1.0.4 | 14,369 | 9,654 | 82,332 | 9,160 |
| 2 | dev | 15,162 | 9,441 | 66,279 | 7,273 |
| 3 | dev | 14,939 | 9,326 | 37,675 | 7,178 |
| 4 | EXE 1.0.4 | 13,401 | 10,405 | 38,068 | 10,686 |
| Trung vị EXE | | 13,885 | 10,030 | 60,200 | 9,923 |
| Trung vị dev | | 15,051 | 9,384 | 51,977 | 7,226 |

Hai lượt dev ghi nhận model load 38,781 / 12,106 giây, nhưng synthesis chỉ 13,351 / 12,299 giây. Vì vậy trung vị tổng TTS không phải bằng chứng riêng thuật toán tổng hợp nhanh hơn 13,7%. Khi nạp model đã nhanh hơn ở lượt cuối, processing EXE/dev gần nhau: 38,068 / 37,675 giây.

OCR trả về cùng vùng che ở cả bốn lượt:
`x=15.28%, y=47.19%, width=69.58%, height=6.09%, confidence=0.989, samples=31`.
Log quét 36 frame mỗi lượt; thời gian OCR nội bộ làm tròn là EXE 12,6 / 12,1 giây và dev 14,1 / 13,9 giây. Chênh lệch không phải vì dev xử lý file chất lượng cao hơn hoặc tìm ra vùng khác.

## Dữ liệu và giới hạn

Raw results, log, bản sao source và runtime:
`build/same-file-compare-20261112-1794502588997787200/`.
`comparison.json` chứa từng lượt, `summary.json` chứa trung vị.

Chỉ có hai lượt mỗi bản trên một video; không suy rộng thành mọi codec/video hay mọi cấu hình máy. Chưa profiling để quy chênh lệch OCR cho chính xác một hàm. Không sửa code sản phẩm trong lượt đo này, không build, push, publish, đăng video hoặc sửa/xóa dự án thật. Các worker thử nghiệm đã kết thúc.
