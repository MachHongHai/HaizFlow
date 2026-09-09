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
test/            unit, integration, QML creation và regression
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

`haizflow_desktop.py` cấu hình runtime boundary trước khi import Qt/Torch và chuyển vào `.venv` nếu có. `Main.qml` là shell sống lâu, sở hữu route history, top bar, dialog toàn cục và activity strip. `RouteHost.qml` thay page mà không dựng lại shell.

`HaizFlowController` là singleton facade cho QML. Các controller chuyên trách sở hữu catalog/project, command, import, processing lifecycle, preview video, preview audio, download, publishing, setting, model bootstrap và diagnostics. Danh sách lớn được expose bằng `QAbstractListModel`.

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

HY-MT2 dùng JSON-lines worker persistent. GPU dùng Transformers/safetensors đã verify; CPU dùng GGUF qua `llama-cpp-python`. OmniVoice chạy trong worker dependency-isolated. Demucs dùng checkpoint pin checksum. FFmpeg là external process có cancel và timeout.

Model bootstrap là đường duy nhất cài payload production. Repository, revision, filename, size và SHA-256 được khóa. Loader nhận local path tường minh và không fallback sang network download không pin.

Hardware policy chọn CUDA precision, memory profile, warm-up, batch size và CPU thread. FFmpeg hardware encode được probe riêng; thất bại có thể fallback `libx264`.

## 10. Ranh giới mạng và quyền riêng tư

Mạng chỉ dùng cho:

- verified model download lần đầu;
- URL/channel inspection và download;
- Edge TTS khi user chọn;
- Zernio authentication, upload và publishing.

Credential nằm trong Windows Credential Manager. Import URL validate host và staging. Social upload cần xác nhận. Diagnostic bundle được giới hạn/redact và không chứa media hoặc metadata dự án.

## 11. Quan sát và lỗi

`logs.txt` theo video là log xử lý có thẩm quyền. Pipeline event cập nhật persisted progress và activity presentation. Raw technical log không chiếm workspace mặc định.

Lỗi phải giữ tool thất bại, retry point an toàn và recovery action, đồng thời không xóa artifact đã validate. App log xoay vòng và bắt lỗi Python/thread/Qt.

## 12. Runtime và packaging

Python 3.13 x64 là runtime source/build. `pyproject.toml` khai báo direct dependency; `requirements-lock-py313-win64.txt` khóa transitive set có hash; `uv.lock` phục vụ resolution tái lập.

PyInstaller dùng `onedir`; model không nằm trong installer. Thư mục cài đặt sở hữu runtime mutable:

```text
runtime/
  models/
  cache/
  data/
  tmp/
```

Source mode có thể dùng `HAIZFLOW_HOME` để tạo cùng containment boundary.

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
