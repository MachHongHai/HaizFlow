# HaizFlow

**Công cụ desktop mã nguồn mở để reup video hàng loạt — xử lí local, không tốn phí API.**

[English](README.md) · [Tải cho Windows](https://github.com/MachHongHai/HaizFlow/releases) · [Báo lỗi](https://github.com/MachHongHai/HaizFlow/issues)

HaizFlow đưa việc tải video, dịch, lồng tiếng, làm phụ đề và xuất video vào một quy trình desktop rõ ràng. Bạn chỉ cần tạo dự án, chọn media và thiết lập cần dùng, sau đó theo dõi toàn bộ tiến độ trên giao diện dễ sử dụng.

## Vì sao dùng HaizFlow?

- **Dễ sử dụng** — có không gian riêng cho tải xuống, một video và hàng loạt; điều hướng cùng thao tác được bố trí nhất quán.
- **Tối ưu cho hàng loạt** — quản lí nhiều video trong hàng đợi, lưu lại tiến độ và thiết lập của từng dự án.
- **Mọi thứ trong một ứng dụng** — nhập media, dịch, lồng tiếng, chèn phụ đề, phối âm và xuất video mà không phải chuyển qua nhiều công cụ.
- **Ưu tiên xử lí local** — các bước xử lí media chính chạy trên máy của bạn. Quy trình mặc định không cần API key.
- **Dự án luôn gọn gàng** — media, thiết lập, video xuất, lịch sử hoạt động và dữ liệu khôi phục được quản lí trong cùng một dự án.

## Bạn có thể làm gì?

### Xử lí một video

Nhập video từ máy hoặc từ liên kết công khai, chọn ngôn ngữ đích và giọng đọc, sau đó xuất video đã dịch, lồng tiếng và có phụ đề mới.

### Xử lí hàng loạt

Thêm nhiều video vào một dự án, theo dõi trạng thái trong hàng đợi, rồi bắt đầu hoặc tiếp tục xử lí bất cứ khi nào phù hợp.

### Tải media

Tải video công khai, duyệt video từ kênh công khai được hỗ trợ, hoặc tải/trích âm thanh vào thư mục đầu ra bạn chọn.

### Cải thiện âm thanh và phụ đề

Giữ âm thanh gốc hoặc tách giọng, thêm nhạc nền từ tệp hoặc liên kết, nghe thử phối âm và chỉnh âm lượng trước khi xử lí. HaizFlow có thể nhận diện vùng phụ đề cứng có độ tin cậy cao để đặt phụ đề mới gọn gàng lên trên.

## Bắt đầu sử dụng

1. Tải installer Windows tại [Releases](https://github.com/MachHongHai/HaizFlow/releases).
2. Chọn thư mục muốn cài HaizFlow.
3. Mở ứng dụng và tạo dự án Tải xuống, Đơn lẻ hoặc Hàng loạt.
4. Thêm media, chọn đầu ra mong muốn và bắt đầu xử lí.

Các model lớn chỉ được tải khi lần đầu cần dùng. HaizFlow hiển thị tiến độ tải, kiểm tra file trước khi dùng và sẽ tái sử dụng model ở những lần mở sau.

## Quyền riêng tư và kết nối mạng

Các bước xử lí media chính được thiết kế để chạy trên máy của bạn. Khi tải từ liên kết công khai, ứng dụng sẽ kết nối tới nền tảng nguồn tương ứng. Giọng đọc Edge TTS mặc định là dịch vụ trực tuyến, vì vậy văn bản cần tổng hợp giọng nói sẽ được gửi tới dịch vụ này.

## Sử dụng có trách nhiệm

Chỉ tải, xử lí và xuất bản nội dung bạn sở hữu hoặc được cho phép sử dụng. Hãy tuân thủ điều khoản của từng nền tảng media.

## Hỗ trợ và góp ý

Nếu gặp vấn đề hoặc cần hỗ trợ, hãy tạo [issue trên GitHub](https://github.com/MachHongHai/HaizFlow/issues). Mọi góp ý về sản phẩm và trải nghiệm sử dụng đều rất được chào đón.

## Tác giả

Dự án được tạo bởi **Mạch Hồng Hải**.

- GitHub: [MachHongHai](https://github.com/MachHongHai)
- Email: machhonghaipr@gmail.com

## Giấy phép

HaizFlow dùng [Apache License 2.0](LICENSE). Dependency, model và binary bên thứ ba giữ giấy phép riêng; xem [NOTICE](NOTICE) và `licenses/`.
