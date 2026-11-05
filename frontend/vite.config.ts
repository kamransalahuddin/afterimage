import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: Number(process.env.PORT ?? 5173),
    strictPort: true,
    proxy: { "/api": { target: process.env.AFTERIMAGE_API_URL ?? "http://127.0.0.1:8000", changeOrigin: false } },
  },
  build: { sourcemap: false },
});
