<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# n8n: biên nhận hồ sơ đã duyệt

`bidweave-approved-sync.json` là workflow do BidWeave viết để tích hợp với n8n `2.43.6`. Nó **không duyệt hồ sơ**. Nó đọc bản đã duyệt rồi ghi một comment biên nhận nội bộ, bằng API có kiểm tra revision ở bước ghi cuối cùng.

## Khởi tạo

```bash
make demo
```

Hoặc sau khi đã khởi động đủ profile:

```bash
make up-all
make integrations
```

Script nhập workflow, publish ID `BidWeaveApprovedSync`, restart n8n và chờ readiness. Dữ liệu/khóa mã hóa n8n nằm trong volume riêng và `.env` riêng. Không commit khóa. Không cần mở editor để thực hiện workflow đã được publish.

## Luồng thực thi

1. Trong tab **D**, coordinator chọn **Gửi biên nhận qua n8n** cho revision hiện hành đã duyệt.
2. API gọi `POST /webhook/bidweave-approved` của n8n nội bộ, body có `case_id` và `expected_revision`. Token ngắn hạn đi qua **Authorization header**, không nằm trong body hoặc đối số LLM.
3. n8n đọc hồ sơ qua API, kiểm tra trạng thái và revision.
4. n8n gọi `/api/cases/{id}/automation/receipt-record`. API khóa hồ sơ và kiểm tra **lại** revision + approval trong cùng transaction trước ghi comment/audit. Nếu có sửa đổi xen giữa bước đọc và ghi, API trả 409; không ghi receipt cho nhầm revision.
5. Phản hồi chỉ được coi là thành công khi API kiểm tra comment thật đã tồn tại trong đúng case/tenant. Workspace tải lại dữ liệu để receipt xuất hiện trong tab **H**.

Receipt chỉ nói có phiên bản đã được phê duyệt tại thời điểm ghi. **Không phải bằng chứng đã gửi email, nộp hồ sơ lên hệ thống đấu thầu hoặc có chữ ký số.** Gọi lại có thể tạo thêm comment; không tuyên bố exactly-once. Cấu hình n8n không giữ execution payload thành công/thất bại và không bật lưu execution tiến trình, nhằm hạn chế lưu token trong lịch sử.

## Giấy phép

Workflow JSON gốc: Apache-2.0, với `.license` đi kèm. Phần mềm n8n Community: **Sustainable Use License, không OSI-approved**. Đây là profile tích hợp độc lập, tùy chọn; Flowable Apache-2.0 vẫn là engine bắt buộc của nền tảng. Tách container không thay thế việc tuân thủ SUL hoặc quyết định chấm giấy phép của BTC. Xem [bảng giấy phép](../docs/licensing.md).
