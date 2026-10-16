<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# Kiến trúc: ba tầng, bảy lớp, bốn không gian

**Ba tầng sản phẩm không phải bảy lớp chức năng.** Bảy lớp là các nhóm năng lực xuyên qua ba tầng; H–P–D–I là bốn không gian của tầng 2. Không tính số container để chứng minh đáp ứng đề.

## Ba tầng

| Tầng | Phần chạy trong BidWeave | Ranh giới mã nguồn |
| --- | --- | --- |
| **1 — Nền tảng lõi headless** | Keycloak Identity/SSO, APISIX API Gateway, PostgreSQL và SeaweedFS S3, Flowable BPMN; thêm ClamAV, NATS, Fuseki, Ollama và quan sát hệ thống | Dịch vụ upstream giữ giấy phép riêng. `infra/`, `compose.yaml`, `services/workflow` và các adapter nối API. Không có UI nghiệp vụ ở tầng này; màn hình đăng nhập/quản trị upstream không phải portal nghiệp vụ. |
| **2 — Không gian năng lực H–P–D–I** | Workspace React, đăng nhập PKCE, điều hướng, trạng thái tải/lỗi/rỗng, vai trò; giao diện cộng tác, quy trình, dữ liệu và Agent | `apps/web`. Giao diện không quyết định quyền hay tính hợp lệ của phê duyệt; backend kiểm tra lại mọi thao tác. |
| **3 — Ứng dụng nghiệp vụ dự thầu** | Hồ sơ, phiên bản yêu cầu, minh chứng, tác động sửa đổi, đối soát, xét duyệt và gói xuất | `services/api/bidweave/domain.py`, các route nghiệp vụ, `projections.py`, cấu hình BPMN và các view hồ sơ trong workspace. Quy tắc dự thầu không viết vào Keycloak/APISIX/PostgreSQL/Flowable upstream. |

Tầng 1 và tầng 3 tách trách nhiệm nhưng một số adapter/router cùng được triển khai trong API Python. Đây không phải ba microservice bắt buộc hay cơ chế cài plugin nóng. Ứng dụng khác có thể dùng lại SSO, gateway, S3, PostgreSQL và engine quy trình mà không sao chép UI dự thầu.

## Bảy lớp chức năng tham chiếu

| Lớp | Triển khai thật | Bằng chứng và giới hạn |
| --- | --- | --- |
| **1. Trải nghiệm & Giao diện đa kênh** | Landing page và workspace web responsive; API/MCP cho client ngoài | Web desktop/mobile, điều hướng bàn phím, OIDC PKCE. Không có ứng dụng mobile native hoặc bot Telegram được tuyên bố là đã triển khai. |
| **2. Biên mạng, Cửa ngõ & An toàn thông tin** | APISIX định tuyến/OIDC/rate limit; API kiểm JWT, tenant và role; ClamAV quét trước khi lưu | Thiếu token 401; sai vai trò 403; tài nguyên tenant khác 404. Bí mật sinh ngẫu nhiên trong cấu hình riêng, không phải một triển khai Vault/HSM. |
| **3. Tác nghiệp, Logic & Trạng thái thực thể** | PostgreSQL, mô hình case/revision/requirement/evidence/task/approval; quy tắc số lượng và hiệu lực xác định | `expected_revision` và khóa bản ghi chặn ghi trên phiên bản cũ. LLM không quyết định trạng thái đáp ứng. |
| **4. Tự động hóa, Quy trình & DevSecOps** | Flowable giữ tiến trình duyệt; n8n thực hiện connector biên nhận; Docker source build, CI, nhánh và PR | API đối chiếu lịch sử quyết định từ Flowable. n8n phải gọi endpoint ghi có khóa phiên bản; không tự phê duyệt. Không tuyên bố đã triển khai Kubernetes/ArgoCD. |
| **5. Dữ liệu siêu hội tụ, Truyền phát & Sổ cái** | PostgreSQL + SeaweedFS; transactional outbox → NATS JetStream; lịch sử DuckDB/Parquet; nhật ký nối băm SHA-256 | Object gốc có hash; snapshot gắn phiên bản; sự kiện chỉ đánh dấu gửi sau khi nhận ACK. Chuỗi băm phát hiện sai lệch, **không** chống được quản trị viên viết lại toàn bộ dữ liệu; không gọi nó là blockchain/chữ ký số. |
| **6. Phục vụ Phân tích, Không gian & Trí tuệ** | Tổng hợp tiến độ/đáp ứng; DuckDB; Ollama Qwen; đọc PDF/text, schema output và nguồn; công cụ MCP giới hạn | Chat chỉ nhận metadata trong quyền, không nội dung toàn bộ minh chứng. Không có dữ liệu địa lý cần phân tích trong bài toán này; không dựng màn hình bản đồ giả để điền một ô. |
| **7. Quản trị, Tìm kiếm & Giám sát hệ thống** | PostgreSQL full-text theo tenant/phiên bản hiện tại; JSON-LD/PROV/CCCEV; Fuseki; kiểm chuỗi audit; OpenTelemetry và Prometheus | Có thể truy ngược yêu cầu–minh chứng–phiên bản–quyết định. Metrics tổng toàn hệ thống nằm ở đường nội bộ, không mở qua API người dùng. Không gọi full-text là vector search. |

