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
  // happy-dom (not "node") because secrets/widgets tests touch localStorage
  // and location (via router.ts), which only exist under a DOM environment.
  //
  // Svelte 5 + Vitest: which build of svelte a component is compiled against is
  // chosen by the "browser" export condition. Vitest resolves through the SSR
  // pipeline, whose default for svelte's "." export is index-server.js, where
  // mount() throws "lifecycle_function_unavailable" — that single condition is
  // why .svelte components were untestable for real until FR R-006. `inline`
  // keeps every svelte import in one transformed graph (no second copy of
  // svelte-internals, the failure mode optimizeDeps.include already guards).
  resolve: { conditions: ["browser"] },
  test: {
    environment: "happy-dom",
    include: ["src/**/*.test.ts"],
    server: { deps: { inline: [/svelte/] } },
  },
});
