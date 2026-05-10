# yt-dlp service for FYmuse

A tiny Docker service that wraps `yt-dlp` behind a single HTTP endpoint.
Hosted on Fly.io. Used by FYmuse's Cloudflare Pages Function as a
fallback when YouTube blocks Cloudflare's datacenter IPs.

## Endpoints

`GET /healthz` → 200 `ok` (used by Fly's health checks).

`GET /?url=<encoded-url>` → streams audio bytes from the best audio-only
format available for that URL via `yt-dlp -f bestaudio -o -`.

## Deploy to Fly.io

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
