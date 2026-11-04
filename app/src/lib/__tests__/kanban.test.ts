/** kanban.ts tests (FR-R004) — pure logic, no fetch, no component mount.

The contract under test is docs/independent-enums.md §6: the board axis is
DECLARED and never guessed, a lifecycle move goes through the R-001 machine,
and a free-enum move is a PATCH of exactly one field.

OWNER DIRECTIVE 2026-11-04 (#freshorama): "we won't approve/deny orders. So,
nothing like pending orders." The shipped registry carries NO orders axis and
NO orders lifecycle — the first describe pins that law. The transition-leg
machinery (boardColumns / reachableColumns / planMove) is still exercised, but
against a SYNTHETIC "jobs" machine registered here, never against orders.
*/
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import fixture from "./fixtures/openapi.json";
import { normalizeOpenAPI } from "../openapi";
import {
  axisProblem,
  boardColumns,
  cardLabel,
  kanbanAxes,
  planMove,
  reachableColumns,
  resolveAxis,
  UNASSIGNED,
  type KanbanAxis,
  type ResolvedAxis,
} from "../kanban";
import { getStatusField, hasLifecycle, statusTransitions } from "../statusTransitions";
import type { FieldSpec, ModelSpec } from "../types";

/** A synthetic governed model so the transition machinery stays tested even
 *  though orders (the only real governed model) is ungoverned by owner law. */
const JOBS_MACHINE = {
  statusField: "status",
  states: ["queued", "running", "done"],
  transitions: {
    queued: ["running"],
    running: ["done"],
    done: [], // terminal
  },
};

beforeAll(() => {
  statusTransitions.jobs = JOBS_MACHINE;
});
afterAll(() => {
  delete statusTransitions.jobs;
});

function field(name: string, type: FieldSpec["type"], choices?: string[]): FieldSpec {
  return { name, type, required: false, readOnly: false, choices };
}

function modelSpec(
  id: string,
  fields: FieldSpec[],
  labelField = "name",
  lifecycle: Partial<ModelSpec> = {},
): ModelSpec {
  const singular = id.replace(/s$/, "");
  return {
    id,
    name: singular.charAt(0).toUpperCase() + singular.slice(1),
    singular,
    listPath: `/api/${id}/`,
    detailPath: `/api/${id}/{id}/`,
    fields,
    byName: Object.fromEntries(fields.map((f) => [f.name, f])),
    labelField,
    ...lifecycle,
  };
}

/** The lifecycle URLs a board may move records through are DISCOVERED, not
 *  assumed — taken from the real captured document. */
const JOBS_LIFECYCLE: Partial<ModelSpec> = {
  transitionPath: "/api/jobs/{id}/transition/",
  historyPath: "/api/jobs/{id}/history/",
};

const JOBS = modelSpec(
  "jobs",
  [
    field("id", "number"),
    field("label", "text"),
    field("status", "enum", ["queued", "running", "done"]),
  ],
  "label",
  JOBS_LIFECYCLE,
);

const SHIPMENTS = modelSpec("shipments", [
  field("id", "number"),
  field("carrier", "text"),
  field("status", "enum", ["new", "delivered"]),
  field("priority", "enum", ["low", "normal", "high"]),
]);

const TRANSITION_AXIS: ResolvedAxis = {
  modelId: "jobs",
  field: "status",
  via: "transition",
  columns: ["queued", "running", "done"],
};

const FREE_AXIS: ResolvedAxis = {
  modelId: "shipments",
  field: "priority",
  via: "patch",
  columns: ["low", "normal", "high"],
};

describe("the no-approve/deny law: orders carry no board", () => {
  const LIVE = normalizeOpenAPI(fixture);

  it("the shipped registry declares no orders axis (and never a status axis)", () => {
    expect(Object.keys(kanbanAxes).sort()).toEqual(["products"]);
    expect(kanbanAxes.orders).toBeUndefined();
  });

  it("orders resolve to NO board even though the rig documents status + transition", () => {
    expect(LIVE.byId.orders.byName.status).toBeTruthy();
    expect(LIVE.byId.orders.transitionPath).toBeTruthy();
    expect(resolveAxis(LIVE.byId.orders)).toBeNull();
    expect(axisProblem(LIVE.byId.orders, kanbanAxes)).toBeNull(); // undeclared is not a defect
  });
});

