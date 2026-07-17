/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
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
