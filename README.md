# SA Hub

A self-contained productivity tool for Red Hat Solutions Architects. Connects to Gmail, Google Drive, and Slack to surface follow-ups, contacts, accounts, and an AI-generated one-pager — all refreshed hourly.

## What it does

| Page | Description |
|------|-------------|
| **One-Pager** | AI-drafted status doc (priorities, accounts, ideas, wins) — refreshed hourly, pin sections to preserve your edits |
| **Follow-Ups** | Auto-detects email threads you sent with no reply in 7+ days |
| **Contacts** | All external contacts extracted from your Gmail history, searchable |
| **Accounts** | Contacts grouped by company, expandable rows |

## Stack

- **Backend:** Python / FastAPI + SQLite + APScheduler
- **Frontend:** React + Vite served by Nginx
- **AI:** Ollama with Qwen2.5 7B (contact enrichment + one-pager generation, self-hosted)
- **Runtime:** Docker Compose

---

## Setup

### 1. Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (e.g. `sa-hub`)
3. Enable these APIs:
   - Gmail API
   - Google Drive API (used to read Google Docs for the one-pager; separate Docs API is not required)
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
   - Application type: **Web application**
   - Authorized redirect URI: `http://localhost:3000/api/auth/google/callback` (or your HTTPS domain — see below)
5. Copy the Client ID and Client Secret

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
SECRET_KEY=any_random_32_char_string
```

Optional LLM settings (defaults work with Docker Compose):

```env
LLM_BASE_URL=http://ollama:11434/v1
LLM_MODEL=qwen2.5:7b-instruct
```

### 3. Run

```bash
docker compose up --build
```

**Podman / Docker build fails with `ERR_MODULE_NOT_FOUND` and `node_modules/dist/node/cli.js`:** the image copied your host `node_modules` over `npm ci`. Ensure `frontend/.dockerignore` exists (it excludes `node_modules`), then rebuild:

```bash
docker compose build --no-cache frontend
```

Pull the model into Ollama (first time only, ~4 GB download):

```bash
docker exec sa-hub-ollama ollama pull qwen2.5:7b-instruct
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Ollama API: http://localhost:11434

### 4. Connect Google

Go to **Connections** in the sidebar → click **Connect Google** → complete OAuth flow.

Then click **Sync Now** to run the first sync (Gmail all-time history may take a few minutes).

---

## Slack (Corporate)

Corporate Slack requires admin approval for custom app installs.

**To request:**
1. Go to https://api.slack.com/apps → Create New App
2. Request these Bot Token Scopes from IT:
   - `channels:history`, `channels:read`
   - `groups:history`, `im:history`, `mpim:history`
   - `users:read`
3. Once approved and installed, copy the Bot Token to `.env`:
   ```
   SLACK_BOT_TOKEN=xoxb-...
   ```
4. Restart: `docker compose restart backend`

---

## Production: your domain + HTTPS + login

A domain you own with **HTTPS** fixes the Google redirect issue. Google accepts `https://sa-hub.yourdomain.com/...`; it does not accept raw LAN IPs like `192.168.x.x`.

Typical layout (Caddy and Docker on the **same** RHEL host):

```text
Internet → UDM :443/:80 → RHEL host (Caddy :443)
                              └→ http://127.0.0.1:3000  (SA Hub frontend container)
```

