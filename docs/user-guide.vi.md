# Hướng dẫn sử dụng HaizFlow

[Tài liệu](README.vi.md) · [Repository](../README.vi.md) · [English](user-guide.md)

Tài liệu này trình bày ứng dụng theo thứ tự công việc. Người đọc không cần biết về model hoặc pipeline bên trong.

## 1. Chuẩn bị

HaizFlow là ứng dụng desktop cho Windows. Dự án được lưu cục bộ; các tác vụ nhận dạng, dịch, giọng local, âm thanh và video cốt lõi không cần API suy luận trả phí.

Bạn cần chuẩn bị:

- video nguồn đọc được và có track âm thanh;
- đủ dung lượng cho video nguồn, artifact, cache và video xuất;
- kết nối Internet khi tải model lần đầu hoặc dùng tính năng online;
- GPU NVIDIA nếu muốn tăng tốc model local lớn.

Xử lý local không có nghĩa mọi tính năng đều offline. Edge TTS, nhập URL, cài model và đăng mạng xã hội vẫn cần mạng.

## 2. Cài và mở HaizFlow

Với repository source:

```powershell
git clone https://github.com/MachHongHai/HaizFlow.git
cd HaizFlow
powershell -ExecutionPolicy Bypass -File .\scripts\install-desktop-env.ps1
.\.venv\Scripts\python.exe .\haizflow_desktop.py
```

Lần cài đầu có thể lâu vì Torch, Qt và thư viện media có dung lượng lớn. Không đóng PowerShell khi dependency đang được đồng bộ.

Khi một model được dùng lần đầu, trạng thái tải hoặc chuẩn bị xuất hiện ở thanh hoạt động phía dưới. HaizFlow chỉ kích hoạt model sau khi kích thước và SHA-256 khớp metadata đã khóa.

## 3. Thanh điều hướng

Thanh trên cùng giữ điều hướng, Dự án, Chỉnh sửa, Cài đặt và Trợ giúp. Back và Forward chỉ thay đổi lịch sử trang. Undo và Redo thuộc lịch sử chỉnh sửa, hoàn toàn độc lập với điều hướng.

Các khu vực chính:

- **Trang chủ:** dự án gần đây, thao tác chính, liên kết nhà phát triển và khung video hướng dẫn.
- **Dự án:** toàn bộ loại dự án trong grid có filter.
- **Tải xuống:** dự án tải video, kênh và âm thanh.
- **Đăng mạng xã hội:** dự án đăng bài và hàng đợi.
- **Cài đặt:** ngôn ngữ, thiết bị xử lý, runtime, thư mục model, quyền riêng tư và dọn cache Manual.

Khi mở project, sidebar được ẩn để dành chỗ cho preview và editor. Dùng nút Home hoặc Dự án trên thanh trên để rời workspace.

## 4. Chọn loại dự án

Chọn **Dự án mới**, sau đó chọn loại phù hợp.

### Tự động

Dùng khi muốn một cấu hình chạy trọn quy trình. Pipeline có thứ tự và hỗ trợ tạm dừng, tiếp tục, phục hồi từ checkpoint đã xác minh.

### Thủ công

Dùng khi cần kiểm soát độc lập. Nhận dạng và dịch, chỉnh phụ đề, xử lý hình ảnh, tạo giọng, phối âm và xuất là các công cụ riêng, không phải danh sách bước bắt buộc.

### Hàng loạt

Dùng cho nhiều video có cấu hình chung. Mỗi video vẫn có trạng thái và output riêng. Override của một video không âm thầm trở thành cấu hình mặc định cho video nhập sau.

### Tải xuống

Dùng để lưu video, kênh hoặc âm thanh công khai vào dự án. Nền tảng nguồn có thể thay đổi chính sách truy cập và có thể yêu cầu xác thực.

### Đăng mạng xã hội

Dùng để chuẩn bị caption và xếp hàng đăng video qua tài khoản Zernio do bạn cấu hình.

## 5. Nhập media

### Từ tệp

1. Chọn **Từ tệp**.
2. Chọn video được hỗ trợ.
3. Chờ kiểm tra toàn vẹn và tạo thumbnail.
4. Xác nhận preview và thời lượng đã xuất hiện trước khi xử lý.

Không xóa hoặc di chuyển thư mục dự án khi ứng dụng đang chạy.

### Từ liên kết công khai

1. Chọn **Từ liên kết**.
2. Dán URL video trực tiếp. Nội dung share có chứa một URL được hỗ trợ cũng có thể dùng.
3. Chọn **Kiểm tra**, sau đó xem tiêu đề, nền tảng, người đăng, thời lượng và thumbnail.
4. Chọn **Tải và nhập**.

HaizFlow tự retry có giới hạn khi gặp lỗi DNS, timeout, HTTP tạm thời hoặc manifest hết hạn. Video private, đã gỡ, khóa vùng hoặc yêu cầu đăng nhập được báo lỗi trực tiếp, không lặp vô hạn.

Nếu URL lỗi:

