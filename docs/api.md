<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Tài liệu Đặc tả REST API — BidWeave

Tài liệu chi tiết về kiến trúc API, cơ chế xác thực, danh mục 28 endpoint nghiệp vụ và các ví dụ kiểm thử thực tế của nền tảng **BidWeave**.

---

## 1. Tổng quan & Điểm truy cập (Base URLs)

| Mục đích | URL / Giao thức | Mô tả |
| :--- | :--- | :--- |
| **API Gateway (Chính thức)** | `http://localhost:8090/api` | Đi qua Apache APISIX, kiểm tra rate-limit, CORS và Bearer Token |
| **Direct API (Nội bộ)** | `http://localhost:8000/api` | Endpoint trực tiếp từ container FastAPI |
| **Swagger UI tương tác** | `http://localhost:8000/docs` | Giao diện kiểm thử trực tiếp có OpenAPI Schema |
| **ReDoc Documentation** | `http://localhost:8000/redoc` | Tài liệu giao diện trang tĩnh chuẩn OpenAPI 3.1 |
| **OpenAPI Specification** | `http://localhost:8000/openapi.json` | File schema định dạng JSON |
| **MCP (Model Context Protocol)**| `http://localhost:8090/mcp` | Giao thức công cụ cho Agent qua APISIX |

---

## 2. Xác thực & Phân quyền (Authentication & Authorization)

Toàn bộ các endpoint nghiệp vụ `/api/*` (ngoại trừ `/api/health`) đều được bảo vệ bởi **Keycloak OIDC (OpenID Connect)**.

### Header bắt buộc
```http
Authorization: Bearer <access_token>
```

### Lấy Access Token qua Keycloak (cURL)
```bash
curl -X POST "http://localhost:8091/realms/bidweave/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=bidweave-web" \
  -d "username=coordinator" \
  -d "password=1CMdyz4MCOlodajkKfSv17SE"
```

### Phân vai trò & Đa người thuê (Multi-Tenancy)
* `tenant_id` được trích xuất trực tiếp từ claim của token JWT. Người dùng chỉ xem và thao tác trên tài nguyên của tenant mình.
* **Các vai trò (Roles):**
  * `coordinator`: Điều phối viên (tạo hồ sơ, tạo phiên bản revision, gửi duyệt, liên kết TED, xuất bản đồ thị).
  * `contributor`: Người đóng góp (tải minh chứng, cập nhật task, trao đổi).
  * `reviewer`: Người thẩm định độc lập (xác minh minh chứng, phê duyệt hoặc từ chối hồ sơ).
  * `outsider`: Người dùng thuộc tenant độc lập khác (dùng kiểm thử cách ly dữ liệu).

### Nguyên tắc Bất biến (Core Invariants)
1. **Kiểm tra khóa phiên bản lạc quan (`expected_revision`):** Mọi thao tác sửa đổi, nộp minh chứng, thẩm định hoặc phê duyệt đều phải truyền số revision dự kiến. Nếu sai lệch, API trả về `409 Conflict`.
2. **Quy tắc thẩm định độc lập (Four-eyes principle):** Người tải file không được tự xác minh minh chứng của chính mình (`403 Forbidden`). Người tạo/gửi hồ sơ không được tự duyệt hồ sơ (`403 Forbidden`).
3. **An toàn tệp:** Mọi tệp tải lên đều được ClamAV quét virus thực tế; tệp phát hiện mã độc (ví dụ mã EICAR) sẽ bị từ chối với mã `422 Unprocessable Entity`.

---

## 3. Bảng mã phản hồi HTTP (Status Codes)

| Mã | Tên | Ý nghĩa |
| :---: | :--- | :--- |
| **200** | OK | Thao tác thành công. |
| **201** | Created | Tạo mới tài nguyên thành công. |
| **401** | Unauthorized | Thiếu token hoặc token hết hạn / không hợp lệ. |
| **403** | Forbidden | Người dùng không đủ quyền hoặc vi phạm quy tắc thẩm định độc lập. |
| **404** | Not Found | Không tìm thấy hồ sơ hoặc tài nguyên thuộc tenant khác. |
| **409** | Conflict | Sai `expected_revision` hoặc trạng thái hồ sơ không cho phép chuyển đổi. |
| **422** | Unprocessable Entity | Dữ liệu sai định dạng Pydantic hoặc ClamAV phát hiện virus. |
| **503** | Service Unavailable | Thành phần phụ thuộc (PostgreSQL, SeaweedFS, Flowable, ClamAV) gặp sự cố. |

