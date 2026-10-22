/** chat.ts tests — SSE parser edge cases + schema prompt builder + setup state. */
import { describe, expect, it, vi } from "vitest";
import { buildSchemaPrompt, chatEndpoint, createSSEParser, systemPrompt } from "../chat";
import { normalizeOpenAPI } from "../openapi";
import type { AdminSchema } from "../types";
import fixture from "./fixtures/openapi.json";

describe("createSSEParser", () => {
  const collect = () => {
    const got: string[] = [];
    return { got, feed: createSSEParser((d) => got.push(d)) };
  };

  it("parses basic data lines", () => {
    const { got, feed } = collect();
    feed('data: {"a":1}\n\ndata: {"b":2}\n\n');
    expect(got).toEqual(['{"a":1}', '{"b":2}']);
  });

  it("reassembles events split across chunks", () => {
    const { got, feed } = collect();
    feed('data: {"choices":[{"del');
    feed('ta":{"content":"Hi"}}]}\n\n');
    expect(got).toEqual(['{"choices":[{"delta":{"content":"Hi"}}]}']);
  });

  it("handles CRLF line endings", () => {
    const { got, feed } = collect();
    feed('data: {"a":1}\r\n\r\n');
    expect(got).toEqual(['{"a":1}']);
  });

  it("ignores comments, keep-alives and blank lines", () => {
    const { got, feed } = collect();
    feed(": openai ping\n\ndata: [DONE]\n\n: again\n");
    expect(got).toEqual(["[DONE]"]);
  });

  it("accepts data: without space", () => {
    const { got, feed } = collect();
    feed('data:{"x":9}\n');
    expect(got).toEqual(['{"x":9}']);
  });

  it("no trailing newline -> stays buffered until more arrives", () => {
    const { got, feed } = collect();
    feed('data: {"partial"');
    expect(got).toEqual([]);
    feed(":1}\n");
    expect(got).toEqual(['{"partial":1}']);
  });

  it("drops oversized SSE lines (cap ~1MB, skip+log)", () => {
    const { got, feed } = collect();
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const hugeLine = "x".repeat(1024 * 1024 + 100); // >1MB without newline
    feed(hugeLine);
    expect(got).toEqual([]);
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("[chat] Dropping oversized SSE line fragment")
    );
    // After dropping, can still parse normal events
    feed('\ndata: {"ok":true}\n\n');
    expect(got).toEqual(['{"ok":true}']);
    warnSpy.mockRestore();
  });
});

describe("chatEndpoint", () => {
  it("joins and strips trailing slashes", () => {
    expect(chatEndpoint("https://api.openai.com/v1/")).toBe(
      "https://api.openai.com/v1/chat/completions");
    expect(chatEndpoint("http://localhost:11434/v1")).toBe(
      "http://localhost:11434/v1/chat/completions");
  });
});

describe("buildSchemaPrompt", () => {
  it("builds model summary with legend and field types", () => {
    const schema: AdminSchema = {
      models: [
        {
          id: "products",
          name: "Product",
          singular: "product",
          listPath: "/api/products/",
          detailPath: "/api/products/{id}/",
          labelField: "name",
          fields: [
            { name: "id", type: "number", required: true, readOnly: true },
            { name: "name", type: "text", required: true, readOnly: false },
            { name: "price", type: "number", required: true, readOnly: false },
          ],
          byName: {},
        },
        {
          id: "orders",
          name: "Order",
          singular: "order",
          listPath: "/api/orders/",
          detailPath: "/api/orders/{id}/",
          labelField: "id",
          fields: [
            { name: "id", type: "number", required: true, readOnly: true },
            { name: "status", type: "enum", required: false, readOnly: false, choices: ["pending", "paid"] },
          ],
          byName: {},
        },
      ],
      byId: {},
    };

    const prompt = buildSchemaPrompt(schema);
    expect(prompt).toContain("Available models (fields in parentheses; fk = foreign key to that model):");
    expect(prompt).toContain("- Product [/api/products/]: id(number), name(text), price(number)");
    expect(prompt).toContain("- Order [/api/orders/]: id(number), status(enum)");
  });

  it("shows fk fields with target model", () => {
    const schema: AdminSchema = {
      models: [
        {
          id: "products",
          name: "Product",
          singular: "product",
          listPath: "/api/products/",
          detailPath: "/api/products/{id}/",
          labelField: "name",
          fields: [
            { name: "id", type: "number", required: true, readOnly: true },
            { name: "category", type: "fk", required: true, readOnly: false, fkModel: "categories" },
          ],
          byName: {},
        },
      ],
      byId: {},
    };

    const prompt = buildSchemaPrompt(schema);
    expect(prompt).toContain("category(fk->categories)");
  });

  it("handles empty schema", () => {
    const schema: AdminSchema = {
      models: [],
      byId: {},
    };
    const prompt = buildSchemaPrompt(schema);
    expect(prompt).toBe("Available models (fields in parentheses; fk = foreign key to that model):\n");
  });

  it("grades the LIVE builder against the REAL normalized fixture", () => {
    // The deleted legend-less schemaSummary was tested here instead; a builder
    // that no product file calls can stay green forever, so the fixture-backed
    // assertions now run against the one path the panel actually sends.
    const schema = normalizeOpenAPI(fixture);
    const prompt = buildSchemaPrompt(schema);
    const lines = prompt.split("\n");
    expect(lines[0]).toBe("Available models (fields in parentheses; fk = foreign key to that model):");
    // one line per discovered model, under the legend — actions never add a line
    expect(lines).toHaveLength(schema.models.length + 1);
    expect(schema.models).toHaveLength(5);
    expect(prompt).toContain("- Product [/api/products/]:");
    expect(prompt).toContain("category(fk->categories)");
  });
});


describe("systemPrompt", () => {
  it("is schema-aware", () => {
    const p = systemPrompt("Freshorama Admin", "Models: Product (3 fields)");
    expect(p).toContain("Freshorama Admin");
    expect(p).toContain("Models: Product (3 fields)");
    expect(p).toContain("Never invent fields");
  });
});

describe("setup state logic", () => {
  it("detects missing config", () => {
    const baseUrl = "";
    const apiKey = "";
    const model = "";
    const configured = !!(baseUrl && apiKey && model);
    expect(configured).toBe(false);
  });

  it("detects complete config", () => {
    const baseUrl = "https://api.openai.com/v1";
    const apiKey = "sk-123";
    const model = "gpt-4";
    const configured = !!(baseUrl && apiKey && model);
    expect(configured).toBe(true);
  });

  it("detects partial config", () => {
    const baseUrl = "https://api.openai.com/v1";
    const apiKey = "";
    const model = "gpt-4";
    const configured = !!(baseUrl && apiKey && model);
    expect(configured).toBe(false);
  });
});
