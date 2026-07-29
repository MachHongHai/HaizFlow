# HaizFlow

**Công cụ desktop mã nguồn mở để reup video hàng loạt — xử lí local, không tốn phí API.**

[Tiếng Việt](#tieng-viet) · [English](#english) · [Tải cho Windows](https://github.com/MachHongHai/HaizFlow/releases) · [Báo lỗi](https://github.com/MachHongHai/HaizFlow/issues)

HaizFlow đưa việc tải video, dịch, lồng tiếng, làm phụ đề và xuất video vào một quy trình desktop rõ ràng. Bạn chỉ cần tạo dự án, chọn media và thiết lập cần dùng, sau đó theo dõi toàn bộ tiến độ trên giao diện dễ sử dụng.

<a id="tieng-viet"></a>

## Tiếng Việt

### Vì sao dùng HaizFlow?

- **Dễ sử dụng** — có không gian riêng cho tải xuống, một video và hàng loạt; điều hướng cùng thao tác được bố trí nhất quán.
- **Tối ưu cho hàng loạt** — quản lí nhiều video trong hàng đợi, lưu lại tiến độ và thiết lập của từng dự án.
- **Mọi thứ trong một ứng dụng** — nhập media, dịch, lồng tiếng, chèn phụ đề, phối âm và xuất video mà không phải chuyển qua nhiều công cụ.
- **Ưu tiên xử lí local** — các bước xử lí media chính chạy trên máy của bạn. Quy trình mặc định không cần API key.
- **Dự án luôn gọn gàng** — media, thiết lập, video xuất, lịch sử hoạt động và dữ liệu khôi phục được quản lí trong cùng một dự án.

### Bạn có thể làm gì?

| Nhu cầu | HaizFlow hỗ trợ |
| --- | --- |
| Xử lí một video | Nhập video từ máy hoặc liên kết công khai, chọn ngôn ngữ đích và giọng đọc, sau đó xuất video đã dịch, lồng tiếng và có phụ đề mới. |
| Xử lí hàng loạt | Thêm nhiều video vào một dự án, theo dõi trạng thái trong hàng đợi, rồi bắt đầu hoặc tiếp tục xử lí khi phù hợp. |
| Tải media | Tải video công khai, duyệt video từ kênh công khai được hỗ trợ, hoặc tải/trích âm thanh vào thư mục đầu ra bạn chọn. |
| Âm thanh và phụ đề | Giữ âm thanh gốc hoặc tách giọng, thêm nhạc nền từ tệp/liên kết, nghe thử phối âm và chỉnh âm lượng trước khi xử lí. |
| Phụ đề gốc | Tự nhận diện vùng phụ đề cứng có độ tin cậy cao để đặt phụ đề mới gọn gàng lên trên. |

### Bắt đầu sử dụng

1. Tải installer Windows tại [Releases](https://github.com/MachHongHai/HaizFlow/releases).
2. Chọn thư mục muốn cài HaizFlow.
3. Mở ứng dụng và tạo dự án Tải xuống, Đơn lẻ hoặc Hàng loạt.
4. Thêm media, chọn đầu ra mong muốn và bắt đầu xử lí.

Các model lớn chỉ được tải khi lần đầu cần dùng. HaizFlow hiển thị tiến độ tải, kiểm tra file trước khi dùng và sẽ tái sử dụng model ở những lần mở sau.

### Quyền riêng tư và kết nối mạng

Các bước xử lí media chính được thiết kế để chạy trên máy của bạn. Khi tải từ liên kết công khai, ứng dụng sẽ kết nối tới nền tảng nguồn tương ứng. Giọng đọc Edge TTS mặc định là dịch vụ trực tuyến, vì vậy văn bản cần tổng hợp giọng nói sẽ được gửi tới dịch vụ này.

### Sử dụng có trách nhiệm

Chỉ tải, xử lí và xuất bản nội dung bạn sở hữu hoặc được cho phép sử dụng. Hãy tuân thủ điều khoản của từng nền tảng media.

### Hỗ trợ và góp ý

Nếu gặp vấn đề hoặc cần hỗ trợ, hãy tạo [issue trên GitHub](https://github.com/MachHongHai/HaizFlow/issues). Mọi góp ý về sản phẩm và trải nghiệm sử dụng đều rất được chào đón.

<a id="english"></a>

## English

### Why HaizFlow?

- **Easy to use** — dedicated spaces for downloads, one video, and batches, with consistent navigation and actions.
- **Built for batches** — manage multiple videos in a queue while keeping every project's progress and settings organized.
- **Everything in one app** — import media, translate, dub, add subtitles, mix audio, and export without switching tools.
- **Local-first** — core media processing happens on your computer. No API key is required for the standard workflow.
- **Projects stay organized** — each project keeps its media, settings, output, activity history, and recovery information together.

### What you can do

| Need | HaizFlow helps you |
| --- | --- |
| Process a video | Import a local video or public link, choose a target language and voice, then export a translated, dubbed video with new subtitles. |
| Process batches | Add multiple videos to one project, review their status in a queue, and start or resume processing when ready. |
| Download media | Download public videos, browse supported public channels, or download and extract audio to an output folder you choose. |
| Improve audio and subtitles | Keep original audio or separate vocals, add background music from a file or link, preview the mix, and adjust levels before processing. |
| Replace source subtitles | Detect likely burned-in subtitle areas and place new subtitles cleanly over them. |

### Get started

1. Download the Windows installer from [Releases](https://github.com/MachHongHai/HaizFlow/releases).
2. Choose where you want HaizFlow installed.
3. Open the app and create a Download, Single, or Batch project.
4. Add media, choose your output options, and start processing.

Large local models are downloaded only when first needed. HaizFlow shows download progress and verifies them before use; later launches reuse the installed models.

### Privacy and connectivity

Core media processing is designed to run on your computer. Downloading from a public link connects to the selected source platform. The default Edge TTS voice service is online, so text selected for speech synthesis is sent to that service.

### Responsible use

Only download, process, and publish content you own or have permission to use. Please follow the rules and terms of each media platform.

### Support and feedback

Need help or found a problem? Please open an [issue on GitHub](https://github.com/MachHongHai/HaizFlow/issues). Product feedback and usability suggestions are welcome.

## Author

Created by **Mạch Hồng Hải**.

- GitHub: [MachHongHai](https://github.com/MachHongHai)
- Email: machhonghaipr@gmail.com

## License

HaizFlow is released under the [Apache License 2.0](HaizFlow/LICENSE). Third-party dependencies, models, and bundled binaries retain their own licenses; see [NOTICE](HaizFlow/NOTICE) and `HaizFlow/licenses/`.
