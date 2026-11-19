// vite.config.js - Vite setup. The backend CORS settings expect the dev server on port 5173.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
});
