# Cloudflare API — Endpoint cần thiết cho hệ thống

Bản rút gọn từ file tổng 433+63+71 endpoint đã gửi trước — ở đây **chỉ giữ lại đúng những endpoint hệ thống thật sự gọi tới**, theo từng tính năng đã thiết kế (quản lý DNS tập trung, quản lý Tunnel, Notifications/Alerting, Audit Log), nhưng đi sâu đầy đủ tham số/field thay vì chỉ liệt tên. Nguồn: OpenAPI schema chính thức của Cloudflare. Base URL: `https://api.cloudflare.com/client/v4`.

## 0. Permission Token cần tạo

Nhắc lại bảng đã chốt — khi tạo Cloudflare API Token cho `cloudflare_accounts.api_token`, chọn đúng các permission group này (không chọn Global API Key):

| Endpoint nhóm | Permission group | Phạm vi |
|---|---|---|
| Notifications/Alerting (mục 4) | `Notifications Edit` | Account |
| Cloudflare Tunnel (mục 3) | `Cloudflare Tunnel Edit` | Account |
| Audit Logs cấp account (mục 6) | `Account Settings Read` | Account |
| Zones (mục 1) | `Zone Read` | Zone |
| DNS Records (mục 2) | `DNS Edit` | Zone |
| Traffic Analytics (mục 5) | `Analytics Read` | Zone |

---

## 1. Zones — xác định zone khi bind environment

### `GET /zones`
Liệt kê zone để người dùng chọn khi tạo `cloudflare_configs` (binding environment ↔ zone).

| Tham số | Vị trí | Bắt buộc | Ghi chú |
|---|---|---|---|
| `name` | query | không | Lọc theo domain, hỗ trợ `equal`/`contains`/`starts_with`/`ends_with`... |
| `account.id` | query | không | Lọc theo account — dùng để chỉ hiện zone thuộc `cloudflare_accounts` đang chọn |
| `status` | query | không | Lọc theo trạng thái zone |
| `page`, `per_page` | query | không | Phân trang |

### `GET /zones/{zone_id}`
Lấy chi tiết 1 zone (nameserver, trạng thái...) — gọi khi hiển thị thông tin environment.

---

## 2. DNS Records — quản lý tập trung (mục 6.1)

### `GET /zones/{zone_id}/dns_records`
Liệt kê record hiện có — dùng cả cho màn hình DNS và cho job đối chiếu (mục 6.2).

| Tham số | Ghi chú |
|---|---|
| `zone_id` (path, bắt buộc) | |
| `name` / `name.exact` / `name.contains` | Lọc theo tên record |
| `type` | Lọc theo loại record |
| `content` | Lọc theo giá trị record |
| `proxied` | Lọc record có bật proxy hay không |
| `page`, `per_page`, `order`, `direction` | Phân trang/sắp xếp |

### `POST /zones/{zone_id}/dns_records` — Tạo record
Body là **discriminated union theo field `type`** — mỗi loại record có field riêng. Field dùng chung cho mọi loại (khớp với bảng `dns_records` đã thiết kế):

| Field | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `type` | string enum | có | `A`, `AAAA`, `CNAME`, `MX`, `TXT`, `NS`, ... (hệ thống chỉ expose `A \| AAAA \| CNAME \| TXT \| MX \| OTHER` theo enum đã thiết kế) |
| `name` | string (≤255) | có | Tên đầy đủ của record, dạng Punycode |
| `content` | string | tuỳ loại | Xem bảng theo loại bên dưới |
| `ttl` | number | không | Giây, 60–86400 (Enterprise tối thiểu 30), **mặc định `1` = Auto** — Auto chỉ áp dụng được khi `proxied=true` |
| `proxied` | boolean | không | Bật "đám mây cam" — bật thì Cloudflare proxy traffic qua CDN/WAF, tắt thì chỉ resolve DNS thuần |
| `comment` | string | không | Ghi chú nội bộ, không ảnh hưởng response DNS |
| `tags` | array\<string\> | không | Gắn tag để lọc/tổ chức |

