import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // 開発中は /api/ で始まる頼みを FastAPI へ中継し、画面と API を同じ localhost:5173 に見せる（notes.md 5章）
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
