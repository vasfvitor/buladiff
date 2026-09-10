// @ts-check
import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";
import pagefind from "astro-pagefind";

// Ajuste `site`/`base` ao publicar: GitHub Pages de projeto serve em https://<user>.github.io/buladiff/.
export default defineConfig({
  site: process.env.SITE_URL ?? "https://example.github.io",
  base: process.env.SITE_BASE ?? "/buladiff",
  output: "static",
  trailingSlash: "always",
  build: { format: "directory" },
  integrations: [sitemap(), pagefind()],
});
