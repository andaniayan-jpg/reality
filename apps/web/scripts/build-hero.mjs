import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";

const entry = fileURLToPath(new URL("../hero3d.js", import.meta.url));
const outfile = fileURLToPath(new URL("../hero3d.bundle.js", import.meta.url));

await build({
  entryPoints: [entry],
  outfile,
  bundle: true,
  minify: true,
  format: "esm",
  target: "es2022",
  legalComments: "inline",
});

// Three.js embeds multiline GLSL strings. Removing line-end whitespace keeps
// the committed output clean without changing shader semantics.
const bundled = await readFile(outfile, "utf8");
await writeFile(
  outfile,
  bundled.replace(/[\t ]+(?=\r?$)/gm, "").replace(/^ +\t/gm, "\t"),
  "utf8",
);
