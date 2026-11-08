<script module lang="ts">
  /** Self-updater screen (owner order 2026-11-08: "add self updater for the
   *  admin apps. You'll need to add Github OAuth for that."). A dropped-in
   *  module like every other page — no shell fork. */
  export const meta = { title: "Updates", path: "/updates", nav: "settings", icon: "refresh", order: 80 };
</script>

<script lang="ts">
  /** Updates — compare this build against the brand's GitHub releases.
   *
   *  Auth degrades gracefully (lib/updater.ts):
   *    1. a stored release token (keyring, "updates.token") — works today;
   *    2. GitHub OAuth DEVICE FLOW when the build carries a client id
   *       (AppConfig.githubClientId, inlined by build_admin) — no PAT ever
   *       pasted, the token lives in memory for this session only;
   *    3. anonymous read for public release repos.
   */
  import { onMount } from "svelte";
  import { effectiveConfig, handleApiError, toast } from "../lib/stores";
  import {
    checkForUpdate,
    deviceFlowPollOnce,
    deviceFlowStart,
    downloadAsset,
    loadStoredToken,
    saveStoredToken,
    type DeviceFlowStart,
    type UpdateCheck,
  } from "../lib/updater";
  import { isWebStorage } from "../lib/secrets";
  import Icon from "../components/Icon.svelte";

  const current = __APP_VERSION__;

  let repo = $state("");
  let result = $state<UpdateCheck | null>(null);
  let checking = $state(false);
  let tokenInput = $state("");
  let hasStoredToken = $state(false);
  let device: DeviceFlowStart | null = $state(null);
  let deviceStatus = $state("");
  let deviceTimer: ReturnType<typeof setTimeout> | null = null;

  const clientId = $derived(effectiveConfig().githubClientId ?? "");
  const repoName = $derived(repo || effectiveConfig().updateRepo || "khaalidrafi/freshorama");

  onMount(async () => {
    hasStoredToken = Boolean(await loadStoredToken());
  });

  $effect(() => {
    return () => {
      if (deviceTimer) clearTimeout(deviceTimer);
    };
  });

  async function check(): Promise<void> {
    checking = true;
    try {
      const token = (await loadStoredToken()) ?? null;
      result = await checkForUpdate(repoName, current, token);
    } catch (err) {
      handleApiError(err);
    } finally {
      checking = false;
    }
  }

  async function saveToken(): Promise<void> {
    try {
      await saveStoredToken(tokenInput.trim());
      hasStoredToken = Boolean(tokenInput.trim());
      tokenInput = "";
      toast("success", hasStoredToken ? "Release token saved (OS keychain)" : "Release token cleared");
    } catch (err) {
      toast("error", String((err as Error)?.message ?? err));
    }
  }

  async function startDeviceFlow(): Promise<void> {
    if (!clientId) {
      toast("error", "No GitHub OAuth client id in this build — set AppConfig.githubClientId or paste a release token.");
      return;
    }
    try {
      device = await deviceFlowStart(clientId);
      deviceStatus = `Open ${device.verifyUri} and enter the code`;
      pollDevice(device.deviceCode, device.intervalSeconds);
    } catch (err) {
      deviceStatus = "";
      toast("error", String((err as Error)?.message ?? err));
    }
  }

  function pollDevice(deviceCode: string, intervalSec: number): void {
    if (deviceTimer) clearTimeout(deviceTimer);
    deviceTimer = setTimeout(async () => {
      if (!device) return;
      const answer = await deviceFlowPollOnce(clientId, deviceCode);
      if (answer.status === "pending") {
        pollDevice(deviceCode, intervalSec);
      } else if (answer.status === "slow_down") {
        pollDevice(deviceCode, intervalSec + answer.intervalSeconds);
      } else if (answer.status === "granted") {
        device = null;
        deviceStatus = "";
        await saveSessionToken(answer.token);
        toast("success", "GitHub authorization granted");
        void check();
      } else {
        device = null;
        deviceStatus = "";
        toast("error", answer.reason);
      }
    }, intervalSec * 1000);
  }

  /** Device-flow tokens are session-scoped on purpose: memory only, never
   *  localStorage, never the keyring (the user can paste a durable PAT
   *  instead if they want the check to survive reboots). */
  let sessionToken: string | null = null;
  async function saveSessionToken(token: string): Promise<void> {
    sessionToken = token;
    hasStoredToken = true; // some auth is now available
  }

  async function download(): Promise<void> {
    const url = result?.release?.downloadUrl;
    const name = result?.release?.downloadName;
    if (!url || !name) return;
    try {
      toast("info", "Downloading update…");
      await downloadAsset(url, name);
      toast("success", `${name} downloaded — run the installer to update`);
    } catch (err) {
      toast("error", `Download failed: ${String((err as Error)?.message ?? err)}`);
    }
  }
