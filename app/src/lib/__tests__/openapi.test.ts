/** openapi.ts tests — run against the REAL drf-spectacular fixture. */
import { describe, expect, it } from "vitest";
import fixture from "./fixtures/openapi.json";
import { normalizeOpenAPI, singularize, titleCase } from "../openapi";

const schema = normalizeOpenAPI(fixture);

describe("model discovery", () => {
  it("finds exactly the router-registered models of the live rig", () => {
    // audit is the FR-R003 model; the R-001/R-003 @actions and the R-005 export
    // sibling are detail/collection actions and must NOT become models.
    expect(schema.models.map((m) => m.id).sort()).toEqual(
      ["audit", "categories", "customers", "orders", "products"],
    );
  });

  it("skips schema/auth endpoints (no GET+POST pair or contain params)", () => {
    const ids = schema.models.map((m) => m.id);
    expect(ids).not.toContain("token");
    expect(ids).not.toContain("schema");
  });

  it("builds detail paths", () => {
    expect(schema.byId.products.detailPath).toBe("/api/products/{id}/");
  });

  it("derives display names", () => {
    expect(schema.byId.categories.name).toBe("Category");
    expect(schema.byId.products.name).toBe("Product");
  });
});

describe("field type mapping (Product)", () => {
  const product = schema.byId.products;
  const f = (name: string) => product.byName[name];

  it("leads with read-only pk id", () => {
    expect(product.fields[0].name).toBe("id");
    expect(f("id").readOnly).toBe(true);
    expect(f("id").type).toBe("number");
  });

  it("maps char/text/email -> text", () => {
    expect(f("name").type).toBe("text");
    expect(f("description").type).toBe("text");
  });

  it("maps decimal + integer -> number", () => {
    expect(f("price").type).toBe("number");
    expect(f("price").format).toBe("decimal");
    expect(f("stock").type).toBe("number");
  });

  it("maps boolean", () => {
    expect(f("is_active").type).toBe("boolean");
  });

  it("maps date and date-time formats", () => {
    expect(f("launch_date").type).toBe("date");
    expect(schema.byId.orders.byName.created_at.type).toBe("datetime");
  });

  it("carries required flags from the Request schema", () => {
    expect(f("name").required).toBe(true);
    expect(f("price").required).toBe(true);
    expect(f("description").required).toBe(false);
  });

  it("detects FK via name-matching heuristic", () => {
    const fk = f("category");
    expect(fk.type).toBe("fk");
    expect(fk.fkModel).toBe("categories");
    expect(fk.required).toBe(true);
  });
});

describe("field type mapping (Order)", () => {
  const order = schema.byId.orders;

  it("resolves enum choices from $ref component", () => {
    const status = order.byName.status;
    expect(status.type).toBe("enum");
    expect(status.choices).toEqual(["pending", "paid", "shipped", "refunded"]);
    expect(status.required).toBe(false);
  });

  it("detects both FKs", () => {
    expect(order.byName.customer.type).toBe("fk");
    expect(order.byName.customer.fkModel).toBe("customers");
    expect(order.byName.product.fkModel).toBe("products");
  });

  it("read-only created_at not in writable set", () => {
    expect(order.byName.created_at.readOnly).toBe(true);
    expect(order.byName.created_at.required).toBe(false);
  });

  it("maps the rig's FloatField to number — not an FK, not a string", () => {
    // FR-R005's witness. drf-spectacular emits FloatField as type:number
    // (format:double) while DecimalField stays type:string (format:decimal),
    // and that asymmetry is the whole reason the two export layers can
    // disagree — layer 1 gets JSON.parse's number and String()s it. The FK
    // heuristic must also not capture a bare numeric property whose name
    // matches no model, or a float column becomes a dropdown.
    const weight = order.byName.weight;
    expect(weight.type).toBe("number");
    expect(weight.format).toBe("double");
    expect(weight.required).toBe(false);
    expect(weight.readOnly).toBe(false);
    expect(order.byName.total.type).toBe("number");
    expect(order.byName.total.format).toBe("decimal");
  });
});

describe("label field heuristics", () => {
  it("picks name for Product/Category/Customer", () => {
    expect(schema.byId.products.labelField).toBe("name");
    expect(schema.byId.categories.labelField).toBe("name");
    expect(schema.byId.customers.labelField).toBe("name");
  });

  it("falls back gracefully", () => {
    // Order has no label-ish field -> id
    expect(schema.byId.orders.labelField).toBe("id");
  });
});

describe("helpers", () => {
  it("singularize", () => {
    expect(singularize("categories")).toBe("category");
    expect(singularize("products")).toBe("product");
    expect(singularize("status")).toBe("status");
  });
  it("titleCase", () => {
    expect(titleCase("product")).toBe("Product");
  });
});

