<script lang="ts">
  /** In-app brand editor — "brand the app from inside the app".
   *
   * Edits the brand the backend plugin serves (GET/PUT /admincraft/branding/):
   * name, tagline, five theme colors, radius, font, logo + favicon. Saving
   * applies the new identity live (CSS variables, titles, favicon) without a
   * reload. Launcher/dock icons keep the build-time identity — the
   * admincraft-craft skill handles that half when cutting a release.
   *
   * Asset handling on save (logo, same for favicon):
   *   - newly uploaded file        → sent as a data URL (server checks magic bytes)
   *   - already a server asset     → sent as its filename (kept as-is)
   *   - bundled static asset       → re-uploaded as data URL so the first save
   *                                   doesn't drop the shipped logo
   */
  import { get } from "svelte/store";
  import { ApiError } from "../lib/api";
  import { app, saveBrand, toast } from "../lib/stores";
  import type { Brand } from "../lib/types";
  import { BRAND_DEFAULTS, injectBrandCss } from "../lib/branding";

  const COLOR_KEYS: { key: keyof Brand["colors"]; label: string; hint: string }[] = [
    { key: "primary", label: "Primary", hint: "buttons, links, active nav" },
    { key: "accent", label: "Accent", hint: "highlights, charts" },
    { key: "bg", label: "Background", hint: "app background" },
    { key: "surface", label: "Surface", hint: "cards, sidebar, tables" },
    { key: "text", label: "Text", hint: "all text" },
  ];

  const orig: Brand = structuredClone(get(app).brand);

  // Draft starts from the live brand with color defaults filled in, so
  // every color input has a concrete value to bind to.
  let draft: Brand = $state({
    ...structuredClone(orig),
    colors: { ...BRAND_DEFAULTS, ...(orig.colors ?? {}) },
  });
  let logoUpload: string | null = $state(null);
  let faviconUpload: string | null = $state(null);
  let saving = $state(false);
  let errors: string[] = $state([]);
  let previewing = $state(false);

  function blobToDataUrl(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
  }

  async function onFile(key: "logo" | "favicon", file: File | undefined): Promise<void> {
    if (!file) return;
    if (file.size > 1_000_000) {
      errors = [`${key}: file is larger than 1 MB`];
      return;
    }
    const dataUrl = await blobToDataUrl(file);
    if (key === "logo") logoUpload = dataUrl;
    else faviconUpload = dataUrl;
    errors = [];
  }

  /** Decide what to send for an asset key (see header comment). */
  async function assetPayload(key: "logo" | "favicon"): Promise<string | undefined> {
    const upload = key === "logo" ? logoUpload : faviconUpload;
    if (upload) return upload;
    const current = orig[key];
    if (!current) return undefined;
    if (current.startsWith("data:")) return current;
    if (current.includes("/admincraft/branding/asset/")) {
      return current.split("/").pop(); // server-relative: keep the file
    }
    try {
      // bundled static asset (e.g. /logo.svg): re-upload it so it survives
      const blob = await (await fetch(current)).blob();
      if (blob.size > 1_000_000) return undefined;
      return await blobToDataUrl(blob);
    } catch {
      return undefined;
    }
  }

  function payloadBrand(): Brand {
    return {
      appName: draft.appName.trim(),
      tagline: draft.tagline?.trim() || undefined,
      colors: { ...draft.colors },
      radius: draft.radius,
      font: draft.font,
      logo: undefined,
      favicon: undefined,
    } as Brand;
  }

  async function save(): Promise<void> {
    errors = [];
    if (!draft.appName.trim()) {
      errors = ["appName: must not be empty"];
      return;
    }
    saving = true;
    try {
      const payload = payloadBrand();
      payload.logo = await assetPayload("logo");
      payload.favicon = await assetPayload("favicon");
      await saveBrand(payload);
      logoUpload = null;
      faviconUpload = null;
      toast("success", "Brand saved — applied live");
    } catch (err) {
      if (err instanceof ApiError && Array.isArray((err.detail as any)?.errors)) {
        errors = (err.detail as any).errors;
      } else {
        errors = [String((err as Error)?.message ?? err)];
      }
    } finally {
      saving = false;
    }
  }

  /** Live-preview the draft on the whole app without touching the server. */
  function togglePreview(): void {
    previewing = !previewing;
    if (previewing) injectBrandCss(draft);
    else injectBrandCss(orig);
  }

  const previewLogo = $derived(logoUpload ?? draft.logo ?? "");
  const logoIsImage = $derived(previewLogo.startsWith("data:") || previewLogo.includes("/admincraft/branding/asset/") || !!previewLogo);
</script>