1. Mở URL trong trình duyệt và xác nhận video còn công khai.
2. Kiểm tra thiết lập xác thực của nền tảng nếu có.
3. Chờ một lúc nếu nền tảng đang giới hạn tần suất.
4. Cập nhật repository nếu trang nguồn đã đổi định dạng và yt-dlp có bản sửa.

## 6. Dự án Tự động

1. Thêm video nguồn.
2. Chọn model nhận dạng và ngôn ngữ đích.
3. Chọn OmniVoice để chạy local hoặc Edge TTS để dùng giọng online.
4. Chọn cách xử lý phụ đề gốc: giữ nguyên, làm mờ hoặc vá nền.
5. Chọn âm thanh gốc hoặc tách giọng.
6. Thêm nhạc nền và watermark nếu cần.
7. Chỉnh âm lượng video, giọng đọc và nhạc.
8. Bắt đầu xử lý.

Thanh lệnh hiển thị tác vụ thật đang chạy. Tạm dừng giữ lại checkpoint đã hoàn tất. Chạy lại có thể làm cũ artifact phía sau, vì vậy chỉ dùng khi cần một lượt sạch.

Sau khi dịch, mở trình sửa phụ đề để sửa text hoặc timing. Trình sửa không thêm/xóa câu. Sửa text làm cũ voice của câu đó; sửa timing chỉ đổi vị trí phát clip đã có.

## 7. Trình sửa Thủ công

Các công cụ độc lập và có thể dùng không theo thứ tự tuyến tính.

### Nguồn

- Đổi video nguồn từ tệp hoặc URL.
- Chọn **Giữ âm thanh gốc** để dùng track nguồn.
- Chọn **Tách giọng**, sau đó chạy Demucs để tạo vocals và âm nền.

Đổi chế độ âm thanh sẽ dùng cache tương ứng nếu tồn tại và không tự chạy nhận dạng.

### Nhận dạng & dịch

Chọn model nhận dạng và ngôn ngữ đích rồi chạy. Kết quả là tài liệu phụ đề có timing, chưa có giọng đọc.

Chạy lại sẽ thay tài liệu dịch cũ. Style/vị trí phụ đề, hình ảnh, watermark, nhạc và âm lượng vẫn được giữ. Voice cũ bị làm mất hiệu lực vì không còn khớp text.

### Phụ đề

- Bấm clip trên timeline hoặc bấm phụ đề trong preview kết quả.
- Sửa toàn bộ nội dung đoạn trong inspector.
- Kéo phụ đề trực tiếp trên video để đổi vị trí chung.
- Kéo tay nắm khung để đổi kích thước chữ chung.
- Kéo cạnh clip timeline để đổi thời gian.

Text tự lưu. Trạng thái đổi từ **Đang lưu** sang **Đã lưu**. Bấm vùng trống sẽ commit draft, bỏ focus nhập và ẩn khung chỉnh.

Undo/Redo áp dụng cho lịch sử chỉnh sửa, gồm text, timing, hình ảnh, âm thanh, giọng và setting dự án; chúng không phải Back/Forward.

### Hình ảnh

Chọn giữ hoặc che phụ đề gốc. Nếu chọn che, hãy chọn làm mờ hoặc vá nền trước khi xử lý. Vùng OCR là layer bên dưới phụ đề dịch.

Watermark nằm trong mục này. Nội dung, kích thước và timing phụ đề không nằm trong Hình ảnh.

### Giọng đọc

Bấm **Tạo giọng** để mở cửa sổ cấu hình. Chọn provider, giọng và phạm vi rồi xác nhận; đóng cửa sổ không thay đổi giọng hoặc cache hiện tại. Khi đã có giọng, **Đổi giọng** và **Tạo lại** mở cùng cửa sổ thay vì thay đổi project ngay lập tức.

Chọn **Toàn video** để dùng một giọng thống nhất, hoặc **Đoạn này** để chỉ tạo cho phụ đề đang chọn trên timeline. Thao tác theo đoạn giữ nguyên toàn bộ clip không bị ảnh hưởng. Chỉ câu thiếu cache hoặc đã thay đổi được tổng hợp.

- OmniVoice chạy local sau khi cài asset.
- Edge TTS gửi text phụ đề đến dịch vụ online đã chọn.
- Nhận diện nhiều người nói chỉ hiển thị khi provider hỗ trợ luồng này.

Nếu tài liệu đã có voice, sửa một câu chỉ làm mới câu đó; câu không đổi giữ clip hợp lệ. Đổi timing không gọi TTS.

### Âm thanh

Âm lượng nguồn/âm nền, giọng đọc và nhạc được áp dụng trực tiếp lên preview. Nhạc nền có thể lấy từ tệp hoặc URL. Chỉnh âm thanh không chạy nhận dạng, dịch, Demucs hoặc TTS.

Nếu thiếu voice clip bắt buộc, giao diện báo phần thiếu thay vì tự chạy model.

### Xuất

Xuất dùng trạng thái hiện tại. OCR, giọng tổng hợp, nhạc, watermark hoặc phụ đề dịch đều có thể không tồn tại nếu người dùng không bật/tạo chúng. Lệnh xuất không tự chạy các công cụ AI còn thiếu.

