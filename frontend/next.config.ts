import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // the dev-mode "N" badge sits over the timeline's row labels; hide it
  devIndicators: false,
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
