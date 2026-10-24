/** FR-R007 role gate, RENDERED (night-2 item 7) — a hidden entry is graded by the DOM.
 *
 *  docs/rbac.md promises "Sidebar.svelte hides a `roles`-declared entry unless the
 *  caller holds at least one of them; superusers see everything", and AGENTS.md
 *  repeats it. Measured before writing: deleting BOTH
 *  `.filter((p) => roleAllows(p.roles, $claims))` calls from Sidebar.svelte:20-21 —
 *  i.e. removing the whole nav half of FR-R007 — left the shipped suite answering
 *  `463 passed / 37 files`, rc 0. rbac.test.ts grades the pure `roleAllows()` and the
 *  registry's `roles` handling, and actionMount.test.ts:281 grades the action button,
 *  but nothing ever put claims in the store and looked at the rendered sidebar:
 *  navMount.test.ts resets `claims = null` and never sets it, so its exact sets grade
 *  the UNFILTERED case only. The filtered promise was graded by a code comment.
 *
 *  This file renders the filtered case against the REAL `collectPages` (the same
 *  validation, roles handling and refusal split the glob feeds) and the REAL Sidebar.
 *  The registry module is stubbed only to hand that output to the component, because
 *  the shipped glob can never produce the hidden state: no shipped page declares
 *  `roles`, so an App-level render over the real glob would agree with a gate that
 *  hides nothing and with a gate that hides everything.
 *
 *  Every assertion is an EXACT SET, never "X is absent" — a sidebar rendering no
 *  buttons would pass every absence check. The population is pinned first, so a
 *  fixture whose `roles` key stopped reaching the registry is red rather than quietly
 *  agreeing with an unfiltered render.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { flushSync, mount, unmount } from "svelte";
import Sidebar from "../../components/Sidebar.svelte";
import { claims, logout } from "../stores";
import * as registry from "../pages";
import type { RefusedPage, RegisteredPage } from "../pages/index";
import type { RoleClaims } from "../rbac";

/** The stubbed registry surface, read through the namespace object so every access
 *  hits the live getter (a destructured import would freeze it at import time).
 *  `setFixture` is the mock's own export, which the real module's types do not
 *  describe — hence the explicit shape instead of `typeof registry`. */
const reg = registry as unknown as {
  setFixture(entries: Iterable<[string, unknown]>): void;
  navPages(section?: "main" | "settings"): RegisteredPage[];
  pages: RegisteredPage[];
  refusedPages: RefusedPage[];
};

/** The sidebar's registry, stubbed to a fixture — but built by the REAL
 *  `collectPages`, so validation, the `roles` hand-off and the accepted/refused
 *  split are the shipped ones. The state lives in the factory's own closure: a
 *  `vi.hoisted` holder or a top-level `let` both sit in their temporal dead zone
 *  when vitest instantiates a mocked module during the import phase (measured:
 *  `Cannot access 'holder' before initialization`), and an async factory is the
 *  only shape that can reach the real module through `importActual`. */
vi.mock("../pages", async () => {
  const actual = await vi.importActual<typeof import("../pages/index")>("../pages/index");
  const holder: { pages: any[]; refused: any[] } = { pages: [], refused: [] };
  const nav = (section?: "main" | "settings") =>
    holder.pages.filter((p) => p.nav !== false && (section === undefined || p.nav === section));
  return {
    collectPages: actual.collectPages,
    pageHref: actual.pageHref,
    navPages: nav,
    pageById: (id: string) => holder.pages.find((p) => p.id === id),
    get pages() {
      return holder.pages;
    },
    get refusedPages() {
      return holder.refused;
    },
    get standalonePages() {
      return holder.pages.filter((p) => p.standalone);
    },
    get authPage() {
      return holder.pages.filter((p) => p.standalone)[0];
    },
    authHref: () => "#/login",
    setFixture: (entries: Iterable<[string, any]>) => {
      const out = actual.collectPages(entries);
      holder.pages = out.pages;
      holder.refused = out.refused;
    },
  };
});

/** The synthetic glob every test registers through the real `collectPages`:
 *  four main + two settings entries, three main + one settings carrying a
 *  `roles` list (one role, an any-of pair, a role nobody here holds). */
const comp = (() => null) as never;

type FixtureEntry = [string, { default: typeof comp; meta: Record<string, unknown> }];

