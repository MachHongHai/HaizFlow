# Sử dụng HaizFlow

[Trang chính](../README.vi.md) · [Cài đặt](install.vi.md) · [English](user-guide.md)

## Video đầu tiên

1. Chọn **Dự án mới → Thủ công**, đặt tên và nhập video từ tệp.
2. Trong công cụ **Nhận dạng & dịch**, chọn model nhận dạng, model dịch và ngôn ngữ đích, rồi chạy.
3. Xem lại nội dung phụ đề. Chỉnh những câu nhận dạng sai trước khi tạo giọng.
4. Nếu cần, dùng **Hình ảnh** để tìm và che phụ đề gốc; dùng **Giọng đọc** để tạo giọng.
5. Phát xem trước, kiểm tra âm lượng và thời gian. Chọn **Xuất**, chọn nơi lưu và xác nhận.

Bạn không phải chạy đủ các công cụ. Chỉ chỉnh phụ đề hoặc nhạc nền cũng có thể xuất video.

## Chọn cách làm việc

- **Thủ công:** chỉnh từng công cụ độc lập; phù hợp khi bạn cần kiểm tra và sửa chi tiết.
- **Tự động:** đặt ngôn ngữ, model, giọng, hình ảnh và âm thanh trước khi chạy một video.
- **Hàng loạt:** thêm nhiều video vào hàng đợi và dùng thiết lập chung. Theo dõi lỗi riêng của từng video.
- **Tải xuống:** nhập video, kênh hoặc âm thanh từ liên kết công khai được hỗ trợ.
- **Đăng mạng xã hội:** chuẩn bị bài đăng và gửi qua tài khoản Zernio của bạn.

Dùng Quay lại/Tiến tới để chuyển trang. Hoàn tác/Làm lại trong trình sửa dành cho các thay đổi chỉnh sửa, không phải lịch sử trang.

## Nhận dạng và dịch

Chọn model nhận dạng, model dịch và ngôn ngữ đích trong **Nhận dạng & dịch**.

Whisper nhận dạng lời nói; HY-MT2 dịch trên máy; Gemini dùng dịch vụ trực tuyến với key của bạn. Chọn model phù hợp CPU/GPU đã áp dụng trong Cài đặt. Nếu thiếu gói hoặc key, đọc thông báo rồi mở Cài đặt để bổ sung; dự án không tự chuyển trang.

Nếu đã tách giọng, xem dòng nguồn nhận dạng để biết công cụ đang dùng track giọng hay âm thanh nguồn. Video có tiếng ồn, tiếng nhạc lớn hoặc lời nói chồng nhau cần được kiểm tra kỹ hơn.

## Chỉnh phụ đề

Chọn đoạn trên timeline để sửa nội dung, thời gian và kiểu chữ. Mở cửa sổ chỉnh nội dung để xem các đoạn trước/sau. **Lưu** chỉ khả dụng khi có thay đổi; **Bỏ thay đổi** trả lại nội dung đã lưu.

Bạn có thể đổi font, kích thước, màu, viền, bóng và vùng hiển thị. Kéo vùng phụ đề trong preview để điều chỉnh bố cục. Phụ đề karaoke tô theo thời gian từng từ; các hàng không bắt đầu tô đồng thời.

Bangers được đi kèm ứng dụng. Với font khác, font phải có trên máy để giữ đúng kiểu chữ khi xuất. Nếu app báo thiếu hoặc thay đổi font, chọn lại font trước khi xuất.

Xem lại bản dịch và tên riêng. Khi đổi nội dung sau khi đã tạo giọng, tạo lại những đoạn cần thiết để lời và phụ đề khớp nhau.

## Hình ảnh và phụ đề gốc

Trong **Hình ảnh**, chọn giữ video gốc hoặc che phụ đề gốc. Nếu che, chọn **Làm mờ** hoặc **Vá nền**, kiểm tra vùng phụ đề rồi áp dụng.

OCR tìm vùng chữ, không bảo đảm mọi khung hình đều chính xác. Kiểm tra vị trí che tại vài thời điểm trong video. Khi xử lý xong, preview cập nhật để bạn xem kết quả; không cần xuất thử toàn bộ video.

Watermark có thể là chữ, ảnh hoặc video. Chỉ thêm tài sản bạn có quyền sử dụng và xem trước vị trí, kích thước, độ trong suốt.

## Giọng đọc

Chọn giọng trước khi bấm **Tạo giọng**. Có thể nghe mẫu trước khi chạy cả video.

- **Giọng dựng sẵn:** dùng cùng một giọng cho các câu đã chọn.
- **Nhận diện nhiều người nói:** phân nhóm người nói từ âm thanh nguồn và gán giọng đọc nhất quán. Không tự nhân bản giọng nguồn.
- **Mẫu giọng/nhân bản giọng:** dùng mẫu bạn lựa chọn và có quyền sử dụng; mẫu rõ lời, ít nhạc và một người nói thường dễ xử lý hơn.

