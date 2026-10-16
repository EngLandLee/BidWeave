<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# Ranh giới giấy phép và dữ liệu của BidWeave

## Phạm vi và nguyên tắc

Tệp này là bản kiểm kê biên giới cấp phát hành (không phải ý kiến pháp lý). Mã nguồn, cấu hình, tài liệu, script và định nghĩa workflow do BidWeave tự viết được cấp theo **Apache License 2.0** trừ khi tệp hoặc sidecar nói khác; toàn văn nằm ở [`LICENSE`](../LICENSE) và [`LICENSES/Apache-2.0.txt`](../LICENSES/Apache-2.0.txt). Apache-2.0 của BidWeave **không** cấp lại quyền cho mã upstream, image/container, thư viện kéo từ registry, model weights, dữ liệu TED/eForms/ePO/CCCEV, font hoặc hồ sơ đấu thầu của người dùng.

Mỗi tệp mã có thể ghi chú được phải có:

```text
SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0
```

JSON, font, ảnh, PDF, model, binary và định dạng không có comment dùng sidecar liền kề `<tên-tệp>.license` (hoặc cơ chế legal-notice do công cụ tạo ra). Không chèn SPDX giả vào vật liệu upstream và không xóa copyright/NOTICE của upstream.

## Bảng kiểm kê thành phần

Phiên bản image được lấy từ `compose.yaml`; phiên bản thư viện trực tiếp lấy từ các manifest/lockfile hiện hành. Một image digest không tự cho biết semantic version; nếu không có tag, phải giữ digest và lấy SBOM/NOTICE từ image trước khi phân phối image đó.

