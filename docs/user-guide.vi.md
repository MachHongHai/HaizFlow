# Sử dụng HaizFlow

[Trang chính](../README.vi.md) · [Cài đặt](install.vi.md) · [English](user-guide.md)

## Video đầu tiên

1. Chọn **Dự án mới → Thủ công**, đặt tên và nhập video từ tệp.
2. Trong công cụ **Nhận dạng & dịch**, chọn model nhận dạng, model dịch và ngôn ngữ đích, rồi chạy.
3. Xem lại nội dung phụ đề, chỉnh câu chữ và tên riêng trước khi tạo giọng.
4. Nếu cần, dùng **Hình ảnh** để tìm và che phụ đề gốc; dùng **Giọng đọc** để tạo giọng.
5. Phát xem trước, kiểm tra âm lượng và thời gian. Chọn **Xuất**, chọn nơi lưu và xác nhận.

Bạn không phải chạy đủ các công cụ. Chỉ chỉnh phụ đề hoặc nhạc nền cũng có thể xuất video.

## Chọn cách làm việc

- **Thủ công:** chỉnh từng công cụ độc lập; phù hợp khi bạn cần kiểm tra và sửa chi tiết.
- **Tự động:** đặt ngôn ngữ, model, giọng, hình ảnh và âm thanh trước khi chạy một video.
- **Hàng loạt:** thêm nhiều video vào hàng đợi và dùng thiết lập chung. Theo dõi tiến trình và kết quả của từng video.
- **Tải xuống:** nhập video, kênh hoặc âm thanh từ liên kết công khai được hỗ trợ.
- **Đăng mạng xã hội:** chuẩn bị bài đăng và gửi qua tài khoản Zernio của bạn.

Dùng Quay lại/Tiến tới để chuyển trang. Hoàn tác/Làm lại trong trình sửa dành cho các thay đổi chỉnh sửa, không phải lịch sử trang.

## Nhận dạng và dịch

Chọn model nhận dạng, model dịch và ngôn ngữ đích trong **Nhận dạng & dịch**.

Whisper nhận dạng lời nói; HY-MT2 dịch trên máy; Gemini dùng dịch vụ trực tuyến với key của bạn. Chọn model phù hợp CPU/GPU đã áp dụng trong Cài đặt. Cài các gói cần dùng trong **Gói tài nguyên**; thêm Gemini key trong **API Key** khi chọn dịch bằng Gemini.

Nếu đã tách giọng, xem dòng nguồn nhận dạng để biết công cụ đang dùng track giọng hay âm thanh nguồn. Video có tiếng ồn, tiếng nhạc lớn hoặc lời nói chồng nhau cần được kiểm tra kỹ hơn.

## Chỉnh phụ đề

Chọn đoạn trên timeline để sửa nội dung, thời gian và kiểu chữ. Mở cửa sổ chỉnh nội dung để xem các đoạn trước/sau. **Lưu** chỉ khả dụng khi có thay đổi; **Bỏ thay đổi** trả lại nội dung đã lưu.

Bạn có thể đổi kích thước, màu, viền, bóng và vùng hiển thị. Kéo vùng phụ đề trong preview để điều chỉnh bố cục. Phụ đề karaoke tô theo thời gian từng từ.

Phụ đề dùng font Bangers đi kèm ứng dụng, thống nhất giữa preview và video xuất. Bạn không cần cài thêm font.

Xem lại bản dịch và tên riêng. Khi đổi nội dung sau khi đã tạo giọng, tạo lại những đoạn cần thiết để lời và phụ đề khớp nhau.

## Hình ảnh và phụ đề gốc

Trong **Hình ảnh**, chọn giữ video gốc hoặc che phụ đề gốc. Nếu che, chọn **Làm mờ** hoặc **Vá nền**, kiểm tra vùng phụ đề rồi áp dụng.

OCR tìm vùng chữ để che phụ đề gốc. Xem trước ở vài thời điểm và điều chỉnh vùng che theo video. Preview cập nhật sau khi xử lý để bạn xem kết quả trước khi xuất.

Watermark có thể là chữ, ảnh hoặc video. Chỉ thêm tài sản bạn có quyền sử dụng và xem trước vị trí, kích thước, độ trong suốt.

## Giọng đọc

