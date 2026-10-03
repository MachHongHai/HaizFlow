# Rà soát trước đóng gói — 04/10/2026

## Kết luận

Môi trường phát triển Core đã qua kiểm tra. **Chưa đủ cơ sở phê duyệt bản
installer phát hành công khai**, đặc biệt nếu bản phát hành phải dùng delta update.
Không build executable/installer, commit, push, đăng release hoặc chạy lại dự án
người dùng trong đợt rà soát này. Kết quả source không thay thế kiểm thử bản frozen.

## Kết quả kiểm tra

| Hạng mục | Kết quả | Phạm vi |
| --- | --- | --- |
| Kiểm thử Python | 1.181 qua; 1 bỏ qua; 150 subtest qua | Source, dữ liệu kiểm thử cô lập; không chạy lại pipeline dự án người dùng |
| Qt Quick Test | 77 qua | Điều khiển preview, clone giọng, popup và các component hiện có |
| Python lint/compile | Qua | Source và script; kiểm tra tên chưa định nghĩa và cú pháp |
| QML lint | Qua, không diagnostic | Toàn bộ tệp QML cấp ứng dụng |
| Runtime Core | Qua | Python 3.13.5, PySide6 6.11.1, FFmpeg/ffprobe 8.1.2, PyInstaller 6.21.0 |
| Dependency locks | Qua | Core và ba engine; version/SHA-256/provenance |
| Audit dependencies | Qua với ngoại lệ đã ghi nhận | Core, CPU, CUDA, vision và phiên bản chuẩn của họ PyTorch; không đồng nghĩa không có advisory |
| Resource manifest | 0/3 engine sẵn sàng phát hành | Thiếu URL và SHA-256 của artifact phát hành |
| Hồ sơ tuân thủ | Chặn phát hành công khai | Các mục rà soát chưa được xác nhận |
| Trình biên dịch installer | Có | Inno Setup 6 trong thư mục chương trình cục bộ của người dùng; chưa chạy biên dịch |
| Installer/delta frozen | Chưa kiểm chứng | Không build trong đợt này |

Các kiểm tra qua: `scripts/test.ps1`, `scripts/audit-dependencies.ps1`,
`scripts/verify-dependency-lock.py`, `scripts/verify-engine-dependency-locks.py`,
`scripts/verify-runtime.py --profile core --for-build`.
Lỗi QML metadata phát hiện ở cuối `test.ps1` đã sửa; toàn bộ QML được lint lại
riêng và không còn diagnostic.

## Những lỗi đã sửa trong đợt này

- Bấm ngoài ô nhập bỏ focus và selection, bao gồm API key và watermark. Commit
  bộ đệm IME trước khi chuyển focus; không nuốt click nút và giữ thao tác bàn phím.
- Thông báo chi phí Gemini ngắn hơn; toast bị cắt có nút **Chi tiết** mở toàn bộ
  nội dung. Không dùng nội dung release/provider làm rich text hoặc mã thực thi.
- Lỗi dịch vụ Gemini có thông báo riêng, phân biệt với hết bộ nhớ và thanh toán.
  Log retry ghi model, HTTP status và lần thử, không ghi API key.
- Release test gate dùng pytest để thu cả unittest và test dạng hàm/fixture.
  pytest được khóa phiên bản/hashes; không được đưa vào Core frozen.
- Bổ sung `tiktokWaitingCount` vào metadata QML; thuộc tính backend đã có sẵn.
- Nâng urllib3 2.7.0 lên 2.8.0 trong môi trường dev và cả ba engine locks để vá
  PYSEC-2026-4175/4176/4177. Không nâng phiên bản model hoặc các dependency AI khác.
- Chặn `load_custom_generate` trước khi nạp HY-MT2 và OmniVoice, phòng
  CVE-2026-80047. Giữ hàm sinh chuẩn; có test chặn download và kiểm tra lặp an toàn.
  Ngoại lệ bảo mật tạm thời được ghi tại
  [chính sách dependency](dependency-security.vi.md), phải rà lại trước release.
