import { build } from "vite";
import { readFile, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

await build();
await build({
  build: {
    ssr: "src/modules/landing/server.ts",
    outDir: "node_modules/.tmp/landing-ssr",
    rollupOptions: { output: { entryFileNames: "server.mjs" } },
  },
});
const { render } = await import(
  pathToFileURL(resolve("node_modules/.tmp/landing-ssr/server.mjs")).href
);
const template = await readFile("dist/index.html", "utf8");
if (!template.includes("<!--landing-html-->"))
  throw new Error("Landing HTML slot is missing");
await writeFile(
  "dist/index.html",
  template.replace("<!--landing-html-->", await render()),
);
