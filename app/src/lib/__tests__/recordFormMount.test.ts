/** RecordForm mounted for real, through its only caller (ModelPage) — the wire
 *  level proof the mirror tests could not give. RecordForm.test.ts re-implements
 *  buildPayload inside the test file and asserts against its own copy, so a
 *  component that sends different bytes, to the wrong URL, or hydrated from the
 *  previous record stays green. Same law as chatMount.test.ts and
 *  lifecycleMount.test.ts: assert the captured request, not a hand-written
 *  builder. Harness = browser resolve condition + flushSync + stubbed fetch,
 *  schema = normalizeOpenAPI of the captured fixture.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import ModelPageHarness from "./fixtures/ModelPageHarness.svelte";
import RecordFormHarness from "./fixtures/RecordFormHarness.svelte";
import { harnessProps, recordFormHarnessProps } from "./fixtures/harnessProps";
import Toaster from "../../components/Toaster.svelte";
import { normalizeOpenAPI } from "../openapi";
import { app, toasts } from "../stores";
import fixture from "./fixtures/openapi.json";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

let currentProps: Record<string, any> = {};

const instances: Array<ReturnType<typeof mount>> = [];
const hosts: HTMLElement[] = [];
afterEach(() => {
  while (instances.length) unmount(instances.pop()!);
  instances.length = 0;
  mockFetch.mockReset();
  toasts.set([]);
  app.set({} as any);
  harnessProps.set({});
  recordFormHarnessProps.set({});
  while (hosts.length) hosts.pop()!.remove();
});

const LIVE = normalizeOpenAPI(fixture);

/** Two Product rows: #7 is opened by hand, #9 arrives by deep link. */
const ROW7 = {
  id: 7, name: "Cold Brew Kit", description: "Glass carafe", price: "24.90",
  stock: 4, is_active: true, launch_date: "2026-01-02", category: 1,
};
const ROW9 = {
  id: 9, name: "Pour-Over Kettle", description: "Gooseneck", price: "89.00",
  stock: 12, is_active: false, launch_date: "2026-03-04", category: 2,
};
const CATEGORIES = [
  { id: 1, name: "Brewing" },
  { id: 2, name: "Kettles" },
];

function reply(status: number, data: any) {
  return { ok: status < 400, status, json: async () => data, text: async () => JSON.stringify(data) };
}

/** Route by URL so the test asserts WHICH endpoint the client believed in. */
function route(opts: { products?: any[]; detail?: Record<string, any> } = {}) {
  const rows = opts.products ?? [ROW7, ROW9];
  mockFetch.mockImplementation(async (url: string, init?: any) => {
    const u = String(url);
    if (u.startsWith("http://api.test/api/categories/")) return reply(200, { count: 2, results: CATEGORIES, next: null });
    if (/\/api\/products\/\d+\/$/.test(u)) {
      const id = u.match(/\/api\/products\/(\d+)\/$/)![1];
      if (init?.method === "PUT") return reply(200, { ...(opts.detail?.[id] ?? ROW7), id });
      return reply(200, opts.detail?.[id] ?? rows.find((r) => String(r.id) === id) ?? ROW7);
    }
    if (u.startsWith("http://api.test/api/products/")) return reply(200, { count: rows.length, results: rows, next: null });
    if (u.startsWith("http://api.test/api/orders/")) return reply(200, { count: 0, results: [], next: null });
    return reply(200, { count: 0, results: [] });
  });
}

