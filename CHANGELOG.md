<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# Changelog

Các thay đổi đáng chú ý được ghi theo phiên bản. Nội dung phản ánh tính năng và kiểm chứng đã thực hiện, không bảo đảm điểm thi, giải thưởng hay khả năng vận hành production.

## 1.0.0 — 2026-10-16

### Tính năng

- Nền tảng headless: Keycloak/OIDC, Apache APISIX, PostgreSQL, SeaweedFS, ClamAV và workflow phê duyệt Flowable build từ nguồn.
- Hồ sơ dự thầu với yêu cầu theo phiên bản, minh chứng có hash, xác minh độc lập, phân quyền theo tenant/vai trò, xét duyệt và xuất gói của phiên bản hiện tại đã được duyệt.
- Phân tích tác động khi đổi ngưỡng/hạn/yêu cầu: giữ lịch sử, không tái sử dụng phê duyệt hoặc xác minh cũ một cách ngầm định; hỗ trợ từ chối và gửi lại.
- Workspace tiếng Việt đủ H–P–D–I: nhóm, nhiệm vụ, trao đổi, inbox quy trình, kiểm tra độ đầy đủ, tìm kiếm, thống kê, lịch sử, truy nguồn và Agent.
- LLM cục bộ qua Ollama: trả lời có nguồn và trích xuất yêu cầu thành bản nháp cần kiểm tra. MCP có sáu công cụ giới hạn quyền; không có công cụ tự phê duyệt hoặc chạy shell tùy ý.
- Liên kết metadata TED; RDF/JSON-LD theo phiên bản; Fuseki tùy chọn, NATS JetStream/outbox, lịch sử Parquet truy vấn bằng DuckDB.
- n8n tùy chọn với webhook và biên nhận idempotent. Sustainable Use License được công bố riêng, không gắn nhãn n8n là OSI-approved.
- Chuỗi kiểm toán có hash, OpenTelemetry/Prometheus cục bộ và backup/restore riêng tư của database, volume và cấu hình.
- Landing tĩnh cho GitHub Pages, giao diện mobile, 11 ảnh chụp thực tế, hướng dẫn chạy/sử dụng và ma trận ba tầng/bảy lớp.

### Sửa lỗi qua kiểm chứng tích hợp

- Kiểm tra lại phiên bản tại giao dịch ghi biên nhận n8n, tránh ghi vào hồ sơ đã đổi trong lúc xử lý callback.
- Hiển thị lỗi chỉnh sửa ngay trong dialog; cập nhật bình luận sau khi nhận biên nhận workflow.
- Sửa healthcheck theo công cụ thực sự có trong container APISIX; dùng DNS Docker với thời gian làm mới ngắn khi upstream đổi IP.
- Đóng gói BPMN từ một tài nguyên classpath duy nhất cho cả Maven và Docker.
- Sửa bước khởi động lại dịch vụ sau cold backup; chạy thật cả backup, kiểm tra và restore.
- SBOM nhận diện thành phần shaded trong JAR, giữ nguyên thông tin giấy phép chưa rõ và đáp ứng kiểm tra cấu trúc SPDX 2.3.

### Chất lượng nguồn mở và phát hành

- Apache-2.0 cho mã tự viết; SPDX header hoặc sidecar phù hợp định dạng; LICENSE/NOTICE và danh mục license/dependency riêng.
- CI kiểm tra header/REUSE, regression tests, frontend, Java build, source archive, SPDX và checksum.
- Quy trình issue, branch và PR; biểu mẫu báo lỗi/đề xuất, hướng dẫn đóng góp, hỗ trợ, bảo mật và CODEOWNERS.
- Source release `.tar.gz` loại trừ bí mật/runtime/dependency cài sẵn; kèm hai SPDX SBOM, inventory và SHA256SUMS.
- Đã kiểm chứng luồng SSO → minh chứng → duyệt R1 → sửa R2 → xác minh lại → duyệt → xuất gói; model thật, đủ sáu công cụ MCP, quét EICAR và backup/restore. Chi tiết và giới hạn tại [biên bản kiểm chứng](docs/verification.md).
