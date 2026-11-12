# Rà soát hiệu năng — 08/11/2026

Đã rà 225 tệp QML và truy vết các đường Python điều khiển UI, preview, audio,
timeline, batch, catalog và export. Sau báo cáo ban đầu, đã triển khai 11 điểm
chính (D-001 đến D-010 và D-013); hai điểm nhỏ hơn vẫn giữ nguyên. Không nạp
model nặng hoặc chạy lại/sửa dữ liệu dự án thật trong lượt kiểm thử này.

## Những điểm nên ưu tiên

| Khu vực | Điểm còn tốn công | Hướng tối ưu |
|---|---|---|
| Preview âm thanh | Mỗi buffer quét mọi câu/track và vùng ducking, kể cả câu chưa tới | Chỉ mục khoảng thời gian; chỉ trộn track đang có âm thanh |
| Kéo phụ đề | Hai lượt dựng/quét mốc snap toàn timeline mỗi pointer event | Cache mốc biên theo revision, binary search |
| Track timeline | Sửa document làm reset model track ngoài, kéo theo tạo lại clip/waveform | Model keyed ổn định theo track_id, notify granular |
| Preview video | Fullscreen result có thể chạy thêm bộ giải mã watermark; view nguồn vẫn seek overlay kết quả ẩn | Một chủ sở hữu playback, chặn source/seek khi layer không active |
| Batch | Progress làm quét lại settings/results toàn batch và metadata preview | Tách notify settings/membership khỏi progress, cập nhật theo video |
| Animation/cắt ghép | Mỗi tick lọc/sort keyframe và quét source edit decisions | Chuẩn bị index một lần; binary search/cursor khi phát |
| Panel xuất | Notify rộng làm đọc document và chạy preflight filesystem lặp trên GUI thread | Cache/coalesce panel; luôn kiểm tra nghiêm ngặt lại trước khi thực xuất |
| Snapshot/catalog | Getter document/phụ đề đọc hai lần; cập nhật một project vẫn lọc toàn catalog | Projection cache và membership/row index |

Các đường trên có quan hệ gọi cụ thể đã xác minh; đều là mức P2, không phải
kết luận chắc chắn một project đang lag vì tất cả các điểm này đồng thời.

## Bản vá đã áp dụng

- Audio index được chuẩn bị cùng track, dùng cây khoảng thời gian để tránh
  quét toàn bộ cue kể cả khi có một track nguồn/nhạc dài. Giữ thứ tự cộng mẫu,
  overlap, ducking, fade, loop, mute và danh sách PCM gốc khi nhận kết quả.
- Index keyframe/overlay dựng khi document thay đổi, không sort mỗi tick.
- Timeline cache mốc snap và lookup source decision; giữ nguyên tie-breaking,
  timestamp biên, gap và thứ tự ưu tiên của quyết định nguồn chồng nhau.
- Track ngoài dùng keyed ListModel, giữ delegate/clip/waveform khi chỉnh nội
  dung. Đồng bộ chỉ sau khi ListModel sẵn sàng, tránh lỗi undefined trong log.
- Fullscreen/nguồn/kết quả có quyền sở hữu decoder rõ ràng; overlay ẩn không
  giữ source hoặc seek video nền.
- Progress batch không phát lại notify settings. Summary chỉ cập nhật khi
  status/error/step hoặc danh sách job đổi, không theo mỗi tick phần trăm xuất.
- Catalog giữ membership và row index, không lọc toàn bộ project để sửa một
  video. Cache caption projection theo revision; expose source decisions riêng
  thay vì serialize toàn editor document hai lần.
- Preflight panel gộp notify trong 120 ms, dùng snapshot và cache tối đa 1 giây.
  Nút xuất gọi kiểm tra mới cưỡng bức, không dùng kết quả cache của panel.
- Bỏ ba lời gọi composition.refresh trùng ngay sau set_document; signal của
  document model đã gọi refresh. Không thay cache key/version OCR hoặc voice.

## Lỗi warm-up của testdai và trạng thái khởi động

Log `testdai` ghi hai lượt lỗi bàn giao sau đúng 30 giây, trước khi pipeline
chạy (16:46:55 và 16:53:22 giờ Việt Nam). Điều kiện chờ trong quiesce coi cả
model đang nạp đúng capability sắp sử dụng là model phải giải phóng. Điều kiện
này đã có trong source trước diff tối ưu hiện tại; log không đủ để quy một
commit cụ thể là nguyên nhân khiến tình huống lần đầu xuất hiện trên máy.

