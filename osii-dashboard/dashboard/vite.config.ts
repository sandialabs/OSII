// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiPort = process.env.OSII_API_PORT ?? "8511";
const chatPort = process.env.OSII_CHAT_PORT ?? "8611";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": `http://127.0.0.1:${apiPort}`,
      "/artifact": `http://127.0.0.1:${apiPort}`,
      "/chat-api": {
        target: `http://127.0.0.1:${chatPort}`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/chat-api/, "/api"),
      },
    },
  },
});
