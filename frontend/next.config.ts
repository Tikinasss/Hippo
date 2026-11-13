import type { NextConfig } from "next";

// Le navigateur appelle /api/… sur la même origine ; Next relaie vers le backend FastAPI.
const backend = process.env.HIPPO_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
