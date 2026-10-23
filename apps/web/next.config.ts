import type { NextConfig } from "next";
import { withEve } from "eve/next";
import { fileURLToPath } from "node:url";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/files/:path*",
        destination: "http://tusd:1080/files/:path*",
      },
    ];
  },
  experimental: {
    // Use the TypeScript compiler API. The CLI path emits non-JSON wrapper
    // output in this restricted appliance environment during `next build`.
    useTypeScriptCli: false,
  },
};
const eveRoot = fileURLToPath(new URL("../..", import.meta.url));

export default withEve(nextConfig, { eveRoot });