</script>

<div class="mx-auto max-w-2xl">
  <div class="mb-6">
    <h1 class="text-2xl font-semibold">Updates</h1>
    <p class="text-sm text-text/50">
      This app is <code class="rounded border border-text/20 bg-text/10 px-1.5 py-0.5 text-[12px]">v{current}</code>.
      Updates come from the GitHub releases of the app's repository.
    </p>
  </div>

  <div class="card p-5" data-tour="updates">
    <div class="flex flex-wrap items-end gap-3">
      <div class="min-w-0 flex-1">
        <label class="mb-1 block text-xs font-medium text-text/60" for="upd-repo">Release repository</label>
        <input id="upd-repo" class="input" type="text" placeholder="owner/repo" bind:value={repo} />
      </div>
      <button class="btn btn-primary" disabled={checking} onclick={check}>
        <Icon name="refresh" size={15} />
        {checking ? "Checking…" : "Check for updates"}
      </button>
    </div>

    {#if result}
      {#if result.error && !result.release}
        <div class="mt-4 rounded-lg border border-text/15 bg-text/[0.04] px-3 py-2 text-xs text-text/70">
          {result.error}
        </div>
      {:else if result.upToDate}
        <div class="mt-4 flex items-center gap-2 rounded-lg border border-text/15 bg-text/[0.04] px-3 py-2 text-sm">
          <Icon name="check" size={15} />
          You are up to date (latest release: {result.latest}).
        </div>
      {:else if result.release}
        <div class="mt-4 rounded-xl border border-accent/40 p-4">
          <div class="flex items-center justify-between gap-2">
            <div class="text-sm font-semibold">Update available: {result.release.name}</div>
            <span class="rounded-full bg-accent/15 px-2 py-0.5 text-[11px] text-[var(--brand-accent)]">
              v{result.latest}
            </span>
          </div>
          {#if result.release.notes}
            <pre class="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-text/70">{result.release.notes}</pre>
          {/if}
          <div class="mt-3 flex flex-wrap gap-2">
            {#if result.release.downloadUrl}
              <button class="btn btn-primary" onclick={download}>
                <Icon name="download" size={15} />
                Download {result.release.downloadName}
              </button>
            {/if}
            {#if result.release.htmlUrl}
              <button class="btn btn-ghost" onclick={() => window.open(result?.release?.htmlUrl, "_blank")}>
                Open release page
              </button>
            {/if}
          </div>
        </div>
      {/if}
      {#if result.via !== "none"}
        <div class="mt-2 text-[11px] text-text/40">
          Read via {result.via === "anonymous" ? "anonymous access" : result.via === "token" ? "your stored release token" : "GitHub device-flow authorization"}.
        </div>
      {/if}
    {/if}
  </div>

  <div class="card mt-4 p-5">
    <h2 class="text-sm font-semibold">GitHub authorization</h2>
    <p class="mt-1 text-xs leading-relaxed text-text/50">
      Private release repos need GitHub authorization. Device-flow OAuth is the recommended path —
      no token is ever pasted or stored; the session token only reads this repository's releases.
      A stored personal access token (Contents: read) also works and survives reboots.
    </p>
    <div class="mt-3 flex flex-wrap items-center gap-2">
      <button class="btn btn-primary" onclick={startDeviceFlow} disabled={!clientId || Boolean(device)}>
        <Icon name="logout" size={15} />
        Authorize with GitHub (device flow)
      </button>
      {#if !clientId}
        <span class="text-[11px] text-text/40">build has no OAuth client id — paste a token below instead</span>
      {/if}
    </div>
    {#if device}
      <div class="mt-3 rounded-lg border border-accent/40 bg-accent/10 px-3 py-2 text-xs">
        <div>
          Enter code <strong class="font-mono text-sm">{device.userCode}</strong> at
          <a class="underline" href={device.verifyUri} target="_blank" rel="noreferrer">{device.verifyUri}</a>
        </div>
        <div class="mt-1 text-text/50">{deviceStatus}</div>
      </div>
    {/if}

    <details class="mt-3">
      <summary class="cursor-pointer text-xs text-text/50">Or paste a release token (advanced)</summary>
      <div class="mt-2 flex gap-2">
        <input
          class="input"
          type="password"
          placeholder={hasStoredToken ? "stored — paste a new one to replace, empty to clear" : "github_pat_…"}
          bind:value={tokenInput}
        />
        <button class="btn btn-ghost shrink-0" onclick={saveToken}>Save</button>
      </div>
      <div class="mt-1 text-[11px] text-text/40">
        {isWebStorage() ? "Browser mode: stored in localStorage." : "Stored in the OS keychain."}
      </div>
    </details>
  </div>
</div>
