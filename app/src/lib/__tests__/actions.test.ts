/** FR-R003 client half: the drop-in action registry + the DRF @action /
 *  audit-log API surface. The registry assertions follow the widget contract
 *  test — never a pinned count or id list, because dropping another `.ts`
 *  into src/actions/ must widen the suite, not break it. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  actionPath,
  ApiError,
  callBulkAction,
  callRecordAction,
  fetchAudit,
  fetchHistory,
  transitionRecord,
} from "../api";
import { actions, actionsFor, actionFailureReason } from "../actions/index";
import DataTable from "../../components/DataTable.svelte";
import { normalizeOpenAPI } from "../openapi";
import fixture from "./fixtures/openapi.json";
import type { ModelSpec } from "../types";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const CFG = { apiUrl: "http://localhost:8000", authPath: "/api/auth/token/", schemaPath: "/api/schema/" };
/** Discovered from the real captured document, never hand-written: the R-001
 *  calls below must hit the URLs the schema actually proves, so a hand-made
 *  spec could not detect a renderer wired to a guessed path. */
const ORDERS = normalizeOpenAPI(fixture).byId.orders;
/** Same provenance rule for the R-003 audit read: the log's path is the
 *  schema-discovered listPath of the audit model, never a hand-written
 *  "/api/audit/" segment. */
const AUDIT = normalizeOpenAPI(fixture).byId.audit;

const ENTRY = {
  id: 9,
  action: "order.flag",
  object_type: "order",
  object_id: "42",
  actor: "ops1",
  summary: "Order flagged: suspected fraud",
  data: { reason: "suspected fraud" },
  created_at: "2026-10-19T03:40:00.123456Z",
};

function jsonReply(data: any, status = 201) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data),
  };
}

function lastUrl() {
  return mockFetch.mock.calls.at(-1)![0] as string;
}

function lastInit() {
  return mockFetch.mock.calls.at(-1)![1] as RequestInit;
}

beforeEach(() => mockFetch.mockReset());

describe("action registry (drop-in contract)", () => {
  const labelOf = (id: string) => `${id}: ${JSON.stringify(actions[id].meta.label)}`;

  it("discovers the built-ins without pinning the set", () => {
    const ids = Object.keys(actions);
    for (const builtIn of ["flag", "bulk_flag"]) {
      expect(ids, `missing built-in ${builtIn}`).toContain(builtIn);
    }
    expect(ids).not.toContain("index");
  });

  it("every discovered action satisfies the meta contract", () => {
    expect(Object.keys(actions).length).toBeGreaterThan(0);
    for (const action of Object.values(actions)) {
      expect(typeof action.meta.label, labelOf(action.id)).toBe("string");
      expect(action.meta.label.length, labelOf(action.id)).toBeGreaterThan(0);
      expect(["record", "bulk"], labelOf(action.id)).toContain(action.meta.scope);
      expect(typeof action.meta.handler, labelOf(action.id)).toBe("function");
    }
  });

  it("splits by scope and hides actions bound to another model", () => {
    const synthetic = {
      a: { id: "a", meta: { label: "A", scope: "record" as const, handler: async () => [] } },
      b: { id: "b", meta: { label: "B", scope: "bulk" as const, model: "orders", handler: async () => [] } },
      c: { id: "c", meta: { label: "C", scope: "record" as const, model: "products", handler: async () => [] } },
    };
    expect(actionsFor("orders", "record", synthetic).map((x) => x.id)).toEqual(["a"]);
    expect(actionsFor("orders", "bulk", synthetic).map((x) => x.id)).toEqual(["b"]);
    expect(actionsFor("products", "record", synthetic).map((x) => x.id)).toEqual(["a", "c"]);
  });

  it("the built-in record action targets orders, the bulk one targets orders", () => {
    expect(actionsFor("orders", "record").map((x) => x.id)).toContain("flag");
    expect(actionsFor("orders", "bulk").map((x) => x.id)).toContain("bulk_flag");
    expect(actionsFor("products", "record").map((x) => x.id)).not.toContain("flag");
  });
});

