<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# Biên bản kiểm chứng

**Ngày thực hiện: 16/10/2026.** Đây là kết quả quan sát trên máy Linux chạy Docker Compose, không phải chứng nhận an toàn thông tin, kết quả chấm thi hay cam kết triển khai production. Dữ liệu demo là dữ liệu tổng hợp; không công khai tài khoản, token, bản sao lưu hoặc hồ sơ khách hàng.

## 1. Luồng nghiệp vụ chạy thật

Lệnh `make smoke` chạy qua gateway, Keycloak, API, PostgreSQL, SeaweedFS, ClamAV và Flowable; không thay các dịch vụ này bằng mock.

- Lần chạy ghi nhận lúc **2026-10-16T04:52:31.386182+00:00**, hồ sơ `c4a8099e-96fb-464e-a4de-8c50ff7ba3ab`.
- Bốn danh tính Keycloak thật: điều phối viên, người đóng góp, người xét duyệt và người ngoài tenant.
- Request chưa xác thực nhận `401`; truy cập khác tenant nhận `404`; phiên bản cũ hoặc hồ sơ chưa đủ điều kiện nhận `409`.
- Tải minh chứng → quét virus → lưu object → người độc lập xác minh → gửi Flowable → duyệt R1 → xuất gói và kiểm tra SHA-256.
- Sửa ngưỡng số lượng và thời hạn ở R2: trạng thái đủ điều kiện bị tính lại, xác minh cũ không tự trở thành xác minh R2; chặn xuất bản cũ và bản hiện tại chưa được duyệt.
- Đã thực hiện cả nhánh **từ chối → bản nháp → gửi lại → phê duyệt R2**, cùng giao việc, trao đổi, thống kê và truy nguồn.
- SHA-256 của gói cuối trong lần chạy này: `298ef71863db8259c2488894ebd8a7905033a5a20b05b84ed352f8efde12433f`.

Kiểm tra bổ sung: tệp thử antivirus **EICAR** bị từ chối với `422`, không tạo bản ghi minh chứng. Đây là mẫu kiểm thử antivirus vô hại, không phải mã độc được phát hành trong dự án.

## 2. Giao diện được thao tác bằng trình duyệt thật

Hồ sơ `70678349-d5a5-4bf3-9b45-5ec1985e60d6` được tạo và thao tác qua UI:

1. Đăng nhập SSO; tạo R1 với yêu cầu hai hợp đồng; liên kết notice TED `00668268-2024`.
2. Tải minh chứng, trao đổi/giao việc, đổi người dùng để xác minh độc lập và phê duyệt R1.
3. Tạo R2 nâng ngưỡng **2 → 3** và đổi hạn. UI hiển thị giá trị trước/sau, giữ lịch sử R1, khóa xuất gói khi R2 chưa duyệt.
4. Bổ sung một hợp đồng; xác nhận lại minh chứng cũ cho R2; gửi và duyệt R2 bằng các vai trò phù hợp.
5. Tìm kiếm, xuất bản đồ thị RDF, kiểm tra chuỗi kiểm toán và chạy biên nhận n8n. Biên nhận làm số bình luận tăng **2 → 3** ngay trên UI, không cần tải lại thủ công.
6. Hỏi Agent về trạng thái hồ sơ và trích xuất tài liệu thật bằng model cục bộ. Bản trích xuất giữ nguồn `document:tender-terms.txt#page:1`, ngưỡng 2 và `needs_review: true`.
7. Bấm xuất gói qua UI, tải `.tar.gz`, đọc manifest: đúng hồ sơ/R2, **hai tệp minh chứng có SHA-256 khớp**.

Đã kiểm tra desktop 1440 px và mobile **390 × 844**; chiều rộng tài liệu mobile bằng 390 px, không tràn ngang. Các lỗi phát hiện khi chạy — lỗi nhập liệu bị che sau dialog, biên nhận chưa cập nhật màn hình và DNS upstream cũ sau khi đổi container — đã được sửa và chạy lại đường tương ứng.

Ảnh chụp thực tế, không phải mockup:

- [Landing](images/landing.png), [banner](images/banner.png), [biên tập phiên bản](images/revision-editor.png).
- [H — cộng tác](images/human-workspace.png), [xét duyệt độc lập](images/independent-review.png), [D — truy nguồn](images/data-lineage.png).
- [Tác động sửa đổi](images/amendment-impact.png), [R2 đã duyệt](images/approved-amendment.png).
- [Agent có nguồn](images/agent-grounded-answer.png), [trích xuất cần kiểm tra](images/extraction-review.png), [mobile](images/mobile-workspace.png).

## 3. LLM, MCP và dữ liệu liên kết

