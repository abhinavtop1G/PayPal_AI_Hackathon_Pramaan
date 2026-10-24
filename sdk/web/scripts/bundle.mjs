// Script-tag build: dist/pramaan.min.js exposes `window.Pramaan` for pages without a bundler.
import { build } from "esbuild";

await build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  minify: true,
  sourcemap: true,
  format: "iife",
  globalName: "Pramaan",
  target: ["es2020"],
  outfile: "dist/pramaan.min.js",
});
console.log("-> dist/pramaan.min.js");