Field riêng theo từng loại record hệ thống hỗ trợ:

| Loại | Field riêng trong `content`/khác | Ghi chú |
|---|---|---|
| `A` | `content`: địa chỉ IPv4 hợp lệ | có thêm `private_routing` (routing nội bộ tới origin) |
| `AAAA` | `content`: địa chỉ IPv6 hợp lệ | tương tự A |
| `CNAME` | `content`: hostname hợp lệ, **không được trùng `name`** | có `settings.flatten_cname` — CNAME flattening |
| `MX` | `content`: hostname mail server + field `priority` (số, bắt buộc riêng cho MX) | |
| `TXT` | `content`: chuỗi text trong ngoặc kép, tối đa 255 byte/chuỗi (dài hơn tự động bị Cloudflare tách) | |

Quy tắc ràng buộc cần biết trước khi tạo (Cloudflare tự chặn nếu vi phạm, nên validate phía UI cho gọn):
- A/AAAA không thể tồn tại cùng `name` với CNAME.
- NS record không thể tồn tại cùng `name` với bất kỳ loại record nào khác.

### `GET /zones/{zone_id}/dns_records/{dns_record_id}` — Chi tiết 1 record

### `PATCH /zones/{zone_id}/dns_records/{dns_record_id}` — Sửa một phần
Chỉ cần gửi field muốn đổi. Dùng cho form "Sửa record" thông thường trong UI.

### `PUT /zones/{zone_id}/dns_records/{dns_record_id}` — Ghi đè toàn bộ
Phải gửi đủ toàn bộ field (như tạo mới) — dùng khi muốn chắc chắn record khớp 100% với dữ liệu gửi lên, không giữ lại field cũ nào.

### `DELETE /zones/{zone_id}/dns_records/{dns_record_id}` — Xoá record

---

## 3. Cloudflare Tunnel — quản lý tập trung (mục 6.1)

### `GET /accounts/{account_id}/cfd_tunnel` — Liệt kê Tunnel
| Tham số | Ghi chú |
|---|---|
| `name` | Lọc theo tên |
| `is_deleted` | true/false/rỗng — có gồm tunnel đã xoá không |
| `status` | Lọc theo trạng thái hoạt động |

### `POST /accounts/{account_id}/cfd_tunnel` — Tạo Tunnel
| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `name` | có | Tên gợi nhớ cho tunnel |
| `config_src` | không | `local` (quản lý bằng file YAML trên máy chủ origin) hoặc `cloudflare` (**remotely-managed — bắt buộc chọn cái này** để hệ thống điều khiển ingress rule qua API, xem mục Configurations bên dưới) |
| `tunnel_secret` | không | Mật khẩu chạy tunnel local-managed, ≥32 byte base64 — bỏ qua nếu dùng `config_src=cloudflare` |

### `GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}` — Chi tiết Tunnel
### `PATCH /accounts/{account_id}/cfd_tunnel/{tunnel_id}` — Đổi tên/secret
### `DELETE /accounts/{account_id}/cfd_tunnel/{tunnel_id}` — Xoá Tunnel

### `GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/token` — Lấy token kết nối
Trả về token để chạy `cloudflared tunnel run --token <token>` trên máy chủ origin. **Bắt buộc phải hiển thị cho người dùng ngay sau khi tạo Tunnel** — đây là bước họ cần để tunnel thực sự "sống" (kết nối được), không thể tự động hoá tiếp vì phải chạy trên hạ tầng của họ.

### `GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/connections` — Danh sách kết nối
Dùng để cập nhật `cloudflare_tunnels.status` (HEALTHY/DEGRADED/DOWN) — không có connector nào đang kết nối = DOWN.