- Audit tools, file tạm và cache của pip-audit được chuyển vào `build/dependency-cache`
  trên ổ D; runtime/model/Hugging Face/Torch cache cũng được xác minh ở ổ D.

## Bổ sung editor, import và OCR

- Mặc định project GPU và warm lúc khởi động cùng chọn Whisper large-v3-turbo;
  CPU vẫn chọn Small CPU. Không thay thế lựa chọn model đã được lưu riêng trong
  dự án. Kiểm tra request warm bằng test; chưa chạy inference Turbo thật trong
  đợt này. Các giới hạn bộ nhớ và ưu tiên tác vụ đang xử lý được giữ nguyên.
- Project Manual mới dùng phụ đề 84 px, vị trí dọc 80%, vùng cao 12%; vùng OCR
  dùng để xóa chữ nguồn, không thay thế bố cục phụ đề dịch. Không sửa bố cục đã
  chỉnh trong các tài liệu editor hiện có.
- Thanh tua giữ nguyên vị trí và chiều dài khi phát/dừng hoặc giữ chuột. Bổ sung
  test GUI với thao tác chuột; việc đổi monitor giữ đúng đồng hồ sequence.
- Theo yêu cầu mới, tạm khóa kéo/trim trực tiếp clip nguồn ở UI và backend.
  Thao tác cắt nguồn riêng, chỉnh phụ đề/voice và các quyết định source đã lưu
  vẫn được giữ. Kiểm thử PCM stereo và render FFmpeg thật bằng media tổng hợp
  xác nhận timeline có gap vẫn là hình đen và âm thanh im lặng.
- Import từ project tải xuống trả về đúng kết quả xếp hàng batch, không đóng
  cửa sổ khi queue từ chối. URL mới không hiển thị metadata của URL trước đó.
- UI đăng mạng xã hội và nhập link dùng component/theme hiện có, giảm nhãn và
  màu trạng thái lặp; giữ tiến trình, lỗi và thao tác mở bài đăng/sao chép caption.
  Không thực hiện đăng hoặc tải video từ dịch vụ bên ngoài để kiểm thử UI.
- Danh sách nhập sang mạng xã hội dùng bản render đã hoàn tất của từng dự án,
  không dùng điều kiện cache-hit của pipeline để ẩn video đã xuất. Đối chiếu
  dữ liệu hiện có xác nhận file render hoàn tất của `testgg` còn tồn tại nhưng khác chữ ký
  cấu hình hiện tại; danh sách sau sửa có cả `testgg` và `discord`. Import pin
  đúng snapshot đã chọn, xác minh trước khi sao chép; không phụ thuộc file
  xuất bên ngoài hoặc tự chạy lại model. Test dùng dự án tổng hợp, không có
  logic xử lý riêng theo tên dự án người dùng.
- Chọn phụ đề bằng ID clip đồng bộ đoạn trong inspector; điều hướng trong
  cửa sổ chỉnh sửa cũng đồng bộ selection trên timeline. Đổi nhãn thành
  “Chỉnh sửa”; Lưu giữ cửa sổ mở và vị trí nút ổn định qua trạng thái dirty/saved
  và khi đổi đoạn. Test GUI kiểm tra click timeline và nhiều lần lưu tiếng Việt.
- OCR đọc 36 khung hình của project `discord` xác nhận hai dòng chữ trên áo bị
  gộp vào caption. Detector v23 vẫn lọt dòng thứ hai khi OCR chỉ nhận được vài
  quan sát: khoảng percentile 10/90 che mất hai vị trí thể hiện chuyển động.
  Detector v24 dùng khoảng 5/95 cùng điều kiện lặp ngoài dải caption, loại dòng
  này trước khi gộp. Đã tái hiện và kiểm lại qua hàm detector thật, đúng JPEG
  quality 4/scale/fps của app: box từ 16,88% xuống 7,73%. Subtitle nhiều dòng và
  từ lặp trong caption vẫn qua test; không xử lý theo tên project/câu chữ.