| Kiểm chứng | Kết quả quan sát |
| --- | --- |
| Ollama 0.6.8 + `qwen2.5:1.5b` | Chat và trích xuất chạy với model thật; trích xuất đúng ngưỡng 2 trong tài liệu mẫu. Không đánh giá chất lượng pháp lý từ một mẫu này. |
| MCP | Đã gọi đủ `read_case`, `read_evidence`, `read_impact`, `propose_tasks`, `propose_revision`, `submit_for_review`. |
| Phân quyền MCP | Người đóng góp không được gửi xét duyệt; trạng thái giữ nguyên bản nháp. Điều phối viên gửi được sang Flowable; người xét duyệt duyệt qua API, sau đó xuất và kiểm tra gói. |
| Fuseki | API xuất RDF và truy vấn SPARQL có xác thực đọc lại **111 triples** của hồ sơ UI. Đồ thị nội bộ không công khai trên Pages. |
| DuckDB/Parquet | Truy vấn trực tiếp tệp lịch sử trả về đủ snapshot R1 và R2 của hồ sơ UI. |
| n8n | Workflow tùy chọn nhận webhook và ghi biên nhận idempotent thật. Không mô tả đây là gửi email hoặc đồng bộ CRM. |
| Prometheus/OpenTelemetry | Ba target `prometheus`, `bidweave-api`, `otel-collector` đều `up=1`; có HTTP metrics và các batch trace thật. Collector debug exporter không phải kho trace lưu trữ dài hạn. |

## 4. Sao lưu và khôi phục

Đã thực hiện backup lạnh, kiểm tra checksum và khôi phục chính project Docker `bidweave`:

- PostgreSQL, sáu data volume và cấu hình riêng; manifest kiểm tra **tám tệp riêng tư**.
- Sau khôi phục: đăng nhập SSO được; dữ liệu hồ sơ, phê duyệt, minh chứng và lịch sử khớp dữ liệu trước sao lưu.
- Hồ sơ UI vẫn ở R2 đã duyệt; hai minh chứng kiểm tra hash thành công; hai snapshot và 111 triples được bảo toàn.
- So sánh manifest theo nội dung và hash, không dựa vào thứ tự phần tử từ SQL hoặc hứa hẹn gói export có byte gzip giống hệt.

Thư mục backup và tệp cấu hình chỉ ở máy chạy, bị loại khỏi Git và source release. Đây không phải kết quả diễn tập trên một máy production độc lập. Quy trình vận hành: [operations.md](operations.md).

## 5. Kiểm tra mã và đóng gói

- **13 regression tests API** đã qua; gồm quy tắc phiên bản, số lượng, trạng thái xét duyệt, dữ liệu liên kết và biên nhận đồng thời.
- **Một regression test trình tạo dependency SBOM** đã qua: nhận diện thành phần shaded trong JAR, không gán checksum của JAR bao ngoài cho thư viện nhúng và không đoán quan hệ AND/OR của nhiều giấy phép.
- `npm ci --ignore-scripts` và build TypeScript/Vite chạy thành công từ source archive được giải nén vào thư mục tạm; build cũng tạo các thông báo giấy phép frontend.
- Workflow Java 21/Maven được build từ nguồn; BPMN trong JAR là cùng tài nguyên được quản lý trong Git. **Không có Java unit-test suite** và không ghi nhận Maven build là một bộ test.
- Header checker và REUSE lint đã qua. JSON/ảnh dùng sidecar `.license`, không chèn comment làm hỏng định dạng.
- Cả source SPDX và dependency SPDX được xác thực bằng **spdx-tools 0.8.3**, không bỏ qua validation. Dependency inventory quan sát được **363 package records**, gồm các hệ sinh thái/dịch vụ khác nhau; không đồng nghĩa 363 giấy phép đều đã được tự động kết luận.
- Source archive không chứa `.git`, `.env`, `.runtime`, backup, virtualenv, `node_modules` hoặc các giá trị bí mật sinh tại máy. Checksum các asset được kiểm tra bằng SHA-256.

## 6. Cách tái hiện và giới hạn

```sh
make configure
make demo
make test
make headers
make smoke
make intelligence
```

Các lệnh runtime cần Docker, tài nguyên máy và Internet cho lần tải dependency/model đầu; xem [hướng dẫn chạy](operations.md) và [hướng dẫn sử dụng](user-guide.md). Smoke tạo dữ liệu demo; không chạy trên dữ liệu production.

Bản ghi này là bằng chứng local. Trạng thái công khai có thể kiểm tra trực tiếp tại [CI](https://github.com/EngLandLee/BidWeave/actions/workflows/ci.yml), [Pages](https://github.com/EngLandLee/BidWeave/actions/workflows/pages.yml), [release workflow](https://github.com/EngLandLee/BidWeave/actions/workflows/release.yml) và [Releases](https://github.com/EngLandLee/BidWeave/releases).

Giới hạn: GitHub Pages chỉ là landing tĩnh, không vận hành backend; n8n dùng Sustainable Use License và là thành phần tùy chọn không thuộc tuyên bố lõi OSI; không có thử tải, pentest độc lập, triển khai HA hay chứng nhận nghiệp vụ pháp lý. Các nhận định từ model và dữ liệu TED vẫn phải được người có quyền kiểm tra.
