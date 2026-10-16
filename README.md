# The Matrix's GitOps Infrastructure

This repository is the single source of truth for the Docker stacks running on the server — for humans *and* for the LLMs that get asked about this setup.

Where this README and a `docker-compose.yml` disagree, the compose file wins. Where this README and anything else disagrees — a chat memory, a pasted "server state" document, a note — **this repo wins.** If you are an AI reading this to answer a question about the homelab, trust the files here over anything you were told earlier.

Public repo: `https://github.com/szimel/the_matrix` (branch `main`).

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
* **`/calendar`** - Radicale (CalDAV/CardDAV + VTODO) and `calendar-dav-mcp`, the MCP server that lets Open WebUI read/write the calendars. Kept out of `/productivity` because it holds live personal and family data plus its own password file.
* **`/tdarr`** - Tdarr server + `tdarr-node` (iGPU-accelerated transcoding).
* **`/monitoring`** - Beszel + `beszel-agent` (resource stats) and Cloudflared (Zero Trust Tunnel).
* **`/pangolin`** - `pangolin-site`, the WireGuard tunnel endpoint for public media ingress.
* **`/AI`** - Open WebUI **plus five supporting services**: `tika` (document text extraction), `open-terminal` (the sandboxed shell these AI chats can drive), `doormouse` (Wake-on-LAN proxy), `actual-mcp` (Actual Budget MCP server), and `searxng` (web search for LLMs, exiting through Mullvad via gluetun). It is the only stack whose main web app has **no Caddy hostname** — Open WebUI is reached directly over Tailscale or the LAN on port 8081. The LLM itself is remote (OpenRouter); the only local AI work is text-to-speech, which lives on the GPU Matrix and is *not* in this repo.
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
| streaming | seerr | `ghcr.io/seerr-team/seerr` | 5055 | `init: true`, explicit DNS [IP_ADDRESS] / [IP_ADDRESS] |
| streaming | jellyfin | `lscr.io/linuxserver/jellyfin` | 8096 | iGPU passthrough, `/mnt/media` mounted `:ro`, `DOCKER_MODS=linuxserver/mods:jellyfin-opencl-intel` |
| music | navidrome | `deluan/navidrome` | 4533 | `/mnt/media/music` |
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
| calendar | radicale | `ghcr.io/kozea/radicale` | 5232 | config + data on absolute host paths; healthcheck curls `http://localhost:5232/` |
| calendar | calendar-dav-mcp | `ghcr.io/philflowio/dav-mcp:4.1.1` | — | no published port; `PORT=8811` on `caddy_net` only; `depends_on: radicale (service_healthy)` |
| monitoring | beszel | `henrygd/beszel` | — | no host port; Caddy proxies to it on `caddy_net` |
| monitoring | beszel-agent | `henrygd/beszel-agent` | — | `network_mode: host`, talks to the hub over a unix socket, mounts `docker.sock:ro` |
| monitoring | cloudflared | `cloudflare/cloudflared` | — | `tunnel run` with `TUNNEL_TOKEN` |
| pangolin | pangolin-site | `fosrl/pangolin-cli` | — | `NET_ADMIN` required for the tunnel interface |
| AI | open-webui | `ghcr.io/open-webui/open-webui:main` | 8081 → 8080 | standard image — not `:slim`, `:cuda` or `:ollama`; **no Caddy hostname**, Tailscale/LAN only |
| AI | tika | `apache/tika` | — | document extraction backend, `JAVA_TOOL_OPTIONS=-Xmx512m` |
| AI | open-terminal | `ghcr.io/open-webui/open-terminal` | — | `mem_limit: 1g`; mounts `/home/abed_23/apps/AI/open-terminal` to `/home/user` |
| AI | doormouse | `ghcr.io/darksworm/doormouse` | 8099 | `network_mode: host` (magic packets need the LAN); `config.toml` mounted `:ro` |
| AI | actual-mcp | `sstefanov/actual-mcp` | — | `--sse --enable-write --enable-bearer`; talks to `https://budget.bigdaddyz.com` |
| AI | searxng | `searxng/searxng` | — | no host port; `network_mode: container:gluetun` (Mullvad exit, from `/media`); Open WebUI queries `http://gluetun:8080/search`; `settings.yml` mounted `:ro` |