---

## 4. Danh mục 28 Endpoint chi tiết

### Nhóm 1: Hệ thống & Danh tính (System & Identity)

#### `GET /api/health`
* **Mô tả:** Kiểm tra trạng thái hoạt động của API và kết nối cơ sở dữ liệu PostgreSQL. Mở công khai không cần token.
* **Phản hồi mẫu (200 OK):**
  ```json
  {
    "status": "ok",
    "database": "ok"
  }
  ```

#### `GET /api/me`
* **Mô tả:** Lấy thông tin tài khoản, danh sách vai trò và tenant hiện tại từ token.
* **Yêu cầu:** Bearer Token.
* **Phản hồi mẫu (200 OK):**
  ```json
  {
    "id": "e9b28b7a-9a84-482f-87d2-7c83f2a89c71",
    "username": "coordinator",
    "tenant_id": "tenant-default",
    "roles": ["coordinator"]
  }
  ```

---

### Nhóm 2: Quản lý Hồ sơ Dự thầu (Cases)

#### `GET /api/cases`
* **Mô tả:** Danh sách các hồ sơ dự thầu thuộc tenant của người gọi.
* **Phản hồi mẫu (200 OK):** Mảng các đối tượng `CaseOut`.

#### `POST /api/cases`
* **Mô tả:** Tạo hồ sơ dự thầu mới (khởi tạo ở revision 0).
* **Quyền:** `coordinator`.
* **Body (JSON):**
  ```json
  {
    "title": "Gói thầu Nâng cấp Hạ tầng CNTT",
    "deadline": "2026-11-30T17:00:00Z",
    "description": "Chuẩn bị hồ sơ năng lực và kỹ thuật theo hồ sơ mời thầu"
  }
  ```
* **Phản hồi (200 OK):** Đối tượng `CaseOut` chứa ID hồ sơ vừa tạo.

#### `GET /api/cases/{case_id}`
* **Mô tả:** Lấy toàn bộ thông tin chi tiết của một hồ sơ: danh sách yêu cầu (requirements), minh chứng (evidence), nhiệm vụ (tasks), bình luận (comments), lịch sử phiên bản (revisions), phê duyệt (approvals) và tác động (impact).

---

### Nhóm 3: Phiên bản & Ma trận Yêu cầu (Revisions & Requirements)

#### `POST /api/cases/{case_id}/revisions`
* **Mô tả:** Tạo phiên bản sửa đổi mới (R1, R2...). Tự động tính toán phân tích tác động (amendment impact), sinh ra các task cần xử lý và vô hiệu hóa trạng thái sẵn sàng duyệt cũ.
* **Quyền:** `coordinator`.
* **Body (JSON):**
  ```json
  {
    "expected_revision": 0,
    "deadline": "2026-11-30T17:00:00Z",
    "reason": "Thiết lập yêu cầu ban đầu R1",
    "requirements": [
      {
        "key": "EXP",
        "title": "Hợp đồng tương tự đã hoàn thành",
        "description": "Phải có ít nhất 2 hợp đồng dịch vụ CNTT hoàn thành",
        "kind": "count",
        "minimum": 2,
        "mandatory": true,
        "source_ref": "HSMT mục 2.1 - Tiêu chuẩn đánh giá",
        "owner": "contributor"
      }
    ]
  }
  ```
* **Các loại yêu cầu (`kind`):**
  * `count`: Đếm số lượng minh chứng hợp lệ khác nhau về mã hash (kèm `minimum`).
  * `validity`: Kiểm tra hạn hiệu lực (bảo đảm còn hạn sau deadline hồ sơ).
  * `document`: Minh chứng dạng tài liệu văn bản cần thẩm định.
  * `text`: Cam kết hoặc văn bản tự khai báo.

---

### Nhóm 4: Quản lý Minh chứng (Evidence)