Đã đổi thành bàn giao cho đúng runtime/request lock đang sở hữu model, không
nạp bản thứ hai và không báo lỗi giải phóng chỉ vì cold load vượt 30 giây.
Warm-up khác capability vẫn bị preempt/chờ an toàn. Thêm kiểm tra atomic ngay
trước khi bắt đầu warm để background không lách qua lúc foreground vừa suspend.
Không tự fallback CPU hoặc tắt kiểm tra bộ nhớ. Có test matching/non-matching
capability, không cần model thật.

Danh sách dự án phân biệt loading/ready/error. Khi dữ liệu chưa về, UI không
báo “Chưa có dự án”; trạng thái trống chỉ xuất hiện sau khi catalog được công bố.

## Kiểm tra scaling nhẹ

- Hàm PCM mixer hiện tại, dữ liệu tổng hợp 100/1.000/10.000 track nối tiếp:
  khoảng 0,106/0,213/2,038 ms cho mỗi buffer 480 frame. Timer refill là 10 ms;
  nên tránh quét toàn bộ số câu khi số câu tăng.
- Hàm evaluate keyframe hiện tại, 5 thuộc tính, 100/1.000/10.000 key tổng cộng:
  khoảng 0,033/0,271/2,728 ms mỗi tick. Nhiều overlay active sẽ cộng thêm chi phí.

Mỗi case chạy 20 lượt trên hàm gốc được tách để kiểm tra scaling, không khởi
động model. Đây **không phải** benchmark end-to-end hoặc cam kết mức tăng tốc.

Đo sau bản vá (`scripts/benchmark-preview-index.py`, median 20 lượt):

- 10.000 track, buffer 480 frame: khoảng 2,94 ms → 0,024 ms; PCM đối chứng
  byte-identical. Không suy ra tốc độ render hoặc TTS tăng cùng tỉ lệ.
- 10.000 keyframe, 5 thuộc tính: khoảng 2,23 ms → 0,004 ms.
- Projection 1.000 caption tổng hợp: khoảng 35,4 ms → 16,6 ms. Đây là giảm chi
  phí UI lặp sau xử lý, chưa phải đo toàn thời gian từ khi OCR/TTS kết thúc đến
  khi video thật sẵn sàng. Document testdai hiện không có caption do dịch lỗi,
  nên không dùng nó để công bố tốc độ reload phụ đề.

## Những điểm nhỏ hơn, chưa cần ưu tiên

- Khi mở log kỹ thuật, rich text bị dựng/layout lại; log đã giới hạn 800 dòng/
  60.000 ký tự và được unload khi đóng. Có thể debounce search/filter chung.
- Kéo size watermark text relayout text chính và 8 outline; có thể scale group
  khi kéo rồi rasterize lại khi thả.
- Cần profiling thêm việc tính subtitleSampleText trong dialog khi fallback
  text đã bị sprite thay thế; hiện chỉ là nghi vấn (75/100), chưa chốt sửa.

## Kết quả kiểm tra và giới hạn

- Qt qmllint: 225/225 thành công, không có native warnings.
- Linter quy ước: 1.812 pattern/style findings; không được hiểu là 1.812 lỗi
  runtime hoặc nguyên nhân lag. Phần lớn là thứ tự khai báo/style/binding.
- Deep review: 13 cơ hội tối ưu đã truy vết, 1 điểm cần profiling thêm.
- Bộ kiểm thử hồi quy cho thay đổi giọng mặc định, OpenRouter, quyền riêng tư,
  resume, thay nguồn, batch và voice scope: 425 passed; thêm 4 kiểm thử an toàn
  cho script audit, tổng 429 passed. Không phải chạy toàn bộ test suite repo.
- Sau bản vá có 159 test Qt Quick (toàn thư mục tests/qml) đạt, 0 failure/error.
  XML: `build/qml-preview-perf-20261108.xml`. Các test mới kiểm tra delegate giữ
  identity, half-open intervals, snap ties, overlap/gap, PCM, preflight và loading.
