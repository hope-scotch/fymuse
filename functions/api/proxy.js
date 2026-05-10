// Cloudflare Pages Function — same-origin proxy for arbitrary audio URLs.
//
// The Splitter's "Load from URL" feature lets the user paste a direct
// audio link. Most file hosts don't send Access-Control-Allow-Origin,
// so the browser blocks the fetch with a CORS error. This function
// re-fetches the URL server-side (no CORS in Workers) and streams the
// bytes back to the same origin, sidestepping the browser's CORS check.
//
// Endpoint: GET /api/proxy?url=<encoded-url>
//
// Hard cap on response size so this can't be abused as a free CDN.

const MAX_BYTES = 200 * 1024 * 1024; // 200 MB

export async function onRequestGet({ request }) {
  const u = new URL(request.url);
  const target = u.searchParams.get('url');
  if (!target) {
    return new Response('missing ?url=', { status: 400 });
  }
  let parsed;
  try {
    parsed = new URL(target);
  } catch {
    return new Response('invalid ?url=', { status: 400 });
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return new Response('only http(s) allowed', { status: 400 });
  }

  let upstream;
  try {
    upstream = await fetch(parsed.toString(), {
      headers: {
        'User-Agent': 'FYmuse-proxy/1.0',
        'Accept': '*/*',
      },
      redirect: 'follow',
      cf: { cacheEverything: true, cacheTtl: 86400 },
    });
  } catch (e) {
    return new Response('upstream fetch failed: ' + (e && e.message || e), { status: 502 });
  }

  if (!upstream.ok) {
    return new Response('upstream HTTP ' + upstream.status + ' ' + upstream.statusText, {
      status: 502,
    });
  }

  // Enforce size cap. If Content-Length is present and exceeds, refuse.
  const lenHeader = upstream.headers.get('Content-Length');
  if (lenHeader && Number(lenHeader) > MAX_BYTES) {
    return new Response('upstream too large (cap 200 MB)', { status: 413 });
  }

  // Build response headers — preserve content type / length, layer on
  // the COOP/COEP/CORP set already emitted by _headers (Pages merges).
  const out = new Headers();
  const ct = upstream.headers.get('Content-Type') || 'application/octet-stream';
  out.set('Content-Type', ct);
  if (lenHeader) out.set('Content-Length', lenHeader);
  out.set('Cross-Origin-Resource-Policy', 'cross-origin');
  // Same-origin from the page's perspective — no extra ACAO needed,
  // but set it anyway for debugging tools.
  out.set('Access-Control-Allow-Origin', '*');
  out.set('Cache-Control', 'public, max-age=86400');

  // If no Content-Length, stream through with a TransformStream that
  // tracks total bytes and aborts on overflow.
  if (!lenHeader) {
    let total = 0;
    const cap = new TransformStream({
      transform(chunk, controller) {
        total += chunk.byteLength;
        if (total > MAX_BYTES) {
          controller.error(new Error('exceeded 200 MB cap'));
          return;
        }
        controller.enqueue(chunk);
      },
    });
    return new Response(upstream.body.pipeThrough(cap), { status: 200, headers: out });
  }

  return new Response(upstream.body, { status: 200, headers: out });
}
