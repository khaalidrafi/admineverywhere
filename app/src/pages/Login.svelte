<script module lang="ts">
  export const meta = {
    title: "Sign in",
    path: "/login",
    nav: false,
    standalone: true,
    order: 1,
  };
</script>

<script lang="ts">
  import { app, handleApiError, loadSchema, login, toast } from "../lib/stores";
  import { navigate } from "../lib/router";
  import Icon from "../components/Icon.svelte";
  import { ApiError } from "../lib/api";

  let username = $state("");
  let password = $state("");
  let apiUrl = $state("");
  let busy = $state(false);
  let error = $state("");
  // the one settings field is a collapsed disclosure — the gate reads as a
  // plain sign-in until someone actually needs to point it at another API
  let showApi = $state(false);

  // prefill the one settings field from config/override
  $effect(() => {
    if ($app.config) apiUrl = $app.apiUrlOverride || $app.config.apiUrl;
  });

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    if (busy) return;
    error = "";
    if (!username || !password) {
      error = "Enter username and password.";
      return;
    }
    busy = true;
    try {
      app.update((a) => ({ ...a, apiUrlOverride: apiUrl.trim() }));
      localStorage.setItem("dad.apiUrl", apiUrl.trim());
      await login(username, password);
      toast("success", `Welcome, ${username}!`);
      navigate("#/");
      await loadSchema();
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        error = "Invalid credentials — check username and password.";
      } else if (err instanceof ApiError && err.network) {
        error = `Backend unreachable at ${apiUrl}. Is the server running?`;
        handleApiError(err);
      } else {
        error = (err as Error).message;
        handleApiError(err);
      }
    } finally {
      busy = false;
    }
  }
</script>

<div class="flex min-h-screen items-center justify-center p-4">
  <div class="w-full max-w-sm">
    <div class="card p-8 shadow-2xl">
      <!-- brand -->
      <div class="mb-6 flex flex-col items-center gap-3 text-center">
        {#if $app.brand.logo}
          <img src={$app.brand.logo} alt="logo" class="size-14 rounded-2xl" />
        {:else}
          <div class="size-14 rounded-2xl bg-gradient-to-br from-primary to-accent"></div>
        {/if}
        <div>
          <div class="text-xl font-semibold">{$app.brand.appName}</div>
          {#if $app.brand.tagline}
            <div class="mt-1 text-sm text-text/50">{$app.brand.tagline}</div>
          {/if}
        </div>
      </div>

      <form onsubmit={submit} class="flex flex-col gap-4">
        <div>
          <label class="mb-1 block text-xs font-medium text-text/60" for="username">Username</label>
          <input id="username" class="input" type="text" autocomplete="username"
                 bind:value={username} placeholder="admin" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text/60" for="password">Password</label>
          <input id="password" class="input" type="password" autocomplete="current-password"
                 bind:value={password} placeholder="••••••••" />
        </div>
        <!-- advanced disclosure: the one settings field stays out of the way -->
        <button
          type="button"
          class="flex items-center gap-1 self-start text-xs text-text/50 transition-colors hover:text-text/70"
          aria-expanded={showApi}
          aria-controls="advanced-api"
          onclick={() => (showApi = !showApi)}
        >
          <Icon name="left" size={12} class="transition-transform {showApi ? '-rotate-90' : 'rotate-180'}" />
          Advanced — API URL
        </button>
        {#if showApi}
          <div id="advanced-api">
            <label class="mb-1 block text-xs font-medium text-text/60" for="api">API URL</label>
            <input id="api" class="input" type="url" bind:value={apiUrl}
                   placeholder="https://your-api.example.com" />
            <div class="mt-1 text-[11px] text-text/40">DRF + drf-spectacular backend (token auth)</div>
            <div class="mt-2 text-[11px] text-text/40">
              No API at hand? Run the bundled demo backend — see <code>README → demo-backend/</code> (admin / admin123).
            </div>
          </div>
        {/if}

        {#if error}
          <div class="rounded-lg border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-200">
            {error}
          </div>
        {/if}

        <button class="btn btn-primary w-full" disabled={busy}>
          {#if busy}
            <Icon name="refresh" size={16} class="animate-spin" />
          {/if}
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>

    <div class="mt-4 text-center text-xs text-text/40">
      Works with any Django REST Framework backend exposing a drf-spectacular schema.
    </div>
  </div>
</div>