#### `POST /api/cases/{case_id}/evidence`
* **Mô tả:** Tải lên tệp minh chứng. Tệp được ClamAV quét trực tiếp, tính mã băm SHA-256 và lưu trữ vào SeaweedFS S3.
* **Content-Type:** `multipart/form-data`.
* **Tham số Form:**
  * `file`: Tệp tải lên (PDF, DOCX, PNG, v.v.).
  * `requirement_key`: Mã yêu cầu gắn kết (ví dụ `EXP`).
  * `expected_revision`: Số revision hiện hành (ví dụ `1`).
  * `quantity`: Số lượng (nếu là loại `count`).
  * `valid_until`: Ngày hết hạn ISO 8601 (nếu là loại `validity`).
  * `notes`: Ghi chú minh chứng.
* **Mã lỗi đặc biệt:** `422` nếu tệp chứa mã độc (ClamAV phát hiện).

#### `POST /api/cases/{case_id}/evidence/{evidence_id}/verify`
* **Mô tả:** Thẩm định xác minh minh chứng độc lập.
* **Quyền:** `reviewer` (phải khác với `uploaded_by` của file).
* **Body (JSON):**
  ```json
  {
    "expected_revision": 1
  }
  ```

#### `GET /api/cases/{case_id}/evidence/{evidence_id}/preview`
* **Mô tả:** Xem trước minh chứng an toàn (trả về nội dung xem trước với Content-Type phù hợp).

#### `GET /api/cases/{case_id}/evidence/{evidence_id}/download`
* **Mô tả:** Tải về tệp minh chứng gốc.

---

### Nhóm 5: Quy trình Phê duyệt BPMN (Flowable Workflow)

#### `POST /api/cases/{case_id}/submit`
* **Mô tả:** Điều phối viên gửi hồ sơ sang Flowable Workflow để xét duyệt. Hệ thống kiểm tra xem toàn bộ các yêu cầu bắt buộc đã có đủ minh chứng đã xác minh hay chưa.
* **Quyền:** `coordinator`.
* **Body (JSON):**
  ```json
  {
    "expected_revision": 1
  }
  ```

#### `POST /api/cases/{case_id}/review`
* **Mô tả:** Reviewer độc lập đưa ra quyết định phê duyệt hoặc từ chối hồ sơ trên tiến trình Flowable.
* **Quyền:** `reviewer` (phải khác người gửi và người tạo hồ sơ).
* **Body (JSON):**
  ```json
  {
    "expected_revision": 1,
    "decision": "approve",
    "comment": "Đã đối soát đầy đủ các hợp đồng tương tự theo R1."
  }
  ```
  *(Giá trị `decision` có thể là `"approve"` hoặc `"reject"`)*.

---

### Nhóm 6: Đóng gói Xuất bản (Package Export)

#### `GET /api/cases/{case_id}/export?revision={N}`
* **Mô tả:** Tải về gói lưu trữ nén `.tar.gz` chứa toàn bộ minh chứng và file `manifest.json` ghi nhận mã băm SHA-256 từng tệp.
* **Quy tắc:** Chỉ cho phép tải khi revision được chỉ định là revision hiện hành và **đã được phê duyệt** (`status == approved`). Nếu chưa duyệt hoặc sai revision, trả về `409 Conflict`.

---

### Nhóm 7: Cộng tác & Nhiệm vụ (Collaboration & Tasks)

#### `POST /api/cases/{case_id}/comments`
* **Mô tả:** Đăng bình luận hoặc biên bản trao đổi trong hồ sơ.
* **Body (JSON):**
  ```json
  {
    "body": "Đã bổ sung tài liệu hợp đồng số 3 vào hệ thống."
  }
  ```

#### `PATCH /api/cases/{case_id}/tasks/{task_id}`
* **Mô tả:** Nhận việc hoặc đánh dấu hoàn thành nhiệm vụ (`open` / `done`). Lưu ý: Hoàn thành task không thay thế việc xác minh minh chứng.
* **Body (JSON):**
  ```json
  {
    "status": "done",
    "assignee": "contributor"
  }
  ```

---

### Nhóm 8: Dữ liệu Liên kết & Đồ thị Tri thức (Linked Open Data & RDF)

#### `GET /api/lod/notices?date=YYYY-MM-DD&cpv_prefix=72`
* **Mô tả:** Truy vấn SPARQL trực tiếp lên cổng dữ liệu mở châu Âu **TED** theo eProcurement Ontology (ePO) để tìm các thông báo mời thầu dịch vụ CNTT (CPV 72xxxxxx).

