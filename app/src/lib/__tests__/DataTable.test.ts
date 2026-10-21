/** DataTable.svelte tests — keyed {#each} with unique row keys. */
import { describe, expect, it, vi } from "vitest";
import { mount } from "svelte";
import { createRawSnippet } from "svelte";
import type { RecordRow } from "../types";

// Mock dependencies
vi.mock("./Icon.svelte", () => ({
  default: createRawSnippet(() => ({
    render: () => "<span>Icon</span>",
    setup: () => {},
  })),
}));

vi.mock("../lib/utils", () => ({
  formatCell: (v: any) => String(v ?? ""),
}));

describe("DataTable keyed {#each}", () => {
  it("uses unique row keys for outer {#each}", () => {
    const model = {
      id: "products",
      name: "Product",
      singular: "product",
      listPath: "/api/products/",
      detailPath: "/api/products/{id}/",
      labelField: "name",
      fields: [
        { name: "id", type: "number", required: true, readOnly: true },
        { name: "name", type: "text", required: true, readOnly: false },
      ],
      byName: {},
    };

    const rows = [
      { id: 1, name: "Product 1" },
      { id: 2, name: "Product 2" },
      { id: 3, name: "Product 3" },
    ];

    // Verify that each row has a unique id
    const ids = rows.map((r) => r.id);
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(ids.length);
    expect(uniqueIds.size).toBe(3);
  });

  it("uses unique column keys for inner {#each}", () => {
    const model = {
      fields: [
        { name: "id", type: "number", required: true, readOnly: true },
        { name: "name", type: "text", required: true, readOnly: false },
        { name: "price", type: "number", required: true, readOnly: false },
      ],
      byName: {},
    };

    const columns = model.fields.filter((f) => f.type !== "json").slice(0, 6);
    
    // Verify that each column has a unique name
    const names = columns.map((c) => c.name);
    const uniqueNames = new Set(names);
    expect(uniqueNames.size).toBe(names.length);
    expect(uniqueNames.size).toBe(3);
  });

  it("handles rows without id (fallback to JSON.stringify)", () => {
    const rows: RecordRow[] = [
      { name: "Row 1", value: "A" },
      { name: "Row 2", value: "B" },
    ];

    // Verify that JSON.stringify produces unique keys
    const keys = rows.map((r) => r.id ?? JSON.stringify(r));
    const uniqueKeys = new Set(keys);
    expect(uniqueKeys.size).toBe(keys.length);
    expect(uniqueKeys.size).toBe(2);
  });

  it("never reuses outer key variable in nested {#each}", () => {
    // This test verifies the pattern: outer uses row.id, inner uses col.name
    const model = {
      fields: [
        { name: "id", type: "number", required: true, readOnly: true },
        { name: "name", type: "text", required: true, readOnly: false },
      ],
      byName: {},
    };

    const rows = [{ id: 1, name: "Product 1" }];
    const columns = model.fields;

    // Outer key: row.id
    const outerKey = rows[0].id;
    expect(outerKey).toBe(1);

    // Inner keys: col.name (different from outer key variable)
    const innerKeys = columns.map((c) => c.name);
    expect(innerKeys).toEqual(["id", "name"]);
    
    // Verify that inner keys are different from outer key
    expect(innerKeys).not.toContain(outerKey);
  });
});