| Thành phần/phiên bản đang tích hợp | Vai trò và biên giới | Giấy phép/ghi chú bắt buộc | Nguồn chính đã kiểm tra |
|---|---|---|---|
| Keycloak `26.0.7` | Identity service, chạy như container riêng | Apache-2.0; trademark và NOTICE upstream vẫn thuộc Keycloak/Red Hat | [LICENSE.txt upstream](https://raw.githubusercontent.com/keycloak/keycloak/main/LICENSE.txt) |
| Apache APISIX `3.11.0-debian` | Gateway/container riêng | Apache-2.0; LICENSE upstream liệt kê subcomponent có notice/điều khoản riêng | [LICENSE upstream](https://github.com/apache/apisix/blob/master/LICENSE) |
| PostgreSQL `16.4-alpine3.20` | Database container riêng | PostgreSQL License (không gọi tắt là Apache/MIT) | [PostgreSQL License](https://www.postgresql.org/about/licence/) |
| Flowable OSS `7.0.1` | Workflow REST engine **bắt buộc**, build từ POM của dự án; không thay bằng n8n | Apache-2.0 | [LICENSE upstream](https://raw.githubusercontent.com/flowable/flowable-engine/flowable-7.0.1/LICENSE), [POM hiện hành](../services/workflow/pom.xml) |
| SeaweedFS `3.80` | Object storage/S3 container riêng | Apache-2.0 | [LICENSE upstream](https://raw.githubusercontent.com/seaweedfs/seaweedfs/master/LICENSE) |
| ClamAV `1.4-debian13-slim@sha256:1d4083fccfcd485cdaeee593db7655c923afdb8ed528e828d03e1c8b1e351bec` | Malware scanning service; database/signature updates có biên giới riêng | GNU GPL v2; image digest không biến thành mã Apache-2.0 | [ClamAV introduction/license](https://docs.clamav.net/Introduction.html) |
| NATS `2.10.22-alpine` | Messaging/JetStream service riêng | Apache-2.0 | [LICENSE upstream](https://raw.githubusercontent.com/nats-io/nats-server/main/LICENSE) |
| Apache Jena/Fuseki `stain/jena-fuseki@sha256:b1d0c96f19adddef417520184471ac816cf36c6e72936a88ea02b29f4305929a` | Semantic/SPARQL service tùy chọn (`semantic` profile) | Jena/Fuseki Apache-2.0; compose chỉ pin digest, không chứa tag semantic version. Kiểm tra SBOM/NOTICE của image khi redistributing. | [Jena releases](https://jena.apache.org/download/index.cgi), [Jena docs](https://jena.apache.org/documentation.html) |
| DuckDB `1.1.3` và Apache Parquet | Phân tích dữ liệu/định dạng Parquet; thư viện không phải source BidWeave | DuckDB MIT; Parquet format/source Apache-2.0 | [DuckDB LICENSE](https://raw.githubusercontent.com/duckdb/duckdb/main/LICENSE), [Parquet LICENSE](https://raw.githubusercontent.com/apache/parquet-format/master/LICENSE) |
| Ollama `0.6.8` | Local model runtime tùy chọn (`llm` profile) | Ollama MIT; model và model card có giấy phép riêng | [Ollama LICENSE](https://raw.githubusercontent.com/ollama/ollama/main/LICENSE) |
| Qwen2.5 `1.5b` (model được gọi là `qwen2.5:1.5b`) | Model weights tải/được quản lý ngoài source | Qwen/Qwen2.5-1.5B-Instruct Apache-2.0; giữ attribution Alibaba Cloud và LICENSE của model; output không phải license grant của BidWeave | [Qwen LICENSE](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct/blob/main/LICENSE), [model card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) |
| n8n `2.43.6` | **Tùy chọn**, connector/workflow ngoài core; file export của BidWeave không chứa n8n runtime | Sustainable Use License (SUL), fair-code/source-available, **không phải license OSI-approved**. Flowable vẫn là workflow bắt buộc. Việc tách n8n không phải bảo đảm loại bỏ mọi rủi ro giấy phép của cuộc thi; phải rà soát use case, phân phối và điều khoản riêng. | [n8n Community License/SUL](https://docs.n8n.io/n8n-community-license), [n8n LICENSE.md](https://github.com/n8n-io/n8n/blob/master/LICENSE.md) |
| OpenTelemetry Collector Contrib `0.120.0` và Python OTel `1.30.0` | Telemetry tùy chọn | Apache-2.0 (các dependency con vẫn cần inventory theo SBOM/lockfile) | [Collector LICENSE](https://raw.githubusercontent.com/open-telemetry/opentelemetry-collector-contrib/main/LICENSE), [Python repository](https://github.com/open-telemetry/opentelemetry-python) |
| Prometheus `v3.2.1` | Metrics tùy chọn (`observability` profile) | Apache-2.0 | [LICENSE upstream](https://raw.githubusercontent.com/prometheus/prometheus/main/LICENSE) |
| React `18.x`/`react-dom` và `keycloak-js` `26.0.6` | Web runtime/client | React MIT; keycloak-js Apache-2.0 | [React LICENSE](https://raw.githubusercontent.com/facebook/react/main/LICENSE), [keycloak-js LICENSE.txt](https://raw.githubusercontent.com/keycloak/keycloak-js/main/LICENSE.txt) |
| Newsreader `@fontsource-variable/newsreader` `5.3.0` | Font được đóng gói vào web build | SIL Open Font License 1.1; giữ copyright “The Newsreader Project Authors” và OFL trong legal notices; font không được bán riêng | [Newsreader OFL](https://raw.githubusercontent.com/productiontype/Newsreader/master/OFL.txt), [Fontsource package](https://www.npmjs.com/package/@fontsource-variable/newsreader) |

Các thư viện trực tiếp khác của API/MCP/web (FastAPI, SQLAlchemy, psycopg, boto3, pypdf, rdflib, MCP, Vite, TypeScript và dependency bắc cầu) được pin trong [`services/api/pyproject.toml`](../services/api/pyproject.toml), [`services/mcp/requirements.txt`](../services/mcp/requirements.txt), [`services/workflow/pom.xml`](../services/workflow/pom.xml), [`apps/web/package.json`](../apps/web/package.json) và `package-lock.json`. Không được rút gọn toàn bộ chúng thành “Apache-2.0”: release inventory/SBOM phải lấy license và copyright của từng package từ metadata/NOTICE upstream. Web build tạo `dist/THIRD-PARTY-NOTICES.txt` và `dist/licenses/`; không xóa các tệp này khi đóng gói.

## Dữ liệu, metadata và hồ sơ

- **TED live linked metadata:** liên kết tới notice/API hoặc snapshot không làm BidWeave thành tác giả notice hay tender document. Việc tải, lưu, hiển thị và tái sử dụng phải theo [TED data-reuse help](https://ted.europa.eu/en/help/data-reuse), [TED legal notice](https://ted.europa.eu/en/legal-notice) và [hướng dẫn tái sử dụng XML/API](https://docs.ted.europa.eu/ODS/latest/reuse/index.html). Gắn nguồn, thời điểm lấy và URL; không gắn Apache-2.0 của BidWeave lên dữ liệu TED.
- **eForms/ePO/CCCEV:** đây là vocabularies/ontology và tài liệu của Publications Office/EU có phiên bản, attribution và điều kiện riêng. [ePO business overview](https://docs.ted.europa.eu/EPO/latest/business.html) mô tả provenance, phiên bản và CCCEV; đó không phải giấy phép blanket cho tender evidence.
- **Tender/evidence riêng:** tệp upload, chứng chỉ, chữ ký, PDF, và evidence do tenant hoặc bên thứ ba cung cấp vẫn thuộc rightsholder/điều khoản riêng; không đưa vào source release và không cấp quyền công khai bằng NOTICE.
- **Dữ liệu synthetic của BidWeave:** `data/synthetic-*.json` là dữ liệu tự tạo, có sidecar `.license` Apache-2.0 và tuyên bố không đại diện tổ chức/credential/hồ sơ thật. Không dùng chúng làm bằng chứng cho quyền đối với dữ liệu thực.
- **Parquet/JSON/binary:** format không quyết định quyền với nội dung. Sidecar phải nói rõ tác giả, nguồn, license, phiên bản/digest và (nếu có) hạn chế dữ liệu; binary upstream phải đi kèm license/NOTICE chính gốc hoặc đường dẫn inventory.

## Notice runtime và tái phân phối

Không vendoring upstream source là chủ ý; khi phân phối image hoặc bundle phải cung cấp attribution/license tương ứng với artifact thật. Với web bundle, script `apps/web/scripts/third-party-notices.mjs` quét dependency runtime và sao chép license files vào `dist/licenses/`; `dist/THIRD-PARTY-NOTICES.txt` là một phần legal notice bắt buộc của bundle. Với image digest, giữ nguyên digest và phát hành SBOM/NOTICE của image, không đoán license từ tên tag.

Giấy phép upstream không cấp quyền dùng trademark để quảng bá BidWeave. Apache-2.0, MIT, PostgreSQL, GPLv2, OFL và SUL có điều kiện khác nhau; chỉ gọi đúng tên khi đã kiểm tra nguồn chính ở bảng trên. Chạy model local không tự động bảo đảm mọi dữ liệu riêng tư; quyền truy cập, log, telemetry, image và cấu hình triển khai vẫn là trách nhiệm của operator. Không tài liệu nào ở đây tuyên bố RAG loại bỏ hallucination hoặc hash chain là “immutable/non-repudiable”.

## BTC, REUSE và giới hạn kết luận

Theo điều khoản/ghi chú BTC đã được kiểm tra, lỗi được nêu nguyên văn là: **“Giấy phép không được ghi trong từng tệp mã” -5**. Header SPDX, sidecar và `reuse lint` là lựa chọn tooling để làm bằng chứng quản trị của nhóm, **không phải bảo đảm chính thức rằng BTC sẽ chấp nhận**. Cần rà soát từng file phát hành, generated artifact, binary và dependency inventory trước khi nộp; tài liệu này không hứa hẹn điểm, tỷ lệ 50/50 hay kết quả pháp lý.

## Checklist phát hành

1. Đối chiếu version/tag/digest thực tế với `compose.yaml`, manifest và SBOM; image Fuseki được định danh bằng digest, không suy đoán phiên bản Jena từ tên image.
2. Giữ `LICENSE`, `NOTICE`, `LICENSES/Apache-2.0.txt`, license upstream và `dist/THIRD-PARTY-NOTICES.txt`/`dist/licenses/` trong bundle tương ứng.
3. Kiểm tra sidecar cho JSON, font, ảnh, model và binary; không sửa header vào upstream.
4. Tách n8n SUL khỏi core Apache-2.0, duy trì Flowable mandatory, và xin rà soát điều khoản nếu n8n được cung cấp cho customer/contest.
5. Gắn provenance/attribution cho TED/eForms/ePO/CCCEV; phân loại rõ live link, snapshot, synthetic data và private evidence.