### `DELETE /accounts/{account_id}/cfd_tunnel/{tunnel_id}/connections` — Dọn kết nối cũ
Tham số `client_id` (query, tuỳ chọn) — không truyền thì xoá tất cả connector. Cloudflare khuyến nghị chạy lệnh này sau khi xoay vòng (rotate) token.

### `GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations` — Lấy cấu hình ingress hiện tại
### `PUT /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations` — Ghi cấu hình ingress

Đây là endpoint quản lý **public hostname** (đúng thứ user nêu ở phần "publish host"). Body:

```json
{
  "config": {
    "ingress": [
      {
        "hostname": "api.example.com",
        "service": "http://localhost:8001",
        "path": "optional-subpath"
      }
    ]
  }
}
```

| Field trong mỗi `ingress` rule | Bắt buộc | Ghi chú |
|---|---|---|
| `hostname` | có | Public hostname — khớp `tunnel_public_hostnames.hostname` |
| `service` | có | Đích thật (origin) — hỗ trợ `http://`, `https://`, `tcp://`, `ssh://`, `rdp://`, `unix://`... hoặc trả thẳng mã lỗi kiểu `http_status:404` |
| `path` | không | Chỉ route request có path này tới hostname tương ứng |
| `originRequest` | không | Tinh chỉnh nâng cao (timeout, TLS verify origin...) |

**Quan trọng — đã nêu ở mục 6.1:** endpoint này **ghi đè toàn bộ mảng `ingress`** mỗi lần gọi, không có API thêm/sửa từng rule riêng lẻ. Muốn thêm 1 hostname mới: `GET` cấu hình hiện tại → nối thêm phần tử vào mảng `ingress` ở tầng ứng dụng → `PUT` lại toàn bộ mảng. Ít nhất phải có 1 rule trong `ingress` (`minItems: 1`).

---

## 4. Notifications / Alerting — cảnh báo native (mục 7)

### `GET /accounts/{account_id}/alerting/v3/available_alerts` — Danh mục loại cảnh báo
Không tham số ngoài `account_id`. Trả về danh sách `alert_type` khả dụng cho account (DDoS, traffic anomaly, origin error rate...) — hiển thị cho người dùng chọn khi tạo `alert_rules`.

### `POST /accounts/{account_id}/alerting/v3/destinations/webhooks` — Đăng ký webhook đích
| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `name` | có | Tên gợi nhớ |
| `url` | có | URL backend của hệ thống, vd `https://<backend>/webhooks/cloudflare-alert` |
| `secret` | không nhưng **nên có** | Cloudflare gửi kèm giá trị này trong header `cf-webhook-auth` mỗi lần gọi webhook — **backend phải kiểm tra header này khớp secret đã lưu trước khi tin request**, tránh giả mạo request tới `/webhooks/cloudflare-alert` |

### `GET /accounts/{account_id}/alerting/v3/destinations/webhooks` — Liệt kê webhook đã đăng ký
### `DELETE /accounts/{account_id}/alerting/v3/destinations/webhooks/{webhook_id}` — Xoá webhook đích

### `POST /accounts/{account_id}/alerting/v3/policies` — Tạo Notification Policy
| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `name` | có | Tên policy |
| `alert_type` | có | Lấy từ `available_alerts` — lưu vào `alert_rules.cf_alert_type` |
| `enabled` | có | Bật/tắt |
| `mechanisms` | có | Nơi nhận cảnh báo — object gồm `email: [{id: "email@..."}]`, `webhooks: [{id: "<webhook_id>"}]`, `pagerduty: [{id: "<uuid>"}]`. **Trỏ `webhooks` về đúng `webhook_id` đã tạo ở bước trên** để cảnh báo đổ về backend |
| `filters` | không | Lọc hẹp hơn theo alert_type cụ thể (vd chỉ theo zone nào, mức độ nào) — tuỳ loại alert có hỗ trợ hay không |
| `alert_interval` | không | Khoảng thời gian tối thiểu giữa 2 lần báo lại cùng 1 sự cố (không phải alert_type nào cũng hỗ trợ) |
| `description` | không | Ghi chú |