describe("kanban axis is declared, never guessed", () => {
  it("gives a model with no declared axis no board at all", () => {
    // SHIPMENTS has two enum fields — a name-guess would happily build a board
    expect(resolveAxis(SHIPMENTS)).toBeNull();
    expect(resolveAxis(SHIPMENTS, {})).toBeNull();
  });

  it("resolves a declared transition axis in the machine's state order", () => {
    const axis = resolveAxis(JOBS, {
      jobs: { field: "status", via: "transition" },
    });
    expect(axis).not.toBeNull();
    expect(axis!.field).toBe("status");
    expect(axis!.via).toBe("transition");
    expect(axis!.columns).toEqual(["queued", "running", "done"]);
  });

  it("never infers column order from the schema enum list", () => {
    // drf-spectacular sorts filter params; declaration order is not a contract.
    // A transition axis takes its order from the machine's states instead.
    const shuffled = modelSpec(
      "jobs",
      [field("id", "number"), field("status", "enum", ["done", "queued", "running"])],
      "label",
      JOBS_LIFECYCLE,
    );
    expect(resolveAxis(shuffled, { jobs: { field: "status", via: "transition" } })!.columns).toEqual(
      ["queued", "running", "done"],
    );
  });

  it("refuses a transition axis whose endpoint the API does not document", () => {
    // The registry declares the machine, but a backend that never shipped the
    // R-001 @action would answer every drop with a 404. Refused, nameably —
    // the same law as an axis on a non-enum field or a patch axis on a
    // lifecycle field (docs/independent-enums.md §6).
    const undocumented = modelSpec("jobs", [
      field("id", "number"),
      field("status", "enum", ["queued", "running", "done"]),
    ]);
    const source: Record<string, KanbanAxis> = { jobs: { field: "status", via: "transition" } };
    expect(resolveAxis(undocumented, source)).toBeNull();
    expect(axisProblem(undocumented, source)).toMatch(/does not document/);
  });

  it("honours an explicit column override", () => {
    const axis = resolveAxis(SHIPMENTS, {
      shipments: { field: "priority", via: "patch", columns: ["high", "low"] },
    });
    expect(axis!.columns).toEqual(["high", "low"]);
  });

  it("refuses a transition axis on a model without the R-001 machine", () => {
    const source: Record<string, KanbanAxis> = {
      shipments: { field: "status", via: "transition" },
    };
    expect(hasLifecycle("shipments")).toBe(false);
    expect(axisProblem(SHIPMENTS, source)).toMatch(/no R-001 state machine/);
    expect(resolveAxis(SHIPMENTS, source)).toBeNull();
  });

  it("refuses a patch axis on a lifecycle field — it would bypass the machine", () => {
    const source: Record<string, KanbanAxis> = {
      jobs: { field: "status", via: "patch" },
    };
    expect(axisProblem(JOBS, source)).toMatch(/lifecycle-governed/);
    expect(resolveAxis(JOBS, source)).toBeNull();
  });

  it("refuses an axis whose field is missing or not an enum", () => {
    expect(axisProblem(JOBS, { jobs: { field: "ghost", via: "patch" } }))
      .toMatch(/is not a field of "jobs"/);
    expect(axisProblem(JOBS, { jobs: { field: "label", via: "patch" } }))
      .toMatch(/type "text", not an enum/);
  });

  it("derives free-enum columns from that field's own choices", () => {
    const axis = resolveAxis(SHIPMENTS, {
      shipments: { field: "priority", via: "patch" },
    });
    expect(axis!.columns).toEqual(["low", "normal", "high"]);
    // and never the other field's set on the same model
    expect(axis!.columns).not.toEqual(SHIPMENTS.byName.status.choices);
  });

  it("keeps every shipped declaration consistent with the captured document", () => {
    // The registry is product code, so EVERY declaration in it is graded against
    // the captured document. The population is pinned: orders was REMOVED by
    // owner law and must never quietly come back through this sweep.
    const live = normalizeOpenAPI(fixture);
    expect(Object.keys(kanbanAxes).sort()).toEqual(["products"]);
    for (const [modelId, declared] of Object.entries(kanbanAxes)) {
      const model = live.byId[modelId];
      expect(model, `axis names "${modelId}", which the captured document does not carry`).toBeTruthy();
      expect(axisProblem(model, kanbanAxes), `"${modelId}.${declared.field}" is refused`).toBeNull();
      const axis = resolveAxis(model, kanbanAxes)!;
      expect(axis.field).toBe(declared.field);
      expect(axis.via).toBe(declared.via);
      expect(axis.columns.length).toBeGreaterThan(0);
      if (declared.via === "transition") {
        expect(hasLifecycle(modelId)).toBe(true);
        expect(getStatusField(modelId)).toBe(declared.field);
      } else {
        // a free-enum axis must NOT be a lifecycle field, and its columns are
        // that field's OWN choices — never another field's set, and never the
        // BlankEnum sentinel turned into a board column (§3 guardrails 1 + 2,
        // §4: the empty state is the optional signal, not a choice)
        expect(getStatusField(modelId)).not.toBe(declared.field);
        expect(axis.columns).toEqual(model.byName[declared.field].choices);
        expect(axis.columns).not.toContain("");
      }
    }
  });

  it("a model with no axis is not a defect", () => {
    expect(axisProblem(SHIPMENTS)).toBeNull();
  });
});