function render(props: Record<string, any> = { modelId: "products" }) {
  const host = document.createElement("div");
  const toastHost = document.createElement("div");
  hosts.push(host, toastHost);
  document.body.append(host, toastHost);
  currentProps = props;
  harnessProps.set(props);
  app.update((a) => ({
    ...a,
    schema: LIVE,
    token: "tok",
    booted: true,
    apiUrlOverride: "http://api.test",
    config: { apiUrl: "http://api.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
  }));
  instances.push(mount(ModelPageHarness, { target: host }));
  instances.push(mount(Toaster, { target: toastHost }));
  return { host, toastHost };
}

const urls = () => mockFetch.mock.calls.map((c) => String(c[0]));
/** The WRITE to a matching URL — a detail GET to the same path carries no body. */
const bodyOf = (match: (u: string) => boolean) => {
  const call = mockFetch.mock.calls.find((c) => match(String(c[0])) && c[1]?.body);
  return call?.[1] ? JSON.parse(call[1].body) : undefined;
};

/** Update the mounted page's props exactly like the shell does — a hash change
 *  re-renders <Page {...$route.params} /> (Shell.svelte:54), it does not
 *  remount, so a param change travels into a live component. */
function setProps(props: Record<string, any>) {
  currentProps = { ...currentProps, ...props };
  harnessProps.set(currentProps);
  flushSync(() => {});
}

async function awaitTable(host: HTMLElement, text: string) {
  await vi.waitFor(() => {
    flushSync(() => {});
    expect(host.textContent).toContain(text);
  });
}

function click(host: HTMLElement, selector: string) {
  const el = host.querySelector<HTMLElement>(selector);
  expect(el, `missing ${selector}`).toBeTruthy();
  flushSync(() => el!.click());
  return el!;
}

function openForm(host: HTMLElement) {
  const form = host.querySelector("form.card");
  expect(form, "no RecordForm modal mounted").toBeTruthy();
  return form as HTMLFormElement;
}

function fieldValue(form: HTMLFormElement, name: string) {
  const el = form.querySelector<HTMLInputElement>(`#f-${name}`);
  return el ? el.value : undefined;
}

function type(host: HTMLElement, name: string, value: string) {
  const el = host.querySelector<HTMLInputElement>(`#f-${name}`);
  expect(el, `missing field #f-${name}`).toBeTruthy();
  flushSync(() => {
    el!.value = value;
    el!.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

/** Pick an FK/enum option the way a browser reports it.
 *  Svelte's `bind:value` on a <select> reads the change event through
 *  `select.querySelector(":checked")` and falls back to the first
 *  non-disabled option (svelte/src/internal/client/dom/elements/bindings/
 *  select.js:89-100) — and happy-dom never matches `:checked` for <option>,
 *  not even via the `selected` property, so a plain value+change drive reads
 *  as "user picked the placeholder". The shim answers ONLY the `:checked`
 *  lookup with the option a real browser would have marked checked, which is
 *  the fact under test; the assignment and the event stay native. */
function choose(host: HTMLElement, name: string, value: string) {
  const el = host.querySelector<HTMLSelectElement>(`#f-${name}`);
  expect(el, `missing select #f-${name}`).toBeTruthy();
  const opt = [...el!.options].find((o) => o.value === value);
  expect(opt, `no option "${value}" in #f-${name}`).toBeTruthy();
  const native = el!.querySelector.bind(el);
  (el as any).querySelector = (q: string) => (q === ":checked" ? opt : (native as any)(q));
  try {
    flushSync(() => {
      el!.value = value;
      el!.dispatchEvent(new Event("change", { bubbles: true }));
    });
  } finally {
    delete (el as any).querySelector;
  }
}

function check(host: HTMLElement, name: string, value: boolean) {
  const el = host.querySelector<HTMLInputElement>(`#f-${name}`);
  expect(el, `missing checkbox #f-${name}`).toBeTruthy();
  flushSync(() => {
    el!.checked = value;
    el!.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

function submitForm(host: HTMLElement) {
  flushSync(() => openForm(host).dispatchEvent(new SubmitEvent("submit", { cancelable: true, bubbles: true })));
}

/** The FK <select> is disabled while its options load, so a case that picks a
 *  target has to wait for the real fetch — otherwise `category` stays empty and
 *  the required-field guard refuses the submit. */
async function awaitFkLoaded(host: HTMLElement) {
  await vi.waitFor(() => {
    flushSync(() => {});
    const sel = host.querySelector<HTMLSelectElement>("#f-category");
    expect(sel && !sel.disabled && sel.options.length > 1).toBe(true);
  });
}

async function awaitWrite(match: (u: string) => boolean) {
  await vi.waitFor(() => {
    expect(mockFetch.mock.calls.some((c) => match(String(c[0]))), `no write to a matching URL`).toBe(true);
  });
}

describe("mounted RecordForm — the bytes the CRUD spec actually sends", () => {
  it("hydrates every field type from the record it was opened with", async () => {
    route();
    const { host } = render();
    await awaitTable(host, "Cold Brew Kit");

    click(host, "button[title='Edit']"); // first row = #7
    const form = openForm(host);
    expect(form.textContent).toContain("Edit Product #7");
    expect(fieldValue(form, "name")).toBe("Cold Brew Kit");
    expect(fieldValue(form, "price")).toBe("24.90");
    expect(fieldValue(form, "stock")).toBe("4");
    expect(fieldValue(form, "launch_date")).toBe("2026-01-02");
    // decimal arrives as a string, so the number input must carry it un-re-flowed
    expect(host.querySelector("#f-price")!.getAttribute("step")).toBe("0.01");
  });

  it("feeds the FK dropdown through the discovered listPath, never apiUrl + id", async () => {
    route();
    const { host } = render();
    await awaitTable(host, "Cold Brew Kit");
    click(host, "button[title='Edit']");
    await vi.waitFor(() => {
      flushSync(() => {});
      const sel = host.querySelector<HTMLSelectElement>("#f-category");
      expect(sel?.options.length).toBeGreaterThan(2); // placeholder + 2 targets
    });
    expect(urls().filter((u) => u.includes("/api/categories/"))).toEqual([
      "http://api.test/api/categories/?page=1&page_size=100",
    ]);
    const labels = [...host.querySelector<HTMLSelectElement>("#f-category")!.options].map((o) => o.textContent?.trim());
    expect(labels).toEqual(["—", "Brewing", "Kettles"]);
    // the row's own FK is selected, and the select is enabled once options land
    const sel2 = host.querySelector<HTMLSelectElement>("#f-category")!;
    expect(sel2.value).toBe("1");
    expect(sel2.disabled).toBe(false);
  });

  it("PUTs the component's own buildPayload to the detail path, with its rules intact", async () => {
    route();
    const { host, toastHost } = render();
    await awaitTable(host, "Cold Brew Kit");
    click(host, "button[title='Edit']");

    type(host, "name", "Cold Brew Kit v2");
    type(host, "price", "29.90");
    submitForm(host);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(toastHost.textContent).toContain("Product updated");
    });

    const call = mockFetch.mock.calls.find((c) => /\/api\/products\/7\/$/.test(String(c[0])) && c[1]?.body)!;
    expect(String(call[0])).toBe("http://api.test/api/products/7/");
    expect(call[1].method).toBe("PUT");
    expect(call[1].headers.Authorization).toBe("Token tok");
    const sent = JSON.parse(call[1].body);
    expect(sent.name).toBe("Cold Brew Kit v2");
    // number fields are coerced, not echoed as text — a quoted 29.90 re-flows the decimal
    expect(sent.price).toBe(29.9);
    expect(sent.stock).toBe(4);
    expect(sent.category).toBe(1);
    expect(sent.is_active).toBe(true);
    expect(sent.launch_date).toBe("2026-01-02");
  });

  it("omits an empty non-nullable field and nulls an empty nullable one", async () => {
    route();
    const { host, toastHost } = render();
    await awaitTable(host, "Cold Brew Kit");
    click(host, "button[title='Edit']");

    type(host, "description", ""); // non-nullable CharField -> omit, sending null 400s
    type(host, "launch_date", ""); // nullable date -> explicit null clears it
    submitForm(host);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(toastHost.textContent).toContain("Product updated");
    });

    const sent = bodyOf((u) => /\/api\/products\/7\/$/.test(u));
    expect("description" in sent).toBe(false);
    expect(sent.launch_date).toBeNull();
  });

  it("a blank required field is refused client-side, with zero requests", async () => {
    route();
    const { host } = render();
    await awaitTable(host, "Cold Brew Kit");
    click(host, "button[title='Edit']");
    const before = mockFetch.mock.calls.length;

    type(host, "name", "");
    submitForm(host);
    flushSync(() => {});
    expect(host.textContent).toContain("This field is required.");
    expect(mockFetch.mock.calls.length).toBe(before);
  });

  it("creates through the list path when no record was given", async () => {
    route();
    const { host, toastHost } = render();
    await awaitTable(host, "Cold Brew Kit");

    const create = [...host.querySelectorAll("button")].find((b) => b.textContent?.includes("New Product"));
    expect(create, "no 'New Product' button").toBeTruthy();
    flushSync(() => create!.click());
    expect(openForm(host).textContent).toContain("New Product");
    type(host, "name", "Travel Grinder");
    type(host, "price", "45.00");
    await awaitFkLoaded(host);
    choose(host, "category", "2");
    check(host, "is_active", true);
    submitForm(host);

    const call = mockFetch.mock.calls.find((c) => String(c[0]).startsWith("http://api.test/api/products/") && c[1]?.method === "POST")!;
    expect(String(call[0])).toBe("http://api.test/api/products/");
    const sent = JSON.parse(call[1].body);
    expect(sent).toEqual({ name: "Travel Grinder", price: 45, category: 2, is_active: true, launch_date: null });
    // untouched empty fields: the non-nullable stock is omitted (DRF applies its
    // default), the nullable launch_date is sent as explicit null
    expect("stock" in sent).toBe(false);
    expect("description" in sent).toBe(false);
  });

  it("re-hydrates when a deep link names another record while the form is open", async () => {
    route({ detail: { "7": ROW7, "9": ROW9 } });
    const { host, toastHost } = render({ modelId: "products" });
    await awaitTable(host, "Cold Brew Kit");
    click(host, "button[title='Edit']");
    expect(fieldValue(openForm(host), "name")).toBe("Cold Brew Kit");

    // #/m/products/9 with the modal already up: the page refetches and points
    // `editing` at #9, and the editor must show #9's bytes — never #7's.
    setProps({ recordId: "9" });
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(openForm(host).textContent).toContain("Edit Product #9");
    });
    expect(fieldValue(openForm(host), "name")).toBe("Pour-Over Kettle");
    expect(fieldValue(openForm(host), "price")).toBe("89.00");
    expect(fieldValue(openForm(host), "description")).toBe("Gooseneck");
    // the FK lists are re-read with the form, not inherited from the previous
    // hydration — the same instance served the record switch
    expect(urls().filter((u) => u.includes("/api/categories/")).length).toBe(2);

    submitForm(host);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(toastHost.textContent).toContain("Product updated");
    });
    await awaitWrite((u) => /\/api\/products\/9\/$/.test(u));
    const sent = bodyOf((u) => /\/api\/products\/9\/$/.test(u));
    expect(sent.name).toBe("Pour-Over Kettle");
    expect(sent.price).toBe(89);
    expect(mockFetch.mock.calls.some((c) => c[1]?.method === "PUT" && /\/api\/products\/7\/$/.test(String(c[0])))).toBe(false);
  });

  it("renders the blank=True choices field as the select it declares (FR-R002 case C)", async () => {
    // The consequence the gap was about: {oneOf:[PackagingEnum,BlankEnum]} used
    // to reach RecordForm as an unrecognized shape and fall through to a
    // free-text <input>, so a user could type any string into a choices field
    // and the server would 400 it. The select's own "—" option is the blank
    // state; BlankEnum never becomes a choice.
    route();
    const { host } = render();
    await awaitTable(host, "Cold Brew Kit");
    click(host, "button[title='Edit']");
    const el = openForm(host).querySelector("#f-packaging");
    expect(el?.tagName, "packaging degraded to an <input>").toBe("SELECT");
    expect([...(el as HTMLSelectElement).options].map((o) => o.value)).toEqual(["", "box", "crate", "pallet"]);

    // untouched blank stays OMITTED, never an explicit null — that half of the
    // wire contract is pinned by the create case below, whose exact-payload
    // assertion failed the moment buildPayload treated this field as nullable
    choose(host, "packaging", "crate");
    submitForm(host);
    await awaitWrite((u) => /\/api\/products\/7\/$/.test(u));
    expect(bodyOf((u) => /\/api\/products\/7\/$/.test(u)).packaging).toBe("crate");
  });

  it("refuses to carry an open form into another module", async () => {
    route();
    const { host } = render();
    await awaitTable(host, "Cold Brew Kit");
    click(host, "button[title='Edit']");
    expect(host.querySelector("form.card")).toBeTruthy();

    // The shell swaps `modelId` in place, so `model` becomes Orders while
    // `editing` still points at a Product row: a PUT /api/orders/7/ wearing
    // Product field names.
    setProps({ modelId: "orders" });
    flushSync(() => {});
    expect(host.querySelector("form.card")).toBeNull();
    expect(mockFetch.mock.calls.some((c) => c[1]?.method === "PUT")).toBe(false);
  });
});