- Bộ hồi quy gộp sau cùng: **647 passed** (87,6 giây), 1 cảnh báo deprecation
  QQmlPropertyMap trong test. XML: `build/performance-regressions-20261108.xml`.
  Lint Qt cho cả 225 tệp QML, Ruff F và compileall đạt. Đây không phải tuyên bố
  toàn bộ test suite repo đã hoàn tất: lượt gate toàn repo được dừng để xử lý
  các failure, sau đó chạy lại các nhóm liên quan trong bộ gộp trên.
- Đã sửa hồi quy identity của danh sách PCM do bước thêm index: danh sách track
  cũ vẫn giữ nguyên, lookup dùng cấu trúc riêng. Hai bài dừng/phát lại/đổi proxy
  bắt lỗi này và đã qua sau sửa; không đổi/nới các assertion đó.
- Các failure khác được đối chiếu: test cắt sai ranh giới Loader sau lazy-load;
  fixture CPU phải chọn backend CPU rõ ràng sau đổi mặc định VieNeu GPU; test
  forward hook đối chứng với phép cân âm đã có từ trước, không bỏ phép cân âm.
  Đồng bộ checksum pyproject trong manifest dependency sau khi xác minh 78 pin
  vẫn thỏa mãn; không đổi lock, phiên bản hay tải thư viện mới.
- Các loader/cache/cải tiến OCR có sẵn được giữ nguyên. Không build, push hoặc publish.

Báo cáo ban đầu gồm từng finding, vị trí, đường gọi, độ tin cậy, biện pháp và
toàn bộ lint nằm tại `build/performance-review-20261108.md` (artifact cục bộ).
Nên đo profiler trên project dài trước/sau từng bản vá, tách các thay đổi nhỏ
để dễ phát hiện hồi quy thay vì thay mọi đường xử lý cùng lúc.

## Bổ sung: mở lại dự án lỗi và tải danh sách ban đầu

- Manual inspector không phát lại lỗi được lưu chỉ vì workspace/delegate được
  tạo lại. Backend theo dõi lần chuyển sang failed và nhận diện lượt chạy lại,
  kể cả cùng thông báo lỗi; mỗi sự kiện mới chỉ được nhận một lần. Trạng thái
  lỗi và log vẫn được giữ. Dòng lỗi của tool được trả bất đồng bộ không được
  thay thế nội dung lỗi mới hơn trong metadata.
- Danh sách dùng chung một snapshot chỉ mục đã kiểm tra cho liệt kê video và
  tóm tắt dự án đăng, thay vì đọc lại toàn bộ chỉ mục cho từng thư mục. Registry
  các thư mục dự án không còn được ghi/fsync nếu nội dung không thay đổi.
- Bảo trì khởi động đợi danh sách đầu tiên được đưa lên UI (hoặc lỗi tải) rồi
  mới bắt đầu, tránh tranh ổ đĩa/khóa chỉ mục. Không thêm thời gian chờ cố định,
  không đọc dữ liệu nặng lại trên GUI, không dùng cache danh sách cũ giả trạng thái.
  Nhãn tải chỉ phản ánh lượt đọc nền đầu tiên, không phải bước xử lý video mới.
- Kiểm thử gộp liên quan: **234 passed**, 7 subtests passed; 5 cảnh báo deprecation
  QQmlPropertyMap trong test, không phải lỗi runtime. Artifact:
  `build/project-reopen-regressions-20261108.xml`. Toàn bộ 159 Qt Quick test đạt
  (`build/qml-project-reopen-20261108.xml`); 225 tệp qua native qmllint, Ruff F,
  compileall và diff whitespace đều đạt.
- Probe điều hướng dùng controller thật, dữ liệu thử riêng và không nạp AI.
  Đã cập nhật fixture theo async catalog và export summary, mô phỏng đúng signal
  document.changed; có test model/composition thật để kiểm tra chỉ refresh một lần.
  Chưa công bố thời gian khởi động trên toàn bộ dự án thật của user; không chạy
  inference/video, không sửa dữ liệu dự án, không build/push/publish.

Đã tiếp tục tối ưu phần chuẩn bị preview sau OCR/TTS, đo đối chứng file thật và
kiểm tra bit-identical. Xem `docs/preview-completion-optimization.md` để biết
phạm vi, kết quả, cơ chế hủy/cache và giới hạn phép đo.