describe("boardColumns", () => {
  const rows = [
    { id: 1, status: "queued" },
    { id: 2, status: "running" },
    { id: 3, status: "queued" },
    { id: 4, status: "" },
    { id: 5, status: null },
    { id: 6, status: "archived" }, // a value outside the declared set
  ];

  it("shows every declared column, empty ones included", () => {
    const cols = boardColumns(rows, TRANSITION_AXIS);
    expect(cols.map((c) => c.key)).toEqual([
      "queued", "running", "done", UNASSIGNED,
    ]);
    expect(cols.find((c) => c.key === "done")!.rows).toEqual([]);
  });

  it("groups by the axis value and never loses a record", () => {
    const cols = boardColumns(rows, TRANSITION_AXIS);
    expect(cols.find((c) => c.key === "queued")!.rows.map((r) => r.id)).toEqual([1, 3]);
    const unassigned = cols.find((c) => c.key === UNASSIGNED)!;
    expect(unassigned.rows.map((r) => r.id)).toEqual([4, 5, 6]);
    expect(unassigned.accepts).toBe(false);
    const total = cols.reduce((n, c) => n + c.rows.length, 0);
    expect(total).toBe(rows.length);
  });

  it("drops the unassigned column when nothing needs it", () => {
    const cols = boardColumns([{ id: 1, status: "running" }], TRANSITION_AXIS);
    expect(cols.map((c) => c.key)).toEqual(["queued", "running", "done"]);
  });
});

describe("reachableColumns", () => {
  it("offers only the machine's next states on a lifecycle axis", () => {
    expect(reachableColumns(TRANSITION_AXIS, "queued")).toEqual(["running"]);
    expect(reachableColumns(TRANSITION_AXIS, "running")).toEqual(["done"]);
    expect(reachableColumns(TRANSITION_AXIS, "done")).toEqual([]);
  });

  it("offers every other value on a free enum", () => {
    expect(reachableColumns(FREE_AXIS, "low")).toEqual(["normal", "high"]);
  });
});

