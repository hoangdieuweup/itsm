# Grafana Loki Setup

Guide for getting a Loki endpoint and credentials, then configuring the "Loki Configuration" for an environment in the DevOps Control Panel (query-time log search, live tail, and Ruler-backed `LOKI_QUERY` alert rules).

Loki ships with **no built-in authentication** — access is always via either a hosted offering that fronts it for you (Grafana Cloud) or your own reverse proxy in front of a self-hosted instance. Pick one of the two options below.

## Option A — Grafana Cloud (recommended, no self-hosting)

1. Log in to [grafana.com](https://grafana.com) → **My Account** → find the **Loki** stack under your Grafana Cloud instance → click **Details**.
2. Note two values shown there:
   - **User** — a numeric Instance ID (this is the Basic Auth *username*, not a Grafana login).
   - **URL** — the Loki query endpoint, e.g. `https://logs-prod-XXX.grafana.net`.
3. Generate a credential: **Access Policies → Create access policy** with the `logs:read` and `logs:write` scopes (or use a classic **API Key** from the same Loki details page) → **Create token**. Copy it immediately, it's shown only once.
4. Map these into the app's fields:

   | App field | Value |
   |---|---|
   | Endpoint URL | The **URL** from step 2 (no trailing `/loki/api/v1/...`) |
   | Tenant ID | Leave empty — Grafana Cloud scopes by the credential itself, not a client-sent `X-Scope-OrgID` |
   | Authentication | **Basic** |
   | Credential | `<Instance ID>:<API key>` |

## Option B — Self-hosted Loki

1. Install Loki (Docker Compose is the quickest path for a single project):
   ```yaml
   services:
     loki:
       image: grafana/loki:3.3.2
       ports:
         - "3100:3100"
       command: -config.file=/etc/loki/local-config.yaml
   ```
   See [Install using Docker or Docker Compose](https://grafana.com/docs/loki/latest/setup/install/docker/) for other install methods (Helm, Tanka, from source).
2. **Multi-tenancy** — `auth_enabled` in Loki's config defaults to `true`, which requires every request to carry an `X-Scope-OrgID` header identifying the tenant (this is exactly the app's `tenant_id` field). If one Loki cluster is shared across several projects/environments in this system, give each one its own tenant ID here. If this Loki instance only ever serves one project, set `auth_enabled: false` in Loki's config and leave `tenant_id` empty in the app. See [Manage tenant isolation](https://grafana.com/docs/loki/latest/operations/multi-tenancy/).
3. **Authentication** — since Loki itself has none, put an authenticating reverse proxy (e.g. nginx) in front before exposing it beyond a trusted private network. A minimal nginx Basic Auth example that also forwards the tenant header:
   ```nginx
   location / {
       auth_basic           "Loki";
       auth_basic_user_file /etc/nginx/.htpasswd;
       proxy_set_header X-Scope-OrgID $remote_user;
       proxy_pass http://loki:3100;
   }
   ```
   See [Manage authentication](https://grafana.com/docs/loki/latest/operations/authentication/) for other supported reverse proxies and an mTLS option.
4. Map these into the app's fields:

   | App field | Value |
   |---|---|
   | Endpoint URL | The reverse proxy's URL (or Loki's own address if it's only reachable from a trusted private network with no proxy) |
   | Tenant ID | The `X-Scope-OrgID` value assigned to this project, or empty if `auth_enabled: false` |
   | Authentication | Whatever the reverse proxy expects — **Basic** (`username:password`), **Bearer** (a raw token, if using a token-checking proxy/gateway), or **None** on a trusted network with no proxy |
   | Credential | Matches the Authentication choice above |

## Shipping logs into Loki (integrating a project's containers)

Neither Option A nor B above puts a single log line into Loki — they only give you a place to store and query logs. The DevOps Control Panel itself never ships logs either; it's purely a **consumer** of Loki's API (query, live tail, Ruler alerting) — confirmed by reading this repo's own `backend/app/integrations/loki/client.py` and `backend/app/modules/observability/`: every method there is a `GET`/WebSocket read (`query_range`, `tail`, `rules`) or a Ruler-rule write, never a log-line push. This matches the system design note in `docs/tasks/devops-control-panel-schema.md`: `loki_configs` is deliberately generic (`endpoint_url` + `tenant_id` + auth + `default_query`) with no built-in labeling scheme, so the app works with *whatever* labels a project's own log-shipping setup produces — there's nothing project-specific to wire up here beyond pointing that project's containers at the same Loki instance/tenant that's entered in the app's Loki Configuration form.

### Simplest: Docker's own Loki logging driver (no separate agent process)

Since every environment in this system is a Docker-based deployment (matches the Cloudflare Tunnel setup used elsewhere in this project), the lowest-effort integration is Loki's own [Docker logging driver](https://grafana.com/docs/loki/latest/send-data/docker-driver/) — a plugin installed once per host, then just referenced from `docker-compose.yml`. No extra agent container to run or maintain.

1. Install the plugin once on the host running the project's containers:
   ```bash
   docker plugin install grafana/loki-docker-driver:3.7.0-amd64 --alias loki --grant-all-permissions
   ```
2. Add a `logging:` block to each service in that project's `docker-compose.yml`:
   ```yaml
   services:
     api:
       image: your-project/api
       logging:
         driver: loki
         options:
           loki-url: "https://<loki-endpoint>/loki/api/v1/push"
           loki-tenant-id: "<match the Tenant ID configured in the app, if set>"
           # loki-external-labels defaults to container_name={{.Name}} — add more if useful, e.g.:
           # loki-external-labels: "container_name={{.Name}},job=docker"
   ```
   `loki-url` can embed Basic Auth credentials directly (`https://<user>:<pass>@<host>/loki/api/v1/push`) if that's how the endpoint is protected (e.g. Option A's Grafana Cloud instance ID + API key).
3. `docker-compose` automatically attaches `compose_project` and `compose_service` labels to every log line, on top of the default `container_name`. Any of these can be the app's **Default query**, e.g. `{compose_service="api"}` or `{container_name="/myproject_api_1"}`.

### Alternative: Grafana Alloy

For log sources the Docker driver doesn't cover (plain files, non-containerized processes, or when logs need filtering/parsing before Loki), use **[Grafana Alloy](https://grafana.com/docs/alloy/latest/)** (the successor to Promtail) instead:

```alloy
discovery.docker "containers" {
  host = "unix:///var/run/docker.sock"
}

loki.source.docker "default" {
  host       = "unix:///var/run/docker.sock"
  targets    = discovery.docker.containers.targets
  forward_to = [loki.write.default.receiver]
}

loki.write "default" {
  endpoint {
    url = "https://<loki-endpoint>/loki/api/v1/push"

    basic_auth {
      username = "<instance id, if Option A>"
      password = "<api key / password>"
    }
  }
  external_labels = {
    tenant = "<match the Tenant ID configured in the app, if set>",
  }
}
```

Run Alloy as its own container (or systemd service) on the same host — see [Use Grafana Alloy to send logs to Loki](https://grafana.com/docs/alloy/latest/tutorials/send-logs-to-loki/) and [Ingesting logs to Loki using Alloy](https://grafana.com/docs/loki/latest/send-data/alloy/) for `loki.source.file` (plain log files) and Kubernetes variants.

Whichever method is used, whatever labels it attaches are what the app's **Default query** needs to select on.

## Enabling alert rules (`LOKI_QUERY` source)

Alert rules of source `LOKI_QUERY` are pushed into Loki's own **Ruler** component (`POST /loki/api/v1/rules/{namespace}`), so Loki actually evaluates them and fires — the app never polls on its own. This requires the Ruler to be configured with a rule storage backend and an Alertmanager (or webhook) receiver; see [Loki Alerting Rules](https://grafana.com/docs/loki/latest/alert/) and the endpoint table already documented in [`docs/tasks/grafana-loki-integration.md`](../tasks/grafana-loki-integration.md).

## Create the Loki Configuration in the app

Go to a project's environment → **Logs** tab → **Configure** → fill in:

- **Endpoint URL** — from Option A or B above.
- **Tenant ID** — optional, only for a multi-tenant cluster.
- **Authentication** — None / Basic / Bearer, matching how the endpoint is protected.
- **Credential** — `username:password` for Basic, a raw token for Bearer (hidden by default, has a show/hide toggle).
- **Default query** / **Default range (minutes)** — the LogQL query and time range the log view opens with by default; can be changed later per view.

## References

- [Install Loki — Grafana Loki documentation](https://grafana.com/docs/loki/latest/setup/install/)
- [Manage authentication — Grafana Loki documentation](https://grafana.com/docs/loki/latest/operations/authentication/)
- [Manage tenant isolation — Grafana Loki documentation](https://grafana.com/docs/loki/latest/operations/multi-tenancy/)
- [Loki Alerting Rules — Grafana Loki documentation](https://grafana.com/docs/loki/latest/alert/)
- [Loki HTTP API — Grafana Loki documentation](https://grafana.com/docs/loki/latest/reference/loki-http-api/)
