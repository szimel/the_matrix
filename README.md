# The Matrix's GitOps Infrastructure

This repository is the single source of truth for the Docker stacks running on the server.
Where this README and a `docker-compose.yml` disagree, the compose file wins.

## 🏗️ Architecture: Why is it set up this way?

1. **Split Compose Files:** We do not use one giant `docker-compose.yml`. Breaking apps into logical stacks (Media, Music, Productivity, etc.) limits the "blast radius." If you make a typo in a media container and Docker restarts the stack, it won't take down Vaultwarden (passwords) or Vikunja (tasks) in the process.
2. **GitOps (Dockhand):** Dockhand acts as the orchestrator. You do not run `docker compose up` manually anymore. You edit code here, push to GitHub, and Dockhand automatically pulls the changes and deploys them.
3. **Secure Webhooks (Cloudflared):** To make Git deployments instant without opening firewall ports, we run a Cloudflare Zero Trust Tunnel (`cloudflared`). GitHub sends the webhook ping to a Cloudflare subdomain -> Cloudflare securely tunnels it to the `cloudflared` container -> which hands it to Dockhand to trigger the update.

## 📂 Folder Breakdown

All folders reside on the host at `/home/abed_23/apps/`.

* **`/media`** - The *Arr stack: Radarr, Sonarr, Prowlarr, Flaresolverr, Cleanuparr, Transmission + Gluetun (VPN). *Does not include Jellyfin — see `/streaming`.*
* **`/streaming`** - Jellyfin and Seerr. Kept separate from `/media` so Arr-stack maintenance never takes the user-facing frontends down.
* **`/music`** - Navidrome, Soulseek (`slskd`), and Soulsync.
* **`/productivity`** - Vaultwarden, Actual Budget, Vikunja, Omni Tools, BentoPDF, FreshRSS, Mealie, the custom Python `notifications` bot, and the `productivity-feed` (YouTube replacement) service.
* **`/tdarr`** - Tdarr server + `tdarr-node` (iGPU-accelerated transcoding).
* **`/monitoring`** - Beszel + `beszel-agent` (resource stats) and Cloudflared (Zero Trust Tunnel).
* **`/pangolin`** - `pangolin-site`, the WireGuard tunnel endpoint for public media ingress.
* **`/caddy`** - Reverse proxy. **Not tracked** (Caddyfile is host-only, as are its `cloudflare` DNS-plugin build credentials).
* **`/dockhand`** - The GitOps manager. **Not tracked** — standalone stack, deployed by hand.

*Note: All stacks share a common external Docker network called `caddy_net` so the reverse proxy can route traffic seamlessly.*

## 📦 Services and Ports

