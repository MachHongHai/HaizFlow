# Trạng thái kỹ thuật Manual editor

[Tài liệu](README.vi.md) · [Kiến trúc](architecture.vi.md#7-manual-editor-và-artifact-graph) · [English](manual-editor-stabilization.md)

Tài liệu tách hành vi đã triển khai khỏi phần nghiệm thu còn lại. Đây là ghi chú bảo trì, không phải hướng dẫn sử dụng hoặc tuyên bố mọi tổ hợp media/thiết bị đã được chứng nhận.

## Đã triển khai

- `ManualSubtitleModel` có segment ID ổn định, save theo revision, giữ session draft, working document atomic và publish immutable tuần tự.
- `SubtitleTextEditor` có vùng nhập wrap toàn chiều cao, autosave 500 ms, commit khi mất focus, trạng thái save/retry và commit Windows IME trước action đổi focus.
- `SubtitleOverlayRenderer` dùng ASS writer/font của export để tạo sprite normal/karaoke; bounds lấy từ alpha render thật, không từ QML text metric.
- Base proxy Manual không chủ đích burn translated caption; subtitle overlay là layer riêng.
- Transport, fullscreen và timeline dùng chung scrub state, seek được gộp và callback source generation cũ bị bỏ.
- Một preview audio controller/output sở hữu âm kết quả. Source, no-vocals, TTS và music chạy theo cùng clock; đổi level không render lại video.
- Sửa text chỉ invalid voice của segment đó; sửa timing chỉ đổi vị trí clip cache.
- OmniVoice giữ warm worker trong idle timeout hữu hạn. Edge TTS đi qua luồng tuần tự theo video và clip cache theo nội dung.
- Edit history tách khỏi navigation và ghi text, timing, media, voice, audio, visual, project, publishing, application setting theo context sở hữu.
- Voice manifest chỉ activate khi subtitle document signature vẫn current lúc generation hoàn tất.
- Preview artifact publish atomic; callback stale bị chặn bằng generation/revision.

## Đã có test tự động

- Draft tiếng Việt/Unicode dài sống qua save, reload và stale callback mà không bị trim.
- Đóng text editor commit đủ nội dung đúng một lần.
- Alpha bounds lấy từ renderer và cache miss không hiển thị phrase trước.
- Seek lặp tái sử dụng và giải phóng một audio output trong test abstraction.
- Inspector Manual khởi tạo với controller thật trong Qt runtime cô lập.
- Test voice cache phân biệt invalidation do text với timing/style.
- `scripts/test.ps1` chạy compile, correctness lint, unit/integration và QML lint.

Không ghi số test cố định; output gate của commit được review là nguồn có thẩm quyền.

## Nghiệm thu còn lại

- So sánh karaoke theo pixel giữa idle preview, selected preview và frame video xuất trên media đại diện.
- Stress audio thật trên Windows với source swap, hơn 100 seek, đổi device, suspend/resume và đóng workspace.
- Đo decode/memory cho video dài; PCM cache có giới hạn nhưng một track cực dài vẫn cần chiến lược window/memmap được kiểm chứng.
- Test crash ở mọi atomic boundary của subtitle publication và voice refresh.
- Kiểm Edge TTS thật khi outage/rate-limit và retry UI với nhiều locale voice.
- Chứng minh mọi worker/media connection Manual được giải phóng khi đổi project nhanh.
- Nghiệm thu quota cache dưới low-disk và bảo vệ artifact active/pinned.

## Invariant hồi quy

1. Seek không chạy OCR, dịch, TTS, tách giọng hoặc final render.
2. Đổi option giọng chỉ đổi requested state; không thay active preview audio trước khi user tạo hoặc activate artifact hoàn chỉnh khớp.
3. Callback voice/subtitle/preview/media cũ không được activate trên revision mới.
4. Size/vị trí phụ đề không đổi text, timing hoặc TTS identity.
5. Timing không gọi TTS.
6. Image mode không gọi nhận dạng/dịch.
7. Audio level không gọi model hoặc dựng lại visual proxy.
8. Export dùng optional layer hợp lệ hiện tại và không tự chạy tool thiếu.
9. Rời workspace dừng đúng một audio owner và release player connection mà không ảnh hưởng worker project khác.

Thay đổi vi phạm invariant cần quyết định kiến trúc và acceptance criteria mới, không được vá cục bộ trong UI.
