/** kanban.ts tests (FR-R004) — pure logic, no fetch, no component mount.

The contract under test is docs/independent-enums.md §6: the board axis is
DECLARED and never guessed, a lifecycle move goes through the R-001 machine,
and a free-enum move is a PATCH of exactly one field.
*/
import { describe, expect, it } from "vitest";
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
import { getStatusField, hasLifecycle } from "../statusTransitions";
import type { FieldSpec, ModelSpec } from "../types";

function field(name: string, type: FieldSpec["type"], choices?: string[]): FieldSpec {
  return { name, type, required: false, readOnly: false, choices };
}

function modelSpec(id: string, fields: FieldSpec[], labelField = "name"): ModelSpec {
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
  };
}

const ORDERS = modelSpec("orders", [
  field("id", "number"),
  field("customer", "fk"),
  field("total", "number"),
  field("status", "enum", ["pending", "paid", "shipped", "refunded"]),
]);

const SHIPMENTS = modelSpec("shipments", [
  field("id", "number"),
  field("carrier", "text"),
  field("status", "enum", ["new", "delivered"]),
  field("priority", "enum", ["low", "normal", "high"]),
]);

const TRANSITION_AXIS: ResolvedAxis = {
  modelId: "orders",
  field: "status",
  via: "transition",
  columns: ["pending", "paid", "shipped", "refunded"],
};

const FREE_AXIS: ResolvedAxis = {
  modelId: "shipments",
  field: "priority",
  via: "patch",
  columns: ["low", "normal", "high"],
};

describe("kanban axis is declared, never guessed", () => {
  it("gives a model with no declared axis no board at all", () => {
    // SHIPMENTS has two enum fields — a name-guess would happily build a board
    expect(resolveAxis(SHIPMENTS)).toBeNull();
    expect(resolveAxis(SHIPMENTS, {})).toBeNull();
  });

  it("resolves the declared orders axis in lifecycle order", () => {
    const axis = resolveAxis(ORDERS);
    expect(axis).not.toBeNull();
    expect(axis!.field).toBe("status");
    expect(axis!.via).toBe("transition");
    expect(axis!.columns).toEqual(["pending", "paid", "shipped", "refunded"]);
  });

  it("never infers column order from the schema enum list", () => {
    // drf-spectacular sorts filter params; declaration order is not a contract.
    // A transition axis takes its order from the machine's states instead.
    const shuffled = modelSpec("orders", [
      field("id", "number"),
      field("status", "enum", ["refunded", "pending", "shipped", "paid"]),
    ]);
    expect(resolveAxis(shuffled)!.columns).toEqual(
      ["pending", "paid", "shipped", "refunded"],
    );
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
      orders: { field: "status", via: "patch" },
    };
    expect(axisProblem(ORDERS, source)).toMatch(/lifecycle-governed/);
    expect(resolveAxis(ORDERS, source)).toBeNull();
  });

  it("refuses an axis whose field is missing or not an enum", () => {
    expect(axisProblem(ORDERS, { orders: { field: "ghost", via: "patch" } }))
      .toMatch(/is not a field of "orders"/);
    expect(axisProblem(ORDERS, { orders: { field: "total", via: "patch" } }))
      .toMatch(/type "number", not an enum/);
  });

  it("derives free-enum columns from that field's own choices", () => {
    const axis = resolveAxis(SHIPMENTS, {
      shipments: { field: "priority", via: "patch" },
    });
    expect(axis!.columns).toEqual(["low", "normal", "high"]);
    // and never the other field's set on the same model
    expect(axis!.columns).not.toEqual(SHIPMENTS.byName.status.choices);
  });

  it("keeps every shipped declaration consistent with the transition registry", () => {
    for (const [modelId, declared] of Object.entries(kanbanAxes)) {
      const model = modelId === "orders" ? ORDERS : undefined;
      if (!model) continue;
      expect(axisProblem(model, kanbanAxes)).toBeNull();
      if (declared.via === "transition") {
        expect(hasLifecycle(modelId)).toBe(true);
        expect(getStatusField(modelId)).toBe(declared.field);
      }
    }
  });

  it("a model with no axis is not a defect", () => {
    expect(axisProblem(SHIPMENTS)).toBeNull();
  });
});

describe("boardColumns", () => {
  const rows = [
    { id: 1, status: "pending" },
    { id: 2, status: "paid" },
    { id: 3, status: "pending" },
    { id: 4, status: "" },
    { id: 5, status: null },
    { id: 6, status: "cancelled" }, // a value outside the declared set
  ];

  it("shows every declared column, empty ones included", () => {
    const cols = boardColumns(rows, TRANSITION_AXIS);
    expect(cols.map((c) => c.key)).toEqual([
      "pending", "paid", "shipped", "refunded", UNASSIGNED,
    ]);
    expect(cols.find((c) => c.key === "shipped")!.rows).toEqual([]);
  });

  it("groups by the axis value and never loses a record", () => {
    const cols = boardColumns(rows, TRANSITION_AXIS);
    expect(cols.find((c) => c.key === "pending")!.rows.map((r) => r.id)).toEqual([1, 3]);
    const unassigned = cols.find((c) => c.key === UNASSIGNED)!;
    expect(unassigned.rows.map((r) => r.id)).toEqual([4, 5, 6]);
    expect(unassigned.accepts).toBe(false);
    const total = cols.reduce((n, c) => n + c.rows.length, 0);
    expect(total).toBe(rows.length);
  });

  it("drops the unassigned column when nothing needs it", () => {
    const cols = boardColumns([{ id: 1, status: "paid" }], TRANSITION_AXIS);
    expect(cols.map((c) => c.key)).toEqual(["pending", "paid", "shipped", "refunded"]);
  });
});

