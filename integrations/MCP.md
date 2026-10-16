<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# MCP dùng danh tính người gọi

Server `services/mcp/server.py` sử dụng official MCP Python SDK với Streamable HTTP. Endpoint qua gateway: `http://localhost:8090/mcp`; địa chỉ nội bộ là `http://mcp:8001/mcp`.

Client cần gửi token OIDC hợp lệ trong **HTTP `Authorization: Bearer …`**. Không truyền token qua prompt, URL, đối số công cụ hay một token admin dùng chung. Token được lấy trong ngữ cảnh của từng request rồi chuyển tới API, nơi kiểm tra lại tenant/quyền. Client cần hỗ trợ HTTP headers; server không cung cấp đường vòng bằng `bearer_token`.

| Công cụ | Dữ liệu và tác động |
| --- | --- |
| `read_case(case_id)` | Yêu cầu, trạng thái, metadata minh chứng, lịch sử theo tenant |
| `read_evidence(case_id)` | Metadata, không trả byte tài liệu |
| `read_impact(case_id)` | Thay đổi của revision hiện hành và công việc |
| `propose_tasks(case_id, expected_revision)` | Bản đề xuất việc còn thiếu; không ghi database |
| `propose_revision(case_id, expected_revision, reason, requirement_keys)` | Phạm vi rà soát dựa trên key có thật; người dùng sửa/lưu trong editor |
| `submit_for_review(case_id, expected_revision)` | Lệnh ghi duy nhất: gửi xét duyệt qua API, vẫn cần coordinator và đủ minh chứng |

Không có công cụ duyệt, shell, SQL tùy ý hoặc đọc tệp hệ thống. Các đề xuất không phải bằng chứng đã hoàn thành thao tác. Chat trong workspace dùng MCP để lấy ngữ cảnh, không tự thực hiện công cụ ghi.

## Kiểm tra

```bash
make demo
make smoke
make intelligence
```

`scripts/llm-smoke.py` dùng SDK thật để initialize/list/call, kiểm tra việc không có quyền duyệt, trường token không xuất hiện trong schema công cụ và truy cập chéo tenant bị từ chối. Nó còn gọi model Ollama thật; nếu model không chạy, kiểm tra phải lỗi thay vì trả câu trả lời giả. Xem [bằng chứng](../docs/verification.md) để biết chính xác đường đi nào đã được thực hiện.

MCP SDK là dependency nguồn mở riêng, không phải giao thức do BidWeave phát minh. Khi tích hợp một client/Agent bên ngoài, phải cấu hình cơ chế cấp token và kiểm tra chính sách lưu hội thoại của client đó; MCP không tự bảo đảm client giữ bí mật.