<div class="mx-auto max-w-2xl">
  <div class="mb-6 flex items-center justify-between">
    <div>
      <h1 class="text-xl font-bold">Branding</h1>
      <p class="text-sm text-text/60">
        Saved to the backend and applied live. Launcher icons change at the next built release.
      </p>
    </div>
    <div class="flex gap-2">
      <button class="btn btn-ghost" onclick={togglePreview}>
        {previewing ? "Stop preview" : "Preview live"}
      </button>
      <button class="btn btn-primary" onclick={save} disabled={saving}>
        {saving ? "Saving…" : "Save brand"}
      </button>
    </div>
  </div>

  {#if errors.length}
    <div class="card mb-4 border-red-400/40 bg-red-500/10 p-4 text-sm text-red-300">
      <div class="mb-1 font-semibold">The backend rejected this brand:</div>
      <ul class="list-disc pl-5">
        {#each errors as e (e)}
          <li>{e}</li>
        {/each}
      </ul>
    </div>
  {/if}

  <!-- live preview card -->
  <div class="card mb-6 flex items-center gap-4 p-4">
    {#if logoIsImage && previewLogo}
      <img src={previewLogo} alt="logo preview" class="size-12 rounded-xl" />
    {:else}
      <div class="size-12 rounded-xl" style="background: linear-gradient(135deg, {draft.colors.primary}, {draft.colors.accent})"></div>
    {/if}
    <div class="min-w-0">
      <div class="truncate text-lg font-bold">{draft.appName || "App name"}</div>
      <div class="truncate text-xs text-text/50">{draft.tagline}</div>
    </div>
    <div class="ml-auto flex gap-1.5">
      {#each COLOR_KEYS as c (c.key)}
        <div class="size-6 rounded-full border border-text/10" style="background: {draft.colors[c.key]}" title={c.label}></div>
      {/each}
    </div>
  </div>

  <div class="card space-y-5 p-6">
    <div class="grid gap-4 sm:grid-cols-2">
      <label class="block">
        <span class="mb-1 block text-sm font-medium">App name</span>
        <input class="input" type="text" bind:value={draft.appName} maxlength="120" />
      </label>
      <label class="block">
        <span class="mb-1 block text-sm font-medium">Tagline</span>
        <input class="input" type="text" bind:value={draft.tagline} maxlength="140" placeholder="Optional one-liner" />
      </label>
      <label class="block">
        <span class="mb-1 block text-sm font-medium">Font (Google Fonts name)</span>
        <input class="input" type="text" bind:value={draft.font} placeholder="Inter" />
      </label>
      <label class="block">
        <span class="mb-1 block text-sm font-medium">Corner radius</span>
        <input class="input" type="text" bind:value={draft.radius} placeholder="0.75rem" />
      </label>
    </div>

    <div>
      <div class="mb-2 text-sm font-semibold">Theme colors</div>
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {#each COLOR_KEYS as c (c.key)}
          <label class="flex items-center gap-3 rounded-lg border border-text/10 bg-bg/40 p-2.5">
            <input
              type="color"
              class="size-8 cursor-pointer rounded border-none bg-transparent"
              value={draft.colors[c.key]}
              oninput={(e) => (draft.colors[c.key] = (e.target as HTMLInputElement).value)}
            />
            <span class="min-w-0">
              <span class="block text-sm font-medium">{c.label}</span>
              <span class="block truncate text-xs text-text/40">{c.hint}</span>
            </span>
          </label>
        {/each}
      </div>
    </div>

    <div class="grid gap-4 sm:grid-cols-2">
      <label class="block">
        <span class="mb-1 block text-sm font-medium">Logo (PNG, JPG or SVG, ≤ 1 MB)</span>
        {#if logoUpload}
          <div class="flex items-center gap-2 text-xs text-text/60">
            new logo selected <button class="btn btn-ghost px-2 py-0.5" onclick={() => (logoUpload = null)}>undo</button>
          </div>
        {:else}
          <input class="input file:mr-3 file:rounded file:border-0 file:bg-surface file:px-3 file:py-1 file:text-sm"
                 type="file" accept="image/png,image/jpeg,image/svg+xml"
                 onchange={(e) => onFile("logo", (e.target as HTMLInputElement).files?.[0])} />
        {/if}
      </label>
      <label class="block">
        <span class="mb-1 block text-sm font-medium">Favicon / launcher hint (PNG ≤ 1 MB)</span>
        {#if faviconUpload}
          <div class="flex items-center gap-2 text-xs text-text/60">
            new favicon selected <button class="btn btn-ghost px-2 py-0.5" onclick={() => (faviconUpload = null)}>undo</button>
          </div>
        {:else}
          <input class="input file:mr-3 file:rounded file:border-0 file:bg-surface file:px-3 file:py-1 file:text-sm"
                 type="file" accept="image/png,image/jpeg,image/svg+xml"
                 onchange={(e) => onFile("favicon", (e.target as HTMLInputElement).files?.[0])} />
        {/if}
      </label>
    </div>

    <p class="text-xs text-text/40">
      Changes require a staff account on the backend. The server validates everything
      (closed schema, magic-byte checks on uploads) — nothing sketchy can be injected.
    </p>
  </div>
</div>