const FIXTURE: FixtureEntry[] = [
  ["/p/Overview.svelte", { default: comp, meta: { title: "Overview", path: "/overview", order: 10 } }],
  ["/p/AuditTrail.svelte", { default: comp, meta: { title: "Audit trail", path: "/audit-trail", order: 20, roles: ["auditors"] } }],
  ["/p/Bookings.svelte", { default: comp, meta: { title: "Bookings", path: "/bookings", order: 30, roles: ["managers", "auditors"] } }],
  ["/p/Vault.svelte", { default: comp, meta: { title: "Vault", path: "/vault", order: 40, roles: ["owners"] } }],
  ["/p/Branding.svelte", { default: comp, meta: { title: "Branding", path: "/branding", nav: "settings", order: 50 } }],
  ["/p/Keys.svelte", { default: comp, meta: { title: "API keys", path: "/keys", nav: "settings", order: 60, roles: ["managers"] } }],
];

/** The one declaration `collectPages` must REFUSE, not gate: a `roles` list that is
 *  not a list of non-empty strings. Rendering it hidden would be wrong — it never
 *  registers, and the reason is shown on the Modules screen. */
const BAD_ROLES: FixtureEntry = [
  "/p/Broken.svelte",
  { default: comp, meta: { title: "Broken", path: "/broken", order: 70, roles: ["ok", 7] as unknown as string[] } },
];

const AUDITOR: RoleClaims = { username: "auditor", isStaff: false, isSuperuser: false, roles: ["auditors"] };
const MANAGER: RoleClaims = { username: "boss", isStaff: true, isSuperuser: false, roles: ["managers"] };
const NOBODY: RoleClaims = { username: "temp", isStaff: false, isSuperuser: false, roles: ["temp-read"] };
const ROOT: RoleClaims = { username: "admin", isStaff: true, isSuperuser: true, roles: [] };

/** The same declarations with BOTH settings entries gated: the group can then be
 *  emptied by claims, which is the case `{#if settingsNav.length}` exists for. */
const GATED_SETTINGS: FixtureEntry[] = [
  FIXTURE[0],
  ["/p/Branding.svelte", { default: comp, meta: { title: "Branding", path: "/branding", nav: "settings", order: 50, roles: ["managers"] } }],
  FIXTURE[5],
];

const MAIN_ALL = ["Overview", "Audit trail", "Bookings", "Vault"];
const SETTINGS_ALL = ["Branding", "API keys"];

const mounted: Array<Record<string, any>> = [];

function render(): HTMLElement {
  const host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(Sidebar, { target: host }));
  });
  return host;
}

const label = (el: Element) => (el.textContent ?? "").replace(/\s+/g, " ").trim();

function mainButtons(aside: HTMLElement): HTMLButtonElement[] {
  const nav = aside.querySelector("nav");
  expect(nav, "the sidebar rendered no <nav> group").not.toBeNull();
  return [...nav!.querySelectorAll("button")] as HTMLButtonElement[];
}

/** The bottom settings block element, or null. It renders only
 *  `if settingsNav.length`, so a group whose every entry is gated out must vanish
 *  WITH its heading — an empty "Settings" frame over nothing is a rendered bug. */
function settingsGroup(aside: HTMLElement): HTMLElement | null {
  const groups = [...aside.querySelectorAll("div")].filter((d) =>
    [...d.children].some((c) => label(c) === "Settings"),
  );
  expect(groups.length, "the Settings heading rendered more than once").toBeLessThanOrEqual(1);
  return groups[0] ?? null;
}

function settingsButtons(aside: HTMLElement): HTMLButtonElement[] {
  const group = settingsGroup(aside);
  return group ? [...group.querySelectorAll("button")] as HTMLButtonElement[] : [];
}

function goto(hash: string) {
  location.hash = hash;
  flushSync(() => window.dispatchEvent(new Event("hashchange")));
}

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!);
  document.body.innerHTML = "";
  claims.set(null);
  goto("#/");
});

describe("the fixture registry is the population this harness grades", () => {
  it("six accepted nav pages, four of them role-gated, none refused", () => {
    reg.setFixture(FIXTURE);

    expect(reg.pages).toHaveLength(6);
    expect(reg.refusedPages).toEqual([]);
    expect(reg.navPages("main").map((p) => p.title)).toEqual(MAIN_ALL);
    expect(reg.navPages("settings").map((p) => p.title)).toEqual(SETTINGS_ALL);
    expect(reg.navPages().filter((p) => p.roles?.length).map((p) => p.title)).toEqual([
      "Audit trail",
      "Bookings",
      "Vault",
      "API keys",
    ]);
  });
});

