import { defineConfig } from "vite";
import path from "path";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
   base: "./",
   build: {
      outDir: "static/dist",
      emptyOutDir: true,
      rollupOptions: {
         input: {
            dashboard: path.resolve(__dirname, "frontend/index.js"),
            home: path.resolve(__dirname, "frontend/home.js"),
         } 
      },
   },
   plugins: [
      tailwindcss(),
   ]
});
