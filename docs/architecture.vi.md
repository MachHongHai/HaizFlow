# Kiến trúc HaizFlow

[Tài liệu](README.vi.md) · [Repository](../README.vi.md) · [English](architecture.md)

Tài liệu này mô tả ranh giới hệ thống, hướng dependency, persistence, artifact graph và execution model của ứng dụng desktop. Đối tượng đọc là contributor cần thay đổi HaizFlow mà không ghép UI với chi tiết xử lý media.

## 1. Ranh giới hệ thống

HaizFlow là ứng dụng Windows desktop. Main process chạy giao diện PySide6/Qt Quick và điều phối dữ liệu dự án local, model worker cùng FFmpeg process. Không có HaizFlow web backend, browser client hoặc hosted project database.

```text
QML desktop UI
  -> HaizFlowController facade
  -> desktop controller chuyên trách
  -> service hoặc pipeline operation
  -> artifact thuộc dự án local
  -> preview hoặc FFmpeg output cuối
```

Mạng chỉ xuất hiện trong tính năng cụ thể: tải model đã verify, nhập media công khai, Edge TTS khi được chọn và đăng bài qua Zernio do user cấu hình. OmniVoice, Whisper/WhisperX, HY-MT2, Demucs và FFmpeg chạy local sau khi asset hợp lệ đã có.

## 2. Nguyên tắc kiến trúc

- **Local ownership:** input, artifact, setting và output thuộc thư mục dự án.
- **UI boundary hẹp:** QML đọc observable state và gọi slot; không chạy inference, FFmpeg hoặc mutation filesystem.
- **Side effect tường minh:** một command chạy đúng operation được đặt tên.
- **Content-addressed reuse:** kết quả nặng được định danh bởi input/config, không bởi màn hình đang mở.
- **Atomic publication:** output chỉ visible sau validation và promote atomic từ staging.
- **Backward-readable data:** schema mới có default/migration; schema tương lai không biết bị từ chối.
- **Bounded concurrency:** worker model/media bị giới hạn để bảo vệ playback, GPU memory và tính nhất quán dự án.

## 3. Phân lớp và hướng dependency

```text
src/haizflow/
  core/          runtime path, hardware policy, diagnostics, shared event
  desktop/       Qt bootstrap, QML facade, controller, model, presenter
    qml/         page, workspace, dialog, shared control
    assets/      branding và voice sample
    translations/ Qt translation catalog
  pipeline/      transcription, speech, audio và render transform
  schemas/       persisted/cross-layer contract
  services/      project, storage, download, queue, cache, integration
  utils/         helper media/process không trạng thái
  vendor/        mã tương thích có license upstream
tests/           unit, integration, QML creation và regression
scripts/         setup, verification và release tooling
installer/       Inno Setup
licenses/        third-party notice và license
```

Dependency đi từ presentation vào application services: QML → facade/controller → service/pipeline → schema/core. Service, pipeline, schema và core không import QML.

| Layer | Sở hữu | Không sở hữu |
| --- | --- | --- |
| QML | layout, direct manipulation, focus, presentation state | inference, filesystem mutation, subprocess |
| QML facade | property/signal/slot ổn định và wiring | thuật toán dài |
| Desktop controller | lifecycle/cancel của một workflow | codec và schema definition |
| Service | use case, persistence, queue, cache manifest | visual state |
| Pipeline | transform với input/output tường minh | navigation/project selection |
| Schema | contract đã validate | I/O orchestration |

## 4. Desktop composition

`haizflow_desktop.py` cấu hình runtime boundary, chuyển vào `.venv` nếu có rồi mới import Qt. Nó không import framework suy luận hoặc khởi động engine. `Main.qml` là shell sống lâu, sở hữu route history, top bar, dialog toàn cục và activity strip. `RouteHost.qml` thay page mà không dựng lại shell.

`HaizFlowController` là singleton facade cho QML. Các controller chuyên trách sở hữu catalog/project, command, import, processing lifecycle, preview video, preview audio, download, publishing, setting, gói tài nguyên, kiểm tra cập nhật, smart warm-up và diagnostics. Danh sách lớn được expose bằng `QAbstractListModel`.

`AppUpdateController` gọi GitHub Releases công khai trên worker thread và chỉ chuyển kết quả đã phân tích về Qt thread. Controller chỉ chấp nhận trang phát hành thuộc repository chính thức cố định rồi so sánh version stable. Ứng dụng mở trang đó khi có bản mới; nó không tự tải hoặc chạy bộ cài.

