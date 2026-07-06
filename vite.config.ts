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
    https: hasCert
      ? {
          key: fs.readFileSync(keyPath),
          cert: fs.readFileSync(certPath),
        }
      : undefined,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
    // 공유기(iptime) 경유 접속에서 HMR 웹소켓이 차단되면 vite 클라이언트가
    // "서버 재시작"으로 오인해 페이지를 무한 리로드한다 → HMR 비활성화.
    // 코드 변경 반영은 브라우저 수동 새로고침으로 한다.
    hmr: false,
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
