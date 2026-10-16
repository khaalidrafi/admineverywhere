/** openapi.ts tests — run against the REAL drf-spectacular fixture. */
import { describe, expect, it } from "vitest";
import fixture from "./fixtures/openapi.json";
import { normalizeOpenAPI, schemaSummary, singularize, titleCase } from "../openapi";

const schema = normalizeOpenAPI(fixture);

describe("model discovery", () => {
  it("finds exactly the 4 router-registered models", () => {
    expect(schema.models.map((m) => m.id).sort()).toEqual(
      ["categories", "customers", "orders", "products"],
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

describe("schemaSummary (AI system prompt)", () => {
  it("lists every model with its fields on one line each", () => {
    const s = schemaSummary(schema);
    expect(s).toContain("- Product [/api/products/]:");
    expect(s).toContain("category(fk->categories)");
    expect(s.split("\n")).toHaveLength(4);
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
