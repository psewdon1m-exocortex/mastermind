import {build} from "esbuild";
import {mkdir, copyFile, readFile, writeFile} from "node:fs/promises";
import {createHash} from "node:crypto";
await mkdir("dist", {recursive: true});
await build({entryPoints: ["src/main.ts"], outfile: "dist/main.js", bundle: true,
  platform: "node", format: "cjs", target: "es2022", external: ["obsidian", "electron", "@codemirror/view", "@codemirror/state"],
  sourcemap: false, minify: false});
await copyFile("manifest.json", "dist/manifest.json");
await copyFile("styles.css", "dist/styles.css");
const hashes = {};
for (const file of ["main.js", "manifest.json", "styles.css"]) {
  hashes[file] = createHash("sha256").update(await readFile("dist/" + file)).digest("hex");
}
await writeFile("dist/integrity.json", JSON.stringify(hashes, null, 2) + "\n");
