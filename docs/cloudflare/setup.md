# Cloudflare API Token Setup

Hướng dẫn tạo Cloudflare API Token và cấu hình quyền để dùng với DevOps Control Panel (Cloudflare Accounts, DNS, Tunnels, Log Viewer, Alerting).

## 1. Vào trang tạo token

Đăng nhập [dash.cloudflare.com](https://dash.cloudflare.com) → góc trên phải, click avatar → **My Profile** → tab **API Tokens** → **Create Token** → chọn **Create Custom Token** (không dùng template có sẵn, vì app cần đúng bộ quyền dưới đây).

## 2. Đặt tên token

Ví dụ: `itsm-devops-panel`.

## 3. Chọn Permissions

Bấm **+ Add more** để thêm từng dòng, ứng với các tính năng app đã build:

| Resource | Permission | Bắt buộc cho |
|---|---|---|
| Account | Cloudflare Tunnel — **Edit** | Tạo/xoá Tunnel, quản lý hostname (Phase 5) |
| Account | Notifications — **Edit** | Alert rules Cloudflare-native, webhook destination, test policy (Phase 9) |
| Account | Audit Logs — **Read** | Tab "Cloudflare Audit Logs" trong Log Viewer (Phase 6) |
| Zone | Zone — **Read** | Liệt kê zone khi bind account↔environment (Phase 4) |
| Zone | DNS — **Edit** | Tạo/sửa/xoá DNS record (Phase 4) |

Nếu chỉ muốn test riêng phần Alerting, tối thiểu cần: Account → Notifications Edit + Zone → Zone Read + Zone → DNS Edit (vì phải bind account/zone trước khi tạo alert rule) — không cần Cloudflare Tunnel Edit.

## 4. Chọn Account Resources

→ **Include** → chọn đúng account Cloudflare cần quản lý (hoặc **All accounts** nếu chỉ có 1 account).

## 5. Chọn Zone Resources

→ **Include** → **Specific zone** (chọn domain sẽ bind vào environment) hoặc **All zones** cho tiện test.

## 6. (Tuỳ chọn) Client IP Address Filtering / TTL

Để mặc định là được, không bắt buộc.

## 7. Tạo token

**Continue to summary → Create Token** — Cloudflare chỉ hiện token **1 lần duy nhất**, copy lại ngay.

## 8. Lấy Cloudflare Account ID

Khác với token — ở trang chủ dashboard, cột phải có mục **Account ID** (chuỗi hex). Đây là giá trị điền vào field `cfAccountId` khi tạo Cloudflare Account trong app.

## 9. Tạo Cloudflare Account trong app

Vào `/admin/cloudflare-accounts` → **Create Account** → điền:

- `Label`: tên gợi nhớ, vd "Production"
- `Cloudflare Account ID`: giá trị lấy ở bước 8
- `API Token`: token lấy ở bước 7

App sẽ tự gọi **Test Connection** (`GET /zones?account.id=`) ngay khi tạo — nếu token/permission thiếu sẽ báo lỗi rõ tại bước này, trước khi bind zone hay tạo alert rule.

## Nguồn tham khảo

- [API token permissions — Cloudflare Fundamentals docs](https://developers.cloudflare.com/fundamentals/api/reference/permissions/)
