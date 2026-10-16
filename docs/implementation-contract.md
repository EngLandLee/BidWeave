<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Hợp đồng API và các bất biến

Mã thực thi: `services/api/bidweave/`, schema Pydantic ở `schemas.py`, client typed ở `apps/web/src/api.ts`. Đây là hợp đồng của sản phẩm, không phải chỉ dẫn nội bộ cho công cụ sinh mã.

## Danh tính và cách ly

- Workspace dùng OpenID Connect Authorization Code + PKCE của Keycloak, token trong bộ nhớ, không lưu mật khẩu.
- Gateway kiểm tra token; API kiểm tra lại chữ ký RS256, issuer, audience, thời hạn và claim cần thiết. `tenant_id` lấy từ danh tính đã xác thực, không nhận từ body để quyết định phạm vi.
- Các đường dẫn `/api/*` cần Bearer token, trừ `/api/health`. Không tìm thấy hồ sơ trong tenant trả 404, không tiết lộ tenant khác có hồ sơ hay không.
- `coordinator`, `contributor`, `reviewer` là vai trò mẫu. API là nơi quyết định quyền, không dựa vào việc UI ẩn nút.
- Flowable, S3, DB, Ollama, Fuseki và collector chỉ hoạt động trên mạng nội bộ Compose.

## Vòng đời

Hồ sơ bắt đầu ở `draft`, revision 0 chưa có yêu cầu. Tạo yêu cầu sinh R1. Mỗi sửa đổi tiếp theo tạo revision mới, không sửa đè requirement của revision cũ.

- Các lệnh sửa revision, tải/xác minh minh chứng, submit, review và receipt nhận `expected_revision`. Sai phiên bản trả 409, không tự sửa sang phiên bản mới nhất.
- Gửi duyệt chỉ được khi các yêu cầu bắt buộc có minh chứng **đã xác minh của revision hiện hành** đáp ứng ràng buộc.
- Loại `count`: cộng số lượng từ các nội dung có hash khác nhau; tải lặp cùng byte không làm tăng số lượng.
- Loại `validity`: hiệu lực phải bao phủ hạn nộp của revision. `document`/`text` cần xác nhận của người có quyền; máy không tự chứng nhận tính đúng của nội dung pháp lý.
- Người tải không tự xác minh tệp; người tạo/gửi không tự duyệt hồ sơ.
- Submit tạo instance Flowable. Review hoàn tất task và đối chiếu lịch sử engine với đúng case, tenant, revision, người duyệt và quyết định trước khi ghi trạng thái nghiệp vụ.
- `approve` → `approved`; `reject` → `draft`, có thể gửi lại bằng instance mới. Sửa đổi khi đang duyệt hủy instance cũ và ghi nhận bị thay thế.
- Sau sửa đổi, quyết định cũ chỉ là lịch sử. Minh chứng cũ muốn dùng lại phải được reviewer xác nhận cho revision mới; hệ thống tạo bản ghi mới thay vì đổi dấu xác nhận cũ.
- Chỉ revision hiện hành đã được duyệt mới được export. Một bộ hồ sơ xuất trước khi có sửa đổi không tự biến thành bản hiện hành sau đó.

## Các endpoint chính

Base URL trong demo: `http://localhost:8090`. Các path dưới đây bao gồm tiền tố `/api`.