describe("reachableColumns", () => {
  it("offers only the machine's next states on a lifecycle axis", () => {
    expect(reachableColumns(TRANSITION_AXIS, "pending")).toEqual(["paid"]);
    expect(reachableColumns(TRANSITION_AXIS, "paid")).toEqual(["shipped", "refunded"]);
    expect(reachableColumns(TRANSITION_AXIS, "refunded")).toEqual([]);
  });

  it("offers every other value on a free enum", () => {
    expect(reachableColumns(FREE_AXIS, "low")).toEqual(["normal", "high"]);
  });
});

describe("planMove — exactly one request body per drop", () => {
  it("a legal lifecycle drop posts the R-001 transition, nothing else", () => {
    const plan = planMove(TRANSITION_AXIS, { id: 7, status: "pending" }, "paid");
    expect(plan).toEqual({ ok: true, via: "transition", column: "paid", body: { transition: "paid" } });
  });

  it("refuses an illegal lifecycle drop before the network sees it", () => {
    const plan = planMove(TRANSITION_AXIS, { id: 7, status: "pending" }, "shipped");
    expect(plan.ok).toBe(false);
    if (!plan.ok) {
      expect(plan.reason).toMatch(/illegal transition: 'pending' -> 'shipped'/);
      expect(plan.reason).toMatch(/allowed from current state: paid/);
    }
  });

  it("names the allowed set for a terminal state instead of leaving it blank", () => {
    const plan = planMove(TRANSITION_AXIS, { id: 7, status: "refunded" }, "paid");
    expect(!plan.ok && plan.reason).toMatch(/none — terminal/);
  });

  it("treats a same-column drop as a no-op rejection", () => {
    const plan = planMove(TRANSITION_AXIS, { id: 7, status: "paid" }, "paid");
    expect(!plan.ok && plan.reason).toMatch(/already in "paid"/);
  });

  it("refuses the unassigned bucket and any undeclared column", () => {
    expect(planMove(TRANSITION_AXIS, { id: 7, status: "paid" }, UNASSIGNED).ok).toBe(false);
    const offBoard = planMove(TRANSITION_AXIS, { id: 7, status: "paid" }, "cancelled");
    expect(!offBoard.ok && offBoard.reason).toMatch(/not a declared column/);
  });

  it("refuses a record without an id", () => {
    const plan = planMove(TRANSITION_AXIS, { status: "pending" }, "paid");
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
    const plan = planMove(TRANSITION_AXIS, { id: 7, status: "pending" }, "paid");
    expect(plan.ok && plan.body).not.toHaveProperty("status");
  });
});

describe("cardLabel", () => {
  it("uses the model's label field", () => {
    expect(cardLabel(ORDERS, { id: 1, name: "Widget" })).toBe("Widget");
  });

  it("falls back to name + id, then to the model name", () => {
    expect(cardLabel(ORDERS, { id: 1 })).toBe("Order #1");
    expect(cardLabel(ORDERS, {})).toBe("Order");
  });
});

describe("against the real drf-spectacular fixture", () => {
  const schema = normalizeOpenAPI(fixture);

  it("orders gets a lifecycle board built from the hoisted StatusEnum", () => {
    const axis = resolveAxis(schema.byId.orders);
    expect(axis).not.toBeNull();
    expect(axis!.field).toBe("status");
    expect(axis!.via).toBe("transition");
    expect(axis!.columns).toEqual(["pending", "paid", "shipped", "refunded"]);
  });

  it("no other fixture model gets a board, enum fields or not", () => {
    for (const model of schema.models.filter((m) => m.id !== "orders")) {
      expect([model.id, resolveAxis(model)]).toEqual([model.id, null]);
    }
  });

  it("a board over live-shaped rows keeps every record visible", () => {
    const axis = resolveAxis(schema.byId.orders)!;
    const rows = [
      { id: 1, status: "pending" },
      { id: 2, status: "paid" },
      { id: 3, status: "shipped" },
      { id: 4, status: "refunded" },
      { id: 5, status: "pending" },
    ];
    const cols = boardColumns(rows, axis);
    expect(cols.map((c) => [c.key, c.rows.length])).toEqual([
      ["pending", 2],
      ["paid", 1],
      ["shipped", 1],
      ["refunded", 1],
    ]);
  });
});