Các tên lớp trên bám khung tham chiếu trong đề. Việc không cài mọi sản phẩm được đề nêu là lựa chọn triển khai, không phải một xác nhận miễn yêu cầu từ BTC. Đối chiếu yêu cầu bắt buộc tại [contest.md](contest.md).

## H–P–D–I trong cùng một hồ sơ

| Không gian | Việc người dùng làm | Quy tắc không được bỏ qua |
| --- | --- | --- |
| **H — Con người** | Nhận việc, đánh dấu tiến độ, trao đổi, bàn giao cho người xét duyệt | Đánh dấu việc xong không tự làm minh chứng hợp lệ. |
| **P — Quy trình** | Soạn yêu cầu, tạo sửa đổi, gửi duyệt, yêu cầu sửa hoặc chấp thuận | Không tự xác minh tệp do mình tải lên; không tự duyệt hồ sơ mình tạo/gửi. Phê duyệt chỉ gắn một phiên bản. |
| **D — Dữ liệu** | Đọc/tải minh chứng, kiểm hash/hiệu lực, tra TED, tìm yêu cầu, xem đồ thị và snapshot, xuất gói | Tạo sửa đổi phải xác nhận lại minh chứng; gói xuất chỉ dùng phiên bản hiện tại đã duyệt. Dữ liệu nội bộ không công khai theo dữ liệu TED. |
| **I — Trí tuệ** | Hỏi trên metadata, trích yêu cầu đề xuất, đưa bản nháp sang trình soạn để kiểm tra | Mô hình có thể sai; `needs_review` không được đổi thành chứng nhận tuân thủ. MCP không có công cụ phê duyệt hay shell/SQL tùy ý. |

## Luồng quyết định

Người đóng góp tải tệp → ClamAV → S3 + metadata/hash → người khác xác nhận → bộ quy tắc kiểm đáp ứng → coordinator gửi đúng revision → Flowable tạo tác vụ → reviewer độc lập quyết định → API đối chiếu lịch sử engine → ghi phê duyệt/outbox → lịch sử và sự kiện → xuất gói đúng revision.

Nếu có sửa đổi: tăng revision, giữ nguyên lịch sử cũ, tạo tác động/công việc mới, bỏ trạng thái sẵn sàng cũ. Nếu sửa đổi xảy ra trong lúc xét duyệt, tiến trình cũ bị hủy; yêu cầu ghi cũ không được âm thầm áp dụng vào phiên bản mới.

## Liên kết dữ liệu và mô hình tin cậy

TED được truy vấn trực tiếp bằng SPARQL theo eProcurement Ontology. JSON-LD nội bộ dùng URI ổn định, PROV cho nguồn gốc, CCCEV cho minh chứng và [vocabulary do dự án định nghĩa](../apps/web/public/vocab.jsonld). Hồ sơ phản hồi nội bộ không bị gán nhầm thành thủ tục mua sắm của bên mời thầu. Named graph trong Fuseki là riêng theo tenant/case; URL định danh graph không có nghĩa là dữ liệu đó được công bố trên Internet.

Keycloak là nguồn danh tính, Flowable là nguồn tiến trình, PostgreSQL/S3 là nguồn trạng thái/bytes. Snapshot và đồ thị là bản chiếu; LLM là người đề xuất không có thẩm quyền. n8n giữ vai trò connector tùy chọn, không thay thế workflow lõi nguồn mở.
