# HaizFlow 1.0.3

[Tải bộ cài Windows](https://github.com/MachHongHai/HaizFlow/releases/download/v1.0.3/HaizFlow-1.0.3-Setup.exe)

## Bản vá runtime Windows

- Nâng `aiohttp` trong engine CPU/CUDA từ 3.14.3 lên 3.14.5 (cùng bản Core đang dùng), xử lý các advisory HTTP client/server mới được audit phát hiện. Không thêm ngoại lệ bỏ qua cảnh báo bảo mật.

- Sửa lỗi thông tin CPU có thể bị kẹt ở “Đang đọc thông tin CPU”: sửa lần dò đầu khi cache trống, đọc Registry dự phòng khi CIM/PowerShell không khả dụng và cập nhật kết quả lên UI mà không dò lại CUDA.
- Sửa lỗi engine báo thiếu `update-layout.json` với bố cục app dạng phẳng. Bộ xử lý dùng đúng thư mục app và không tự tạo marker cập nhật, di chuyển dữ liệu hay bỏ qua marker hỏng của bản cài versioned.
- Siết đóng gói SciPy cho engine CPU/CUDA: khai báo rõ extension `_linalg_pythran` và bắt buộc kiểm tra module này trước khi nạp model. Lỗi nạp SciPy có hướng dẫn xác minh/cài lại gói xử lý. Chưa xác định được nguyên nhân riêng trên máy user báo lỗi 1.0.1 do không có log; gói CPU 15 đã kiểm tra có module và chạy smoke test đạt.

Số luồng xử lý theo mức RAM không thay đổi; “4 luồng” trong một profile CPU không có nghĩa app nhận CPU phần cứng chỉ có bốn luồng. Không đổi model, dữ liệu dự án, API key hay cache hợp lệ.

## Cập nhật từ 1.0.1 và 1.0.2

Mở **Phiên bản mới → Cập nhật** để nâng trực tiếp từ **1.0.1** hoặc **1.0.2**. Release có Delta riêng cho từng bản, Core đầy đủ dự phòng và bộ cài Windows. Giữ nguyên các release và asset cũ.

**Sau khi cập nhật Core, mở Gói tài nguyên và cập nhật bộ xử lý khi app yêu cầu:** CPU **16**, CUDA **18**, OCR **8**. Đây là các engine được đóng gói lại để nhận bản sửa, không phải tải lại model. Gói CUDA lớn được chia thành các phần có checksum; không tự ghép hoặc chạy EXE của gói tài nguyên.

Người cài mới dùng **Setup.exe**, không dùng ZIP Core cập nhật thay bộ cài hoàn chỉnh. Giữ/backup `runtime` và mọi dự án trước khi sửa một bản cài đã hỏng.

Ngoài bản vá thư viện HTTP nêu trên, checkpoint, mẫu giọng, font, codec và thư viện khác không đổi; [nguồn thư viện tương ứng](https://github.com/MachHongHai/HaizFlow/releases/download/v1.0.0/HaizFlow-1.0.0-ThirdPartySources.zip) vẫn được giữ tại URL cũ. Giới hạn giấy phép, gồm checkpoint OmniVoice phi thương mại, vẫn áp dụng.

Windows x64. Bản Windows **chưa ký Authenticode**; Windows có thể cảnh báo hoặc chặn theo chính sách. Không tắt phần mềm bảo vệ. Kiểm thử cục bộ/frozen không chứng nhận mọi máy Windows, CPU/GPU hoặc điều kiện mạng.