| Nhóm | Endpoint | Hành vi |
| --- | --- | --- |
| Danh tính | `GET /api/me` | Danh tính, tenant và vai trò của token |
| Hồ sơ | `GET, POST /api/cases`; `GET /api/cases/{id}` | Danh sách theo tenant; tạo hồ sơ; toàn bộ trạng thái hiện hành và lịch sử |
| Sửa đổi | `POST /api/cases/{id}/revisions` | `expected_revision`, `deadline`, `reason`, `requirements`; kiểm tra key duy nhất và ràng buộc trước hủy workflow cũ |
| Tệp | `POST /api/cases/{id}/evidence` | Multipart: `file`, `requirement_key`, `expected_revision`, `quantity`/`valid_until`/`notes` nếu có; ClamAV và S3 thật |
| Xác minh | `POST /api/cases/{id}/evidence/{evidence_id}/verify` | Reviewer độc lập, đúng revision; phản hồi chi tiết hồ sơ |
| Đọc tệp | `GET /api/cases/{id}/evidence/{evidence_id}/download` hoặc `/preview` | Tenant check; preview có giới hạn, không tải URL do người dùng tùy ý chỉ định |
| Duyệt | `POST /api/cases/{id}/submit`; `POST /api/cases/{id}/review` | Review có `decision: approve/reject`, `comment`, `expected_revision` |
| Xuất | `GET /api/cases/{id}/export?revision=N` | Gói gzip tar, manifest và SHA-256; 409 nếu cũ/chưa duyệt |
| Cộng tác | `POST /api/cases/{id}/comments`; `PATCH /api/cases/{id}/tasks/{task_id}` | Trao đổi, nhận/giao việc, trạng thái `open/done`; không tự xác nhận requirement |
| Phân tích | `GET /api/analytics`; `GET /api/cases/{id}/history` | Tổng hợp tenant hiện hành và snapshot được truy vấn bằng DuckDB |
| Liên kết | `GET /api/lod/notices?date=YYYY-MM-DD&cpv_prefix=72` | SPARQL cố định có tham số kiểm tra tới TED; không nhận truy vấn tùy ý |
| Metadata | `POST /api/cases/{id}/notices` | Gắn notice, URI và nguồn vào bản nháp; không sửa metadata của bản đã duyệt |
| Đồ thị | `GET /api/cases/{id}/lineage`; `POST /api/cases/{id}/lineage/publish` | JSON-LD; coordinator ghi named graph vào Fuseki |
| Quản trị | `GET /api/search/requirements?q=...`; `GET /api/audit/verify` | Full-text yêu cầu hiện hành theo tenant; coordinator kiểm tra liên kết/hash audit |
| Automation | `POST /api/cases/{id}/automation/receipt` | Coordinator gọi workflow n8n; revision phải đang được duyệt |
| Callback | `POST /api/cases/{id}/automation/receipt-record` | Kiểm tra lại approval + revision trong transaction có khóa trước ghi comment; không tin kết quả GET trước đó của n8n |
| AI | `GET /api/agent/status`; `POST /api/agent/chat`; `POST /api/agent/extract` | Availability thật, chat có nguồn, multipart PDF/text thành bản nháp cần review |

OpenAPI được sinh bởi FastAPI ở `/openapi.json` của container API nội bộ. Gateway không mở riêng Swagger cho người dùng cuối.

## Trích xuất và MCP

`/agent/chat` nhận `case_id` và `message`. Ngữ cảnh được lấy theo quyền qua MCP; danh sách source ID bị giới hạn vào dữ liệu đã truy xuất. Cấu trúc JSON hợp lệ không chứng minh câu trả lời đúng; người dùng vẫn phải đối chiếu nguồn.

`/agent/extract` quét tệp rồi đọc text/PDF bằng pypdf, giới hạn 10 MB, 40 trang PDF và 24.000 ký tự ngữ cảnh. PDF scan không có text phải OCR trước bằng công cụ của người dùng; không có OCR/Docling ngầm hoặc dữ liệu giả. Model phải trả requirement có key duy nhất, nguồn hợp lệ và ngưỡng số lượng khi chọn `count`. Kết quả luôn cần review, không tự lưu revision.

MCP Streamable HTTP ở `http://localhost:8090/mcp`, dùng official Python SDK. **Chỉ nhận token qua HTTP Authorization header**, không qua tham số công cụ hoặc token quản trị dùng chung.

| Công cụ | Tác động |
| --- | --- |
| `read_case`, `read_evidence`, `read_impact` | Đọc metadata theo quyền; không đưa byte minh chứng qua công cụ đọc metadata |
| `propose_tasks` | Đề xuất việc còn thiếu, không ghi task |
| `propose_revision` | Đề xuất phạm vi rà soát theo requirement key hiện có, không ghi revision |
| `submit_for_review` | Gửi đúng revision tới workflow; cần quyền coordinator và đủ minh chứng |

Không có công cụ approve, SQL tùy ý hoặc shell. LLM chat không tự gọi công cụ ghi. Chi tiết cấu hình client: [MCP](../integrations/MCP.md).

## Nhất quán, lỗi và phạm vi bảo đảm

- 401: không có danh tính hợp lệ; 403: không đủ quyền/vi phạm độc lập; 404: không nhìn thấy tài nguyên; 409: revision/trạng thái xung đột; 422: đầu vào không hợp lệ; 503: dependency không khả dụng hoặc chưa xác nhận kết quả.
- PostgreSQL là nguồn trạng thái nghiệp vụ; transaction outbox chuyển sự kiện qua NATS. Snapshot/graph là projection, có thể trễ; không dùng chúng để thay quyết định phê duyệt trong database.
- PostgreSQL, Flowable, S3 và NATS không có một distributed transaction chung. Mã giữ các kiểm tra phiên bản, khóa hồ sơ, đối chiếu workflow history và publication idempotent; không tuyên bố exactly-once hoặc không bao giờ lỗi giữa các dịch vụ.
- Chuỗi audit phát hiện sửa byte/liên kết trong bản đang giữ. Không có checkpoint tin cậy độc lập hoặc chữ ký pháp lý, nên không gọi là sổ cái bất biến/chống chối bỏ.
- Receipt n8n là comment đồng bộ nội bộ, không chứng minh đã gửi email hay nộp thành công trên một cổng đấu thầu.