Chọn giọng trước khi bấm **Tạo giọng**. Có thể nghe mẫu trước khi chạy cả video.

- **Giọng dựng sẵn:** dùng cùng một giọng cho các câu đã chọn.
- **Nhận diện nhiều người nói:** phân nhóm người nói từ âm thanh nguồn và gán giọng đọc nhất quán. Không tự nhân bản giọng nguồn.
- **Mẫu giọng/nhân bản giọng:** dùng mẫu bạn lựa chọn và có quyền sử dụng; mẫu rõ lời, ít nhạc và một người nói thường dễ xử lý hơn.

Nhận diện người nói chạy trên CPU và được tích hợp trong ứng dụng. Nghe lại hội thoại và điều chỉnh giọng của từng nhóm theo nhân vật trong video. Với mẫu giọng, ưu tiên đoạn chỉ có một người nói rõ lời.

Checkpoint OmniVoice hiện tại **giới hạn phi thương mại**. Không mặc định dùng cho quảng cáo, video kiếm tiền hoặc khách hàng. Quyền của người có giọng trong mẫu cũng phải được bảo đảm.

## Âm thanh và nhạc nền

**Tách giọng** dùng Demucs theo chế độ CPU/GPU của ứng dụng. Cài gói tương ứng trước khi chạy.

Trong timeline, kiểm tra track âm thanh nguồn, giọng đọc và nhạc nền. Chỉnh âm lượng và tắt tiếng theo nhu cầu để tránh nghe đồng thời lời gốc và lời mới.

Nhập nhạc từ tệp hoặc liên kết được hỗ trợ. Bật **Lặp nhạc nền** nếu muốn nhạc phủ video, và **Tự giảm nhạc khi có lời** để lời dễ nghe hơn. Các lựa chọn này cũng có trong thiết lập Tự động.

## Tạm dừng, tiếp tục và chạy lại

**Tạm dừng** dừng công việc tại điểm có thể lưu. Những phần hoàn tất, còn hợp lệ được giữ để **Tiếp tục** không phải làm lại từ đầu.

**Tiếp tục** dùng thiết lập của lượt đang tạm dừng. Khi muốn đổi thiết lập, chọn **Chạy lại** để bắt đầu một lượt mới. Kiểm tra thông báo xác nhận trước khi thay kết quả hiện tại.

Tiến trình video hiển thị trên thanh trạng thái của ứng dụng. Tiến trình tải/cài gói hiển thị trong Gói tài nguyên, không dùng chung thanh trạng thái video.

## Xem trước và xuất

Dùng timeline hoặc thanh dưới preview để tua. Chọn **So sánh** để đối chiếu video gốc và kết quả chỉnh sửa. **Hoàn tác/Làm lại** giúp xem lại các thay đổi trong trình sửa.

Nghe và xem ít nhất vài đoạn: câu đầu, lúc chuyển người nói, chỗ có nhạc và cuối video. Kiểm tra font, vùng phụ đề, watermark và âm lượng.

Chọn **Xuất**, chọn chất lượng và nơi lưu. Nếu tệp đã có, ứng dụng yêu cầu xác nhận ghi đè. Lưu bản xuất ngoài các thư mục dữ liệu dự án do HaizFlow quản lý để giữ bản sao độc lập. Xuất không tự chạy thêm các công cụ AI bạn chưa chọn.

## Đăng mạng xã hội

Thêm và kiểm tra Zernio key trong **Cài đặt → API Key**. Chấm xanh/đỏ cạnh từng key thể hiện kết quả kiểm tra.

Tạo dự án đăng bài, chọn tài khoản và nội dung, thêm video cục bộ hoặc video đã xử lý từ dự án, rồi kiểm tra nơi đăng trước khi xác nhận. Sau khi đăng, dùng **Mở bài đăng** để xem trên nền tảng.

Nền tảng và dịch vụ Zernio có hạn mức, chi phí và quy định riêng. Hãy bảo đảm quyền sử dụng nội dung trước khi đăng.

## Tài liệu liên quan

Xem [hướng dẫn cài đặt](install.vi.md) để chọn gói, API key, vị trí lưu dữ liệu và cập nhật. Trang [Trợ giúp](support.vi.md) hướng dẫn quản lý tài nguyên và liên hệ hỗ trợ. Không gửi API key hoặc dữ liệu riêng tư khi liên hệ.
