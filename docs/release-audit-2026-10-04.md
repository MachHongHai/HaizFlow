# Rà soát trước đóng gói — 04/10/2026

## Kết luận

Môi trường phát triển Core đã qua kiểm tra. **Chưa đủ cơ sở phê duyệt bản
installer phát hành công khai**, đặc biệt nếu bản phát hành phải dùng delta update.
Không build executable/installer, commit, push, đăng release hoặc chạy lại dự án
người dùng trong đợt rà soát này. Kết quả source không thay thế kiểm thử bản frozen.

## Kết quả kiểm tra

| Hạng mục | Kết quả | Phạm vi |
| --- | --- | --- |
| Kiểm thử Python | 1.244 qua; 1 bỏ qua; 150 subtest qua | Source, dữ liệu kiểm thử cô lập; không chạy lại pipeline dự án người dùng |
| UI Qt cô lập | 15 qua | Cài đặt/Áp dụng, API key, bản quyền, chỉnh phụ đề/karaoke nhiều dòng, lặp nhạc và thanh trạng thái; ảnh kiểm tra trên D: |
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

- Karaoke nhiều dòng trong editor không còn tô đồng thời từ đầu của từng dòng.
  Preview tách vùng tô theo biên glyph từng dòng và lấy thứ tự/thời lượng từ
  clock ASS xuất. Tua lùi giữ đúng trạng thái; delegate ảnh được giữ giữa các
  nhịp phát, không chạy FFmpeg lại theo playhead. Cache sprite chuyển sang v3
  để không dùng lại metadata cũ. Auto dùng chung overlay; mẫu 45% cũng theo
  một clock liên tục thay vì 45% ở tất cả các dòng. Kiểm thử Qt thực kiểm tra
  kéo tăng hàng và tái sử dụng delegate; FFmpeg kiểm tra pixel màu trên ba
  thời điểm của ASS nhiều dòng, xác nhận dòng sau không đổi màu trước lượt.
  Không xuất lại dự án người dùng hoặc làm mất cache nhận dạng/dịch/giọng.
- Auto và Batch dùng bộ chỉnh kiểu chữ tương ứng Manual: màu chữ/karaoke/
  viền, đậm và nghiêng. Lược điều khiển phông, bóng, giãn ký tự, căn chữ,
  in hoa và ô cỡ chữ; các góc khung vẫn điều chỉnh cỡ chữ. Giá trị đã lưu
  trong project cũ được giữ nguyên, không xóa dữ liệu style.
  Preview dùng raster libass cùng đường xuất video, worker riêng không thay
  thế overlay của editor. Đóng cửa sổ giải phóng trạng thái mẫu; refresh khi
  kéo được gom lại, không tạo worker theo mỗi sự kiện con trỏ.
- Cài đặt → API Key quản lý Gemini và Zernio; project giữ model dịch, lựa chọn
  tài khoản, nội dung và tùy chọn đăng. Khi chưa có key, chức năng cục bộ vẫn
  sử dụng được; thao tác cần dịch vụ có hướng dẫn đến đúng mục cài đặt.
  Lược banner trạng thái màu, huy hiệu và đoạn giải thích dài trong UI key.