Response trả về `policy_id` — lưu vào `alert_rules.cf_policy_id` để sau đồng bộ 2 chiều (sửa/xoá).

### `PUT /accounts/{account_id}/alerting/v3/policies/{policy_id}` — Sửa policy (field tương tự, tất cả optional)
### `DELETE /accounts/{account_id}/alerting/v3/policies/{policy_id}` — Xoá policy
### `POST /accounts/{account_id}/alerting/v3/policies/{policy_id}/test` — Gửi thử cảnh báo
Hữu ích để test kênh thông báo (Base.vn/Telegram/Email) có nhận được không, mà không cần chờ sự cố thật xảy ra. Field tuỳ chọn: `severity` (mặc định INFO), `source`.

### `GET /accounts/{account_id}/alerting/v3/history` — Lịch sử cảnh báo đã gửi
| Tham số | Ghi chú |
|---|---|
| `since` | RFC3339, lọc từ thời điểm nào |
| `per_page`, `page` | Phân trang |

Lưu ý: chỉ giữ lịch sử theo giới hạn gói (Free/Pro/Business = 30 ngày, Enterprise = 90 ngày) — muốn giữ lâu hơn thì vẫn phải dựa vào `incidents`/Mongo `logs` bên hệ thống mình, endpoint này chỉ để đối chiếu/backfill.

---

## 5. Log của domain đang chạy — traffic log cấp zone

Khác với Audit Logs (mục 6) — ghi *ai sửa cấu hình gì* — nhóm này là **log HTTP request thật đang chạy qua domain** (ai gọi vào, path nào, status code, thời gian phản hồi...). Đây mới là thứ "log của domain đang chạy" bạn cần. Cloudflare có 2 cơ chế song song cho zone-level, tuỳ mục đích:

### 5.1 Logpull cổ điển — tra cứu trực tiếp qua API, không cần hạ tầng lưu trữ riêng

**Yêu cầu trước:** phải bật flag lưu trữ log cho zone trước, và **chỉ khả dụng ở gói Enterprise**.

`GET /zones/{zone_id}/logs/control/retention/flag` — kiểm tra flag đang bật hay tắt.
`POST /zones/{zone_id}/logs/control/retention/flag` — bật/tắt, body `{ "flag": true }`.

`GET /zones/{zone_id}/logs/received` — lấy log request thô theo khoảng thời gian.

| Tham số | Bắt buộc | Ghi chú |
|---|---|---|
| `start` | không | Thời điểm bắt đầu, **inclusive** |
| `end` | **có** | Thời điểm kết thúc, **exclusive** — Cloudflare khuyến nghị query theo từng phút một (`start=...T10:00:00Z&end=...T10:01:00Z`, rồi tiếp `10:01→10:02`...) để không bị trùng/thiếu dữ liệu |
| `fields` | không | Danh sách field muốn lấy, phân tách bằng dấu phẩy — lấy danh mục field khả dụng qua `GET /zones/{zone_id}/logs/received/fields` |
| `sample` | không | Tỷ lệ lấy mẫu (giảm tải khi traffic lớn) |
| `count` | không | Giới hạn số dòng trả về |
| `timestamps` | không | Định dạng timestamp trong response |

`GET /zones/{zone_id}/logs/rayids/{ray_id}` — tra theo **Ray ID** cụ thể (mã định danh 1 request, thường thấy trong header `CF-RAY` khi debug lỗi với 1 request cụ thể của user). Có thể trả về 0, 1, hoặc nhiều dòng (Ray ID không đảm bảo duy nhất tuyệt đối).

Phù hợp cho: worker định kỳ pull log request theo phút về Mongo, hoặc tra cứu nhanh 1 request lỗi cụ thể theo Ray ID mà user report lên.

