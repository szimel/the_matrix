# The Matrix's GitOps Infrastructure

This repository is the single source of truth for all Docker containers running on the server. 

## 🏗️ Architecture: Why is it set up this way?

1. **Split Compose Files:** We do not use one giant `docker-compose.yml`. Breaking apps into logical stacks (Media, Music, Productivity, etc.) limits the "blast radius." If you make a typo in a media container and Docker restarts the stack, it won't take down Vaultwarden (passwords) or Vikunja (tasks) in the process.
2. **GitOps (Dockhand):** Dockhand acts as the orchestrator. You do not run `docker compose up` manually anymore. You edit code here, push to GitHub, and Dockhand automatically pulls the changes and deploys them.
3. **Secure Webhooks (Cloudflared):** To make Git deployments instant without opening firewall ports, we run a Cloudflare Zero Trust Tunnel (`cloudflared`). GitHub sends the webhook ping to a Cloudflare subdomain -> Cloudflare securely tunnels it to the `cloudflared` container -> which hands it to Dockhand to trigger the update.

## 📂 Folder Breakdown

All folders reside on the host at `/home/abed_23/apps/`.

* **`/media`** - The *Arr stack, Jellyfin, Transmission + Gluetun (VPN), and Cleanuparr.
* **`/music`** - Navidrome, Soulseek (`slskd`), and Soulsync.
* **`/productivity`** - Vaultwarden, Actual Budget, Vikunja, OmniTool, Bento, and a custom ultra-lightweight Python bot (`vikunja-discord`) for rich Discord notifications.
* **`/monitoring`** - Beszel (resource stats) and Cloudflared (Zero Trust Tunnel).
* **`/caddy`** - Reverse proxy (not tracked).
* **`/dockhand`** - The GitOps manager (not tracked).

*Note: All stacks share a common external Docker network called `caddy_net` so the reverse proxy can route traffic seamlessly.*

## 🧠 Future-Me Reminders & Gotchas

### 1. The `.gitignore` Allowlist
This repository uses an **allowlist** approach. By default, it ignores *everything*. It only syncs specific file types (`.yml`, `.py`, `Dockerfile`, `Caddyfile`). 

### 2. Volumes vs. Builds (The Path Trap)
When editing `docker-compose.yml` files, pay close attention to paths:
* **Volumes use `${ROOT_DIR}`:** (e.g., `${ROOT_DIR}/jellyfin/config:/config`). This tells Dockhand to mount data from the *actual host hard drive.*
* **Builds use `./`:** (e.g., `build: ./vikunja-discord`). Dockhand needs to build the image from the files it just downloaded from GitHub. It cannot read the host's hard drive to find the `Dockerfile`, so we use relative paths here.

### 3. Environment Variables (`.env`)
Secrets (API tokens, VPN keys, `ROOT_DIR` paths) are **never** stored in GitHub. They are manually entered into the Dockhand Web UI under the **Environment / .env** tab for each specific stack. Dockhand encrypts them and injects them at runtime. 

## 🚀 How to update a service
1. Edit the `docker-compose.yml` or script locally or directly on GitHub, add envirnment variables via dockhand
2. Commit and push the changes to the `main` branch.
3. GitHub sends a webhook through Cloudflare to Dockhand.
4. Dockhand automatically recompiles (if needed) and gracefully recreates only the containers that changed.