| Stack | Service | Container / image | Host port | Notes |
| --- | --- | --- | --- | --- |
| media | gluetun | `qmcgaw/gluetun` | 9091, 51413/tcp+udp | Mullvad WireGuard; owns transmission's network |
| media | transmission | `lscr.io/linuxserver/transmission` | — | `network_mode: service:gluetun`, no port mapping of its own |
| media | prowlarr | `lscr.io/linuxserver/prowlarr` | 9696 | |
| media | radarr | `lscr.io/linuxserver/radarr` | 7878 | |
| media | sonarr | `lscr.io/linuxserver/sonarr` | 8989 | |
| media | flaresolverr | `ghcr.io/flaresolverr/flaresolverr` | 8191 | |
| media | cleanuparr | `ghcr.io/cleanuparr/cleanuparr` | 11011 | |
| streaming | seerr | `ghcr.io/seerr-team/seerr` | 5055 | `init: true`, explicit DNS 1.1.1.1 / 8.8.8.8 |
| streaming | jellyfin | `lscr.io/linuxserver/jellyfin` | 8096 | iGPU passthrough, `/mnt/media` mounted `:ro` |
| music | navidrome | `deluan/navidrome` | 4533 | |
| music | slskd | `slskd/slskd` | 5030, 50300 | |
| music | soulsync | `ghcr.io/nezreka/soulsync` | 8008 | |
| tdarr | tdarr | `ghcr.io/haveagitgat/tdarr` | 8265, 8266 | server, no iGPU |
| tdarr | tdarr-node | `ghcr.io/haveagitgat/tdarr_node` | — | iGPU passthrough, node name `thinkpad-node` |
| productivity | actual-server | `actualbudget/actual-server` | 5006 | |
| productivity | productivity-feed | `ghcr.io/szimel/youtube-lobotomy:main` | 9090 → 8080 | container name is `youtube-replacer`; app listens on 8080 (see gotcha 5) |
| productivity | vaultwarden | `vaultwarden/server` | 8080 → 80 | |
| productivity | vikunja | `vikunja/vikunja` | 3456 | |
| productivity | notifications | built from `./notifications` | 8001 | custom Python, `python:3.11-alpine` |
| productivity | omni-tools | `iib0011/omni-tools` | 8085 → 80 | |
| productivity | bentopdf | `bentopdf/bentopdf` | 8086 → 8080 | |
| productivity | freshrss | `lscr.io/linuxserver/freshrss` | 8087 → 80 | |
| productivity | mealie | `ghcr.io/mealie-recipes/mealie` | 9925 → 9000 | |
| monitoring | beszel | `henrygd/beszel` | — | no host port; Caddy proxies to it on `caddy_net` |
| monitoring | beszel-agent | `henrygd/beszel-agent` | — | `network_mode: host`, talks to the hub over a unix socket |
| monitoring | cloudflared | `cloudflare/cloudflared` | — | `tunnel run` with `TUNNEL_TOKEN` |
| pangolin | pangolin-site | `fosrl/pangolin-cli` | — | `NET_ADMIN` required for the tunnel interface |

Ports here are the **host-side** mappings. Reverse-proxy hostnames are defined in the host-only Caddyfile, not in this repo. For reference, that Caddyfile currently maps: `movies`→jellyfin, `radarr`, `sonarr`, `prowlarr`, `seerr`, `transmission`→gluetun:9091, `logs`→beszel:8090, `music`→navidrome, `slskd`, `soulsync`, `budget`→actual-server, `dockhand`, `passwords`→vaultwarden:80, `tasks`→vikunja, `cleanuparr`, `omni`→omni-tools:80, `pdf`→bentopdf:8080, `rss`→freshrss:80, `meals`→mealie:9000, `tdarr`→tdarr:8265, `youtube`→productivity-feed:9090.

### Hardware acceleration

Intel iGPU is passed into `jellyfin` and `tdarr-node` as `/dev/dri/renderD128`, with the container added to render group `991`. If a rebuilt container loses transcoding, check those two lines first.

## 🔐 Public ingress (Pangolin)

Jellyfin/Seerr are not exposed by opening router ports. The path is:

```
user -> movies.bigdaddyz.com (Cloudflare DNS-only / grey cloud)
     -> Cloudy Matrix (Oracle VPS) :80/:443
     -> Traefik -> WireGuard tunnel (51820/21820)
     -> pangolin-site on The Matrix
     -> caddy_net -> jellyfin:8096 / seerr:5055
```

Everything else behind `*.bigdaddyz.com` is proxied internally by Caddy via Cloudflare's DNS-01 challenge.

## 🧠 Future-Me Reminders & Gotchas

### 1. The `.gitignore` Allowlist
This repository uses an **allowlist** approach. `/*` ignores everything at the root, then each stack directory is re-admitted with an explicit `!/dir` + `/dir/*` + `!dir/docker-compose.yml` block. Only these files are ever tracked:

```
.gitignore, README.md
*/docker-compose.yml
music/slskd/slskd.example.yml
productivity/notifications/{Dockerfile,main.py}
```

**Consequence:** a brand-new stack folder is *not* tracked until you add its allowlist block, and any new file type (a `.sh`, a `.json`, a second compose file) is silently ignored. If `git status` looks empty after adding a file, this is why.