### 5.2 Logpush cho zone — xuất log liên tục ra kho lưu trữ riêng

Khác Logpull (kéo theo yêu cầu), Logpush **tự động đẩy liên tục** log ra đích lưu trữ bạn chỉ định (S3, R2, GCS, Splunk...). Phù hợp khi muốn giữ log traffic lâu dài ngoài Mongo, hoặc khối lượng lớn không tiện query trực tiếp qua Logpull.

`GET /zones/{zone_id}/logpush/jobs` — liệt kê job đang chạy cho zone.
`POST /zones/{zone_id}/logpush/jobs` — tạo job mới:

| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `destination_conf` | có | URI đích (vd `s3://bucket/path?region=...`), định danh nơi log sẽ được đẩy tới |
| `dataset` | không | Tên bộ dữ liệu — với traffic log của domain thường dùng `http_requests` |
| `output_options` | không | Chọn field cụ thể + định dạng timestamp (thay cho `logpull_options` cũ, đã deprecated) |
| `filter` | không | Lọc bớt request cần log (vd chỉ log status ≥ 400) |
| `max_upload_bytes` / `max_upload_records` / `max_upload_interval_seconds` | không | Kiểm soát batch — kích thước 5MB–1GB, 1.000–1.000.000 dòng, 30–300 giây, `0` = tắt giới hạn đó |
| `enabled` | không | Bật/tắt job |
| `ownership_challenge` | có (lần đầu) | Token xác minh bạn sở hữu đích lưu trữ — lấy qua `POST /zones/{zone_id}/logpush/ownership` trước khi tạo job |

`GET /zones/{zone_id}/logpush/jobs/{job_id}` / `PUT .../{job_id}` / `DELETE .../{job_id}` — xem/sửa/xoá job cụ thể.

### 5.3 Instant Logs cho zone — xem traffic live ngay trên trang

`GET /zones/{zone_id}/logpush/edge/jobs` — liệt kê Instant Logs job đang mở.
`POST /zones/{zone_id}/logpush/edge/jobs` — tạo job mới:

| Field | Ghi chú |
|---|---|
| `fields` | Danh sách field muốn xem, phân tách dấu phẩy |
| `filter` | Lọc drill-down (vd chỉ xem request lỗi 5xx) |
| `sample` | Tỷ lệ lấy mẫu — `1` = 100%, `10` = 10%... |

Đây chính là cơ chế "xem live" traffic của domain trong dashboard Cloudflare — dùng session ngắn, không lưu trữ (giống bản chất Live Tailing của Loki đã bàn ở phần trước), phù hợp cho màn hình debug tức thời chứ không phải nguồn lưu trữ lâu dài.

---

## 6. Audit Logs — theo dõi thay đổi cấu hình cấp account

### `GET /accounts/{account_id}/audit_logs`
| Tham số | Ghi chú |
|---|---|
| `actor.email` | Lọc theo người thực hiện thay đổi |
| `actor.ip` | Lọc theo IP nguồn |
| `action.type` | Lọc theo loại hành động |
| `zone.name` | Lọc theo zone bị ảnh hưởng — dùng tham số này để chỉ xem audit log liên quan đúng domain đang chạy |
| `since`, `before` | Khoảng thời gian |
| `export` | `true` để xuất CSV thay vì JSON |
| `hide_user_logs` | Ẩn bớt log cấp user nếu chỉ muốn xem log cấp hệ thống |

Đây là nguồn dữ liệu cho worker định kỳ pull về Mongo (`type: INCIDENT_DETECTION`/audit) đã mô tả ở tài liệu thiết kế chính — cũng là cách phát hiện gián tiếp ai đó thao tác tay trên Cloudflare dashboard (bổ sung cho job đối chiếu DNS/Tunnel ở mục 6.2 của tài liệu thiết kế, vì audit log ghi lại **mọi** hành động, không chỉ riêng DNS/Tunnel).