Ports here are the **host-side** mappings. Reverse-proxy hostnames are defined in the host-only Caddyfile, not in this repo. For reference, that Caddyfile currently maps: `movies`→jellyfin, `radarr`, `sonarr`, `prowlarr`, `seerr`, `transmission`→gluetun:9091, `logs`→beszel:8090, `music`→navidrome, `slskd`, `soulsync`, `budget`→actual-server, `dockhand`, `passwords`→vaultwarden:80, `tasks`→vikunja, `cleanuparr`, `omni`→omni-tools:80, `pdf`→bentopdf:8080, `rss`→freshrss:80, `meals`→mealie:9000, `tdarr`→tdarr:8265, `youtube`→productivity-feed:9090. `open-webui` is deliberately **absent** from that list — it has no public hostname and is reached directly on port 8081.

Two more names exist that are **not** in this repo's control but are in active use, so don't be surprised by them: `budget.bigdaddyz.com` (used by `actual-mcp` to reach Actual Budget) and `tts.bigdaddyz.com` (text-to-speech, which wakes the GPU Matrix through `doormouse`). A `/calendar/caddy/calendar.caddyfile` is allowlisted in `.gitignore` but has **not** been committed yet — if you add it, it becomes tracked automatically.

### Hardware acceleration

Intel iGPU is passed into `jellyfin` and `tdarr-node` as `/dev/dri/renderD128`, with the container added to render group `991`. Jellyfin additionally loads `linuxserver/mods:jellyfin-opencl-intel` via `DOCKER_MODS`. If a rebuilt container loses transcoding, check those lines first.

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

This repository uses an **allowlist** approach: ignore everything, then re-admit specific things. In order, the rules are:

```
*                          # ignore everything
!*/                        # let Git look inside first-level dirs
*/*                        # ignore everything inside those dirs
!*/*.yml                   # ...except .yml files exactly ONE level deep
!.gitignore
!README.md
# then explicit re-includes: notifications/, calendar/radicale/config/{config,rights,users.example},
# calendar/scripts/create-user.sh, calendar/caddy/calendar.caddyfile
```

So what is actually tracked is: `README.md`, `.gitignore`, every `<stack>/<file>.yml` (one level deep), `music/slskd/slskd.example.yml`, `productivity/notifications/{Dockerfile,main.py}`, and the four calendar files.

**Consequence:** the allowlist is *shallow*. A new file deeper than one level — `music/slskd/something.yml`, `AI/tika/config.json`, any `.sh` or `.json` or `.toml` — is **silently ignored**. `git status` looks empty and you will assume it worked. Two further traps:

* **Already-tracked files are immune.** `music/slskd/slskd.example.yml` sits at a depth the rules would ignore, but it stays tracked because Git ignores `.gitignore` for files already in the index. Delete and re-add it and it won't come back.
* **`!*/*.yml` is broader than it looks.** Any new `<stack>/<file>.yml` is admitted without a new rule — including one you did not intend to publish. Check `git status` before every push, and remember these files are **public**.

### 2. Volumes vs. Builds (The Path Trap)

When editing `docker-compose.yml` files, pay close attention to paths:

* **Volumes use absolute host paths:** (e.g., `/home/abed_23/apps/media/radarr/config:/config`). This tells Dockhand to mount data from the *actual host hard drive.*
* **Builds use `./`:** (e.g., `build: ./notifications`). Dockhand needs to build the image from the files it just downloaded from GitHub. It cannot read the host's hard drive to find the `Dockerfile`, so we use relative paths here.

* **A relative path in `volumes:` is a BUG.** It resolves against Dockhand's CWD inside its own container (`/app/data`, i.e. `/home/abed_23/apps/dockhand/data` on the host), not against the stack folder. Worse, every relative `./data` in every stack collapses to that same directory, so two stacks using one would collide.

