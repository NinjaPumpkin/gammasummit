// Vite config — scaffold (card E1.1).
// Serves frontend/mockups/*.html at /mockups/* in dev so the placeholder app
// can point at the approved reference visual (dashboard-v3.html) without
// copying or moving the mockup files.
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";
import { defineConfig, type Plugin } from "vite";

const MOCKUPS_DIR = path.resolve(process.cwd(), "mockups");

function serveMockups(): Plugin {
  return {
    name: "serve-mockups",
    configureServer(server) {
      server.middlewares.use("/mockups", (req, res, next) => {
        const name = path.basename((req.url ?? "").split("?")[0] ?? "");
        const file = path.join(MOCKUPS_DIR, name);
        if (!name || !fs.existsSync(file) || !file.startsWith(MOCKUPS_DIR)) return next();
        res.setHeader("Content-Type", "text/html; charset=utf-8");
        fs.createReadStream(file).pipe(res);
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), serveMockups()],
  server: { port: 5173 },
});
