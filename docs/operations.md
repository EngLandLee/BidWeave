<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Chạy và vận hành BidWeave

## Điều kiện

- Linux, Docker Engine với Docker Compose v2, Git, GNU Make, Python 3.12 hoặc 3.13 và [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Internet cho lần dựng đầu: image, dependency, cơ sở nhận diện ClamAV và model. Tra TED cần Internet ở thời điểm tra cứu.
- Khuyến nghị 16 GB RAM cho toàn bộ profile và model CPU; dành ít nhất 15 GB đĩa trống. Đây là cấu hình khuyến nghị, không phải kết quả benchmark. Có thể chỉ chạy lõi để giảm tài nguyên.
- Các cổng cục bộ 8090, 8091, 5678, 9090 chưa bị chiếm. Không cần IoT, tài khoản LLM trả phí hoặc khóa API TED.

## Khởi động từ mã nguồn

```bash
git clone https://github.com/EngLandLee/BidWeave.git
cd BidWeave
make demo
```

`make demo` chạy tuần tự: sinh cấu hình → build API, workspace, MCP và Flowable từ nguồn → khởi động các dịch vụ → kích hoạt theme đăng nhập trên realm hiện có → tải `qwen2.5:1.5b` vào Ollama → nhập và publish workflow n8n. Lần đầu có thể chậm vì tải dependency/model và dữ liệu ClamAV. Lệnh phải kết thúc thành công; không bỏ qua lỗi readiness.

- Landing/workspace: <http://localhost:8090>.
- Keycloak: <http://localhost:8091>. Realm: `bidweave`.
- n8n tùy chọn: <http://localhost:5678>. Không cần mở editor để chạy workflow đã nhập. Nếu mở editor lần đầu, tự thiết lập tài khoản chủ sở hữu; đây không phải tài khoản SSO của workspace.
- Prometheus tùy chọn: <http://localhost:9090>.
- Ollama, Fuseki, DB, S3, Flowable và API nội bộ **không xuất cổng trực tiếp ra máy chủ**. Truy cập dữ liệu nghiệp vụ qua gateway, không mở các cổng nội bộ để tiện demo.

Chỉ chạy lõi bắt buộc và workspace:

```bash
make up
make health
make smoke
```

`make up` không tự kéo model hoặc bật các profile tùy chọn. Giao diện phải báo dịch vụ chưa sẵn sàng thay vì trả kết quả AI/dữ liệu giả. Bật đầy đủ sau đó bằng `make demo`.

### Cập nhật theme trên dữ liệu hiện có

`make up` và `make up-all` mount theme từ `infra/keycloak/themes/bidweave` và chạy `make keycloak-theme` sau khi Keycloak sẵn sàng. Lệnh này chỉ cập nhật `loginTheme` qua Admin API, không nhập lại realm, đặt lại mật khẩu hay tạo lại người dùng/client.

Nếu dịch vụ đã chạy với volume cũ, dùng `make up` để cập nhật mount rồi kích hoạt theme; có thể gọi riêng `make keycloak-theme` khi chỉ cần áp dụng lại lựa chọn. Script lấy thông tin quản trị từ `.env` riêng, không in token. Thiếu thông tin xác thực hoặc Admin API từ chối sẽ làm lệnh thất bại; không dùng `make configure --force` để xử lý.

Realm mới được cấu hình theme BidWeave và tiếng Việt. Với realm hiện có, các thiết lập ngôn ngữ và tài khoản được giữ nguyên. Workspace và login chia sẻ lựa chọn sáng/tối qua cookie chỉ khi dùng cùng hostname, như `localhost:8090` và `localhost:8091`.

## Tài khoản mẫu và bí mật

`scripts/configure.py` sinh `.env` riêng với quyền `0600`; cấu hình mount nằm trong `.runtime/` với thư mục gốc `0700`. **Không commit, chụp ảnh, đính kèm issue hay gửi các thư mục này lên GitHub.**

Mở `.env` bằng trình soạn thảo cục bộ và lấy `DEMO_PASSWORD`. Bốn tài khoản tổng hợp dùng chung mật khẩu mẫu này:

| Tài khoản | Quyền | Phạm vi |
| --- | --- | --- |
| `coordinator` | Tạo hồ sơ, sửa đổi, gửi duyệt, xuất, gọi đồng bộ n8n | Tenant mẫu chính |
| `contributor` | Bổ sung minh chứng, cộng tác | Tenant mẫu chính |
| `reviewer` | Xác minh minh chứng, quyết định xét duyệt | Tenant mẫu chính |
| `outsider` | Kiểm tra cách ly tenant | Tenant mẫu khác |

Đây là tài khoản demo, **không phải cấu hình triển khai công khai**. Người tải tệp không được tự xác minh tệp đó; người tạo/gửi hồ sơ không được tự phê duyệt. Khi kiểm tra các vai trò, dùng **Đăng xuất** rồi đăng nhập tài khoản khác.

Chạy `make configure` lại không đổi các mật khẩu hiện có. `--force` chỉ dành cho môi trường **chưa có dữ liệu**; nó không thực hiện xoay vòng thông tin xác thực trong database/volume đang tồn tại. Tuyệt đối không dùng nó để chữa lỗi đăng nhập trên hệ thống đang chạy.

Đổi model có chủ đích, không đổi mật khẩu:

```bash
python3 scripts/configure.py --llm-model qwen2.5:1.5b
make demo
```

Giấy phép model độc lập với Ollama. Xem [ranh giới giấy phép](licensing.md) trước khi chọn model khác.

## Chạy các kịch bản kiểm chứng

```bash
make test
make headers
make smoke
make intelligence
```

- `test`: kiểm thử hành vi domain, projection và chuỗi kiểm toán.
- `headers`: header từng tệp và REUSE; cần Git index chứa các tệp nguồn dự định phát hành.
- `smoke`: tạo hồ sơ **tổng hợp mới**, đăng nhập thật bốn vai trò, đi qua gateway, quét/lưu tệp, phê duyệt Flowable, sửa đổi R1 → R2, từ chối/gửi lại, kiểm tra chống truy cập chéo và xuất gói.
- `intelligence`: dùng hồ sơ của smoke, SDK MCP thật và Ollama thật; không thay thế bằng mock khi model chưa sẵn sàng.

Kết quả riêng nằm trong `.runtime/smoke-result.json` và `.runtime/intelligence-result.json`. Chỉ đưa kết quả đã lọc thông tin nhạy cảm vào báo cáo. Smoke tạo dữ liệu mới, không xóa hoặc reset hồ sơ cũ.

Thao tác trên trình duyệt theo [hướng dẫn người dùng](user-guide.md). GitHub Pages chỉ chạy landing tĩnh, **không phải backend demo công khai**.

## Sao lưu và khôi phục

Sao lưu lạnh dừng ngắn các writer, giữ PostgreSQL (bao gồm Flowable), danh tính Keycloak, tệp S3, lịch sử Parquet, NATS và các volume n8n/Fuseki đã tồn tại. Model Ollama có thể tải lại nên không nằm trong bản sao. Bản sao **bao gồm `.env` và khóa mã hóa n8n**; cần bảo quản như bí mật, mã hóa khi chuyển/lưu ngoài máy và không đưa lên release.

```bash
make backup BACKUP_DIR=backups/before-upgrade
python3 scripts/backup.py verify --directory backups/before-upgrade
```

Bản sao có manifest và SHA-256. Tệp `.partial` nghĩa là bản sao chưa hoàn thành; trình khôi phục sẽ từ chối. Mã băm phát hiện thay đổi byte, không chứng minh ai đã tạo bản sao.

**Khôi phục thay thế dữ liệu hiện tại của đúng project.** Chỉ thực hiện sau khi đã sao lưu trạng thái hiện tại, kiểm tra manifest và xác nhận tên project. Với project mặc định `bidweave`:

```bash
OTEL_ENABLED=true make restore BACKUP_DIR=backups/before-upgrade CONFIRM_PROJECT=bidweave
make health
```

Trên máy mới: clone đúng phiên bản nguồn, chạy `make demo` để tạo đủ các container/profile cần khôi phục rồi dùng lệnh trên. Script kiểm tra tên project, mount và đường dẫn archive trước khi thay thế volume. Sau khôi phục, đăng nhập lại và kiểm tra hồ sơ, lịch sử, minh chứng và mã băm xuất; `make health` một mình không đủ. Nếu khôi phục lỗi, giữ writer dừng và điều tra, không tiếp tục ghi lên dữ liệu phục hồi dở dang.

## Theo dõi và xử lý sự cố

```bash
docker compose --profile '*' ps
docker compose logs --since 10m api workflow outbox
docker compose logs --since 10m keycloak apisix clamav
```

Không đăng nguyên log lên issue trước khi lọc đường dẫn, dữ liệu hồ sơ và thông tin xác thực. OTel bật với `make up-all`/`make demo`; collector nhận trace/metric nội bộ, Prometheus thu metric. Đây là quan sát cục bộ, không phải backend truy vết lưu dài hạn. API không xuất metric qua `/api` công khai.

| Hiện tượng | Kiểm tra |
| --- | --- |
| Lõi chưa healthy | `docker compose ps` và log của đúng dịch vụ; ClamAV cần tải dữ liệu ban đầu |
| 401 sau đổi máy/hostname | Issuer Keycloak, đồng hồ hệ thống, URL frontend; không bỏ kiểm tra JWT |
| 409 | Đọc thông báo; tải lại hồ sơ, kiểm tra revision, trạng thái duyệt và vai trò |
| 503 từ LLM | `docker compose exec ollama ollama list`, model trong `.env`, RAM và log Ollama |
| 503 từ TED | Kết nối endpoint công khai; không dùng metadata bịa để vượt lỗi |
| Chưa thấy snapshot lịch sử | Kiểm tra outbox, NATS và worker; projection cập nhật bất đồng bộ |
| n8n chưa có webhook | Chạy `make integrations` sau `make up-all`, kiểm tra publish workflow |

Dừng nhưng giữ dữ liệu: `make down`. **Không chạy `docker compose down -v` nếu muốn giữ dữ liệu.**

## Trước khi mở Internet

Compose này là môi trường **localhost**. Trước triển khai thật: HTTPS và hostname/issuer nhất quán; tài khoản riêng và MFA; vô hiệu hóa password-grant client dành cho smoke; giới hạn file/quota theo nhu cầu; chính sách tenant; backup mã hóa; rà soát image/dependency hiện hành; tách quản trị; theo dõi tài nguyên; đánh giá dữ liệu cá nhân và tài liệu thầu. Không công khai cổng quản trị n8n, Keycloak, Prometheus hoặc dịch vụ nội bộ bằng cách bỏ địa chỉ loopback.
