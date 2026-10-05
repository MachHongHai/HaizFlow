<div align="center">
  <img src="src/haizflow/desktop/assets/branding/haizflow-mark.png" width="96" alt="Logo HaizFlow">
  <h1>HaizFlow</h1>
  <p><strong>Dịch video. Chỉnh phụ đề. Hoàn thiện bản dựng.</strong></p>
  <p>Một không gian làm việc cho phụ đề, giọng đọc và âm thanh trên Windows.</p>
  <p><a href="docs/install.vi.md">Cài đặt</a> · <a href="docs/user-guide.vi.md">Hướng dẫn sử dụng</a> · <a href="https://github.com/MachHongHai/HaizFlow/issues">Hỗ trợ</a> · <a href="README.md">English</a></p>
</div>

## Từ video gốc đến bản dựng của bạn

HaizFlow giúp bạn nhận dạng lời nói, dịch nội dung và chỉnh lại từng câu ngay trên video. Kết hợp phụ đề karaoke, giọng đọc, nhạc nền và watermark, rồi xem trước và xuất bản dựng tại một nơi.

Bạn có thể để ứng dụng chạy theo thiết lập đã chọn, hoặc chủ động chỉnh từng bước trong trình sửa Thủ công. Không cần tạo giọng hay dịch nội dung nếu công việc của bạn chỉ là chỉnh phụ đề và phối âm.

## Làm được gì với HaizFlow?

- **Dịch và chỉnh phụ đề:** nhận dạng lời nói bằng Whisper, dịch cục bộ bằng HY-MT2 hoặc dùng Gemini với API key của bạn; chỉnh nội dung, thời gian, font và hiệu ứng karaoke.
- **Hoàn thiện âm thanh:** tách giọng bằng Demucs, điều chỉnh âm lượng, thêm và lặp nhạc nền, tự giảm nhạc khi có lời.
- **Tạo giọng đọc:** dùng giọng dựng sẵn, phân biệt nhiều người nói để giữ giọng nhất quán, hoặc tạo giọng từ mẫu bạn có quyền sử dụng.
- **Chỉnh hình ảnh:** che phụ đề gốc bằng làm mờ hoặc vá nền, thêm watermark và so sánh với video gốc.
- **Xử lý nhiều video:** chạy hàng đợi Hàng loạt, theo dõi kết quả từng video và thử lại công việc lỗi.
- **Chuẩn bị đăng bài:** nhập từ tệp hoặc liên kết được hỗ trợ; kết nối Zernio để đăng mạng xã hội.

Kết quả nhận dạng, dịch và phân biệt người nói cần được xem lại trước khi xuất, nhất là video có tiếng ồn hoặc nhiều người nói chồng nhau.

## Bắt đầu

Bản 0.1.0 đang được kiểm thử trước phát hành; chưa có bộ cài công khai được duyệt cho bản này. Nếu bạn đang thử bản do tác giả cung cấp, dùng [hướng dẫn cài đặt](docs/install.vi.md). Khi phát hành, tải bộ cài từ [GitHub Releases chính thức](https://github.com/MachHongHai/HaizFlow/releases), không dùng các EXE của gói tài nguyên để mở ứng dụng.

1. Cài HaizFlow và mở ứng dụng. Giao diện mặc định là tiếng Việt.
2. Chọn CPU hoặc GPU NVIDIA trong **Cài đặt → Chung**, rồi cài các gói cần dùng trong **Gói tài nguyên**.
3. Tạo dự án **Thủ công** để làm quen với từng công cụ, hoặc **Tự động** để chạy theo thiết lập.
4. Kiểm tra bản dịch, phụ đề và âm thanh. Chọn **Xuất** để lưu video ra thư mục của bạn.

## Chạy trên máy của bạn

HaizFlow hỗ trợ Windows 10 phiên bản 1809 trở lên và Windows 11, bản x64. Không cần cài Python khi dùng bộ cài. Máy chỉ có CPU vẫn mở được ứng dụng và dùng các lựa chọn CPU; tính năng GPU yêu cầu NVIDIA tương thích cùng gói tương ứng.

Các công cụ cục bộ chạy trên máy sau khi cài gói. Internet cần cho việc tải gói, kiểm tra cập nhật, nhập từ liên kết và các dịch vụ trực tuyến. Gemini, Zernio và những dịch vụ bên ngoài có điều khoản, hạn mức và chi phí riêng.

Bộ cài hiển thị dung lượng ứng dụng; gói tài nguyên, video và tệp xuất cần thêm chỗ trống. Bạn có thể chuyển vị trí lưu tài nguyên trong Cài đặt. [Xem cách chọn gói và quản lý dung lượng](docs/install.vi.md).

## Sử dụng cho nội dung thương mại

HaizFlow miễn phí sử dụng theo [giấy phép ứng dụng](LICENSE). Quyền đối với video, nhạc, mẫu giọng và model vẫn áp dụng riêng.

**Checkpoint OmniVoice hiện tại có giới hạn phi thương mại.** Không mặc định dùng chức năng này cho video kiếm tiền, quảng cáo hoặc công việc khách hàng khi chưa có quyền phù hợp. Việc công khai mã nguồn hoặc miễn phí ứng dụng không cấp thêm quyền thương mại cho model. Các công cụ khác cần được xem xét theo giấy phép riêng; HaizFlow không tuyên bố mọi quy trình đều được cấp phép thương mại.

## Tài liệu và hỗ trợ

- [Hướng dẫn cài đặt](docs/install.vi.md): máy CPU/GPU, gói tài nguyên, API key và dữ liệu.
- [Hướng dẫn sử dụng](docs/user-guide.vi.md): dự án đầu tiên, phụ đề, giọng đọc và xuất video.
- [Báo lỗi](https://github.com/MachHongHai/HaizFlow/issues): gửi bước thực hiện, phiên bản và ảnh lỗi; không gửi API key.
- [Tài liệu phát triển](docs/development.vi.md) và [kiến trúc](docs/architecture.vi.md): dành cho người đóng góp và bảo trì.

HaizFlow do **Mạch Hồng Hải** phát triển. Nếu ứng dụng hữu ích, bạn có thể [đánh dấu sao repository](https://github.com/MachHongHai/HaizFlow) hoặc góp ý để cải thiện trải nghiệm.

### Giấy phép và thông báo

HaizFlow Source-Available 1.0 không phải giấy phép nguồn mở OSI. Điều kiện phân phối lại, đóng gói lại và kinh doanh phần mềm được quy định trong [LICENSE](LICENSE). Xem [NOTICE](NOTICE) và [thành phần bên thứ ba](THIRD_PARTY_NOTICES.md). [Dự thảo không có hiệu lực](legal/LICENSE-SOURCE-AVAILABLE-DRAFT.md) và [hồ sơ rà soát giấy phép](docs/licensing-review.md) được lưu riêng cho công việc bảo trì.
