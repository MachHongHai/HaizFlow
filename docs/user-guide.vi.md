# Hướng dẫn sử dụng HaizFlow

[Tài liệu](README.vi.md) · [Trang chính](../README.vi.md) · [English](user-guide.md)

Tài liệu này hướng dẫn cài đặt, tạo dự án, chỉnh video và xử lý các lỗi thường gặp. Người dùng không cần biết model hay định dạng tệp bên trong ứng dụng.

## 1. Trước khi cài đặt

HaizFlow hỗ trợ Windows 10 phiên bản 1809 trở lên và Windows 11 trên máy x64. RAM tối thiểu chính thức là 16 GiB. GPU NVIDIA không bắt buộc; GPU tương thích giúp model chạy nhanh hơn nhưng không cần thiết để mở và dùng ứng dụng Core.

Hãy tính chỗ trống cho bốn phần riêng:

1. ứng dụng Core;
2. bộ xử lý và model được chọn trong Gói tài nguyên;
3. video nguồn và video xuất;
4. dữ liệu tạm của trình sửa.

Setup hiển thị dung lượng đo từ đúng bản đang cài. Gói Core vừa được kiểm tra có dung lượng 477 MiB và Setup khuyến nghị chừa 4 GiB. Gói tài nguyên tùy chọn cùng dữ liệu dự án được đo riêng, không nằm trong con số của Core.

HaizFlow có thể nhận dạng, dịch, tạo giọng cục bộ, tách âm và OCR trên máy sau khi cài đủ gói. Edge TTS, nhập liên kết công khai, tải gói tài nguyên và đăng mạng xã hội cần Internet.

## 2. Cài và mở ứng dụng

Với bản phát hành, hãy chạy Setup và dùng vị trí Windows đề xuất nếu không có lý do chọn ổ cục bộ khác. Không đặt bộ xử lý hoặc model trên ổ mạng.

Để chạy từ mã nguồn:

```powershell
git clone https://github.com/MachHongHai/HaizFlow.git
cd HaizFlow
powershell -ExecutionPolicy Bypass -File .\scripts\install-desktop-env.ps1
.\.venv\Scripts\python.exe .\haizflow_desktop.py
```

Trang chủ mở mà không phải chờ model AI. Nếu bật **Giữ model sẵn sàng**, HaizFlow chuẩn bị model đã cài bằng một tiến trình riêng sau khi giao diện phản hồi ổn định. Việc chuẩn bị này không tự xử lý video.

## 3. Cài gói tài nguyên

Mở **Cài đặt → Gói tài nguyên**. Các gói được chia thành Bộ xử lý, Nhận dạng, Dịch, Giọng đọc và Hình ảnh.

Mỗi dòng cho biết dung lượng tải, dung lượng đã cài, phiên bản, vị trí và trạng thái. Trước khi cài, HaizFlow còn tính chỗ giải nén, bản cũ giữ lại để khôi phục và 2 GiB trống dự phòng.

- **Cài đặt** tải và kiểm tra gói.
- **Tạm dừng** và **Tiếp tục** điều khiển lượt tải mà không xóa phần hợp lệ đã nhận.
- **Sửa chữa** kiểm tra rồi thay tệp hỏng.
- **Gỡ bỏ** xóa gói không được tác vụ nền sử dụng.
- **Chuyển vị trí lưu** sao chép toàn bộ tài nguyên sang ổ cục bộ khác, kiểm tra bản sao rồi mới xóa dữ liệu cũ.

HaizFlow không tự tải gói còn thiếu. Khi một công cụ cần tài nguyên, thông báo sẽ ghi rõ tên gói và mở đúng khu vực trong Cài đặt. Sau khi cài xong, quay lại dự án và chủ động chạy lệnh.

## 4. Điều hướng

Thanh trên gồm Trang chủ, Quay lại, Tiến tới, Dự án, Chỉnh sửa, Cài đặt và Trợ giúp.

- **Quay lại** và **Tiến tới** dùng cho lịch sử trang.
- **Hoàn tác** và **Làm lại** trong Chỉnh sửa dùng cho các thay đổi được hỗ trợ; chúng không chuyển trang.
- **Trợ giúp** mở cửa sổ Giới thiệu và các liên kết hỗ trợ.

Thanh bên xuất hiện ở Trang chủ, Dự án, Tải xuống và Đăng mạng xã hội. Khi mở dự án, thanh này được ẩn để nhường chỗ cho video và timeline. Dùng Trang chủ hoặc Dự án trên thanh trên để rời dự án.

## 5. Tạo dự án

Chọn **Dự án mới**, sau đó chọn loại phù hợp:

