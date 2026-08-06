import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const proxyTarget = process.env.VITE_PROXY_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/backoffice/",
  server: {
    port: 5173,
    proxy: {
      "/admin": proxyTarget,
      "/agent": proxyTarget,
      "/history": proxyTarget,
      "/schedule": proxyTarget,
      "/health": proxyTarget,
      "/reminders": proxyTarget,
      "/webhook": proxyTarget,
      "/whatsapp": proxyTarget,
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
