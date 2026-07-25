/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The app uses no next/image anywhere, but Next still serves the /_next/image optimizer, which
  // 14.2.x has a known DoS advisory against. Turning optimization off costs nothing here and takes
  // the app off that path. remotePatterns stays empty (the default), so no external host can be
  // fetched through it either. The advisory itself is only fully closed by the Next 16 upgrade,
  // which is a breaking migration (React 19) and tracked separately.
  images: { unoptimized: true },
  // The FastAPI backend serves the API. In dev, proxy /api and the bare endpoints to it so the
  // client can call same-origin paths exactly like the static UI did (no CORS, no hardcoded host).
  async rewrites() {
    const api = process.env.CHAVRUTA_API_ORIGIN || "http://127.0.0.1:8080";
    return [
      { source: "/query", destination: `${api}/query` },
      { source: "/sessions/:path*", destination: `${api}/sessions/:path*` },
      { source: "/sessions", destination: `${api}/sessions` },
      { source: "/lessons/:path*", destination: `${api}/lessons/:path*` },
      { source: "/lessons", destination: `${api}/lessons` },
      { source: "/health", destination: `${api}/health` },
      { source: "/ready", destination: `${api}/ready` },
    ];
  },
};

export default nextConfig;
