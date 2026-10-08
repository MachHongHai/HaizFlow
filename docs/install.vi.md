# Cài đặt HaizFlow

[Trang chính](../README.vi.md) · [Sử dụng](user-guide.vi.md) · [English](install.md)

## 1. Chuẩn bị

HaizFlow dùng trên Windows 10 phiên bản 1809 trở lên hoặc Windows 11 x64, RAM hệ thống từ 16 GB. GPU NVIDIA không bắt buộc. Chế độ GPU hỗ trợ card NVIDIA tương thích có VRAM riêng từ 6 GB; bộ nhớ đồ họa chia sẻ không tính vào mức này. Cần Internet để tải ứng dụng và những gói bạn chọn.

Chọn ổ còn đủ chỗ cho ứng dụng, tài nguyên, video nguồn và video xuất. Setup hiển thị yêu cầu của bản đang cài; mỗi gói có yêu cầu riêng và có thể cần thêm chỗ tạm khi tải, giải nén hoặc sửa.

## 2. Cài ứng dụng

**[Tải HaizFlow-0.1.6-Setup.exe](https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.6/HaizFlow-0.1.6-Setup.exe).** Đây là file duy nhất bạn cần để cài ứng dụng. Các tệp Core ở [trang phiên bản](https://github.com/MachHongHai/HaizFlow/releases/latest) dành cho cập nhật tự động; không tải hoặc giải nén chúng để cài.

1. Mở tệp **Setup.exe**, chọn ngôn ngữ và đọc điều kiện sử dụng.
2. Chọn thư mục cài. Có thể dùng ổ D hoặc ổ khác còn đủ chỗ.
3. Hoàn tất cài đặt và mở **HaizFlow** bằng shortcut hoặc **HaizFlow.exe**.

Bạn không cần cài Python hay chạy các EXE của gói tài nguyên. Giữ nguyên cấu trúc thư mục ứng dụng.

Bản hiện tại chưa có chữ ký số. Windows có thể hiển thị nhà phát hành không xác định hoặc chặn mở. Kiểm tra nguồn tải và SHA-256 do tác giả cung cấp; không tắt antivirus hoặc bỏ qua cảnh báo khi chưa xác minh được tệp. Nếu chính sách máy không cho chạy ứng dụng chưa ký, liên hệ người quản lý máy.

## 3. Chọn CPU hoặc GPU

Mở **Cài đặt → Chung**:

- **CPU:** dành cho máy không có GPU NVIDIA tương thích, hoặc khi bạn muốn dùng các model CPU.
- **GPU NVIDIA:** dành cho máy có GPU tương thích. Các lựa chọn GPU còn cần gói xử lý và model tương ứng.

Chọn **Áp dụng**. Khi đổi chế độ, kiểm tra lại model trong dự án trước khi chạy. Máy CPU không cần cài gói CUDA. Bạn cũng không cần tự cài CUDA Toolkit để dùng gói xử lý của HaizFlow.

## 4. Cài những gói cần dùng

Mở **Cài đặt → Gói tài nguyên**, chọn **Cài đặt** cạnh công cụ:

Để tải từ Douyin, cài thêm **Trình duyệt Douyin (Chromium)** trong nhóm **Tải xuống**. Gói được tải từ nguồn Chromium chính thức khi bạn chọn cài; dùng chung cho video, kênh và âm thanh.

| Công việc | Gói cần xem |
| --- | --- |
| Nhận dạng lời nói | Whisper Small hoặc Whisper Turbo; chọn theo chế độ được hỗ trợ |
| Dịch trên máy | HY-MT2 CPU hoặc HY-MT2 GPU |
| Tách giọng khỏi nhạc | Demucs CPU hoặc Demucs GPU, theo chế độ của ứng dụng |
| Tìm vùng phụ đề gốc | OCR |
| Tạo giọng cục bộ | OmniVoice và môi trường xử lý tương ứng |

Ứng dụng hiển thị các tài nguyên cần cho mỗi công cụ. Một số tài nguyên được dùng chung giữa các gói; trạng thái **Đã cài** cho biết tài nguyên đã có và sẵn sàng sử dụng.

Chờ tải, xác minh và cài hoàn tất. **Tạm dừng** giữ phần đã tải; **Tiếp tục** tải tiếp. Menu **…** có **Kiểm tra và sửa** và **Gỡ gói** để quản lý tài nguyên ngay trong ứng dụng. Dùng các thao tác này thay vì xóa thủ công tệp bên trong gói.

Demucs là một lựa chọn tách giọng trong dự án, nhưng có hai gói CPU/GPU. Ứng dụng dùng gói theo chế độ đã áp dụng. Việc cài gói GPU không thay thế gói CPU.

## 5. API key — chỉ khi cần

Whisper, HY-MT2, Demucs và OCR không cần Gemini hoặc Zernio key.

- **Gemini:** thêm key nếu dùng dịch qua Gemini.
- **Zernio:** thêm key nếu dùng Đăng mạng xã hội.

Mở **Cài đặt → API Key**, chọn nhà cung cấp, thêm key và kiểm tra. Với Zernio, thao tác kiểm tra kết nối kiểm tra các key trong danh sách: chấm xanh là hợp lệ; chấm đỏ cho biết key cần được kiểm tra lại. Chọn key muốn dùng.

Key được lưu trong Windows Credential Manager. Không gửi key trong ảnh, log công khai hoặc issue. Tài khoản và chi phí của các dịch vụ ngoài do bạn quản lý.

## 6. Dữ liệu và cập nhật

Giữ một bản sao độc lập của video nguồn và video xuất quan trọng. Dữ liệu làm việc của bản cài nằm trong thư mục runtime của ứng dụng; tài nguyên có thể được chuyển qua **Chuyển vị trí** trong Gói tài nguyên. Để ứng dụng hoàn tất thao tác, không di chuyển thư mục khi đang xử lý.

Nút kiểm tra cập nhật sẽ thông báo khi có phiên bản mới. Bạn xác nhận tải và xác nhận khởi động lại để áp dụng. Hoàn tất hoặc tạm dừng công việc đang chạy trước khi cập nhật.

## Bắt đầu sử dụng

Mở [hướng dẫn sử dụng](user-guide.vi.md) để tạo dự án đầu tiên, chỉnh phụ đề, lồng tiếng và đăng video. Trang [Trợ giúp](support.vi.md) hướng dẫn quản lý tài nguyên và liên hệ hỗ trợ.

**Lưu ý về giọng đọc:** checkpoint OmniVoice hiện tại giới hạn phi thương mại. Xem [điều kiện sử dụng](../README.vi.md#giấy-phép-và-sử-dụng-thương-mại) trước khi tạo giọng cho nội dung kiếm tiền hoặc công việc khách hàng.