Khi hoàn tất, dùng nút output hiển thị trực tiếp để phát video hoặc mở thư mục chứa.

## 8. Preview và timeline

- Video nguồn và kết quả có play, pause, stop, mute và fullscreen riêng.
- **Phát cả hai** dùng để so sánh đồng bộ.
- Kéo slider hoặc playhead để tua. UI đi theo chuột ngay và gộp request seek gửi xuống player.
- Khi chuẩn bị preview mới, frame hợp lệ gần nhất vẫn được giữ.
- Progress mảnh chỉ xuất hiện khi công cụ đang tạo artifact thay thế.

Preview dùng proxy nhẹ và layer cache để phản hồi nhanh. Video xuất cuối vẫn dùng đường render output đã cấu hình.

## 9. Hàng loạt

1. Tạo dự án Hàng loạt.
2. Thêm tệp hoặc nhập URL.
3. Đặt cấu hình dùng chung.
4. Kiểm tra override riêng nếu có.
5. Chạy hàng đợi.

Mỗi dòng có trạng thái và progress riêng. Có thể retry video lỗi mà không xóa kết quả video thành công.

## 10. Tải xuống

Workspace có ba tab:

- **Video:** kiểm tra một URL, xem metadata rồi tải.
- **Kênh:** kiểm tra kênh/profile công khai, chọn video rồi đưa vào queue.
- **Âm thanh:** tải audio từ URL hoặc tách audio từ media local.

Download chạy qua queue của dự án. Tệp tạm nằm trong staging thuộc dự án và chỉ được đưa vào kết quả sau validation.

## 11. Đăng mạng xã hội

1. Tạo hoặc mở dự án Đăng mạng xã hội.
2. Kết nối Zernio và lưu API key qua ứng dụng.
3. Đặt caption và tùy chọn mặc định.
4. Thêm video từ tệp, thư mục hoặc dự án HaizFlow.
5. Kiểm tra nền tảng, nội dung và queue.
6. Xác nhận đăng.

Đăng bài sẽ upload media sang dịch vụ bên thứ ba, không phải xử lý local. Hãy đọc điều khoản, quota, quyền riêng tư và giá của Zernio/nền tảng đích. Video đã đăng chỉ giữ hành động **Mở bài đăng**.

## 12. Lưu trữ và cache

Dự án chứa input, metadata, log, preview, cache và output. Cache Manual theo nội dung giúp quay lại voice, OCR, hình ảnh hoặc bản phối cũ còn hợp lệ.

Dùng **Cài đặt → Dọn dữ liệu tạm** khi cần giải phóng cache Manual. Input và output của người dùng không phải cache và không được xóa bởi thao tác này. Nên đóng tác vụ đang chạy trước khi tự di chuyển thư mục dự án.

Người chạy source có thể đặt `HAIZFLOW_HOME` trong `.env` để gom model, cache, data và temp dưới một thư mục local đã chọn.

## 13. Xử lý lỗi thường gặp

### Ứng dụng đang chuẩn bị model

Chờ thanh hoạt động phía dưới hoàn tất. Chuẩn bị model và tiến trình tác vụ là hai trạng thái khác nhau. Nếu lỗi, mở log kỹ thuật rồi kiểm tra dung lượng, mạng, checksum và bộ nhớ GPU.

### URL lỗi ở lần đầu

Build hiện tại tự retry lỗi tạm thời bằng session yt-dlp mới. Nếu lỗi cuối nói private, unavailable, unauthorized hoặc login required, bấm lại khi chưa đổi điều kiện truy cập sẽ không giải quyết được.

### Preview không có âm thanh

Kiểm tra track nguồn/voice/nhạc đã tồn tại, không bị mute và volume lớn hơn 0. Trong Manual, tạo voice và chọn/phối âm là thao tác độc lập.

### Preview khác trong vài giây đầu khi mở project

Chờ cache active tải xong. Preview chỉ nên swap sang artifact hoàn chỉnh. Nếu tiếp tục sai, mở log kỹ thuật và báo trạng thái dự án mà không cần gửi media riêng tư.

### Nhập tiếng Việt mất từ cuối

Build hiện tại commit composition của Windows IME trước khi đổi focus hoặc lưu. Nếu vẫn gặp lỗi, hãy ghi rõ bản Windows, bộ gõ, ô nhập bị lỗi và câu tái hiện chính xác.

### Ứng dụng chậm

- Dừng tác vụ nền không cần thiết.
- Kiểm tra thiết bị xử lý còn đủ RAM/VRAM.
- Dọn variant cache Manual không active nếu ổ gần đầy.
- Không đặt dự án đang chạy trên filesystem mạng chậm.

## 14. Báo lỗi

Mở [GitHub Issues](https://github.com/MachHongHai/HaizFlow/issues) và cung cấp:

- thao tác đã thực hiện;
- kết quả mong muốn và thực tế;
- input tối giản nếu bạn có quyền chia sẻ;
- lỗi hiển thị và đoạn log kỹ thuật liên quan;
- phiên bản Windows, GPU và ứng dụng.

Không đăng credential, link private, metadata dự án đầy đủ hoặc media có bản quyền khi chưa được phép.
