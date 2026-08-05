import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Self-contained server bundle for the container (docker/Dockerfile.web) — only the dependencies
  // actually imported, so the runtime image needs no npm install.
  output: "standalone",
  // Pin the tracing root to this directory. Left to infer it, Next walks up looking for a workspace
  // root, finds a lockfile somewhere above the repo, and nests the bundle under a path mirroring the
  // machine's directory layout (.next/standalone/Documents/Chavruta.AI/web/…) — so the Dockerfile's
  // COPY lands nothing and the image has no server.js.
  outputFileTracingRoot: dirname(fileURLToPath(import.meta.url)),
  // The app uses no next/image anywhere, but Next still serves the /_next/image optimizer. Turning
  // optimization off costs nothing here and takes the app off that path — which also means `sharp`
  // and its inherited libvips CVEs are never invoked. remotePatterns stays empty (the default), so
  // nothing external can be fetched through it either.
  images: { unoptimized: true },
  // The FastAPI backend serves the API. In dev, proxy the bare endpoints to it so the client can
  // call same-origin paths exactly like the static UI does (no CORS, no hardcoded host).
  //
  // ⚠️ EVERY backend route the client calls needs an entry here. A path that is missing does NOT
  // fail loudly: Next owns the origin, finds no page, and serves its own 404 HTML — which the
  // client then tries to JSON.parse, so the user sees a page of markup where an answer belongs.
  // That is exactly how /jobs went unnoticed: the UI polls it for every async generation, and the
  // whole feature returned HTML. When you add an endpoint to app/api.py, add it here too.
  //
  // Prefer a `:path*` prefix over an exact source — `{source:"/query"}` does NOT match
  // /query/async, which is the variant the UI actually uses.
  async rewrites() {
    const api = process.env.CHAVRUTA_API_ORIGIN || "http://127.0.0.1:8080";
    const proxy = (p) => [
      { source: `/${p}`, destination: `${api}/${p}` },
      { source: `/${p}/:path*`, destination: `${api}/${p}/:path*` },
    ];
    return [
      ...proxy("query"),      // /query and /query/async
      ...proxy("sessions"),   // incl. /sessions/async, /sessions/{id}/query[/async], /messages
      ...proxy("jobs"),       // async polling — the UI's main generation path
      ...proxy("lessons"),
      ...proxy("me"),
      ...proxy("account"),    // /account/delete, /account/delete/cancel
      ...proxy("billing"),    // /billing/config, /checkout, /cancel
      ...proxy("coupons"),    // /coupons/redeem
      ...proxy("health"),
      ...proxy("ready"),
      ...proxy("admin"),      // owner-only dashboard — see app/api.py::_is_admin
    ];
  },
};

export default nextConfig;