- Chữ ký OCR được tăng phiên bản; migration chỉ tiếp nhận cache đúng detector
  và đúng identity của source. Không ghi đè cache hay chỉnh sửa của `discord`.
  Người dùng chạy lại Che phụ đề để xuất bản kết quả OCR mới vào project.
- Hàng đợi đăng giới hạn chiều cao phần tiêu đề/setup và đặt khoảng trống dư
  cuối trang, tránh layout kéo giãn khoảng cách giữa heading và list. Test GUI
  sáu video xác nhận khoảng cách 16 px; danh sách 80 video cuộn bằng wheel xuống/
  lên và tiếp tục hoạt động sau khi thu nhỏ cửa sổ. Đã render kiểm tra bố cục.

## Gemini 3.8 Flash

Log dự án ghi HTTP 503 sau retry. Request dùng đúng model ID và mức thinking
được model hỗ trợ. Không có bằng chứng trong log rằng nguyên nhân là tài khoản
miễn phí hoặc bắt buộc thanh toán. Google mô tả 503 là dịch vụ tạm thời không
khả dụng; lỗi này không xác nhận tình trạng toàn bộ dịch vụ Google.

UI hướng dẫn thử lại sau hoặc chọn Flash-Lite; không tự đổi model và không tự
phát sinh request bằng API key của người dùng để kiểm tra.
[Tài liệu xử lý lỗi Google](https://ai.google.dev/gemini-api/docs/troubleshooting),
[model Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash).

## Điều kiện còn thiếu trước phát hành

1. **Artifact engine:** dựng và kiểm thử CPU/CUDA/vision, sau đó điền URL bất biến,
   dung lượng thực và SHA-256. Không lấy hash từ gói giả hoặc tự đoán URL.
   `verify-resource-pack-manifest.py --strict` hiện chặn vì metadata trống.
2. **Delta và installer:** source delta đã có test, nhưng chưa đóng gói
   Launcher/Updater/Core hoặc tích hợp vào installer. Script installer hiện dùng
   layout phẳng và các signing gates cũ; không được coi là quy trình phát hành
   delta không Authenticode. Xem [trạng thái cập nhật](updates.md).
3. **Tuân thủ:** `verify-legal-state.py --public-release` còn chặn các mục
   `owned-code-and-contributor-scope`,
   `omnivoice-noncommercial-checkpoint-and-preview-assets`,
   `ffmpeg-complete-corresponding-source`,
   `qt-lgpl-module-and-relinking-evidence`, và thiếu xác nhận rà soát public release.
   Không tự đánh dấu những mục này hoàn tất hoặc bỏ release gate.
4. **Kiểm thử bản đóng gói:** cài mới/nâng cấp/gỡ cài đặt, bảo toàn project/resource,
   download hỏng/mất mạng, rollback và health acknowledgment của Core thực.
5. **Kiểm thử thiết bị/dịch vụ:** micro thật và IME tiếng Việt trên máy người dùng,
   media thực với worker frozen, CPU/GPU dưới áp lực bộ nhớ, và Gemini 3.8 sau khi
   dịch vụ phản hồi bình thường. Đợt này chỉ kiểm tra UI bằng thao tác Qt tự động,
   không chứng nhận lại chất lượng âm thanh của các project đã có.

Khi chạy test có cảnh báo TorchCodec từ Pyannote: DLL decoder tích hợp không
nạp được trong môi trường hiện tại. Đường VAD của HaizFlow truyền waveform đã
nạp trong bộ nhớ, không dựa vào decoder đó. Vẫn cần kiểm chứng luồng frozen với
media thực; không sửa cảnh báo bằng cách đổi FFmpeg/model hàng loạt.

Thay đổi source đang để người dùng duyệt. Release provenance cần được xác lập
ở lần đóng gói chính thức; không tạo commit thay người dùng để vượt kiểm tra.
