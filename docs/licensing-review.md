# Rà soát giấy phép HaizFlow

Ngày 01/10/2026, Mạch Hồng Hải đã duyệt chuyển phần mã HaizFlow thuộc sở hữu
sang [HaizFlow Source-Available 1.0](../LICENSE). Giấy phép và [NOTICE](../NOTICE)
đặt tiếng Việt trước tiếng Anh; tiếng Việt được ưu tiên khi bản dịch khác nhau.
Đây là quyết định của chủ sở hữu, không phải xác nhận pháp lý của luật sư hay
chứng nhận bản phát hành đủ điều kiện phân phối.

HaizFlow do Mạch Hồng Hải phát triển. Owner xác nhận chỉ có một người phát triển;
không thêm thông báo chung về “HaizFlow contributors” cho phần mã ứng dụng.
Git identity/contact phù hợp thông tin user nhưng không chứng minh quyền đối
với tài sản nhập từ ngoài. Không rewrite Git history hay xóa thông báo hợp lệ
của Evil0ctal, Microsoft, Bangers, thư viện, codec hoặc model.

## Phạm vi

[Rights inventory](../legal/rights-inventory.json) ghi source/scripts/installer/
docs/tests thuộc phạm vi ứng dụng chủ sở hữu xác nhận. Vendor, icons, fonts,
branding/voice do chủ dự án xác nhận quyền phân phối (chưa xác minh độc lập) và runtime binaries được loại khỏi
giấy phép ứng dụng. Mã nguồn công khai không có nghĩa mọi thành phần thuộc
sở hữu độc quyền. Quyền được cấp độc lập và ngoại lệ bắt buộc vẫn được áp dụng.

Giấy phép cho phép dùng miễn phí, xem/clone/build và sửa cá nhân/nội bộ; tạo
video thương mại trong phạm vi quyền về nội dung/model/giọng user có. Không
mặc định cho phép phân phối, bán, đóng gói lại, rebrand hoặc sublicense phần
mềm. App không sở hữu đầu ra của user. Điều kiện NC của model không bị ghi đè.

Bản đề xuất source EN trước đây được lưu để đối chiếu lịch sử, không phải bản
hiện hành. Các bản Application Terms, Contributor Permission và Brand Policy
còn DRAFT — NOT IN FORCE; không coi duyệt source license là chấp thuận CLA
hoặc chuyển nhượng quyền tự động.

## Hồ sơ rà soát đóng gói 06/10/2026

| Phạm vi | Bằng chứng và giới hạn |
| --- | --- |
| Mã ứng dụng | [Phạm vi chủ dự án xác nhận](../legal/reviews/application-scope-2026-10-06.md); giữ quyền đã cấp và thông báo độc lập. Không xác minh độc lập mọi quyền sở hữu. |
| OmniVoice và preview | [Xác nhận trực tiếp của chủ dự án](../legal/reviews/owner-assets-and-omnivoice-2026-10-04.md); giữ checkpoint phi thương mại, công khai giới hạn. Không cấp thêm quyền thương mại. |
| FFmpeg | [Hồ sơ nguồn và cấu hình](../legal/reviews/media-source-2026-10-06.md): CLI GPL riêng; backend PyAV được thay bằng bản shared LGPL, không x264/x265; nguồn đầy đủ cùng recipe và inventory. |
| Qt/PySide | [Hồ sơ module và thay thư viện](../legal/reviews/qt-replacement-2026-10-06.md): dynamic LGPL, nguồn/thông báo đi kèm và đường chạy Core không cần khóa nhà phát hành. Không khẳng định mọi DLL tự biên dịch đều tương thích ABI. |

Đây là rà soát kỹ thuật của Codex dựa trên tài liệu gốc, dữ liệu đóng gói và
quyền phát hành chủ dự án đã yêu cầu; không phải tư vấn hay chứng nhận của luật
sư. Nguồn thư viện phải được tải lên cùng kênh tải binary trước khi phát hành
công khai. Kiểm checksum ZIP cục bộ không chứng minh URL đã công khai.

[Third-party inventory](../THIRD_PARTY_NOTICES.md) phân biệt Core, engines,
models và assets. Notice generator chứng minh có văn bản, không chứng minh
license compatibility. Không gỡ model/library để giả vờ vượt compliance.

## Đồng bộ code và đóng gói

legal/license-state.json ghi approved-by/date/basis, language precedence vi,
active license/hash và scope. scripts/verify-legal-state.py kiểm tra hash,
metadata, owner approval, VI-before-EN và packaged source documents. Public
gate vẫn chặn khi thiếu explicit review/clearance evidence; license approval
không tự xóa blocker. Dependency lock chỉ cập nhật input hash, không đổi phiên
bản package.

About chỉ có giới thiệu/liên hệ/donate. Bản quyền là dialog riêng được mở từ
menu Cài đặt hoặc dấu ? (Giới thiệu/Bản quyền). NOTICE giữ tên duy nhất của
tác giả ứng dụng và các component notices hợp lệ riêng. Installer hiện tại
vẫn đọc LICENSE.txt được copy từ root LICENSE, không trỏ đến draft terms.

Ghi chú lịch sử: khi lập review ban đầu, updater mới là source-only. Đến
2026-10-04 đã có nghiệm thu delta/health/rollback với Core frozen unsigned,
installer DEVELOPMENT thực và chế độ build public `UnsignedRelease` giữ
legal/resource/provenance gate. Xem [báo cáo build hiện tại](installer-build-report-2026-10-04.vi.md).
Không suy ra binary đã được duyệt phát hành chỉ từ các test này.

Chủ dự án đã xác nhận quyền phân phối branding/mẫu preview và chọn giữ
checkpoint OmniVoice với giới hạn phi thương mại. Ghi nhận trực tiếp tại
[hồ sơ xác nhận](../legal/reviews/owner-assets-and-omnivoice-2026-10-04.md).
Xác nhận này không tự giải quyết hồ sơ FFmpeg/Qt hoặc cấp quyền thương mại
cho checkpoint. Hướng dẫn người dùng đã công khai giới hạn này.

## Primary references / English summary

The owner approved Source-Available 1.0 for owned application work on
2026-10-01. Vietnamese precedes English and prevails on translation differences.
Independent third-party rights and mandatory exceptions remain applicable. Application
terms/CLA/brand drafts remain inactive. Scoped technical review records now
cover the owned application scope, owner-attested assets/NonCommercial choice,
native media source closure and Qt replacement mechanism. These records are
not independent legal certification. Source assets must be available alongside
the released binaries; a locally valid ZIP is not a published release.

- [GitHub Terms of Service](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service): public viewing/fork rights.
- [OSI definition](https://opensource.org/osd): public source is not sufficient for open source.
- [Qt LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations).
- [FFmpeg legal](https://ffmpeg.org/legal.html).
- [Pinned OmniVoice model card](https://huggingface.co/k2-fsa/OmniVoice/blob/c5fdb5ccb189668d56333f77ba2629f4cd7535f4/README.md).
- [PyInstaller license exception](https://pyinstaller.org/en/stable/license.html).

Prior audit verification (before activation): 1002 pytest cases +96 subtests,
51 Qt Quick tests, lint and license inventory checks. These are historical
results, not certification of this new change. Current updater results and
packaging limits are recorded in [updates](updates.md) and
[packaging todo](updater-packaging-todo.md).