describe("actionPath — DRF router rules", () => {
  it("record scope nests the pk before the slug", () => {
    expect(actionPath(ORDERS, "flag", 42)).toBe("/api/orders/42/flag/");
  });

  it("bulk scope hangs the slug off the collection", () => {
    expect(actionPath(ORDERS, "bulk_flag")).toBe("/api/orders/bulk_flag/");
  });

  it("percent-encodes an unusual pk instead of trusting it", () => {
    expect(actionPath(ORDERS, "flag", "a b/c")).toBe("/api/orders/a%20b%2Fc/flag/");
  });

  it("normalizes a listPath without a trailing slash", () => {
    expect(actionPath({ ...ORDERS, listPath: "/api/orders" }, "transition", 7)).toBe("/api/orders/7/transition/");
  });
});

describe("callRecordAction / callBulkAction", () => {
  it("POSTs the reason to the record endpoint and normalizes one entry", async () => {
    mockFetch.mockResolvedValueOnce(jsonReply(ENTRY));
    const entries = await callRecordAction(CFG, "tok", ORDERS, 42, "flag", { reason: "fraud" });

    expect(lastUrl()).toBe("http://localhost:8000/api/orders/42/flag/");
    expect(lastInit().method).toBe("POST");
    expect(JSON.parse(lastInit().body as string)).toEqual({ reason: "fraud" });
    expect(entries).toEqual([ENTRY]);
  });

  it("keeps the bulk response as one entry per record", async () => {
    mockFetch.mockResolvedValueOnce(jsonReply([ENTRY, { ...ENTRY, id: 10, object_id: "43" }]));
    const entries = await callBulkAction(CFG, "tok", ORDERS, "bulk_flag", { ids: [42, 43], reason: "fraud" });

    expect(lastUrl()).toBe("http://localhost:8000/api/orders/bulk_flag/");
    expect(JSON.parse(lastInit().body as string)).toEqual({ ids: [42, 43], reason: "fraud" });
    expect(entries).toHaveLength(2);
  });

  it("guard failures keep the 400 + {reason} shape and surface the reason", async () => {
    mockFetch.mockResolvedValue(jsonReply({ reason: "unknown order id(s): 99" }, 400));

    await expect(callBulkAction(CFG, "tok", ORDERS, "bulk_flag", { ids: [99], reason: "x" })).rejects.toThrowError(
      ApiError,
    );
    try {
      await callBulkAction(CFG, "tok", ORDERS, "bulk_flag", { ids: [99], reason: "x" });
    } catch (err) {
      expect((err as ApiError).status).toBe(400);
      expect(actionFailureReason(err)).toBe("unknown order id(s): 99");
    }
  });

  it("an error without a reason is not swallowed by actionFailureReason", () => {
    expect(actionFailureReason({ status: 500, detail: { detail: "server boom" } })).toBeNull();
  });

  it("the built-in flag handler fires the shipped endpoint", async () => {
    mockFetch.mockResolvedValueOnce(jsonReply(ENTRY));
    const entries = await actions.flag.meta.handler({
      cfg: CFG,
      token: null,
      model: ORDERS,
      rows: [{ id: 42 }],
      input: "suspected fraud",
    });

    expect(lastUrl()).toBe("http://localhost:8000/api/orders/42/flag/");
    expect(JSON.parse(lastInit().body as string)).toEqual({ reason: "suspected fraud" });
    expect(entries[0].action).toBe("order.flag");
  });

  it("the built-in bulk handler sends every selected id", async () => {
    mockFetch.mockResolvedValueOnce(jsonReply([ENTRY]));
    await actions.bulk_flag.meta.handler({
      cfg: CFG,
      token: null,
      model: ORDERS,
      rows: [{ id: 42 }, { id: 43 }],
      input: "audit sweep",
    });

    expect(JSON.parse(lastInit().body as string)).toEqual({ ids: [42, 43], reason: "audit sweep" });
  });
});

