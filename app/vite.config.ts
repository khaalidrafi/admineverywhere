/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [tailwindcss(), svelte()],
  clearScreen: false,
  // CRITICAL: one dep-optimization pass for ALL svelte entrypoints.
  // If svelte/store is discovered lazily (after svelte itself), vite emits
  // two optimized builds with different version hashes -> two separate
  // svelte-internals instances -> store subscriptions register with a dead
  // effect registry -> app freezes at first render. Seen in the wild.
  optimizeDeps: {
    include: ["svelte", "svelte/store", "svelte/internal/client", "svelte/internal/disclose-version"],
  },
  server: {
    port: 5173,
    strictPort: true,
    // dev insurance: never let the browser cache transformed modules —
    // stale module graphs create ghost duplicate instances of stores
    headers: { "Cache-Control": "no-store" },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
