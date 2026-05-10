// Cloudflare Pages Function — stub for /api/yt.
//
// The Splitter's URL feature routes YouTube / SoundCloud / Bandcamp links
// through /api/yt because they need an extractor (yt-dlp), not a generic
// HTTP proxy. yt-dlp is a Python tool with binary deps (ffmpeg) that
// Cloudflare Workers can't run. So on the deployed site we return a
// clear error explaining the limitation.
//
// The local dev server (server.py) implements the real /api/yt endpoint
// using yt-dlp via subprocess.

export async function onRequestGet() {
  return new Response(
    'yt-dlp extraction is local-only. Run server.py on your machine ' +
    '(pip install --user yt-dlp) and open http://localhost:8765/ — ' +
    'the deployed site cannot extract YouTube / SoundCloud audio.',
    {
      status: 501,
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    },
  );
}