describe("fetchAudit — append-only log read", () => {
  it("unwraps the paginated shape and filters by object_type/object_id", async () => {
    mockFetch.mockResolvedValueOnce(jsonReply({ count: 1, next: null, previous: null, results: [ENTRY] }, 200));
    const page = await fetchAudit(CFG, "tok", {
      path: AUDIT.listPath,
      objectType: "order",
      objectId: 42,
    });

    expect(lastUrl()).toBe("http://localhost:8000/api/audit/?object_type=order&object_id=42");
    expect(page.count).toBe(1);
    expect(page.results).toEqual([ENTRY]);
  });

  it("reads the whole log unfiltered", async () => {
    mockFetch.mockResolvedValueOnce(jsonReply({ count: 0, results: [] }, 200));
    await fetchAudit(CFG, "tok", { path: AUDIT.listPath });
    expect(lastUrl()).toBe("http://localhost:8000/api/audit/");
  });

  it("tolerates a bare list response (a backend without pagination)", async () => {
    mockFetch.mockResolvedValueOnce(jsonReply([ENTRY], 200));
    const page = await fetchAudit(CFG, "tok", { path: AUDIT.listPath, objectType: "order" });
    expect(page.results).toEqual([ENTRY]);
    expect(page.count).toBe(1);
  });

  it("a backend that documents no audit model is refused with zero network calls", async () => {
    // findAuditModel() answers null there, so the caller has no discovered
    // path. Inventing "/api/audit/" would fire a request at whatever the
    // deployment happens to mount at that segment — the evidence law forbids
    // it (same refusal as transitionRecord/fetchHistory above).
    mockFetch.mockClear();
    await expect(fetchAudit(CFG, "tok", { objectType: "order" })).rejects.toThrowError(ApiError);
    await expect(fetchAudit(CFG, "tok")).rejects.toThrowError(ApiError);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("the refusal names the missing evidence", async () => {
    await expect(fetchAudit(CFG, "tok", { path: "" })).rejects.toThrow(/audit/);
  });
});

describe("lifecycle endpoints build their URLs off the schema path", () => {
  it("transition posts to <listPath><id>/transition/", async () => {
    mockFetch.mockResolvedValueOnce(jsonReply({ id: 7, status: "paid" }, 200));
    await transitionRecord(CFG, "tok", ORDERS, 7, "paid");

    expect(lastUrl()).toBe("http://localhost:8000/api/orders/7/transition/");
    expect(JSON.parse(lastInit().body as string)).toEqual({ transition: "paid" });
  });

  it("history reads <listPath><id>/history/", async () => {
    mockFetch.mockResolvedValueOnce(jsonReply([{ id: 1, from_status: "", to_status: "pending" }], 200));
    const rows = await fetchHistory(CFG, "tok", ORDERS, 7);

    expect(lastUrl()).toBe("http://localhost:8000/api/orders/7/history/");
    expect(rows[0].to_status).toBe("pending");
  });

  it("a 409 guard failure carries the reason through ApiError", async () => {
    mockFetch.mockResolvedValue(jsonReply({ reason: "pending → shipped is not allowed" }, 409));
    await expect(transitionRecord(CFG, "tok", ORDERS, 7, "shipped")).rejects.toThrowError(ApiError);

    try {
      await transitionRecord(CFG, "tok", ORDERS, 7, "shipped");
    } catch (err) {
      expect((err as ApiError).status).toBe(409);
      expect((err as ApiError).detail.reason).toBe("pending → shipped is not allowed");
    }
  });

  it("a machine the API does not document is refused with zero network calls", async () => {
    // Same document, lifecycle actions stripped — i.e. a backend that never
    // shipped the R-001 @actions. The client must not invent the URL.
    const { transitionPath, historyPath, ...bare } = ORDERS;
    mockFetch.mockClear();
    await expect(transitionRecord(CFG, "tok", bare as ModelSpec, 7, "paid")).rejects.toThrowError(ApiError);
    await expect(fetchHistory(CFG, "tok", bare as ModelSpec, 7)).rejects.toThrowError(ApiError);
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