#### `POST /api/cases/{case_id}/notice`
* **Mô tả:** Liên kết mã số thông báo mời thầu TED (publication number) vào hồ sơ dự thầu dạng bản nháp.
* **Body (JSON):**
  ```json
  {
    "publication_number": "00668268-2024"
  }
  ```

#### `GET /api/cases/{case_id}/lineage`
* **Mô tả:** Xuất đồ thị dữ liệu liên kết JSON-LD thể hiện phả hệ (lineage) của hồ sơ theo các chuẩn W3C PROV, CCCEV và ePO.

#### `POST /api/cases/{case_id}/lineage/publish`
* **Mô tả:** Xuất bản và đồng bộ Named Graph vào cơ sở dữ liệu tri thức **Apache Jena Fuseki**.

---

### Nhóm 9: Phân tích & Quản trị Hệ thống (Analytics, History & Audit)

#### `GET /api/analytics`
* **Mô tả:** Báo cáo tổng hợp số liệu hồ sơ, số lượng phê duyệt, nhiệm vụ mở và các sự kiện gần nhất trong tenant.

#### `GET /api/cases/{case_id}/history`
* **Mô tả:** Truy vấn bản chụp lịch sử (analytical snapshots) được lưu dưới định dạng **DuckDB / Parquet** để đối soát ngoại tuyến.

#### `GET /api/search/requirements?q={query}`
* **Mô tả:** Tìm kiếm full-text nội dung yêu cầu hồ sơ dự thầu trên toàn bộ tenant.

#### `GET /api/audit/verify`
* **Mô tả:** Xác thực tính toàn vẹn của chuỗi băm sự kiện kiểm toán (Audit hash chain). Trả về trạng thái hợp lệ và mã băm đỉnh (head hash).

---

### Nhóm 10: Trí tuệ Nhân tạo Cục bộ (Local AI & MCP)

#### `GET /api/agent/status`
* **Mô tả:** Kiểm tra trạng thái hoạt động của mô hình LLM cục bộ (Ollama `qwen2.5:1.5b`).

#### `POST /api/agent/chat`
* **Mô tả:** Hỏi đáp với trợ lý AI trên ngữ cảnh hồ sơ hiện hành. AI chỉ trả lời dựa trên metadata đã trích xuất kèm dẫn nguồn cụ thể.
* **Body (JSON):**
  ```json
  {
    "case_id": "c4a8099e-96fb-464e-a4de-8c50ff7ba3ab",
    "message": "Hồ sơ R2 hiện tại còn thiếu những minh chứng nào?"
  }
  ```

#### `POST /api/agent/extract`
* **Mô tả:** Đọc tài liệu PDF hoặc văn bản mời thầu, phân tích và trích xuất thành danh sách yêu cầu bản nháp (mỗi yêu cầu đều có cờ `needs_review: true` để người dùng thẩm tra trước khi lưu).
* **Content-Type:** `multipart/form-data` (trường `file`).

---

### Nhóm 11: Tự động hóa & Webhooks (Automation)

#### `POST /api/cases/{case_id}/automation/receipt`
* **Mô tả:** Kích hoạt webhook gửi thông tin hồ sơ đã duyệt sang công cụ tự động hóa ngoài (n8n).
* **Quyền:** `coordinator`.

#### `POST /api/cases/{case_id}/automation/receipt-record`
* **Mô tả:** Callback ghi nhận biên nhận tự động. Hệ thống thực hiện kiểm tra khóa phiên bản trong database transaction trước khi ghi nhận comment biên nhận.

---

### Nhóm 12: Model Context Protocol (MCP)

#### `POST /mcp`
* **Mô tả:** Điểm cuối chuẩn Streamable HTTP của Model Context Protocol (MCP).
* **Cơ chế:** Phân quyền theo Authorization Bearer Token.
* **Danh sách 6 công cụ khả dụng:**
  1. `read_case`: Đọc metadata của hồ sơ.
  2. `read_evidence`: Đọc danh sách và trạng thái minh chứng.
  3. `read_impact`: Xem phân tích tác động sửa đổi phiên bản.
  4. `propose_tasks`: Gợi ý công việc cần làm dựa trên yêu cầu còn thiếu.
  5. `propose_revision`: Gợi ý phạm vi sửa đổi yêu cầu.
  6. `submit_for_review`: Gửi hồ sơ sang luồng Flowable (yêu cầu vai trò coordinator).

