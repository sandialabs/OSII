// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8511",
      "/artifact": "http://localhost:8511",
      "/chat-api": {
        target: "http://localhost:8611",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/chat-api/, "/api"),
      },
    },
  },
});