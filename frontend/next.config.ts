import path from "node:path";
import type { NextConfig } from "next";

// The console runs the web SDK from source (../sdk/web/src, imported as "@pramaan/web-sdk" via tsconfig paths), so
// the repository root is the Turbopack root.
const repoRoot = path.join(__dirname, "..");

const nextConfig: NextConfig = {
  // the dev-mode "N" badge sits over the timeline's row labels; hide it
  devIndicators: false,
  cacheComponents: true,
  partialPrefetching: true,
  outputFileTracingRoot: repoRoot,
  turbopack: {
    root: repoRoot,
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
