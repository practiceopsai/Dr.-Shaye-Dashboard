import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    return [{ source: "/:path*", headers: [{ key: "Cache-Control", value: "no-store, no-cache, must-revalidate" }] }];
  },
};
export default nextConfig;