Do **not** forward WAN ports **3000**, **8000**, or **11434** — only **443** (and **80** for Let's Encrypt).

### 1. DNS

At your DNS provider, add an **A record**:

| Type | Name | Value |
|------|------|--------|
| A | `sa-hub` | Your home **public** IPv4 |

Result: `sa-hub.yourdomain.com` → your WAN IP. Verify with `dig +short sa-hub.yourdomain.com`.

On your **UniFi Dream Machine**, forward **443** and **80** to this RHEL box's **LAN IP**.

### 2. SA Hub (Docker on RHEL)

```bash
cd /path/to/sa-hub
mkdir -p data
cp .env.example .env
# edit .env (see below)
docker compose up -d --build
docker exec sa-hub-ollama ollama pull qwen2.5:7b-instruct
```

**RHEL / SELinux:** Compose mounts `./data` with the `:z` flag so the container can write SQLite. Do **not** bind-mount `./backend` over `/app` in production. Do **not** use `docker compose` with `--reload` on RHEL (see troubleshooting §7).

Confirm the UI on the host:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000   # expect 200
```

### 3. Environment (`.env`)

```env
PUBLIC_URL=https://sa-hub.yourdomain.com
FRONTEND_URL=https://sa-hub.yourdomain.com
GOOGLE_REDIRECT_URI=https://sa-hub.yourdomain.com/api/auth/google/callback

SECRET_KEY=generate_a_long_random_string
AUTH_USERNAME=your_username
AUTH_PASSWORD_HASH=<bcrypt hash — see below>
```

Generate the password hash (never put a plain password in `.env`):

```bash
docker compose up -d --build backend
docker compose exec backend python scripts/hash_password.py 'your long random password'
```

Copy the output into `.env` as `AUTH_PASSWORD_HASH=...`, remove any `AUTH_PASSWORD=` line, then:

```bash
docker compose up -d backend
```

**Optional — Docker secret file** (hash not in `.env`):

```bash
docker compose exec backend python scripts/hash_password.py 'your password' > secrets/auth_password_hash
chmod 600 secrets/auth_password_hash
docker compose -f docker-compose.yml -f docker-compose.secrets.yml.example up -d
```

- Set the **same** redirect URI in [Google Cloud Console](https://console.cloud.google.com) → OAuth client → **Authorized redirect URIs** (no trailing slash).
- Restart: `docker compose up -d`

### 4. App login

When `AUTH_USERNAME` and `AUTH_PASSWORD_HASH` (or legacy `AUTH_PASSWORD`) are set, all API routes and Google connect require signing in first. Sessions last 30 days by default (`AUTH_SESSION_DAYS`).

Passwords are verified with **bcrypt**; only the hash is stored. Plain `AUTH_PASSWORD` still works but logs a deprecation warning.

If auth variables are **unset**, the app stays open (fine for localhost-only).

### 5. Caddy on RHEL (HTTPS reverse proxy)

Caddy runs on the **host** (not in `docker-compose`). It terminates TLS and proxies to the frontend container on port **3000**.

#### Install Caddy

**RHEL 9 / Rocky 9 / Alma 9:**

```bash
sudo dnf install -y dnf-plugins-core
sudo dnf copr enable -y @caddy/caddy
sudo dnf install -y caddy
sudo systemctl enable --now caddy
```

**RHEL 8:** If Copr is unavailable, install the binary from [caddyserver.com/docs/install](https://caddyserver.com/docs/install) and add a systemd unit.

#### Caddyfile

Edit `/etc/caddy/Caddyfile` (or merge with existing sites). Example in repo: `deploy/Caddyfile.example`.

```caddy
sa-hub.yourdomain.com {
    reverse_proxy localhost:3000 {
        header_up X-Forwarded-Proto {scheme}
        header_up X-Forwarded-Host {host}
        header_up X-Real-IP {remote_host}
    }
}
```

Replace `sa-hub.yourdomain.com` with your hostname.

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo journalctl -u caddy -f    # logs if something fails
```

Caddy obtains a Let's Encrypt certificate automatically when DNS and ports **80**/**443** reach this host.

#### Firewall (firewalld)

```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

#### SELinux

If HTTPS loads but Caddy returns **502** or logs show connection errors to the backend:

```bash
sudo setsebool -P httpd_can_network_connect 1
sudo systemctl reload caddy
```

Check denials: `sudo ausearch -m avc -ts recent`

#### Port 443 conflict

Only one service can bind **443**:

```bash
sudo ss -tlnp | grep ':443'
```

Caddy should own **443**. If another service uses it, add the `sa-hub.yourdomain.com` block to that proxy instead of running two listeners.

### 6. Verify

```bash
curl -I https://sa-hub.yourdomain.com
# API health through the same path as the UI (via Caddy → frontend nginx → backend)
curl -s https://sa-hub.yourdomain.com/api/health
```

From off your home network:

1. Open `https://sa-hub.yourdomain.com` — valid padlock, login page
2. Sign in
3. **Connections** → **Connect Google** — completes without redirect errors

### 7. Troubleshooting: backend `unhealthy`

**1. Read logs** (crash vs slow start):

```bash
docker compose logs backend --tail=80
```

| Log message | Fix |
|-------------|-----|
| `ModuleNotFoundError: No module named 'bcrypt'` | `docker compose build --no-cache backend && docker compose up -d` |
| `Permission denied` on `/app` or `Will watch for changes` | See §8 restart loop (remove `--reload` / backend bind mount) |
| `unable to open database file` | `mkdir -p data && chmod 755 data` and SELinux `:z` on volume |
| `Uvicorn running on http://0.0.0.0:8000` | App is up; healthcheck may need more time — pull latest compose (`start_period: 60s`) |

**2. Test health inside the container:**

```bash
docker compose exec backend python scripts/healthcheck.py
echo $?
```

Exit code **0** = healthy. **1** = app not listening yet or crashed.

**3. Test from the host:**

```bash
curl -s http://localhost:8000/health
```

**4. Bcrypt hash in `.env` — escape `$`**

Docker Compose treats `$` as variable substitution. A line like `AUTH_PASSWORD_HASH=$2b$12$...` corrupts the hash and can break login. Either:

- Double every `$`: `AUTH_PASSWORD_HASH=$$2b$$12$$...`, or  
- Use `secrets/auth_password_hash` + `docker-compose.secrets.yml.example` (no `$` in `.env`)

**5. Auth env must be consistent**

```bash
docker compose exec backend printenv AUTH_USERNAME AUTH_PASSWORD_HASH SECRET_KEY
```

If `AUTH_USERNAME` is set, you need `AUTH_PASSWORD_HASH` (or legacy `AUTH_PASSWORD`) **and** `SECRET_KEY`.

**6. Frontend stuck waiting**

The frontend waits for a healthy backend. Fix backend first, then `docker compose up -d`.

### 8. Troubleshooting: backend restart loop (`Permission denied` on `/app`)

If logs show **both** of these, uvicorn is running with **`--reload`** (file watcher), which fails on RHEL/SELinux:

```text
INFO:     Will watch for changes in these directories: ['/app']
PermissionError: Permission denied (os error 13) about ["/app"]
```

**Fix:**

1. **Remove auto-override** — Docker Compose silently merges `docker-compose.override.yml` if it exists:

```bash
ls -la docker-compose.override.yml
# If present, delete or rename it:
rm docker-compose.override.yml
```

2. **Confirm the running command** (must NOT contain `--reload`):

```bash
docker inspect sa-hub-backend --format '{{json .Config.Cmd}}'
```

3. **Rebuild the backend image from scratch** and recreate:

```bash
docker compose down
docker compose build --no-cache backend
docker compose up -d
docker compose logs backend --tail=15
```

You should see `Uvicorn running on http://0.0.0.0:8000` **without** “Will watch for changes”.

4. Use current `docker-compose.yml` only (`./data:/app/data:z`, explicit `command` without `--reload`).

5. Ensure data is writable: `mkdir -p data && chmod 755 data`

6. If SQLite still fails on `data/`:

```bash
sudo chcon -Rt svirt_sandbox_file_t data
```

**Dev reload (not for RHEL production):** use `docker compose -f docker-compose.yml -f docker-compose.dev.yml.example` only on a dev machine — never copy that file to `docker-compose.override.yml` on the server.

### 9. Troubleshooting: `redirect_uri_mismatch`

Google requires the redirect URI in the OAuth request to **exactly** match one entry in Cloud Console (scheme, host, port, path — no trailing slash).

**1. See what SA Hub is sending** (after signing in, open **Connections**, or run):

```bash
docker compose exec backend python -c "
import os
from services.google_auth import get_redirect_uri
print(get_redirect_uri())
"
```

**2. Add that exact URI** in [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Credentials → your OAuth client → **Authorized redirect URIs**.

**3. Typical mismatches**

| In Console (wrong) | SA Hub expects (HTTPS production) |
|--------------------|-----------------------------------|
| `http://localhost:8000/auth/google/callback` | `https://sa-hub.yourdomain.com/api/auth/google/callback` |
| `http://localhost:3000/api/...` | `https://sa-hub.yourdomain.com/api/...` |
| `https://sa-hub.yourdomain.com/api/.../` (trailing `/`) | same URI **without** trailing slash |

**4. Align `.env` on the server** (then `docker compose up -d backend`):

```env
PUBLIC_URL=https://sa-hub.yourdomain.com
FRONTEND_URL=https://sa-hub.yourdomain.com
GOOGLE_REDIRECT_URI=https://sa-hub.yourdomain.com/api/auth/google/callback
```

`GOOGLE_REDIRECT_URI` can be omitted if it is `PUBLIC_URL` + `/api/auth/google/callback` (do not copy `{` `}` braces from the Caddyfile into `.env`).

**5. WiFiMan / SSH tunnel only:** use `http://localhost:3000/api/auth/google/callback` in **both** Console and `.env` (or unset `PUBLIC_URL`), and open the app at `http://localhost:3000` via SSH forward — not the LAN IP.

### 10. Troubleshooting: Drive sync errors (Gmail works)

Gmail and Drive share one Google login, but **Drive is a separate API** in Cloud Console.

**Common causes:**

| Symptom | Fix |
|---------|-----|
| `accessNotConfigured` / API not enabled | Enable **Google Drive API** in [API Library](https://console.cloud.google.com/apis/library/drive.googleapis.com) |
| `insufficient permissions` | Re-connect Google (**Connections** → disconnect by clearing token or re-run OAuth with `prompt=consent`) |
| Docs on **Shared drives** | Fixed in current code (`includeItemsFromAllDrives`); rebuild backend |
| Empty docs list | Normal if you have no Google Docs; sync still succeeds |

**Check the error:**

```bash
docker compose logs backend --tail=50 | grep -i drive
```

Or open **Connections** in the UI — **Drive sync** shows the last status message.

After updating the backend:

```bash
docker compose up -d --build backend
```

Click **Sync Now**, then refresh **Connections**.

### 11. Troubleshooting: 502 on Connect Google

A **502 Bad Gateway** when clicking **Connect** almost always means the reverse proxy cannot reach the **backend** container (not a Google error).

**1. Test each hop on the RHEL host**

```bash
# Backend directly
curl -s http://localhost:8000/health

# Through frontend nginx (same path as the browser)
curl -s http://localhost:3000/api/health

# Through Caddy (if configured)
curl -s https://sa-hub.yourdomain.com/api/health
```

All should return `{"status":"ok"}`. If step 1 fails, check backend logs:

```bash
docker compose logs backend --tail=50
```

If step 1 works but step 2 returns 502, rebuild the frontend (nginx proxies `/api/` to `backend:8000`):

```bash
docker compose up -d --build frontend
```

**2. Confirm Google env vars are loaded**

```bash
docker compose exec backend printenv GOOGLE_CLIENT_ID
```

Empty means `.env` is missing values or compose was not restarted after editing `.env`:

```bash
docker compose up -d
```

**3. Sign in before Connect**

If `AUTH_USERNAME` / `AUTH_PASSWORD` are set, you must **sign in** first. The Connect link is a full-page navigation; your session cookie must be present. You should not see a login page after clicking Connect.

**4. SELinux (RHEL)**

If the UI loads but `/api/*` returns 502:

```bash
sudo setsebool -P httpd_can_network_connect 1
sudo systemctl reload caddy
```

**5. Caddy must forward HTTPS headers**

Use the `header_up` block in `deploy/Caddyfile.example`, then `sudo systemctl reload caddy`.

**6. Google redirect URI**

A redirect mismatch usually shows a **Google** error page, not 502. Ensure Console and `.env` match exactly:

`https://sa-hub.yourdomain.com/api/auth/google/callback`

### 12. Troubleshooting: Sync, login, and Ollama

**Confirm you are on the current build** — backend logs should say `Starting sync...` (not `Starting hourly sync...`) after **Sync Now**. Rebuild both images:

```bash
podman-compose build --no-cache backend frontend
podman-compose up -d
```

**Trailing `}` in `.env`** — if logs show `Stripped trailing '}' from URL env value`, fix lines like `PUBLIC_URL=https://sa-hub.digitalgiants.net}` (remove the `}`).

**Gmail works but enrichment fails** — sync continues past Gmail; the next step calls **Ollama**. Pull the model once:

```bash
podman exec -it sa-hub-ollama ollama pull qwen2.5:7b-instruct
```

On startup, the backend logs a warning if the model is missing. After a failed sync, check the full traceback:

```bash
podman-compose logs backend --tail=80 | grep -A5 "Contact enrichment"
```

To skip AI steps until Ollama is ready, add to `.env`:

```env
SYNC_AI_ENABLED=false
```

**Do not click Sync Now twice** — wait for the spinner to finish (several minutes on first Gmail sync). Overlapping syncs slow the server.

**Kicked to sign-in while sync runs** — rebuild the **frontend** so `/auth/session` failures from timeouts do not redirect to login (only HTTP 401 should). Backend `/auth/session` returning `200` in logs means your session is still valid.

### 13. Optional: restrict by VPN

You can still use **WiFiMan** and only use the site over VPN, or combine VPN + app login for defense in depth.

---

## Remote access (UniFi VPN / WiFiMan Desktop)

Use **WiFiMan Desktop** on your laptop to join your home LAN over the VPN built into your UniFi Dream Machine. You do not need to expose SA Hub to the public internet.

### Google OAuth and private IPs

Google **does not allow** redirect URIs like `http://192.168.x.x/...`. You will see errors such as *“must end with a public top-level domain”* or *“valid top private domain”*. Allowed options for a personal setup:

| Redirect URI | Works? |
|--------------|--------|
| `http://localhost:3000/api/auth/google/callback` | Yes |
| `http://127.0.0.1:3000/api/auth/google/callback` | Yes |
| `http://192.168.1.50:3000/...` | **No** |
| `https://yourdomain.com/...` | Yes (real domain + HTTPS) |

**Recommended with WiFiMan:** keep OAuth on **localhost** and use an SSH port forward from your laptop to the SA Hub host (below). Leave `PUBLIC_URL` / `GOOGLE_REDIRECT_URI` unset in `.env` (defaults are fine).

In [Google Cloud Console](https://console.cloud.google.com) → OAuth client → **Authorized redirect URIs**, use only:

```text
http://localhost:3000/api/auth/google/callback
```

Remove any `192.168.x.x` entries you added.

### 1. On the Dream Machine

1. Open **UniFi Network** → your UDM → **Settings** → **Teleport** (or **VPN**).
2. Enable it and link your Ubiquiti account for WiFiMan.
3. Give the SA Hub machine a **fixed LAN IP** (e.g. `192.168.1.50`).

### 2. On your laptop (each session)

1. Connect **WiFiMan Desktop** to your site.
2. Forward ports over SSH (replace user/IP):

```bash
ssh -N -L 3000:127.0.0.1:3000 youruser@192.168.1.50
```

3. Open **http://localhost:3000** in the browser (not the `192.168.x.x` URL).

Google sign-in and the rest of the app use the same origin; OAuth callbacks hit `localhost` on your laptop, which SSH forwards to the server.

For a public **HTTPS domain** on RHEL, see [Production: your domain + HTTPS + login](#production-your-domain--https--login) above.

### Security notes

- Do not forward ports **3000**, **8000**, or **11434** on the WAN firewall.
- Without `AUTH_*` set, VPN/LAN users could use SA Hub by IP; set app login for production or use SSH + localhost only.

---

## Data & Privacy

- All data is stored locally in `./data/sa_hub.db` (SQLite)
- Nothing is sent anywhere except to Google APIs (your own account); AI runs locally via Ollama
- Gmail access is read-only; the app never sends emails

---

## Development (without Docker)

**Backend** (requires Ollama running locally on port 11434):

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env  # fill in values
# For local dev, point at host Ollama:
export LLM_BASE_URL=http://localhost:11434/v1
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev  # runs on :5173, proxies /api to :8000
```