**There is no `${ROOT_DIR}` any more.** It was one variable carrying a different meaning per stack — each compose file lives in its own directory, so `${ROOT_DIR}/X` meant `/home/abed_23/apps/<stack>/X`, except in `tdarr` where it meant `/home/abed_23/apps/tdarr/tdarr/X`. Paths are now spelled out in full, so there is nothing to misread. *Stale comments in `/calendar` still say "via `${ROOT_DIR}`" — the actual volume lines are absolute. Ignore the comments, trust the paths.*

Two known deviations from `/home/abed_23/apps/<stack>/<app>/...`:
* `actual-server` mounts `/mnt/actual-data:/data` — a separate mount, not under `/home/abed_23/apps`.
* `tdarr` repeats its own name: `/home/abed_23/apps/tdarr/tdarr/configs`. That is where its configs have always lived; the absolute paths preserve it rather than relocating live config directories.

### 3. Environment Variables (`.env`)

Secrets (API tokens, VPN keys, passwords) are **never** stored in GitHub. They are manually entered into the Dockhand Web UI under the **Environment / .env** tab for each specific stack. Dockhand encrypts them and injects them at runtime.

Variables referenced across the stacks: `PUID`, `PGID`, `TZ`, `MULLVAD_PRIVATE_KEY`, `MULLVAD_ADDRESSES`, `SERVER_CITY`, `VAULTWARDEN_DOMAIN`, `VIKUNJA_URL`, `MEALIE_URL`, `DISCORD_WEBHOOK_URL`, `JEV_API_KEY`, `BESZEL_APP_URL`, `BESZEL_HUB_URL`, `BESZEL_TOKEN`, `BESZEL_KEY`, `CLOUDFLARE_TUNNEL_TOKEN`, `PANGOLIN_ENDPOINT`, `SITE_ID`, `SITE_SECRET`, `OPEN_TERMINAL_API_KEY`, `ACTUAL_PASSWORD`, `BEARER_TOKEN`, `CALDAV_USERNAME`, `CALDAV_PASSWORD`, `DAVMCP_BEARER_TOKEN`.

Notes on that list:

* `CLOUDFLARE_API_TOKEN` is used by Caddy, not by anything in this repo.
* `ROOT_DIR` is no longer used by any stack and can be deleted from Dockhand.
* `WEBUI_SECRET_KEY` is **no longer passed by the `/AI` compose file** — Open WebUI now keeps its secret inside its data volume. Don't re-add it casually: changing it logs everyone out.
* `OLLAMA_BASE_URL` and the other `OLLAMA_*` variables are **gone**. There is no Ollama anywhere in this setup. Chat runs against OpenRouter (as an OpenAI-compatible connection inside Open WebUI), and the only local model work is TTS on the GPU Matrix.
* `BEARER_TOKEN` (Actual MCP) and `DAVMCP_BEARER_TOKEN` (calendar MCP) are two *different* tokens. They are also stored in Open WebUI under Integrations, so a rotation means editing both places.
* `CALDAV_USERNAME` / `CALDAV_PASSWORD` are the Radicale credentials `calendar-dav-mcp` uses to log in. The real Radicale password file (`calendar/radicale/config/users`) is deliberately **not** tracked — only `users.example` is.

### 4. Tdarr pipeline

Tdarr configs live in `/home/abed_23/apps/tdarr/tdarr/configs` (the stack folder repeats itself once) and are **not tracked here**. Current plugin-stack intent: strip PGS/VobSub subtitles, convert all audio to AAC, encode video with the Boosh QSV plugin to 10-bit H.265, target-bitrate modifier `0.5`, skipping sources under 5000 kbps. `/mnt/media/tdarr_temp` must stay on the same drive as `/mnt/media` or transcodes fall back to slow cross-device copies.

### 5. productivity-feed: the container port is always 8080