describe("the rendered sidebar role gate", () => {
  it("no claims from the server = the whole declared nav renders (plain DRF keeps everything)", () => {
    reg.setFixture(FIXTURE);
    claims.set(null);

    const aside = render();
    expect(mainButtons(aside).map(label)).toEqual(MAIN_ALL);
    expect(settingsButtons(aside).map(label)).toEqual(SETTINGS_ALL);
  });

  it("a single-role caller sees every ungated entry, their own entry and the any-of entry", () => {
    reg.setFixture(FIXTURE);
    claims.set(AUDITOR);

    const aside = render();
    // Bookings declares ["managers","auditors"]: ONE held role is enough (any-of law),
    // and Vault ["owners"] plus API keys ["managers"] are both gated out.
    expect(mainButtons(aside).map(label)).toEqual(["Overview", "Audit trail", "Bookings"]);
    expect(settingsButtons(aside).map(label)).toEqual(["Branding"]);
    expect([...aside.querySelectorAll("button")].map(label)).not.toContain("Vault");
  });

  it("a caller holding none of the declared roles loses every gated entry, keeps every ungated one", () => {
    reg.setFixture(FIXTURE);
    claims.set(NOBODY);

    const aside = render();
    expect(mainButtons(aside).map(label)).toEqual(["Overview"]);
    expect(settingsButtons(aside).map(label)).toEqual(["Branding"]);
  });

  it("a Settings group whose every entry is gated out renders no frame — and it returns with the role", () => {
    // Both settings declarations carry a role the caller does not hold: the group
    // has nothing left to render, so `{#if settingsNav.length}` must drop the
    // heading with it rather than paint an empty "Settings" block.
    reg.setFixture(GATED_SETTINGS);
    claims.set(NOBODY);

    const aside = render();
    expect(mainButtons(aside).map(label)).toEqual(["Overview"]);
    expect(settingsButtons(aside), "an all-gated group must not paint an empty Settings heading").toHaveLength(0);
    expect(settingsGroup(aside), "the Settings frame rendered with no entry inside it").toBeNull();
    unmount(mounted.pop()!);
    document.body.innerHTML = "";

    claims.set(MANAGER);
    const reRendered = render();
    expect(mainButtons(reRendered).map(label)).toEqual(["Overview"]); // GATED_SETTINGS declares one main page
    expect(settingsButtons(reRendered).map(label)).toEqual(SETTINGS_ALL);
  });

  it("a superuser holding no role groups at all sees everything — why the rig seeds a non-superuser", () => {
    reg.setFixture(FIXTURE);
    claims.set(ROOT);

    const aside = render();
    expect(mainButtons(aside).map(label)).toEqual(MAIN_ALL);
    expect(settingsButtons(aside).map(label)).toEqual(SETTINGS_ALL);
  });

  it("the gate is live: claims changing after mount change the nav, and signing out restores it", () => {
    reg.setFixture(FIXTURE);
    claims.set(null);

    const aside = render();
    const visible = () => mainButtons(aside).map(label);
    expect(visible()).toEqual(MAIN_ALL);

    flushSync(() => claims.set(AUDITOR));
    expect(visible()).toEqual(["Overview", "Audit trail", "Bookings"]);

    // a different caller on the same mounted shell: no remount, no re-glob
    flushSync(() => claims.set(NOBODY));
    expect(visible()).toEqual(["Overview"]);

    // logout clears claims, which means NO filtering — a menu that stayed hidden
    // after sign-out would be "hiding is security" in the wrong direction
    flushSync(() => logout());
    expect(get(claims)).toBeNull();
    expect(visible()).toEqual(MAIN_ALL);
  });

  it("a gated entry that IS shown still routes to the href it declared", () => {
    reg.setFixture(FIXTURE);
    claims.set(AUDITOR);

    const aside = render();
    const btn = mainButtons(aside).find((b) => label(b) === "Audit trail");
    expect(btn, "the auditor's own entry did not render").toBeTruthy();
    btn!.click();
    flushSync();
    expect(location.hash).toBe("#/audit-trail");
  });
});

describe("a refused roles declaration never reaches the nav", () => {
  it("no button in any claims state, and the refusal names its reason", () => {
    reg.setFixture([...FIXTURE, BAD_ROLES]);

    expect(reg.pages.map((p) => p.title)).not.toContain("Broken");
    expect(reg.refusedPages).toHaveLength(1);
    expect(reg.refusedPages[0].reason).toContain("roles must be a list");

    for (const who of [null, AUDITOR, ROOT]) {
      claims.set(who);
      const aside = render();
      const rendered = [...mainButtons(aside), ...settingsButtons(aside)].map(label);
      expect(rendered, `claims ${who?.username ?? "null"} must not see a refused page`).not.toContain("Broken");
      unmount(mounted.pop()!);
      document.body.innerHTML = "";
    }
  });
});