describe("RecordForm's own props-move contract", () => {
  // The deep-link case above proves the PAGE keeps the editor honest — but it
  // passes without RecordForm.svelte's re-hydration effect, because in Svelte 5
  // a spread-props re-render re-fires EVERY effect that reads a prop even when
  // the value is identical (probed 2026-10-21: an equal re-spread ran the
  // effect twice), so ModelPage's model-switch guard closes the modal on every
  // route change and the form is REMOUNTED, not moved. The effect's real
  // subject is a prop that moves on a mounted instance, and only a parent of
  // RecordForm's own can deliver that transition. These cases pin the code the
  // fix shipped, not the code the page happens to run.
  let rfProps: Record<string, any> = {};

  function renderRF(props: Record<string, any>) {
    const host = document.createElement("div");
    const toastHost = document.createElement("div");
    hosts.push(host, toastHost);
    document.body.append(host, toastHost);
    rfProps = props;
    recordFormHarnessProps.set(props);
    app.update((a) => ({
      ...a,
      schema: LIVE,
      token: "tok",
      booted: true,
      apiUrlOverride: "http://api.test",
      config: { apiUrl: "http://api.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
    }));
    instances.push(mount(RecordFormHarness, { target: host }));
    instances.push(mount(Toaster, { target: toastHost }));
    return { host, toastHost };
  }

  function setRFProps(patch: Record<string, any>) {
    rfProps = { ...rfProps, ...patch };
    recordFormHarnessProps.set(rfProps);
    flushSync(() => {});
  }

  const NOOP = () => {};

  it("re-hydrates when the record prop moves on the mounted instance", async () => {
    route({ detail: { "7": ROW7, "9": ROW9 } });
    const { host } = renderRF({ model: LIVE.byId["products"], record: ROW7, onclose: NOOP, onsaved: NOOP });
    await awaitFkLoaded(host);
    expect(fieldValue(openForm(host), "name")).toBe("Cold Brew Kit");

    setRFProps({ record: ROW9 });

    await vi.waitFor(() => {
      flushSync(() => {});
      expect(fieldValue(openForm(host), "name")).toBe("Pour-Over Kettle");
    });
    expect(fieldValue(openForm(host), "price")).toBe("89.00");
    expect(fieldValue(openForm(host), "description")).toBe("Gooseneck");
    // the FK option lists are re-read for the new hydration, not inherited
    expect(urls().filter((u) => u.includes("/api/categories/")).length).toBe(2);

    submitForm(host);
    await awaitWrite((u) => /\/api\/products\/9\/$/.test(u));
    const sent = bodyOf((u) => /\/api\/products\/9\/$/.test(u));
    expect(sent.name).toBe("Pour-Over Kettle");
    expect(sent.price).toBe(89);
    expect(sent.category).toBe(2); // values, not the DOM select — state is authoritative
    expect(mockFetch.mock.calls.some((c) => c[1]?.method === "PUT" && /\/api\/products\/7\/$/.test(String(c[0])))).toBe(false);
  });

  it("re-hydrates the field set when the model prop moves on the mounted instance", async () => {
    route();
    const { host } = renderRF({ model: LIVE.byId["products"], record: ROW7, onclose: NOOP, onsaved: NOOP });
    await awaitFkLoaded(host);
    expect(host.querySelector("#f-price")).toBeTruthy();
    expect(host.querySelector("#f-category")).toBeTruthy();

    // record moves with the module (the page would never send a Product row to
    // a Customer path; the form must simply stop wearing Product fields)
    setRFProps({ model: LIVE.byId["customers"], record: null });

    flushSync(() => {});
    expect(openForm(host), "the instance was remounted, not moved").toBeTruthy();
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.querySelector("#f-price")).toBeNull();
    });
    expect(host.querySelector("#f-category")).toBeNull();
    expect(host.querySelector("#f-email")).toBeTruthy();
    expect(host.querySelector("#f-joined_on")).toBeTruthy();
    expect(fieldValue(openForm(host), "name")).toBe("");
  });

  // An equal re-spread must not re-fetch: the effect's identity gate exists
  // because Svelte 5 re-fires prop-reading effects on every parent re-render.
  it("does not re-hydrate when props re-spread with identical values", async () => {
    route();
    const { host } = renderRF({ model: LIVE.byId["products"], record: ROW7, onclose: NOOP, onsaved: NOOP });
    await awaitFkLoaded(host);
    const before = urls().filter((u) => u.includes("/api/categories/")).length;

    setRFProps({ model: LIVE.byId["products"], record: ROW7 }); // same identities, new object
    flushSync(() => {});

    expect(urls().filter((u) => u.includes("/api/categories/")).length).toBe(before);
    expect(fieldValue(openForm(host), "name")).toBe("Cold Brew Kit");
  });
});