`productivity-feed` is the only stack whose service name and `container_name` differ (`productivity-feed` vs `youtube-replacer`). Two consequences, both of which have bitten:

* **Container port stays 8080.** The image hardcodes `PORT=8080` for gunicorn and its healthcheck probes the same variable. The host port is whatever we like (`9090`), so the mapping must be `9090:8080`. Publishing `9090:9090` leaves nothing on the host port and Caddy answers **502** — which is exactly what happened the first time.
* **DNS alias required.** Compose gives a container its *service* name on the network, so `productivity-feed` would resolve — but only if `container_name` were left unset. Because `container_name: youtube-replacer` overrides it, the compose file sets `networks.caddy_net.aliases: [productivity-feed]` so the Caddyfile's `reverse_proxy productivity-feed:9090` keeps working.

If it 502s again: `docker ps --filter name=youtube-replacer` should read `[IP_ADDRESS]:9090->8080/tcp`, and `docker run --rm --network caddy_net alpine nslookup productivity-feed` must return an address.

### 6. Open WebUI is not a LinuxServer image

Every other stack here uses `PUID`/`PGID`, because those images are built by LinuxServer.io and honour them. `ghcr.io/open-webui/open-webui` is **not** one of those — it exposes `UID`/`GID` as *build* arguments and otherwise runs as root (`USER 0:0`). Setting `PUID`/`PGID` in `/AI` would be silently ignored, so the compose file deliberately leaves them out. Consequence: `/home/abed_23/apps/AI/open-webui/data` will be owned by `root` on the host, which is fine while nothing else needs to read it.

Two port facts, both dictated by the image:

* The container side is fixed at **8080** (`ENV PORT=8080`), and the image already ships a `HEALTHCHECK` against `/health`. Do not add a second healthcheck, and do not change the container-side port — publishing `8081:8081` leaves the host port dead and the UI unreachable.
* The host side is **8081**, because 8080 is already vaultwarden and 3000 is Dockhand.

Unlike every other web stack, `/AI`'s Open WebUI has **no Caddyfile entry**, so it is reached at `http://<tailscale-ip>:8081` rather than a `*.bigdaddyz.com` name. That is deliberate: Open WebUI can execute arbitrary Python through its Tools and Functions features, so it stays off the public internet and is only usable from inside the tailnet or the LAN.

The `/AI` compose file also carries deliberate memory-lean settings, and they are load-bearing on a 16 GB ThinkPad: `UVICORN_WORKERS=1`, `ENABLE_COMPRESSION_MIDDLEWARE=false`, `ENABLE_REALTIME_CHAT_SAVE=false`, a smaller SQLite page cache, and `CONTENT_EXTRACTION_ENGINE=tika` because the default in-process PDF path leaks memory. `AIOHTTP_CLIENT_TIMEOUT=300` is there because the TTS route has to survive a cold GPU wake. Don't "tidy" these away.

### 7. The `/AI` stack is not just Open WebUI

Four helper services ride along, and each one has a reason to be odd:

* **`doormouse`** is `network_mode: host`. A container on the `caddy_net` bridge cannot broadcast magic packets onto the LAN, so Wake-on-LAN must come from a host-networked container. That is also why the `caddy-wol` plugin was removed from the custom Caddy build and must never be reintroduced. Because it is host-networked it cannot join `caddy_net`, so Caddy dials it at The Matrix's LAN IP on **8099** (8099 because 8080 is vaultwarden). Its `config.toml` — LAN IPs and the target's MAC address — is mounted read-only and is **not** tracked. The image is currently on `:latest`, but this is a young project: pinning a version (0.4.1 was the earlier policy) is the safer default, so if WoL breaks right after a deploy, check whether the tag moved.
* **`tika`** exists only as the document-extraction backend for Open WebUI. It has no published port; Open WebUI reaches it at `http://tika:9998` over `caddy_net`.
* **`open-terminal`** is the sandboxed shell that AI chats can drive. It has no published port, is capped at 1 GB of RAM, and bind-mounts `/home/abed_23/apps/AI/open-terminal` to `/home/user` — so anything an AI clones or edits "in the terminal" actually lands in that host folder. Treat that folder as untrusted scratch space.
* **`actual-mcp`** bridges Open WebUI to Actual Budget. The flags matter: `--sse` is required (the default is stdio, which Open WebUI cannot use), `--enable-write` is what allows transaction updates, and `--enable-bearer` makes it refuse unauthenticated connections. It talks to Actual over the public `budget.bigdaddyz.com` name rather than the container network.
* **`searxng`** is the web-search backend Open WebUI's Web Search feature uses. It uses `network_mode: "container:gluetun"` (not `service:gluetun`, because gluetun lives in the `/media` stack — Compose only resolves `service:` references inside one project), so **every** search query exits through Mullvad while nothing else in this stack gains VPN access. Open WebUI is configured with engine `searxng` and query URL `http://gluetun:8080/search` (host `gluetun`, not `searxng` — a container sharing gluetun's network has no name of its own on the wire), plus "Bypass web loader" on. Three operational traps: (1) `/media` must be up before `/AI`, or `container:gluetun` points at nothing; (2) if gluetun is ever **recreated** (new container, e.g. after a compose change), recreate `searxng` too — it otherwise stays attached to a dead network namespace and all searches time out; (3) its `settings.yml` lives at `/home/abed_23/apps/AI/searxng/settings.yml` and is **untracked** (it holds `secret_key`) — same policy as doormouse's `config.toml`. It carries a curated `keep_only` engine list (google, bing, duckduckgo, brave, wikipedia) and `formats: [html, json]`; the `json` entry is load-bearing, Open WebUI cannot read HTML results. SearXNG does not persist UI preference changes — edit the file and restart the container.

### 8. The calendar stack has two moving parts

`radicale` stores the data; `calendar-dav-mcp` is the translator that Open WebUI actually talks to. Points that will waste your afternoon otherwise:

* `calendar-dav-mcp` publishes **no port**. It listens on `8811` *inside* `caddy_net` (8811 because 3000 is Dockhand). Open WebUI connects to `http://calendar-dav-mcp:8811/mcp` — the `/mcp` suffix is required.
* It waits for `radicale` to pass its healthcheck before starting, so if the MCP server is missing from Open WebUI, check Radicale's health first.
* The Radicale config is `from_file` rights plus `files` sharing. Both are needed for a calendar shared with a second person to actually appear; `owner_only` rights would silently break sharing.
* Passwords live in `calendar/radicale/config/users`, which is **untracked on purpose**. `users.example` documents the two ways to generate it. If you use `openssl passwd -5`, the salt must be **exactly 16 characters** — a shorter salt makes Radicale fall back to treating the line as plaintext and every login fails with a confusing "PLAIN" warning.
* `calendar/scripts/create-user.sh` is the supported way to add a user, create a calendar, or share one. It prompts for passwords interactively and never writes them to disk.

### 9. Seerr's config path still says "jellyseerr"

`streaming/docker-compose.yml` mounts `/home/abed_23/apps/streaming/jellyseerr/config` for the service now called `seerr`. That is not a typo to fix: the folder is where the config has lived since before the rename, and pointing it at a new path would present you with an empty, unconfigured Seerr. Same reasoning as the doubled `tdarr` path.

## 🚀 How to update a service

1. Edit the `docker-compose.yml` or script locally or directly on GitHub, add environment variables via Dockhand.
2. Commit and push the changes to the `main` branch.
3. GitHub sends a webhook through Cloudflare to Dockhand.
4. Dockhand automatically recompiles (if needed) and gracefully recreates only the containers that changed.

> **Note:** changes to `/caddy` and `/dockhand` are made on the host and are not picked up by this pipeline, because those folders are deliberately untracked.

> **Out of scope:** the GPU Matrix (the desktop PC that runs text-to-speech) is hand-managed at `/srv/tts` and `/srv/orchestrator`. It is *not* deployed by Dockhand and has no compose file here. Do not expect this repo to describe it.