---

## 5. Kịch bản Gọi API Thực tế qua cURL (End-to-End Walkthrough)

Dưới đây là chuỗi lệnh cURL mẫu để chạy thử toàn bộ luồng nghiệp vụ từ đầu đến cuối:

### Bước 1: Lấy token đăng nhập
```bash
TOKEN=$(curl -s -X POST "http://localhost:8091/realms/bidweave/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=bidweave-web&username=coordinator&password=1CMdyz4MCOlodajkKfSv17SE" \
  | jq -r .access_token)
```

### Bước 2: Tạo hồ sơ dự thầu mới
```bash
CASE_ID=$(curl -s -X POST "http://localhost:8090/api/cases" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Dự án Chuyển đổi số 2026","deadline":"2026-12-31T23:59:59Z","description":"Gói dịch vụ phát triển phần mềm"}' \
  | jq -r .id)
echo "Đã tạo Case ID: $CASE_ID"
```

### Bước 3: Thiết lập yêu cầu phiên bản R1
```bash
curl -s -X POST "http://localhost:8090/api/cases/$CASE_ID/revisions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "expected_revision": 0,
    "deadline": "2026-12-31T23:59:59Z",
    "reason": "Yêu cầu kỹ thuật ban đầu",
    "requirements": [
      {
        "key": "EXP",
        "title": "Hợp đồng tương tự",
        "description": "Tối thiểu 1 hợp đồng",
        "kind": "count",
        "minimum": 1,
        "mandatory": true,
        "source_ref": "Mục 3.1 HSMT",
        "owner": "contributor"
      }
    ]
  }' | jq .
```

### Bước 4: Tải minh chứng (qua tài khoản contributor)
```bash
CONTRIBUTOR_TOKEN=$(curl -s -X POST "http://localhost:8091/realms/bidweave/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=bidweave-web&username=contributor&password=1CMdyz4MCOlodajkKfSv17SE" \
  | jq -r .access_token)

echo "Hợp đồng kinh tế mẫu số 102/2025" > contract_sample.txt

EVIDENCE_ID=$(curl -s -X POST "http://localhost:8090/api/cases/$CASE_ID/evidence" \
  -H "Authorization: Bearer $CONTRIBUTOR_TOKEN" \
  -F "file=@contract_sample.txt" \
  -F "requirement_key=EXP" \
  -F "expected_revision=1" \
  -F "quantity=1" \
  -F "notes=Hợp đồng triển khai hạ tầng năm 2025" \
  | jq -r .id)
echo "Đã nộp Minh chứng ID: $EVIDENCE_ID"
```

### Bước 5: Thẩm định độc lập (qua tài khoản reviewer)
```bash
REVIEWER_TOKEN=$(curl -s -X POST "http://localhost:8091/realms/bidweave/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=bidweave-web&username=reviewer&password=1CMdyz4MCOlodajkKfSv17SE" \
  | jq -r .access_token)

curl -s -X POST "http://localhost:8090/api/cases/$CASE_ID/evidence/$EVIDENCE_ID/verify" \
  -H "Authorization: Bearer $REVIEWER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"expected_revision": 1}' | jq .
```

### Bước 6: Gửi duyệt hồ sơ (Coordinator)
```bash
curl -s -X POST "http://localhost:8090/api/cases/$CASE_ID/submit" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"expected_revision": 1}' | jq .
```

### Bước 7: Phê duyệt hồ sơ trên Flowable (Reviewer)
```bash
curl -s -X POST "http://localhost:8090/api/cases/$CASE_ID/review" \
  -H "Authorization: Bearer $REVIEWER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"expected_revision": 1, "decision": "approve", "comment": "Hồ sơ đạt yêu cầu năng lực."}' | jq .
```

### Bước 8: Xuất gói hồ sơ dự thầu đã duyệt
```bash
curl -s -o "dossier_R1.tar.gz" "http://localhost:8090/api/cases/$CASE_ID/export?revision=1" \
  -H "Authorization: Bearer $TOKEN"

tar -ztvf dossier_R1.tar.gz
```
