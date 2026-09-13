# Grafana Loki — API Reference khi tích hợp

Nguồn: [Loki HTTP API · Grafana Loki documentation](https://grafana.com/docs/loki/latest/reference/loki-http-api/) (bản chính thức, mới nhất). Base URL tuỳ triển khai, ví dụ `http://<loki-host>:3100`.

## Lưu ý trước khi tích hợp

- **Đa tenant (multi-tenant):** nếu Loki chạy multi-tenant (phổ biến khi 1 cụm Loki dùng chung cho nhiều dự án — đúng pattern đã ghi trong tài liệu thiết kế DB), mọi request phải kèm header `X-Scope-OrgID: <tenant_id>`. Đây chính là field `loki_configs.tenant_id` trong schema đã thiết kế.
- **Xác thực:** tuỳ nơi host — self-host thường dùng Basic Auth hoặc không auth (đứng sau VPN/nginx gateway riêng); Grafana Cloud dùng Bearer token. Khớp với `loki_configs.auth_type (NONE | BASIC | BEARER)`.
- **`/loki/api/v1/tail` là WebSocket**, và phải trỏ tới **querier**, không qua query-frontend (query-frontend không hỗ trợ WebSocket) — đã nêu chi tiết ở phần trước.
- **`query_range` dùng cho "query theo thời gian"**, `tail` dùng cho "live" — đúng 2 nhánh đã thiết kế trong `loki_configs.default_query` / `default_range_minutes`.

---

## 1. Ingestion — đẩy log vào Loki

| Method | Path | Mô tả |
|---|---|---|
| POST | `/loki/api/v1/push` | Đẩy log entries vào Loki (dùng khi app tự push, không qua Promtail/Alloy) |
| POST | `/otlp/v1/logs` | Đẩy log theo chuẩn OpenTelemetry Protocol (OTLP) |

## 2. Query — truy vấn log & metadata

| Method | Path | Mô tả |
|---|---|---|
| GET | `/loki/api/v1/query` | Query log tại một thời điểm (instant query) |
| GET | `/loki/api/v1/query_range` | Query log trong một khoảng thời gian — dùng cho màn "xem log theo query time" |
| GET | `/loki/api/v1/labels` | Lấy danh sách label đã biết trong khoảng thời gian |
| GET | `/loki/api/v1/label/<name>/values` | Lấy các giá trị của một label cụ thể |
| GET/POST | `/loki/api/v1/series` | Trả về các stream khớp với label selector |
| GET | `/loki/api/v1/index/stats` | Thống kê index (số stream, chunk, byte...) theo query |
| GET | `/loki/api/v1/index/volume` | Thông tin khối lượng dữ liệu theo label |
| GET | `/loki/api/v1/index/volume_range` | Khối lượng dữ liệu theo khoảng thời gian |
| GET | `/loki/api/v1/patterns` | Phát hiện pattern lặp lại trong log |
| GET/POST | `/loki/api/v1/detected_fields` | Khám phá các field được tách tự động từ log |
| GET/POST | `/loki/api/v1/detected_field/{name}/values` | Lấy giá trị của một detected field |
| GET | `/loki/api/v1/format_query` | Format lại một LogQL query cho chuẩn/dễ đọc |
| **GET** | **`/loki/api/v1/tail`** | **WebSocket** — stream log gần thời gian thực, dùng cho màn "live" |

## 3. Ruler / Alerting — cảnh báo dựa trên log

| Method | Path | Mô tả |
|---|---|---|
| GET | `/loki/api/v1/rules` | Liệt kê tất cả rule group |
| GET | `/loki/api/v1/rules/{namespace}` | Lấy rule theo namespace |
| GET | `/loki/api/v1/rules/{namespace}/{groupName}` | Lấy một rule group cụ thể |
| POST | `/loki/api/v1/rules/{namespace}` | Tạo/cập nhật rule group |
| DELETE | `/loki/api/v1/rules/{namespace}/{groupName}` | Xoá một rule group |
| DELETE | `/loki/api/v1/rules/{namespace}` | Xoá cả namespace rule |
| GET | `/prometheus/api/v1/rules` | Liệt kê rule (tương thích chuẩn Prometheus) |
| GET | `/prometheus/api/v1/alerts` | Liệt kê alert đang active |

Đây chính là nhánh **"Loki Ruler/Alertmanager tự phát hiện & bắn webhook"** đã khuyến nghị dùng thay vì tự polling — cấu hình rule tại đây, trỏ Alertmanager receiver về webhook backend.

## 4. Xoá log (Log Deletion / Retention theo yêu cầu)

| Method | Path | Mô tả |
|---|---|---|
| POST / PUT | `/loki/api/v1/delete` | Gửi yêu cầu xoá log khớp điều kiện (thường dùng cho tuân thủ/GDPR) |
| GET | `/loki/api/v1/delete` | Liệt kê các yêu cầu xoá đã gửi |
| DELETE | `/loki/api/v1/delete` | Huỷ một yêu cầu xoá đang chờ xử lý |

## 5. Status & Operational — vận hành/health check

| Method | Path | Mô tả |
|---|---|---|
| GET | `/ready` | Readiness probe (dùng cho health check khi tích hợp k8s/monitoring) |
| GET/POST | `/log_level` | Xem/đổi log level của chính Loki lúc runtime |
| GET | `/metrics` | Expose metrics dạng Prometheus (giám sát chính Loki) |
| GET | `/config` | Xem cấu hình hiện tại của Loki |
| GET | `/services` | Liệt kê các service con đang chạy |
| GET | `/loki/api/v1/status/buildinfo` | Thông tin phiên bản build |
| GET | `/distributor/ring` | Trạng thái ring của distributor (kiến trúc microservices) |
| GET | `/indexgateway/ring` | Trạng thái ring của index gateway |
| GET | `/ruler/ring` | Trạng thái ring của ruler |
| GET | `/compactor/ring` | Trạng thái ring của compactor |
| POST | `/flush` | Ép flush chunk trong bộ nhớ xuống storage |
| GET/POST/DELETE | `/ingester/prepare_shutdown` | Chuẩn bị shutdown ingester an toàn |
| GET/POST | `/ingester/shutdown` | Flush và tắt ingester |

---

## Mapping sang schema đã thiết kế

| Nhu cầu trong hệ thống | Endpoint dùng | Field liên quan trong `loki_configs` |
|---|---|---|
| Xem log theo "query time" | `GET /loki/api/v1/query_range` | `default_query`, `default_range_minutes` |
| Xem log "live" | `GET /loki/api/v1/tail` (WebSocket, trỏ querier) | `endpoint_url`, `auth_type`, `credential` |
| Worker định kỳ pull log về Mongo | `GET /loki/api/v1/query_range` gọi lặp lại theo lịch | — |
| Cảnh báo tự động (khuyến nghị) | Cấu hình `POST /loki/api/v1/rules/{namespace}` + Alertmanager receiver trỏ về `/webhooks/loki-alert` | `alert_rules.source = LOKI_QUERY` |
| Đa tenant cho nhiều dự án dùng chung 1 cụm Loki | Header `X-Scope-OrgID` mọi request | `tenant_id` |
