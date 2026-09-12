/** @type {import('next').NextConfig} */

// The Reporter API is a separate process. Server components can call it
// directly, but the browser cannot: a hard-coded localhost URL would only work
// on the machine running the API, and a cross-origin URL needs CORS and
// leaks the API's address into every page.
//
// So the browser talks to /api/reporter/* on its own origin and Next proxies
// it server-side. Set NEXT_PUBLIC_HOLDING_API_URL only when the API really does
// live on another host; the wallet client will then call it directly.
const API_INTERNAL =
  process.env.HOLDING_API_URL || process.env.NEXT_PUBLIC_HOLDING_API_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/reporter/:path*",
        destination: `${API_INTERNAL.replace(/\/+$/, "")}/:path*`,
      },
    ];
  },
};

export default nextConfig;