- **Tự động:** một video, một bộ thiết lập và chuỗi xử lý có thứ tự; có thể tạm dừng, tiếp tục và khôi phục từ kết quả hợp lệ.
- **Thủ công:** các công cụ độc lập cho nguồn, dịch, phụ đề, hình ảnh, giọng đọc, âm thanh và xuất.
- **Hàng loạt:** nhiều video dùng chung thiết lập cơ sở nhưng mỗi video có tiến trình và kết quả riêng.
- **Tải xuống:** lấy video, kênh hoặc âm thanh từ nguồn công khai được hỗ trợ.
- **Đăng mạng xã hội:** chuẩn bị và gửi video qua tài khoản Zernio của người dùng.

Trang chủ liệt kê các dự án gần đây. Trang Dự án hiển thị toàn bộ dự án bằng lưới thẻ có tìm kiếm và bộ lọc.

## 6. Nhập video

### Từ tệp

1. Chọn **Từ tệp**.
2. Chọn video được hỗ trợ.
3. Chờ thumbnail và thời lượng xuất hiện.
4. Kiểm tra video phát được trước khi chạy tác vụ dài.

Không đổi tên, di chuyển hoặc xóa tệp bên trong thư mục dự án đang mở.

### Từ liên kết công khai

1. Chọn **Từ liên kết**.
2. Dán URL video công khai. Đoạn văn chứa một URL được hỗ trợ cũng có thể dùng.
3. Chọn **Kiểm tra**.
4. Xem lại tiêu đề, nền tảng, người đăng, thời lượng và thumbnail.
5. Chọn **Tải và nhập**.

HaizFlow thử lại các lỗi DNS, timeout, HTTP và địa chỉ media hết hạn bằng một phiên yt-dlp mới. Ứng dụng không lặp vô hạn với video riêng tư, đã xóa, giới hạn khu vực hoặc cần đăng nhập.

Nếu không kiểm tra được URL, hãy mở nó trong trình duyệt. Xác nhận nội dung vẫn công khai, cập nhật thông tin đăng nhập của nền tảng nếu cần và chờ một lúc trước khi thử lại khi dịch vụ đang giới hạn truy cập.

## 7. Dự án Tự động

1. Thêm video nguồn.
2. Chọn ngôn ngữ nguồn, ngôn ngữ đích và model nhận dạng.
3. Chọn OmniVoice để tạo giọng trên máy hoặc Edge TTS để dùng giọng trực tuyến.
4. Chọn giữ nguyên, làm mờ hoặc vá vùng phụ đề gốc.
5. Giữ âm thanh nguồn hoặc tách lời nói khỏi âm nền.
6. Thêm nhạc hoặc watermark nếu cần.
7. Chỉnh mức âm nguồn, giọng đọc và nhạc.
8. Bắt đầu xử lý.

Thanh lệnh phân biệt rõ việc chuẩn bị model và xử lý video. Model sẵn sàng không làm thanh tiến trình tác vụ chạy đầy. Khi tạm dừng, kết quả đã hoàn tất được giữ lại; chạy lại một công đoạn sẽ chủ động làm cũ những kết quả phụ thuộc vào nó.

## 8. Trình sửa Thủ công

Các công cụ Thủ công không phải các bước đánh số. Có thể chọn bất kỳ công cụ nào đã có đủ dữ liệu đầu vào.

### Nguồn

Thay video bằng tệp hoặc liên kết. **Giữ âm thanh gốc** dùng track nguồn. **Tách giọng** chạy Demucs và lưu cả phần lời lẫn âm nền. Chuyển giữa các lựa chọn sẽ dùng kết quả hợp lệ đã lưu và không tự nhận dạng lại.

### Nhận dạng và dịch

Chọn ngôn ngữ cùng model nhận dạng rồi chạy **Nhận dạng và dịch**. Kết quả là phụ đề có thời gian, chưa có giọng đọc.

Chạy lại lệnh sẽ thay nội dung phụ đề sau khi người dùng xác nhận. Kiểu chữ, vị trí, cách che phụ đề gốc, watermark, nhạc và âm lượng vẫn được giữ. Giọng đọc cũ được đánh dấu không còn khớp với nội dung mới.

### Phụ đề

Chọn một clip trên timeline hoặc bấm vào phụ đề trong video kết quả. Trình sửa sẽ mở toàn bộ nội dung của đoạn đó.

