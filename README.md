# HaizFlow

**Open-source desktop tool for batch video repurposing: download, replace subtitles, dub, and export — no API fees.**

[English](#english) · [Tiếng Việt](#tieng-viet) · [Download for Windows](https://github.com/MachHongHai/HaizFlow/releases) · [Report an issue](https://github.com/MachHongHai/HaizFlow/issues)

HaizFlow creates localized, reupload-ready versions of public videos. Download a source video, cover its existing subtitles, generate a new voice and subtitles, then export a finished version — all from one project-based desktop workflow.

<a id="english"></a>

## English

### Why HaizFlow?

- **Easy to use** — dedicated spaces for downloads, one video, batches, and social publishing, with consistent navigation and actions.
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
| Publish to social platforms | Prepare a project-backed queue and publish through the platforms connected to your Zernio account, without browser automation. |

### Get started

1. Download the Windows installer from [Releases](https://github.com/MachHongHai/HaizFlow/releases).
2. Choose where you want HaizFlow installed.
3. Open the app and create a Download, Single, Batch, or Social Publishing project.
4. Add media, choose your output options, and start processing.

Large local models are downloaded only when first needed. HaizFlow shows download progress and verifies them before use; later launches reuse the installed models.

### Privacy and connectivity

Core media processing is designed to run on your computer. Downloading from a public link connects to the selected source platform. OmniVoice is the local TTS option; Edge TTS is the online alternative and sends the selected subtitle text to that service.

Social publishing is an optional cloud workflow. It requires a user-supplied Zernio API key and one or more platform connections authorized through Zernio OAuth. Videos selected for publishing are uploaded through Zernio to the chosen platform. HaizFlow stores the API key in Windows Credential Manager, keeps publishing queues inside their projects, and does not use browser automation. The standard download and video-processing workflows do not require Zernio.

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

<a id="tieng-viet"></a>

## Tiếng Việt

**Công cụ desktop mã nguồn mở để reup video hàng loạt: tải video, che phụ đề gốc, lồng tiếng, thêm phụ đề mới và xuất video sẵn sàng để reup — không tốn phí API.**

HaizFlow tạo phiên bản video sẵn sàng để reup từ các nguồn công khai. Tải video nguồn, che vùng phụ đề cũ, tạo giọng đọc và phụ đề mới, rồi xuất video hoàn chỉnh — tất cả trong một quy trình theo dự án, rõ ràng và dễ theo dõi.

### Vì sao dùng HaizFlow?

- **Dễ sử dụng** — có không gian riêng cho tải xuống, một video, hàng loạt và đăng mạng xã hội; điều hướng cùng thao tác được bố trí nhất quán.
- **Tối ưu cho hàng loạt** — quản lí nhiều video trong hàng đợi, lưu lại tiến độ và thiết lập của từng dự án.
- **Mọi thứ trong một ứng dụng** — nhập tệp, dịch, lồng tiếng, chèn phụ đề, phối âm và xuất video mà không phải chuyển qua nhiều công cụ.
- **Ưu tiên xử lí trên máy** — các bước xử lí chính chạy trên máy của bạn. Quy trình mặc định không cần khóa API.
- **Dự án luôn gọn gàng** — tệp nguồn, thiết lập, video xuất, lịch sử hoạt động và dữ liệu khôi phục được quản lí trong cùng một dự án.

### Bạn có thể làm gì?

| Nhu cầu | HaizFlow hỗ trợ |
| --- | --- |
| Xử lí một video | Nhập video từ máy hoặc liên kết công khai, chọn ngôn ngữ đích và giọng đọc, sau đó xuất video đã dịch, lồng tiếng và có phụ đề mới. |
| Xử lí hàng loạt | Thêm nhiều video vào một dự án, theo dõi trạng thái trong hàng đợi, rồi bắt đầu hoặc tiếp tục xử lí khi phù hợp. |
| Tải nội dung | Tải video công khai, duyệt video từ kênh công khai được hỗ trợ, hoặc tải/trích âm thanh vào thư mục đầu ra bạn chọn. |
| Âm thanh và phụ đề | Giữ âm thanh gốc hoặc tách giọng, thêm nhạc nền từ tệp/liên kết, nghe thử phối âm và chỉnh âm lượng trước khi xử lí. |
| Phụ đề gốc | Tự nhận diện vùng phụ đề cứng có độ tin cậy cao để đặt phụ đề mới gọn gàng lên trên. |
| Đăng mạng xã hội | Chuẩn bị hàng đợi theo dự án và đăng qua các nền tảng đã kết nối với tài khoản Zernio mà không điều khiển trình duyệt. |

### Bắt đầu sử dụng

1. Tải bộ cài đặt Windows tại [trang phát hành](https://github.com/MachHongHai/HaizFlow/releases).
2. Chọn thư mục muốn cài HaizFlow.
3. Mở ứng dụng và tạo dự án Tải xuống, Đơn lẻ, Hàng loạt hoặc Đăng mạng xã hội.
4. Thêm tệp nguồn, chọn đầu ra mong muốn và bắt đầu xử lí.

Các mô hình lớn chỉ được tải khi lần đầu cần dùng. HaizFlow hiển thị tiến độ tải, kiểm tra tệp trước khi dùng và sẽ tái sử dụng ở những lần mở sau.

### Quyền riêng tư và kết nối mạng

Các bước xử lí chính được thiết kế để chạy trên máy của bạn. Khi tải từ liên kết công khai, ứng dụng sẽ kết nối tới nền tảng nguồn tương ứng. OmniVoice là lựa chọn TTS chạy local; Edge TTS là lựa chọn trực tuyến và sẽ nhận phần văn bản phụ đề cần tổng hợp giọng nói.

Đăng mạng xã hội là quy trình cloud tùy chọn. Tính năng này cần API key Zernio do người dùng cung cấp và các nền tảng được ủy quyền qua OAuth của Zernio. Video được chọn đăng sẽ tải qua Zernio tới nền tảng đã chọn. HaizFlow lưu API key trong Windows Credential Manager, giữ hàng đợi trong từng dự án và không tự động hóa trình duyệt. Các quy trình tải xuống và xử lí video thông thường không cần Zernio.

### Sử dụng có trách nhiệm

Chỉ tải, xử lí và xuất bản nội dung bạn sở hữu hoặc được cho phép sử dụng. Hãy tuân thủ điều khoản của từng nền tảng.

### Hỗ trợ và góp ý

Nếu gặp vấn đề hoặc cần hỗ trợ, hãy tạo [báo cáo trên GitHub](https://github.com/MachHongHai/HaizFlow/issues). Mọi góp ý về sản phẩm và trải nghiệm sử dụng đều rất được chào đón.

## Tác giả

Dự án được tạo bởi **Mạch Hồng Hải**.

- GitHub: [MachHongHai](https://github.com/MachHongHai)
- Email: machhonghaipr@gmail.com

## Giấy phép

HaizFlow sử dụng [Apache License 2.0](HaizFlow/LICENSE). Thư viện phụ thuộc, mô hình và tệp nhị phân của bên thứ ba giữ giấy phép riêng; xem [NOTICE](HaizFlow/NOTICE) và `HaizFlow/licenses/`.