describe("server-export discovery (FR-R005 layer 2)", () => {
  /** Minimal doc: one list model at /api/things/ plus an optional sibling. */
  function docWith(sibling?: { get?: boolean; post?: boolean }) {
    const paths: Record<string, any> = {
      "/api/things/": {
        get: { responses: { "200": { content: { "application/json": { schema: { $ref: "#/components/schemas/PaginatedThingList" } } } } } },
        post: { requestBody: { content: { "application/json": { schema: { $ref: "#/components/schemas/ThingRequest" } } } } },
      },
    };
    if (sibling?.get) paths["/api/things/export/"] = { get: { responses: { "200": { content: { "text/csv": { schema: { type: "string" } } } } } } };
    if (sibling?.post) paths["/api/things/export/"].post = { responses: { "200": { content: {} } } };
    return {
      paths,
      components: {
        schemas: {
          Thing: { properties: { id: { type: "integer", readOnly: true }, name: { type: "string" } } },
          ThingRequest: { properties: { name: { type: "string" } }, required: ["name"] },
          PaginatedThingList: {
            properties: { results: { type: "array", items: { $ref: "#/components/schemas/Thing" } } },
          },
        },
      },
    };
  }

  it("binds exportPath when GET <list>export/ exists", () => {
    expect(normalizeOpenAPI(docWith({ get: true })).byId.things.exportPath)
      .toBe("/api/things/export/");
  });

  it("leaves exportPath undefined when the document carries no export", () => {
    expect(normalizeOpenAPI(docWith()).byId.things.exportPath).toBeUndefined();
    // The live rig DOES document GET /api/orders/export/ (FR-R005 layer 2), so
    // the captured fixture binds it — and a model without the sibling stays
    // undefined, which is silent degradation, not an error (same rule as a
    // plain DRF backend and the static brand).
    expect(schema.byId.orders.exportPath).toBe("/api/orders/export/");
    expect(schema.byId.products.exportPath).toBeUndefined();
  });

  it("refuses a sibling that also takes POST — that shape is a list, not an action", () => {
    // Guessing here is how `apiUrl + "export"` once broke the R-001 calls.
    expect(normalizeOpenAPI(docWith({ get: true, post: true })).byId.things.exportPath)
      .toBeUndefined();
  });

  it("never discovers the export sibling as a model of its own", () => {
    const out = normalizeOpenAPI(docWith({ get: true }));
    expect(out.byId.export).toBeUndefined();
    expect(out.models.map((m) => m.id)).toEqual(["things"]);
  });
});

describe("lifecycle discovery (FR-R001)", () => {
  /** Minimal doc: one list model plus optional detail actions. */
  function docWithActions(actions: Record<string, { get?: boolean; post?: boolean }>) {
    const paths: Record<string, any> = {
      "/api/orders/": {
        get: { responses: { "200": { content: { "application/json": { schema: { $ref: "#/components/schemas/PaginatedOrderList" } } } } } },
        post: { requestBody: { content: { "application/json": { schema: { $ref: "#/components/schemas/OrderRequest" } } } } },
      },
      "/api/orders/{id}/": {
        get: { responses: { "200": { content: { "application/json": { schema: { $ref: "#/components/schemas/Order" } } } } } },
      },
    };
    for (const [slug, verbs] of Object.entries(actions)) {
      const op: Record<string, any> = {};
      if (verbs.get) op.get = { responses: { "200": { content: { "application/json": { schema: { type: "array", items: {} } } } } } };
      if (verbs.post) op.post = { responses: { "200": { content: { "application/json": { schema: {} } } } } };
      paths[`/api/orders/{id}/${slug}/`] = op;
    }
    return {
      paths,
      components: {
        schemas: {
          Order: { properties: { id: { type: "integer", readOnly: true }, status: { type: "string" } } },
          OrderRequest: { properties: { status: { type: "string" } }, required: ["status"] },
          PaginatedOrderList: { properties: { results: { type: "array", items: { $ref: "#/components/schemas/Order" } } } },
        },
      },
    };
  }

  it("binds both endpoints where the captured rig documents them", () => {
    expect(schema.byId.orders.transitionPath).toBe("/api/orders/{id}/transition/");
    expect(schema.byId.orders.historyPath).toBe("/api/orders/{id}/history/");
    // the trail is read-only; the transition takes a POST — a model that ships
    // neither keeps both keys absent rather than a guessed path
    expect(schema.byId.products.transitionPath).toBeUndefined();
    expect(schema.byId.products.historyPath).toBeUndefined();
  });

  it("binds transition only on evidence of a POST", () => {
    expect(normalizeOpenAPI(docWithActions({ transition: { post: true } })).byId.orders.transitionPath)
      .toBe("/api/orders/{id}/transition/");
    // a GET-only sibling is not a transition — the verb is the evidence
    expect(normalizeOpenAPI(docWithActions({ transition: { get: true } })).byId.orders.transitionPath)
      .toBeUndefined();
    expect(normalizeOpenAPI(docWithActions({})).byId.orders.transitionPath).toBeUndefined();
  });

  it("binds history only on GET without POST — same law as exportPath", () => {
    expect(normalizeOpenAPI(docWithActions({ history: { get: true } })).byId.orders.historyPath)
      .toBe("/api/orders/{id}/history/");
    expect(normalizeOpenAPI(docWithActions({ history: { get: true, post: true } })).byId.orders.historyPath)
      .toBeUndefined();
  });

  it("never discovers a lifecycle action as a model of its own", () => {
    const out = normalizeOpenAPI(docWithActions({ transition: { post: true }, history: { get: true } }));
    expect(out.models.map((m) => m.id)).toEqual(["orders"]);
  });
});
