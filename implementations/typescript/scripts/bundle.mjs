// Build dist-browser/owp-validator.js: the validator, resolver, and report for the browser (src/browser/api.ts).
// Node's built-in modules are replaced by the in-memory platform in src/browser/; the Node build is unchanged.
import * as esbuild from "esbuild";
import { fileURLToPath } from "node:url";
import * as path from "node:path";

import * as fs from "node:fs";

const here = path.dirname(fileURLToPath(import.meta.url));
const { version } = JSON.parse(fs.readFileSync(path.join(here, "..", "package.json"), "utf8"));
const src = path.join(here, "..", "src", "browser");
await esbuild.build({
  entryPoints: [path.join(src, "api.ts")],
  outfile: path.join(here, "..", "dist-browser", "owp-validator.js"),
  bundle: true,
  format: "esm",
  platform: "browser",
  target: "es2022",
  minify: true,
  sourcemap: false,
  legalComments: "none",
  alias: {
    "node:fs": path.join(src, "memfs.ts"),
    "node:path": path.join(src, "path.ts"),
    "node:crypto": path.join(src, "crypto.ts"),
    "node:os": path.join(src, "stubs.ts"),
    "node:url": path.join(src, "stubs.ts"),
    "node:child_process": path.join(src, "stubs.ts"),
    "node:zlib": path.join(src, "stubs.ts"),
  },
  inject: [path.join(src, "process-shim.ts")],
  define: { __OWP_VERSION__: JSON.stringify(version) },
  logLevel: "warning",
});
console.log("dist-browser/owp-validator.js");