### 2. Volumes vs. Builds (The Path Trap)
When editing `docker-compose.yml` files, pay close attention to paths:
* **Volumes use `${ROOT_DIR}`:** (e.g., `${ROOT_DIR}/radarr/config:/config`). This tells Dockhand to mount data from the *actual host hard drive.*
* **Builds use `./`:** (e.g., `build: ./notifications`). Dockhand needs to build the image from the files it just downloaded from GitHub. It cannot read the host's hard drive to find the `Dockerfile`, so we use relative paths here.

One known deviation from that rule:
* `actual-server` mounts the absolute host path `/mnt/actual-data:/data` (a separate mount, not under `ROOT_DIR`).

`productivity-feed` used to bind-mount `./data:/app/data` — a **relative volume** path. Unlike a
build path, a relative bind mount resolves against wherever Dockhand runs compose, so that data
sat in Dockhand's own container space and would have been lost on a Dockhand redeploy. It now uses
`${ROOT_DIR}/productivity-feed/data:/app/data`. If that service ever looks like it lost its
database, check whether data was migrated out of Dockhand's space when the path changed.

### 3. Environment Variables (`.env`)
Secrets (API tokens, VPN keys, `ROOT_DIR` paths) are **never** stored in GitHub. They are manually entered into the Dockhand Web UI under the **Environment / .env** tab for each specific stack. Dockhand encrypts them and injects them at runtime.

Variables referenced across the stacks: `ROOT_DIR`, `PUID`, `PGID`, `TZ`, `MULLVAD_PRIVATE_KEY`, `MULLVAD_ADDRESSES`, `SERVER_CITY`, `VAULTWARDEN_DOMAIN`, `VIKUNJA_URL`, `MEALIE_URL`, `DISCORD_WEBHOOK_URL`, `BESZEL_APP_URL`, `BESZEL_HUB_URL`, `BESZEL_TOKEN`, `BESZEL_KEY`, `CLOUDFLARE_TUNNEL_TOKEN`, `PANGOLIN_ENDPOINT`, `SITE_ID`, `SITE_SECRET`, `JEV_API_KEY`. `CLOUDFLARE_API_TOKEN` is used by Caddy, not by anything in this repo.

### 4. Tdarr pipeline
Tdarr configs live in `${ROOT_DIR}/tdarr/tdarr/configs` (note the doubled `tdarr/tdarr`) and are **not tracked here**. Current plugin-stack intent: strip PGS/VobSub subtitles, convert all audio to AAC, encode video with the Boosh QSV plugin to 10-bit H.265, target-bitrate modifier `0.5`, skipping sources under 5000 kbps. `/mnt/media/tdarr_temp` must stay on the same drive as `/mnt/media` or transcodes fall back to slow cross-device copies.

### 5. productivity-feed: the container port is always 8080
`productivity-feed` is the only stack whose service name and `container_name` differ
(`productivity-feed` vs `youtube-replacer`). Two consequences, both of which have bitten:

* **Container port stays 8080.** The image hardcodes `PORT=8080` for gunicorn and its
  healthcheck probes the same variable. The host port is whatever we like (`9090`), so the
  mapping must be `9090:8080`. Publishing `9090:9090` leaves nothing on the host port and
  Caddy answers **502** — which is exactly what happened the first time.
* **DNS alias required.** Compose gives a container its *service* name on the network, so
  `productivity-feed` would resolve — but only if `container_name` were left unset. Because
  `container_name: youtube-replacer` overrides it, the compose file sets
  `networks.caddy_net.aliases: [productivity-feed]` so the Caddyfile's
  `reverse_proxy productivity-feed:9090` keeps working.

If it 502s again: `docker ps --filter name=youtube-replacer` should read `0.0.0.0:9090->8080/tcp`,
and `docker run --rm --network caddy_net alpine nslookup productivity-feed` must return an address.

## 🚀 How to update a service
1. Edit the `docker-compose.yml` or script locally or directly on GitHub, add environment variables via Dockhand.
2. Commit and push the changes to the `main` branch.
3. GitHub sends a webhook through Cloudflare to Dockhand.
4. Dockhand automatically recompiles (if needed) and gracefully recreates only the containers that changed.

> **Note:** changes to `/caddy` and `/dockhand` are made on the host and are not picked up by this pipeline, because those folders are deliberately untracked.
