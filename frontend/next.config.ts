import type { NextConfig } from "next";

// Le navigateur appelle /api/… sur la même origine ; Next relaie vers le backend FastAPI.
// En image Docker, l'adresse est fixée à la construction (argument HIPPO_API_URL).
const backend = process.env.HIPPO_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    // l'assistant enchaîne plusieurs appels au modèle : on laisse jusqu'à 3 minutes au relais
    proxyTimeout: 180_000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
