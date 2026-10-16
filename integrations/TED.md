<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Dữ liệu mở liên kết TED

`GET /api/lod/notices?date=YYYY-MM-DD&cpv_prefix=72` truy vấn SPARQL thật tại `https://publications.europa.eu/webapi/rdf/sparql`. Truy vấn được viết cố định trong `services/api/bidweave/intelligence.py`, có kiểm tra định dạng ngày/CPV, giới hạn kết quả và timeout. Người dùng không gửi SPARQL hoặc URL tùy ý.

Ví dụ đã dùng cho demo: ngày `2024-11-04`, CPV prefix `72`. Số kết quả có thể thay đổi theo nguồn. Khi endpoint ngoài lỗi, API trả lỗi rõ ràng; không dùng bản ghi tổng hợp rồi gọi đó là dữ liệu live.

Tab D hiển thị publication number, CPV, source graph và thời điểm thu thập. Coordinator có thể liên kết notice vào **bản nháp** của hồ sơ. Việc gắn metadata không có nghĩa là đội đang tham dự gói thầu đó, hoặc nội dung hồ sơ nội bộ trùng với hồ sơ mời thầu chính thức.

JSON-LD nối hồ sơ `bw:BidCase` tới notice/nguồn TED bằng URI và provenance. Không gán hồ sơ dự thầu nội bộ thành `epo:Procedure`. Từ vựng riêng được công bố tại <https://englandlee.github.io/BidWeave/vocab.jsonld>; đồ thị cụ thể chứa yêu cầu, người dùng và minh chứng vẫn là **dữ liệu riêng theo tenant**. Named graph trong Fuseki không được xuất ra Internet.

Nguồn tham khảo chính:

- [TED Open Data](https://data.ted.europa.eu/)
- [eProcurement Ontology](https://docs.ted.europa.eu/EPO/latest/index.html)
- [EU Publications Office reuse policy](https://op.europa.eu/en/web/about-us/legal-notices)

Quyền tái sử dụng metadata, điều kiện của ontology và quyền đối với toàn văn tài liệu không giống nhau. Hồ sơ người dùng tải lên không tự trở thành open data. Xem [giấy phép và dữ liệu](../docs/licensing.md).
