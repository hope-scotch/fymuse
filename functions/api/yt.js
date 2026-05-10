// Cloudflare Pages Function — YouTube audio extractor.
//
// The Splitter's URL feature routes YouTube / YouTube Music links here
// because they're HTML pages, not direct audio files.
//
// Implementation: youtubei.js (a pure-JS reimplementation of YouTube's
// internal InnerTube API). No subprocess, no ffmpeg, no Python — runs
// inside the Worker. We pick the best audio-only adaptive format,
// resolve its signed CDN URL, then proxy-fetch the audio bytes back
// to the browser through the same origin.
//
// Limits:
// - YouTube only (this project only needs YT Music). For SoundCloud /
//   Bandcamp / Vimeo etc. you'd need yt-dlp on a real container.
// - YouTube occasionally rate-limits or blocks Cloudflare datacenter
//   IPs — when this happens the call returns 502 and the user has to
//   retry or fall back to local server.py.
// - 200 MB hard cap on the streamed response.

import { Innertube, UniversalCache } from 'youtubei.js';

const MAX_BYTES = 200 * 1024 * 1024; // 200 MB

function extractVideoId(rawUrl) {
  let u;
  try { u = new URL(rawUrl); } catch { return null; }
  const host = u.hostname.toLowerCase();
  if (host === 'youtu.be') {
    const id = u.pathname.replace(/^\/+/, '').split('/')[0];
    return /^[\w-]{11}$/.test(id) ? id : null;
  }
  if (host === 'youtube.com' || host.endsWith('.youtube.com')) {
    const v = u.searchParams.get('v');
    if (v && /^[\w-]{11}$/.test(v)) return v;
    // /shorts/<id>, /embed/<id>, /live/<id>
    const m = u.pathname.match(/\/(?:shorts|embed|live)\/([\w-]{11})/);
    if (m) return m[1];
  }
  return null;
}

export async function onRequestGet({ request }) {
  const reqUrl = new URL(request.url);
  const target = reqUrl.searchParams.get('url');
  if (!target) {
    return new Response('missing ?url=', { status: 400 });
  }
  const videoId = extractVideoId(target);
  if (!videoId) {
    return new Response(
      'not a recognizable YouTube URL. Expected youtube.com / music.youtube.com / youtu.be link.',
      { status: 400 },
    );
  }

  // 1) Resolve the audio stream URL via the InnerTube API.
  let streamUrl;
  let containerType = 'audio/mp4';
  try {
    // Cloudflare Workers' fetch / Headers / Request need the global as
    // `this`; youtubei.js destructures them and loses the binding,
    // throwing "Illegal invocation". Wrap them in fresh arrow-fn /
    // class shims so the library can call them however it wants.
    const safeFetch = (input, init) => fetch(input, init);
    const yt = await Innertube.create({
      cache: new UniversalCache(false),
      generate_session_locally: true,
      fetch: safeFetch,
    });
    const info = await yt.getBasicInfo(videoId);
    // Prefer choosing best audio explicitly so we know what we got.
    const format = info.chooseFormat({ type: 'audio', quality: 'best' });
    if (!format) throw new Error('no audio-only adaptive format available');
    streamUrl = format.decipher(yt.session.player);
    if (format.mime_type) {
      // e.g. 'audio/mp4; codecs="mp4a.40.2"' — strip params for the wire
      containerType = format.mime_type.split(';')[0].trim() || containerType;
    }
  } catch (e) {
    return new Response(
      'YouTube extraction failed: ' + (e && e.message || e) +
      '. YouTube may be rate-limiting Cloudflare IPs — try again or use the local server.',
      { status: 502 },
    );
  }

  // 2) Proxy-fetch the audio bytes from YouTube's CDN.
  let upstream;
  try {
    upstream = await fetch(streamUrl, {
      redirect: 'follow',
      cf: { cacheEverything: false },
    });
  } catch (e) {
    return new Response('CDN fetch failed: ' + (e && e.message || e), { status: 502 });
  }
  if (!upstream.ok) {
    return new Response(
      'CDN HTTP ' + upstream.status + ' ' + upstream.statusText,
      { status: 502 },
    );
  }
  const lenHeader = upstream.headers.get('Content-Length');
  if (lenHeader && Number(lenHeader) > MAX_BYTES) {
    return new Response('upstream too large (cap 200 MB)', { status: 413 });
  }

  // 3) Stream back with sensible headers.
  const out = new Headers();
  out.set('Content-Type', upstream.headers.get('Content-Type') || containerType);
  if (lenHeader) out.set('Content-Length', lenHeader);
  out.set('Cross-Origin-Resource-Policy', 'cross-origin');
  out.set('Access-Control-Allow-Origin', '*');
  out.set('Cache-Control', 'no-store');

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
    return new Response(upstream.body.pipeThrough(cap), {
      status: 200,
      headers: out,
    });
  }
  return new Response(upstream.body, { status: 200, headers: out });
}
