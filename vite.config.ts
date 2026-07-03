import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import fs from "fs";

const keyPath = "/etc/apache2/ssl/sound-friend.key";
const certPath = "/etc/apache2/ssl/sound-friend.crt";
const hasCert = fs.existsSync(keyPath) && fs.existsSync(certPath);

export default defineConfig(async () => ({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: true,
    https: hasCert
      ? {
          key: fs.readFileSync(keyPath),
          cert: fs.readFileSync(certPath),
        }
      : undefined,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
    // HMR 웹소켓: 페이지를 연 호스트(iptime 도메인 등)로 wss 접속을 강제하고
    // localhost 폴백 시도를 막는다
    hmr: {
      protocol: hasCert ? "wss" : "ws",
      clientPort: 1420,
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}));