Nhận diện người nói chạy trên CPU và được tích hợp trong ứng dụng. Những câu quá ngắn, tiếng chồng nhau hoặc giọng giống nhau có thể bị gán nhầm; nghe lại hội thoại thay vì chỉ kiểm tra câu đầu.

Checkpoint OmniVoice hiện tại **giới hạn phi thương mại**. Không mặc định dùng cho quảng cáo, video kiếm tiền hoặc khách hàng. Quyền của người có giọng trong mẫu cũng phải được bảo đảm.

## Âm thanh và nhạc nền

**Tách giọng** dùng Demucs theo chế độ CPU/GPU của ứng dụng. Cài gói tương ứng trước khi chạy.

Trong timeline, kiểm tra track âm thanh nguồn, giọng đọc và nhạc nền. Chỉnh âm lượng và tắt tiếng theo nhu cầu để tránh nghe đồng thời lời gốc và lời mới.

Nhập nhạc từ tệp hoặc liên kết được hỗ trợ. Track nhạc xuất hiện ngay khi nhập; bật **Lặp nhạc nền** nếu muốn nhạc phủ video, và **Tự giảm nhạc khi có lời** để lời dễ nghe hơn. Các lựa chọn này cũng có trong thiết lập Tự động.

## Tạm dừng, tiếp tục và chạy lại

**Tạm dừng** dừng công việc tại điểm có thể lưu. Những phần hoàn tất, còn hợp lệ được giữ để **Tiếp tục** không phải làm lại từ đầu.

Không đổi thiết lập rồi tiếp tục lượt cũ. Nếu thiết lập đã thay đổi, ứng dụng cảnh báo và chặn tiếp tục với cấu hình khác. Chọn **Chạy lại** để xử lý bằng thiết lập mới. Chạy lại có thể thay kết quả công cụ hiện tại; kiểm tra trước khi xác nhận.

Tiến trình video hiển thị trên thanh trạng thái của ứng dụng. Tiến trình tải/cài gói hiển thị trong Gói tài nguyên, không dùng chung thanh trạng thái video.

## Xem trước và xuất

Dùng timeline hoặc thanh dưới preview để tua. **So sánh** nằm cùng nhóm Hoàn tác/Làm lại ở giữa thanh công cụ, tách khỏi **Xuất**.

Nghe và xem ít nhất vài đoạn: câu đầu, lúc chuyển người nói, chỗ có nhạc và cuối video. Kiểm tra font, vùng phụ đề, watermark và âm lượng.

Chọn **Xuất**, chọn chất lượng và nơi lưu. Nếu tệp đã có, ứng dụng yêu cầu xác nhận ghi đè. Lưu bản xuất ngoài các thư mục dữ liệu dự án do HaizFlow quản lý để giữ bản sao độc lập. Xuất không tự chạy thêm các công cụ AI bạn chưa chọn.

## Đăng mạng xã hội

Thêm và kiểm tra Zernio key trong **Cài đặt → API Key**. Chấm xanh/đỏ cạnh từng key thể hiện kết quả kiểm tra.

Tạo dự án đăng bài, chọn tài khoản và nội dung, thêm video cục bộ hoặc bản dựng từ dự án, rồi kiểm tra nơi đăng trước khi xác nhận. Sau khi đăng thành công, dùng **Mở bài đăng** để kiểm tra.

Nền tảng và dịch vụ Zernio có hạn mức, chi phí và quy định riêng. Hãy bảo đảm quyền sử dụng nội dung trước khi đăng.

## Quản lý và khắc phục lỗi

- **Thiếu gói:** vào Gói tài nguyên để cài đúng gói CPU/GPU hoặc dùng **Kiểm tra và sửa**.
- **Key lỗi:** kiểm tra lại key đầy đủ, quyền và tài khoản; không gửi key khi báo lỗi.
- **Không nghe tiếng:** kiểm tra track cần dùng tồn tại, không tắt tiếng và âm lượng lớn hơn 0.
- **Thiếu bộ nhớ:** đóng ứng dụng khác, chọn model nhỏ hơn hoặc tắt **Giữ model sẵn sàng**. Tùy chọn này giúp giảm thời gian nạp lại, không làm tăng bộ nhớ của máy.
- **Gần đầy ổ:** chuyển tài nguyên bằng thao tác trong Cài đặt; giữ bản sao media quan trọng. Không xóa thủ công thư mục dự án hay gói đang được dùng.

Xem [hướng dẫn cài đặt](install.vi.md) để quản lý gói, dữ liệu và cập nhật. Nếu vẫn lỗi, [gửi issue](https://github.com/MachHongHai/HaizFlow/issues) với phiên bản, các bước thực hiện và ảnh thông báo. Che thông tin cá nhân và API key.