Activity ngắn nằm ở status strip; raw log chỉ mở khi cần chẩn đoán. Dialog dành cho quyết định hoặc lỗi cần hành động.

## 5. Dữ liệu dự án

`project_store` sở hữu index và `.haizflow-project.json`; `video_store` sở hữu `video.json`, log, media path và checkpoint. ID là immutable identifier; folder name dễ đọc chỉ là nhãn.

Ghi metadata dùng interprocess lock, file tạm, `fsync` và atomic replace. Bản hợp lệ trước được giữ làm backup; input hỏng được quarantine trước phục hồi.

```text
<project-name>--<short-id>/
  .haizflow-project.json
  exports/
  videos/
    <source-name>--<short-id>/
      video.json
      logs.txt
      input/
      temp/
        editor-preview/
        cache/manual/
```

Project Download dùng `downloads/video`, `downloads/channel`, `downloads/audio`. Project Publishing dùng `publishing/media`, thumbnail và queue file atomic. Delete phải resolve registered root; không suy ra target từ display name.

## 6. Automatic và Batch

Automatic/Batch dùng pipeline có thứ tự:

```text
input đã quản lý
  -> âm nguồn hoặc Demucs
  -> Whisper/WhisperX recognition và timing
  -> HY-MT2 translation
  -> subtitle document và ASS
  -> OmniVoice hoặc Edge TTS clip
  -> audio mix theo timestamp
  -> FFmpeg render/mux
```

Checkpoint signature được suy ra từ input và setting liên quan. Resume chỉ nhận checkpoint còn khớp và đủ output không rỗng. Batch thêm ownership của queue và per-video override, không có thuật toán media riêng.

## 7. Manual editor và artifact graph

Manual là phi tuyến. Source, Recognition & Translation, Subtitles, Image, Voice, Audio và Export là tool độc lập.

- Recognition & Translation tạo subtitle document, không tạo voice.
- Image cleanup tái dùng OCR region khi chuyển giữ nguyên/blur/patch.
- Voice chỉ tổng hợp clip thiếu hoặc đã invalid.
- Audio dùng track hiện có, không gọi model.
- Export encode trạng thái hiện tại; layer tùy chọn có thể vắng.

```text
video -> source audio -> optional separation
selected audio -> recognition -> translation -> subtitle document
subtitle document + voice config -> TTS clips
video -> OCR region -> optional blur/patch
video + visual config + subtitle + watermark -> visual proxy
source/no-vocals + TTS + music + levels -> audio mix
current visual + current audio -> export
```

Sửa text chỉ invalid voice clip của câu đó và descendant. Sửa timing sắp lại clip cache mà không gọi TTS. Đổi nhạc/volume chỉ invalid mix. Chọn lại source mode, voice hoặc cleanup mode cũ sẽ activate cache variant phù hợp. Chọn giọng trong Manual là một transaction: trạng thái trong dialog chỉ là draft và chỉ khi xác nhận mới cập nhật manifest được yêu cầu. Override theo từng đoạn tham gia vào signature của từng clip; preview vẫn dùng manifest hoàn chỉnh gần nhất cho tới khi bản thay thế được publish.

### Artifact store

`services/manual_artifacts.py` lưu artifact immutable dưới `temp/cache/manual`. Manifest ghi kind, signature, status, inputs, config fingerprint, outputs, timestamp, size và error.

Producer ghi staging, validate output, tạo complete marker rồi rename atomic. Lookup từ chối partial, thiếu, rỗng hoặc signature sai. Artifact active/runtime đang dùng được pin; variant inactive bị dọn theo LRU và quota.

## 8. Preview và direct manipulation

Seek chỉ thay media position/subtitle clock, không invalid visual cache. Visual config và audio mix có signature riêng. TTS/source/music được mix từ file cache đã validate.

Preview hoàn chỉnh được publish atomic; player swap source nhưng giữ position và playback intent. Subtitle transform dựa trên output dimension, layout rectangle, font, phrase partition và karaoke clock do renderer cung cấp. Khi render matching sẵn sàng, proxy trở thành authoritative.

Khi đổi source, result pane giữ frame hợp lệ gần nhất. Worker/player cũ bị release khi rời workspace để tránh audio lặp và callback stale.

## 9. Model và process isolation