describe("planMove — exactly one request body per drop", () => {
  it("a legal lifecycle drop posts the R-001 transition, nothing else", () => {
    const plan = planMove(TRANSITION_AXIS, { id: 7, status: "queued" }, "running");
    expect(plan).toEqual({ ok: true, via: "transition", column: "running", body: { transition: "running" } });
  });

  it("refuses an illegal lifecycle drop before the network sees it", () => {
    const plan = planMove(TRANSITION_AXIS, { id: 7, status: "queued" }, "done");
    expect(plan.ok).toBe(false);
    if (!plan.ok) {
      expect(plan.reason).toMatch(/illegal transition: 'queued' -> 'done'/);
      expect(plan.reason).toMatch(/allowed from current state: running/);
    }
  });

  it("names the allowed set for a terminal state instead of leaving it blank", () => {
    const plan = planMove(TRANSITION_AXIS, { id: 7, status: "done" }, "running");
    expect(!plan.ok && plan.reason).toMatch(/none — terminal/);
  });

  it("treats a same-column drop as a no-op rejection", () => {
    const plan = planMove(TRANSITION_AXIS, { id: 7, status: "running" }, "running");
    expect(!plan.ok && plan.reason).toMatch(/already in "running"/);
  });

  it("refuses the unassigned bucket and any undeclared column", () => {
    expect(planMove(TRANSITION_AXIS, { id: 7, status: "running" }, UNASSIGNED).ok).toBe(false);
    const offBoard = planMove(TRANSITION_AXIS, { id: 7, status: "running" }, "archived");
    expect(!offBoard.ok && offBoard.reason).toMatch(/not a declared column/);
  });

  it("refuses a record without an id", () => {
    const plan = planMove(TRANSITION_AXIS, { status: "queued" }, "running");
    expect(!plan.ok && plan.reason).toMatch(/no id/);
  });

  it("a free-enum drop patches ONE field and touches nothing else", () => {
    const row = { id: 9, carrier: "DHL", status: "new", priority: "low" };
    const plan = planMove(FREE_AXIS, row, "high");
    expect(plan.ok).toBe(true);
    if (plan.ok) {
      expect(plan.via).toBe("patch");
      expect(Object.keys(plan.body)).toEqual(["priority"]); // never a whole-row PUT
      expect(plan.body).toEqual({ priority: "high" });
    }
  });

  it("a transition plan never leaks the status field into the body", () => {
    const plan = planMove(TRANSITION_AXIS, { id: 7, status: "queued" }, "running");
    expect(plan.ok && plan.body).not.toHaveProperty("status");
  });
});

describe("cardLabel", () => {
  it("uses the model's label field", () => {
    expect(cardLabel(JOBS, { id: 1, label: "Widget" })).toBe("Widget");
  });

  it("falls back to name + id, then to the model name", () => {
    expect(cardLabel(JOBS, { id: 1 })).toBe("Job #1");
    expect(cardLabel(JOBS, {})).toBe("Job");
  });
});

describe("against the real drf-spectacular fixture", () => {
  const schema = normalizeOpenAPI(fixture);

  it("orders gets NO board — ungoverned by owner law even with a hoisted StatusEnum", () => {
    expect(resolveAxis(schema.byId.orders)).toBeNull();
  });

  it("products gets a FREE-ENUM board — its own choices, no lifecycle in sight", () => {
    const axis = resolveAxis(schema.byId.products);
    expect(axis).not.toBeNull();
    expect(axis!.field).toBe("packaging");
    expect(axis!.via).toBe("patch");
    expect(axis!.columns).toEqual(["box", "crate", "pallet"]);
    // BlankEnum is the optional signal, never a board column (§4), so the empty
    // state cannot appear as a draggable choice beside the real ones
    expect(axis!.columns).not.toContain("");
    // and the rig documents no state machine for products, which is what makes a
    // `patch` axis legal here rather than a bypass (guardrail 1)
    expect(schema.byId.products.transitionPath).toBeUndefined();
  });

  it("no UNdeclared fixture model gets a board, enum fields or not", () => {
    // The point of this leg is the GUESS it forbids: a model carrying enum
    // fields still gets nothing until an axis is DECLARED for it. Graded against
    // the shipped registry — orders (and every other enum-carrying fixture
    // model) is undeclared since the no-approve/deny law.
    const undeclared = schema.models.filter((m) => !kanbanAxes[m.id]);
    expect(undeclared.length).toBeGreaterThan(0); // a vacuous sweep is not a test
    for (const model of undeclared) {
      expect([model.id, resolveAxis(model)]).toEqual([model.id, null]);
    }
  });

  it("a board over live-shaped rows keeps every record visible (synthetic machine)", () => {
    const axis = TRANSITION_AXIS;
    const rows = [
      { id: 1, status: "queued" },
      { id: 2, status: "running" },
      { id: 3, status: "queued" },
      { id: 4, status: "done" },
      { id: 5, status: "queued" },
    ];
    const cols = boardColumns(rows, axis);
    expect(cols.map((c) => [c.key, c.rows.length])).toEqual([
      ["queued", 3],
      ["running", 1],
      ["done", 1],
    ]);
  });
});