- Nhập chữ như bình thường; phần chữ tiếng Việt đang được bộ gõ ghép dấu sẽ được chốt trước khi lưu hoặc chuyển sang ô khác.
- Bản nháp tự lưu sau 500 ms không nhập và lưu ngay khi bấm sang nơi khác.
- Trạng thái **Đang lưu**, **Đã lưu** hoặc nút thử lại phản ánh đúng kết quả ghi tệp.
- Kéo phụ đề trên video để đổi vị trí chung của phụ đề.
- Kéo tay nắm của khung để đổi cỡ chữ chung.
- Kéo cạnh clip trên timeline để đổi thời điểm bắt đầu hoặc kết thúc.

Bấm vào vùng trống của video sẽ lưu bản nháp, bỏ chọn ô nhập và ẩn khung căn chỉnh. Đổi nội dung chỉ làm cũ giọng của đúng đoạn đó. Đổi thời gian hoặc kiểu chữ không tạo lại giọng.

Hoàn tác và Làm lại áp dụng cho những thay đổi được hỗ trợ về nội dung, thời gian, hình ảnh, giọng đọc, âm thanh và thiết lập dự án. Chúng tách biệt với Quay lại và Tiến tới.

### Hình ảnh

Chọn **Giữ nguyên** để không thay hình nguồn hoặc chọn **Che**, rồi chọn **Làm mờ** hay **Vá nền**. Việc phân tích chỉ bắt đầu sau khi đã chọn cách che. Vùng che luôn nằm dưới lớp phụ đề dịch.

Watermark cũng được chỉnh tại đây. Nội dung và cỡ phụ đề được chỉnh trực tiếp từ phụ đề hoặc mục Phụ đề, không nằm trong Hình ảnh.

### Giọng đọc

Khi video chưa có giọng, chọn **Tạo giọng**. Sau khi đã có giọng, dùng **Đổi giọng** hoặc **Tạo lại**. Các nút này mở hộp thoại; thay đổi trong hộp thoại chưa tác động video cho tới khi bấm xác nhận.

Chọn **Đoạn này** để chỉ tạo cho phụ đề đang chọn hoặc **Toàn video** để dùng một giọng cho toàn bộ video. Các đoạn không đổi giữ nguyên phần âm thanh hợp lệ. Khi không bật nhận diện nhiều người nói, đoạn được tạo lại dùng cùng cấu hình giọng với phần còn lại.

OmniVoice chạy trên máy sau khi cài gói. Edge TTS là dịch vụ trực tuyến và nhận nội dung cần đọc. Mẫu giọng trong dự án Tự động là tệp ghi sẵn; phát mẫu không chạy model.

### Âm thanh

Các thanh âm nguồn, giọng đọc và nhạc luôn hiển thị. Thay đổi được nghe cùng video hiện tại mà không chạy lại dịch hoặc TTS. Có thể thêm nhạc từ tệp hoặc liên kết được hỗ trợ.

Nếu thiếu một đoạn giọng, HaizFlow chỉ rõ phụ đề bị thiếu thay vì tự tạo mà không hỏi.

### Xuất

Chọn **Xuất video** để kết xuất bản chỉnh sửa hiện tại. Phụ đề dịch, che phụ đề gốc, giọng đọc, nhạc và watermark đều là tùy chọn. Lệnh xuất không tự chạy công cụ AI mà người dùng chưa chọn.

Khi hoàn tất, cửa sổ kết quả có **Phát video**, **Mở thư mục** và **Đóng**. Tệp xuất hiện tại vẫn được mở trực tiếp từ thanh công cụ dự án.

## 9. Xem trước và timeline

Video nguồn và video kết quả có nút phát, tạm dừng, dừng, tắt tiếng và toàn màn hình riêng. **Phát cả hai** bắt đầu hai video tại cùng vị trí để so sánh.

Kéo thanh dưới video, bấm timeline hoặc kéo vạch phát để tua. Trong lúc kéo, nút trượt đi theo con trỏ ngay; yêu cầu tua gửi tới player được gộp để giao diện không giật. Khi thả chuột, vị trí cuối được áp dụng chính xác.

Khi nguồn xem trước thay đổi, khung hình hợp lệ gần nhất được giữ cho tới khi bản thay thế sẵn sàng. Công việc model chạy nền không được chiếm trình phát hoặc đầu ra âm thanh.

## 10. Hàng loạt, Tải xuống và Đăng bài

### Hàng loạt

Thêm video, đặt thiết lập chung rồi chạy hàng đợi. Mỗi dòng giữ trạng thái và tiến trình riêng. Có thể thử lại video lỗi mà không làm mất video đã hoàn tất. Một thiết lập tạm cho từng video không tự trở thành cấu hình chung cho lần nhập sau.

### Tải xuống

