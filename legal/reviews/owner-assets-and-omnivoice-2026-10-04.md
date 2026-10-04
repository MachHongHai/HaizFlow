# Xác nhận tài sản và lựa chọn OmniVoice — 2026-10-04

Đây là ghi nhận lời xác nhận trực tiếp của chủ dự án, không phải xác minh
độc lập quyền sở hữu, tư vấn pháp lý hoặc duyệt toàn bộ binary release.

## Tài sản đi kèm

Chủ dự án được hỏi có quyền phân phối các mẫu giọng preview và tài sản
branding đang đi kèm ứng dụng hay không, trước khi đưa chúng lên release
công khai. Câu trả lời trực tiếp: **“Có, tôi có quyền phân phối”**.

Phạm vi: `src/haizflow/desktop/assets/voice_samples` và
`src/haizflow/desktop/assets/branding` tại thời điểm xác nhận. Không suy ra
quyền đối với tài sản người dùng nhập, bên đóng góp chưa xác nhận hoặc
mọi phiên bản/tài sản bổ sung sau này. Giấy phép độc lập của vendor, icon,
font, runtime và model vẫn giữ nguyên.

## Checkpoint OmniVoice

Chủ dự án được thông báo checkpoint đang dùng có điều kiện NonCommercial,
và được chọn giữa giữ kèm thông báo hoặc không phát hành tính năng phụ
thuộc checkpoint. Câu trả lời trực tiếp: **“Giữ và công khai giới hạn phi
thương mại”**.

Model card tại revision `c5fdb5ccb189668d56333f77ba2629f4cd7535f4`
phân biệt code Apache-2.0 với pretrained model CC-BY-NC. Giấy phép source
HaizFlow và việc dùng ứng dụng miễn phí không ghi đè điều kiện checkpoint.
Không coi lựa chọn này là cấp quyền dùng model/giọng tạo ra cho mục đích
thương mại. Người dùng cần quyền phù hợp trước khi sử dụng thương mại.

[Model card đã pin](https://huggingface.co/k2-fsa/OmniVoice/blob/c5fdb5ccb189668d56333f77ba2629f4cd7535f4/README.md).

## Những việc xác nhận này không giải quyết

Không tự xác nhận corresponding source của FFmpeg và các thư viện static,
nghĩa vụ source/replacement/relinking của Qt/PySide, các điều kiện riêng
của dependency hoặc nghiệm thu installer/update qua GitHub. Public release
gate vẫn phải có hồ sơ rà soát đầy đủ cho đúng phiên bản và artifact.
