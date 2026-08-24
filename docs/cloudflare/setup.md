# Cloudflare API Token Setup

Guide for creating a Cloudflare API Token and configuring the permissions needed by the DevOps Control Panel (Cloudflare Accounts, DNS, Tunnels, Log Viewer, Alerting).

## 1. Go to the token creation page

Log in to [dash.cloudflare.com](https://dash.cloudflare.com) → top-right avatar → **My Profile** → **API Tokens** tab → **Create Token** → choose **Create Custom Token** (don't use a built-in template — the app needs the exact permission set below).

## 2. Name the token

Example: `itsm-devops-panel`.

## 3. Choose permissions

Click **+ Add more** to add each row, matching the features already built in the app:

| Resource | Permission | Required for |
|---|---|---|
| Account | Cloudflare Tunnel — **Edit** | Creating/deleting Tunnels, managing hostnames (Phase 5) |
| Account | Notifications — **Edit** | Cloudflare-native alert rules, webhook destination, test policy (Phase 9) |
| Account | Audit Logs — **Read** | The "Cloudflare Audit Logs" tab in the Log Viewer (Phase 6) |
| Zone | Zone — **Read** | Listing zones when binding an account to an environment (Phase 4) |
| Zone | DNS — **Edit** | Creating/editing/deleting DNS records (Phase 4) |

If you only want to test the Alerting feature, the minimum needed is: Account → Notifications Edit + Zone → Zone Read + Zone → DNS Edit (an account/zone binding is required before an alert rule can be created) — Cloudflare Tunnel Edit is not needed.

## 4. Choose Account Resources

→ **Include** → select the specific Cloudflare account to manage (or **All accounts** if there's only one).

## 5. Choose Zone Resources

→ **Include** → **Specific zone** (the domain that will be bound to an environment) or **All zones** for convenience while testing.

## 6. (Optional) Client IP Address Filtering / TTL

Leaving these at their defaults is fine — not required.

## 7. Create the token

**Continue to summary → Create Token** — Cloudflare shows the token **only once**, so copy it immediately.

## 8. Get the Cloudflare Account ID

Different from the token — on the dashboard home page, the right-hand column shows an **Account ID** field (a hex string). This is the value to enter into the `cfAccountId` field when creating a Cloudflare Account in the app.

## 9. Create the Cloudflare Account in the app

Go to `/admin/cloudflare-accounts` → **Create Account** → fill in:

- `Label`: a memorable name, e.g. "Production"
- `Cloudflare Account ID`: the value from step 8
- `API Token`: the token from step 7

The app automatically calls **Test Connection** (`GET /zones?account.id=`) as soon as the account is created — if the token or a permission is missing, this step surfaces the error clearly before you ever get to binding a zone or creating an alert rule.

## References

- [API token permissions — Cloudflare Fundamentals docs](https://developers.cloudflare.com/fundamentals/api/reference/permissions/)
