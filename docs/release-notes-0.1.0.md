# HaizFlow 0.1.0 — DRAFT, chưa phát hành

Không dùng bản ghi này để xác nhận binary đã đủ điều kiện public. Chỉ bỏ
nhãn DRAFT sau khi đúng artifact upload đã qua legal/resource/provenance
gate và nghiệm thu cài đặt/cập nhật trên máy sạch.

## Nội dung dự kiến

- Cài mới mặc định tiếng Việt; giữ lựa chọn ngôn ngữ đã lưu khi cài lại.
- Bảo vệ dữ liệu khi thay engine/đổi ổ lưu tài nguyên; không dọn nguồn nếu
  bản sao chưa được xác minh, khôi phục bản cũ khi promotion lỗi.
- Sửa đồng bộ CPU/GPU giữa cài đặt app, model trong dự án và model nạp trước.
  Nhận diện nhiều người nói vẫn dùng CPU.
- Installer versioned với launcher/updater riêng; repair và uninstall bảo
  toàn dữ liệu, không đụng dự án/tài nguyên ngoài thư mục app.
- Delta Core không yêu cầu Authenticode. Kiểm SHA-256, inventory, startup
  health và rollback vẫn bắt buộc. Release đầu dùng Full Core; delta chỉ
  dành cho các phiên bản phát hành thật tiếp theo.
- Engine GPU lớn được chia thành các asset dưới 2 GiB; ứng dụng kiểm từng
  phần và toàn ZIP trước khi giải nén/cài. Gói CPU và vision dùng ZIP đơn.

## Cài đặt và dữ liệu

Windows x64, Windows 10 build 17763 hoặc mới hơn. Chọn thư mục app có quyền
ghi; Setup tính payload thực và chỗ trống dự phòng. Engine, model và media
là dung lượng bổ sung, không nằm trong số dung lượng Core. Runtime dưới
thư mục cài đặt được giữ khi gỡ mặc định. API key nằm trong Windows
Credential Manager, không nằm trong file dự án hay release.

## Bản không ký

Bản phát hành dự kiến không có chứng chỉ Authenticode, không cần mua chứng
chỉ để dùng cơ chế delta. Windows có thể cảnh báo Unknown publisher hoặc
chặn theo Smart App Control/chính sách tổ chức. Không khuyên người dùng
tắt bảo vệ, cài trusted root tự ký hoặc bỏ qua checksum.

## Giấy phép và giới hạn

HaizFlow Source-Available 1.0; component có giấy phép độc lập. Checkpoint
OmniVoice tại revision `c5fdb5ccb189668d56333f77ba2629f4cd7535f4` có điều
kiện **phi thương mại (CC-BY-NC)**. Việc app miễn phí hoặc SDK dùng
Apache-2.0 không cấp quyền thương mại cho checkpoint. Cần quyền phù hợp
trước khi dùng giọng tạo ra cho nội dung kiếm tiền, quảng cáo hoặc khách
hàng. [Model card đã pin](https://huggingface.co/k2-fsa/OmniVoice/blob/c5fdb5ccb189668d56333f77ba2629f4cd7535f4/README.md).

## Trạng thái nghiệm thu

Xem [báo cáo build](installer-build-report-2026-10-04.vi.md) và
[quy trình miễn phí](windows-release-setup.vi.md). Hiện chưa xác nhận
installer public/GitHub update end-to-end hoặc mọi pipeline AI frozen trên
VM sạch. Không tải installer DEVELOPMENT lên làm stable Latest.