Core không import Torch, ONNX Runtime, WhisperX, Transformers, Demucs hoặc llama.cpp. Suy luận chạy trong engine CPU, CUDA 12.8 hoặc vision được freeze, version và cài riêng. HY-MT2/OmniVoice dùng server JSON-lines persistent bên trong engine đã chọn; recognition, OCR và Demucs reuse đúng process đã được warm. FFmpeg vẫn là external process do Core quản lý, có cancel và timeout.

Trình quản lý gói tài nguyên là đường production để cài engine và model tùy chọn. Mỗi gói khai báo phiên bản giao thức, URL bất biến, kích thước chính xác và SHA-256. Download hỗ trợ tiếp tục; engine phải vượt smoke test cô lập trước khi được kích hoạt nguyên tử và vẫn giữ một bản rollback. Loader nhận local path tường minh, không fallback sang download mạng chưa khóa.

`SmartWarmupController` chỉ chạy sau khi cửa sổ Core đã phản hồi. Controller dự đoán capability kế tiếp từ project và công cụ đang chọn, chỉ warm gói đã cài trong worker nền và luôn nhường tác vụ người dùng. Trạng thái warm tách khỏi tiến trình video: model sẵn sàng giúp giảm độ trễ inference đầu nhưng không bao giờ làm thanh tác vụ báo hoàn tất. Khi thiếu bộ nhớ, tài nguyên dự đoán được giải phóng trước tác vụ đang chạy.

Hardware policy chọn CUDA precision, memory profile, warm-up, batch size và CPU thread. FFmpeg hardware encode được probe riêng; thất bại có thể fallback `libx264`.

## 10. Ranh giới mạng và quyền riêng tư

Mạng chỉ dùng cho:

- tải gói tài nguyên đã được người dùng xác nhận và kiểm checksum;
- URL/channel inspection và download;
- Edge TTS khi user chọn;
- Zernio authentication, upload và publishing.

Credential nằm trong Windows Credential Manager. Import URL validate host và staging. Social upload cần xác nhận. Diagnostic bundle được giới hạn/redact và không chứa media hoặc metadata dự án.

## 11. Quan sát và lỗi

`logs.txt` theo video là log xử lý có thẩm quyền. Pipeline event cập nhật persisted progress và activity presentation. Raw technical log không chiếm workspace mặc định.

Lỗi phải giữ tool thất bại, retry point an toàn và recovery action, đồng thời không xóa artifact đã validate. App log xoay vòng và bắt lỗi Python/thread/Qt.

## 12. Runtime và packaging

Python 3.13 x64 là runtime source/build. `pyproject.toml` khai báo direct dependency; `requirements-lock-py313-win64.txt` là lock Core chỉ dùng PyPI và có hash. Engine CPU, CUDA, vision có lock hash và manifest review riêng; `uv.lock` phục vụ phát triển, không phải release artifact.

PyInstaller dùng `onedir` cho Core; engine AI, model và dữ liệu mutable không nằm trong installer. Resource Manager tạo resource root local sau khi cài:

```text
runtime/
  engines/
  models/
  packages/
  cache/
  data/
  tmp/
```

Source mode có thể dùng `HAIZFLOW_HOME` để tạo cùng containment boundary.

Inventory lúc khởi động chỉ kiểm tra sự tồn tại và kích thước dự kiến; UI thread không hash checkpoint nhiều GiB.
SHA-256 đầy đủ chạy khi cài, sửa chữa hoặc ngay trước lần load model cần tin cậy đầu tiên. Việc dọn thư mục cũ sau
khi chuyển ổ tài nguyên cũng chạy trong maintenance worker sau frame đầu tiên.

## 13. Checklist thay đổi

| Thay đổi | Nơi sở hữu | Việc bắt buộc |
| --- | --- | --- |
| QML component/screen | `desktop/qml` | focus, accessibility, translation, creation test, không chứa media logic |
| Controller command | desktop controller | facade API hẹp, cancel/state test |
| Pipeline transform | `pipeline` | input/output, progress, signature, cancel |
| Persisted field | schema/store migration | default, validation, old-data test |
| Manual artifact | artifact service/tool runner | signature, publication, dependency, eviction test |
| External provider | `services` | trust boundary, credential, retry/cancel, notice |

Chạy `scripts/test.ps1` trước khi merge. Thay đổi packaging/model integrity còn phải qua [release readiness](release-readiness.vi.md).