- **Video:** kiểm tra một URL, xem thông tin rồi tải.
- **Kênh:** kiểm tra kênh hoặc trang cá nhân công khai, chọn video và thêm vào hàng đợi.
- **Âm thanh:** tải tệp âm thanh được hỗ trợ hoặc tách âm từ tệp trên máy.

Đổi tab không làm mất yêu cầu hoặc hàng đợi đang chạy.

### Đăng mạng xã hội

Kết nối Zernio, đặt nội dung và tùy chọn bài đăng, thêm video đã xuất, kiểm tra nơi đăng rồi xác nhận. Thao tác này gửi video tới dịch vụ bên thứ ba. Hãy đọc điều khoản, quy định riêng tư, hạn mức và chi phí của dịch vụ trước khi dùng. Video đã đăng có nút **Mở bài đăng**.

## 11. Dung lượng và dữ liệu tạm

| Hạng mục | Giới hạn hoặc quy tắc hiện tại |
| --- | ---: |
| Gói Core vừa được kiểm tra | 477 MiB |
| Cài đặt Core | Setup tự tính mức tối thiểu; bản hiện tại khuyến nghị chừa 4 GiB |
| Phần trống giữ lại khi cài tài nguyên | 2 GiB sau khi tính tải, cài và bản khôi phục |
| Dữ liệu tạm của trình sửa Thủ công | mặc định 4 GiB mỗi dự án; 16 GiB toàn bộ |

Các con số của Core không bao gồm bộ xử lý, model, video nguồn, video xuất hoặc tệp kết xuất tạm. Gói tài nguyên và thao tác xuất đều kiểm tra chỗ trống riêng bằng số byte đo được hoặc ước tính theo video.

Dùng **Cài đặt → Dọn dữ liệu tạm Thủ công** để xóa bản xem trước cũ, bản phối cũ và dữ liệu có thể dựng lại. Lệnh này không được xóa video nguồn, video xuất, bản chỉnh sửa đang dùng hoặc phiên bản cần cho Hoàn tác và Làm lại.

Người chạy từ source có thể đặt `HAIZFLOW_HOME` trong `.env` để chuyển model, cache, dữ liệu và tệp tạm tới một thư mục cục bộ khác.

## 12. Lỗi thường gặp

### Ứng dụng đang chuẩn bị model

Bạn vẫn có thể dùng giao diện. Chuẩn bị model và xử lý video có trạng thái riêng. Nếu chuẩn bị thất bại, hãy mở log kỹ thuật rồi kiểm tra chỗ trống, mạng, xác minh tệp và RAM hoặc VRAM còn lại.

### Không nhập được liên kết công khai

Mở liên kết trong trình duyệt và xác nhận nội dung vẫn công khai. Video riêng tư, đã xóa, bị giới hạn hoặc cần đăng nhập phải có quyền truy cập phù hợp; bấm nút nhiều lần không thể bỏ qua giới hạn đó. Với lỗi tạm thời của dịch vụ, hãy chờ một lúc rồi thử lại một lần.

### Video kết quả không có tiếng

Kiểm tra track nguồn, giọng đọc và nhạc cần dùng đã tồn tại, không bị tắt tiếng và có mức âm lớn hơn 0. Trong dự án Thủ công, tạo giọng và chọn bản phối âm là hai thao tác riêng.

### Video kết quả giống video nguồn trong chốc lát

Chờ bản xem trước đã lưu được nạp. Khung kết quả phải giữ hình hợp lệ gần nhất và chỉ đổi khi bản mới hoàn chỉnh. Nếu vẫn sai, mở log kỹ thuật và báo trạng thái dự án.

### Nhập tiếng Việt bị mất từ cuối

Bản hiện tại chốt phần chữ Windows IME đang ghép trước khi lưu. Nếu lỗi vẫn xảy ra, hãy báo phiên bản Windows, bộ gõ, ô nhập và câu dùng để tái hiện.

### Ứng dụng chậm

Dừng tác vụ không còn cần, kiểm tra RAM/VRAM cùng chỗ trống và dọn dữ liệu tạm Thủ công nếu cache đầy. Không chỉnh dự án đang chạy từ một ổ mạng chậm.

## 13. Báo lỗi

Mở [GitHub Issues](https://github.com/MachHongHai/HaizFlow/issues) và cung cấp:

- thao tác đã thực hiện;
- kết quả mong muốn và kết quả thực tế;
- lỗi đang hiển thị và đoạn log kỹ thuật liên quan;
- phiên bản Windows, GPU và HaizFlow;
- tệp mẫu nhỏ chỉ khi bạn có quyền chia sẻ.

Không đăng mật khẩu, API key, liên kết riêng tư, toàn bộ thông tin dự án hoặc nội dung có bản quyền khi chưa được phép.