- Kiểm tra Zernio độc lập với project, không tạo hồ sơ trên dịch vụ khi kiểm tra.
  Key thay thế chỉ được ghi vào Credential Manager sau khi kiểm tra đọc hồ sơ/
  tài khoản thành công; lỗi xác thực, kết nối hoặc lưu giữ nguyên key cũ.
  Kiểm tra này không khẳng định quyền POST; hướng dẫn yêu cầu key đọc và ghi.
  Xóa key không sửa lựa chọn tài khoản, nội dung hoặc hàng đợi trong project.
  Kiểm thử dùng client/credential store giả, không dùng key người dùng hoặc đăng bài thật.
  Hướng dẫn quyền key và định dạng key giới hạn được đối chiếu với
  [tài liệu Zernio](https://docs.zernio.com/api-keys/create-api-key).
- Cài đặt chung Batch được chỉnh trong bản nháp đến khi Áp dụng. Kiểu chữ
  và layout được lưu đầy đủ, video có cài đặt riêng được giữ nguyên trừ khi
  người dùng xác nhận thay thế. Kiểm thử filesystem kiểm tra lưu/mở lại,
  giữ/thay thế override và từ chối dữ liệu sai trước khi ghi. Backend của
  luồng Áp dụng mới chặn model GPU khi app đang dùng CPU; khóa chỉnh trong
  lúc Batch chạy. Không chạy pipeline thật hoặc xuất lại video người dùng.
- Lược icon trang trí và icon cạnh nút/menu đã có nhãn, kể cả trạng thái,
  thông báo và Batch. Giữ điều khiển icon-only (phát/dừng, đóng, điều hướng,
  menu), tay nắm, checkbox, mũi tên dropdown và logo nền tảng. Kiểm thử GUI
  xác nhận icon của nút có nhãn bị ẩn và nút icon-only vẫn hiển thị.
- Tay nắm cạnh phụ đề nằm đúng trên khung chữ, không bị đẩy ra ngoài khi
  chữ thấp. Chiều rộng dùng kích thước khung mới để xác định số từ; phép đo
  glyph theo Win ascent/descent của libass, không nhầm với kích thước EM của
  Pillow/Qt. Đã đối chiếu với raster thật. Chỉ đổi kích thước chứa chữ, không
  đổi thời gian đọc hoặc phóng ngang glyph. Bản render cũ dùng thuật toán
  phân dòng trước sửa không được coi là cache hợp lệ cho lần render mới;
  các checkpoint nhận dạng, dịch, giọng và âm thanh vẫn giữ nguyên.
- Auto vẫn mở được Chỉnh phụ đề khi bật che phụ đề gốc. Checkbox căn theo
  ô che khóa thao tác thủ công; bỏ chọn dùng layout đã lưu trong render.
  Preview dùng câu mẫu dài, chung cách chia từ/dòng với render, nhận đủ
  chiều rộng/cao sau khi kéo. Test GUI kiểm tra kéo ngang thêm từ, kéo dọc
  thêm dòng, giữ cỡ chữ và khóa/mở thao tác qua checkbox.
- Cửa sổ nhập nhạc nền từ liên kết dùng bố cục/điều khiển chung với cửa sổ
  nhập video. Mỗi lần mở có trạng thái hiển thị riêng, không biến kết quả
  thành công/lỗi của lần trước thành cảnh báo cho lần mới. Trạng thái tải
  gọn, lỗi dài có Chi tiết; test GUI kiểm tra mở lại sau thành công và thất bại.
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
  CPU vẫn chọn Small CPU. Giá trị mặc định cũ `small` theo cấu hình ứng dụng;
  giữ nguyên lựa chọn tường minh Small CPU/Small GPU/Turbo của dự án.
  Kiểm tra request warm bằng test; chưa chạy inference Turbo thật trong
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

## Bổ sung nhận dạng mẫu giọng và thao tác phụ đề

- Log clone của `discord` cho thấy 46 giây nhận dạng mẫu trên CPU trước khi
  worker OmniVoice được gọi bằng `cuda:0`; tác vụ dừng trong bước import runtime,
  chưa có bằng chứng OmniVoice tự chuyển sang CPU trong lần chạy này.
- Nhận dạng mẫu theo thiết bị của OmniVoice. Whisper CUDA dùng float16;
  CPU dùng int8. Nếu CUDA thiếu tài nguyên, chỉ bước nhận dạng mẫu được thử lại
  trên CPU và có log riêng; không đổi cấu hình TTS. Nội dung của cùng một mẫu
  được chuẩn bị một lần cho cả danh sách đoạn.
- Thử inference Whisper Small CUDA trên mẫu giọng đóng gói: hai lần khoảng
  11,85 và 8,75 giây, không fallback CPU. Không so trực tiếp với 46 giây của
  mẫu người dùng khác, không suy ra thời gian toàn bộ luồng clone từ phép thử này.
  Kiểm thử tiếp qua request file và subprocess thật: 10,14 giây, worker xác nhận
  `device=cuda compute_type=float16`; log và cache kiểm thử ở thư mục build trên D.
- Khung phụ đề có bốn tay nắm ngang/dọc độc lập, giữ cạnh đối diện và có điều
  khiển bàn phím. Các góc vẫn đổi cỡ chữ. Chiều rộng/cao điều chỉnh sức chứa
  cụm chữ; khung cao hỗ trợ tối đa ba dòng, không đổi đồng hồ từ hoặc âm thanh.
  Preview chỉ dựng đoạn hiện tại khi kéo, giữ raster hợp lệ trong lúc thay thế;
  lưu document/history khi thả chuột, không theo từng sự kiện di chuyển.
- Sửa khung chọn bám theo alpha bounds của chữ render, không bao cả vùng chứa
  câu. Kéo cạnh ngang thay đổi sức chứa từ, không đổi cỡ chữ; giữ hệ tọa độ
  kéo ổn định khi raster được thay thế. Tay nắm không chồng nhau ở chữ một dòng
  nhỏ. Chia cụm theo độ rộng glyph/font và khoảng cách chữ, thay vì đếm ký tự;
  giữ đồng hồ từ, tránh cụm một từ khi có cách chia phù hợp. Kiểm tra bằng
  libass raster thật, thao tác Qt và test tăng/giảm sức chứa ngang.
- Ô watermark lưu khi mất focus hoặc Enter, có kiểm tra nhập tiếng Việt, nhiều
  lần sửa và chống lưu lặp. Dialog dùng nhãn Đóng do nội dung được tự lưu.
- Chuẩn hóa LF cho các dependency locks theo hash đã duyệt; thêm thuộc tính Git
  để checkout Windows không biến đổi hash vì CRLF. Không thay phiên bản gói,
  không sửa manifest hash nhằm bỏ qua kiểm tra toàn vẹn.

## Điều kiện còn thiếu trước phát hành

### Cài đặt, API key và nhận diện người nói

- Cài đặt sử dụng tab điều hướng; nội dung và thanh Áp dụng được căn giữa.
  Áp dụng nằm ngoài vùng cuộn, thay đổi ngôn ngữ/thiết bị chỉ lưu khi xác nhận.
- Gemini và Zernio dùng chung bố cục danh sách key có tên, chọn mặc định và
  form thêm key được che nội dung. Zernio kiểm tra kết nối trước khi đổi mặc định;
  thao tác bị khóa khi đang đăng. Key cũ trong Credential Manager vẫn dùng được.
  Tệp metadata chỉ chứa ID/tên, không chứa secret. Đổi key không tự chuyển
  đích đăng của dự án; tài khoản không khả dụng cần được người dùng chọn lại.
- WeSpeaker model và ONNX CPU được cấu hình đóng gói trong Core; không còn mục
  tải riêng trong danh sách tài nguyên. Chưa dựng installer để xác nhận artifact.
- Đã benchmark CPU/CUDA trên âm thanh thật ở ba lượt/process mới: nhận diện CPU
  nhanh hơn cả video ngắn lẫn dài, embedding gần trùng và cluster trùng nhau.
  Giữ CPU cho tính năng này, không thêm ONNX GPU vào engine CUDA.
  Xem [phương pháp và số liệu benchmark](speaker-backend-benchmark-2026-10-04.md).
  Kiểm thử request thực qua RPC Core với mẫu giọng đóng gói cũng trả về
  `speaker-1` và báo `device=cpu`; không chạy pipeline/cache dự án người dùng.
- Cửa sổ bản quyền tự vừa nội dung, chỉ cuộn ở màn hình thấp. Card dự án đăng
  hiển thị số lượng theo dạng “7 bài đăng”, bỏ dấu gạch không cần thiết.

### Bổ sung UI và nhạc nền editor

- Hướng dẫn Zernio chỉ được tạo tại Cài đặt API Key. Menu dự án điều hướng
  tới đúng trang và mở cùng cửa sổ; không còn cửa sổ hướng dẫn riêng ở dự án.
- Kết quả kiểm tra key hiển thị thành công/thất bại kèm chấm xanh/đỏ.
  Kết quả lần kiểm tra mới không được lấy từ cờ xác thực của key cũ.
- Bỏ dòng thay đổi chưa lưu, nhãn Khuyên dùng và phần giới thiệu nhận diện
  người nói trên trang tài nguyên; giữ tính năng nhận diện CPU tích hợp.
  Thanh trạng thái hiển thị lại Sẵn sàng và giữ nguyên chiều cao giữa các trạng thái.
- Lựa chọn GPU đối chiếu kết quả dò phần cứng thay vì chỉ dùng giá trị đã lưu.
  Trong lúc dò chưa xong, lựa chọn được giữ; thao tác GPU vẫn chờ xác minh.
  Gói môi trường Whisper Small/OmniVoice đi theo lựa chọn CPU/GPU của dự án.
- Nhập/đổi/xóa nhạc nền đồng bộ document editor và model timeline ngay,
  không cần bật tự giảm nhạc. Editor có công tắc lặp nhạc, lưu vào clip;
  preview và bộ trộn khi xuất đều đọc trạng thái này. Hỗ trợ lịch sử hoàn tác.
- Dữ liệu Discord chỉ được đọc để kiểm tra sự lệch giữa video metadata và
  editor document. Không chạy lại pipeline hoặc thay đổi file dự án người dùng.
  Kiểm thử hồi quy dùng dữ liệu tổng quát, không gắn tên hay nội dung một video.

### Các gate còn lại

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
