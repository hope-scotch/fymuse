# yt-dlp service for FYmuse

A tiny Docker service that wraps `yt-dlp` behind a single HTTP endpoint.
Hosted on Fly.io. Used by FYmuse's Cloudflare Pages Function as a
fallback when YouTube blocks Cloudflare's datacenter IPs.

## Endpoints

`GET /healthz` → 200 `ok` (used by Fly's health checks).

`GET /?url=<encoded-url>` → streams audio bytes from the best audio-only
format available for that URL via `yt-dlp -f bestaudio -o -`.

## Deploy to Render (free tier, recommended)

The repo root has a `render.yaml` Blueprint. To deploy:

1. Sign up at https://render.com (no credit card required).
2. Connect your GitHub account.
3. **New → Blueprint** → select the `fymuse` repo → **Apply**.
4. Wait ~5 min for the first Docker build.
5. Once it goes green, copy the URL Render assigns (e.g. `https://fymuse-yt.onrender.com`).

Smoke test:

```bash
curl -I https://fymuse-yt.onrender.com/healthz
# HTTP/2 200
```

The free plan sleeps the service after 15 min of inactivity. The first
request after sleep takes ~30-60 s while the container wakes up;
subsequent requests are normal speed. Acceptable for personal use.

After deploy, wire it into Cloudflare Pages — see "Wire it up to
Cloudflare Pages" section below.

## Deploy to Fly.io (alternative, paid)

Fly.io killed their truly-free tier in late 2024. The minimum is now
~$5/month on the Pay-As-You-Go plan, applied as account credit. If
you've already hit a "high risk account" verification charge during
`fly launch`, that's the same thing.

Upside vs. Render: machines auto-stop on idle but wake instantly
(no 30-60s cold start), and Fly's IPs aren't blocked by YouTube as
often.

One time:

```bash
brew install flyctl   # or: curl -L https://fly.io/install.sh | sh
fly auth signup       # or: fly auth login
```

Then:

```bash
cd yt-service
fly launch --copy-config --no-deploy
# Accept the defaults. When prompted:
# - App name: pick something unique like fymuse-yt-<yourname>
# - Region: nearest to you (sin / ord / lhr / fra / syd / etc.)
# - Postgres / Redis / etc: No
fly deploy
```

After deploy, get the URL:

```bash
fly status
# look for "Hostname: fymuse-yt-<yourname>.fly.dev"
```

Quick smoke test:

```bash
curl -I "https://fymuse-yt-<yourname>.fly.dev/healthz"
# HTTP/2 200
```

## Wire it up to Cloudflare Pages

In the Cloudflare dashboard → your Pages project → Settings → Environment
variables → Production → add:

```
YT_SERVICE_URL = https://fymuse-yt-<yourname>.fly.dev
```

Trigger a redeploy. The Pages Function at `/api/yt` will now try
`youtubei.js` first; if that fails (or all clients are blocked), it
falls through to your Fly service.

## Cost

The free Fly.io allowance covers a single `shared-cpu-1x` machine with
256 MB RAM that auto-stops when idle. Cold starts add ~3–5 s to the
first request after a quiet period. After that, requests are warm.

## Notes

- `yt-dlp` breaks against YouTube every few weeks. Bump the version pin
  in `Dockerfile` and `fly deploy` to refresh.
- The container has a 200 MB hard cap on response size to prevent
  abuse if the service URL ever leaks.
- If you want to lock the service down so only your CF Pages can call
  it, set the `ALLOW_ORIGIN` env var on Fly to your Pages URL.
