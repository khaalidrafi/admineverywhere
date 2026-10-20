/** api.ts tests — security: secrets never in URLs/query strings, redacted from errors. */
import { describe, expect, it, vi } from "vitest";
import { ApiError, fieldErrors } from "../api";

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

describe("ApiError redaction", () => {
  it("redacts tokens from error details", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      text: async () => JSON.stringify({ detail: { password: "secret123", token: "xyz" } }),
    });

    try {
      const { login } = await import("../api");
      await login({ apiUrl: "http://localhost", authPath: "/auth", schemaPath: "/schema" } as any, "u", "p");
    } catch (err) {
      if (err instanceof ApiError) {
        expect(err.detail).toMatchObject({
          detail: { password: "********", token: "********" }
        });
      }
    }
  });

  it("redacts from network errors", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network failure with token=abc"));

    try {
      const { listRecords } = await import("../api");
      await listRecords(
        { apiUrl: "http://localhost", authPath: "/auth", schemaPath: "/schema" } as any,
        "test-token",
        { id: "users", listPath: "/api/users/", detailPath: "/api/users/{id}/", fields: [], byName: {}, name: "User", singular: "user", labelField: "id" } as any
      );
    } catch (err) {
      if (err instanceof ApiError) {
        expect(err.detail).not.toContain("test-token");
      }
    }
  });
});

describe("URL credential stripping", () => {
  it("strips username/password from API URL", async () => {
    let capturedUrl = "";
    mockFetch.mockImplementationOnce((url: string) => {
      capturedUrl = url;
      return Promise.resolve({
        ok: true,
        status: 200,
        text: async () => JSON.stringify([]),
      });
    });

    const { listRecords } = await import("../api");
    await listRecords(
      { apiUrl: "http://user:pass@localhost:8000", authPath: "/auth", schemaPath: "/schema" } as any,
      null,
      { id: "items", listPath: "/api/items/", detailPath: "/api/items/{id}/", fields: [], byName: {}, name: "Item", singular: "item", labelField: "id" } as any
    );

    expect(capturedUrl).not.toContain("user:pass");
    expect(capturedUrl).toBe("http://localhost:8000/api/items/");
  });
});

describe("fieldErrors extraction", () => {
  it("extracts DRF 400 validation errors", () => {
    const detail = {
      name: ["This field is required.", "Must be at least 1 character."],
      email: ["Enter a valid email."],
    };
    const result = fieldErrors(detail);
    expect(result).toEqual({
      name: "This field is required. Must be at least 1 character.",
      email: "Enter a valid email.",
    });
  });

  it("handles string detail", () => {
    const result = fieldErrors("General error message");
    expect(result).toEqual({ _: "General error message" });
  });
});

describe("fetchCsv (FR-R005 layer 2)", () => {
  const MODEL_EXPORT = "/api/orders/export/";

  function respond(over: Record<string, any> = {}) {
    return {
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Disposition": 'attachment; filename="orders-line.csv"' }),
      text: async () => "﻿id\r\n1\r\n",
      ...over,
    };
  }

  it("authenticates the GET and asks for text/csv, on the base URL only", async () => {
    let captured: [string, RequestInit] | null = null;
    mockFetch.mockImplementationOnce((url: string, init: RequestInit) => {
      captured = [url, init];
      return Promise.resolve(respond());
    });
    const { fetchCsv } = await import("../api");
    const pending = fetchCsv(
      { apiUrl: "http://srv:8000/" } as any, "tok-1", MODEL_EXPORT, "fallback.csv",
    );
    const [url, init] = captured as unknown as [string, RequestInit];
    // path comes from the schema, so the call is base + the documented path —
    // never a bare segment concatenated onto a URL.
    expect(url).toBe("http://srv:8000/api/orders/export/");
    // text/csv is the preferred type; the lowercase-q wildcard fallback lets a
    // plain DRF/proxy JSON error body still answer 4xx-readable instead of 406.
    expect((init.headers as any).Accept).toMatch(/^text\/csv,\s*\*\/\*;q=0\.8$/);
    expect((init.headers as any).Authorization).toBe("Token tok-1");
    expect((await pending).filename).toBe("orders-line.csv");
  });

  it("sends no Authorization header when signed out", async () => {
    let captured: RequestInit | null = null;
    mockFetch.mockImplementationOnce((_url: string, init: RequestInit) => {
      captured = init;
      return Promise.resolve(respond());
    });
    const { fetchCsv } = await import("../api");
    await fetchCsv({ apiUrl: "http://srv" } as any, null, MODEL_EXPORT, "f.csv");
    expect((captured as any as RequestInit).headers).not.toHaveProperty("Authorization");
  });

  it("takes the filename from Content-Disposition, quoted or bare", async () => {
    const { fetchCsv } = await import("../api");
    mockFetch.mockResolvedValueOnce(respond());
    expect((await fetchCsv({ apiUrl: "http://srv" } as any, null, MODEL_EXPORT, "fb.csv")).filename)
      .toBe("orders-line.csv");

    mockFetch.mockResolvedValueOnce(respond({
      headers: new Headers({ "Content-Disposition": "attachment; filename=raw-export.csv" }),
    }));
    expect((await fetchCsv({ apiUrl: "http://srv" } as any, null, MODEL_EXPORT, "fb.csv")).filename)
      .toBe("raw-export.csv");
  });

  it("falls back to the caller's name when the header is missing", async () => {
    mockFetch.mockResolvedValueOnce(respond({ headers: new Headers() }));
    const { fetchCsv } = await import("../api");
    expect((await fetchCsv({ apiUrl: "http://srv" } as any, null, MODEL_EXPORT, "orders-line.csv")).filename)
      .toBe("orders-line.csv");
  });

  it("will not let a hostile header steer the save path", async () => {
    mockFetch.mockResolvedValueOnce(respond({
      headers: new Headers({ "Content-Disposition": 'attachment; filename="../../etc/cron.d/x.csv"' }),
    }));
    const { fetchCsv } = await import("../api");
    const name = (await fetchCsv({ apiUrl: "http://srv" } as any, null, MODEL_EXPORT, "fb.csv")).filename;
    expect(name).not.toContain("..");
    expect(name).not.toContain("/");
    expect(name.endsWith(".csv")).toBe(true);
  });

  it("normalises a doubled .csv suffix rather than appending to it", async () => {
    mockFetch.mockResolvedValueOnce(respond({
      headers: new Headers({ "Content-Disposition": 'attachment; filename="orders.csv"' }),
    }));
    const { fetchCsv } = await import("../api");
    expect((await fetchCsv({ apiUrl: "http://srv" } as any, null, MODEL_EXPORT, "fb.csv")).filename)
      .toBe("orders.csv");
  });

  it("raises ApiError with the status on a 4xx/5xx, JSON detail or not", async () => {
    mockFetch.mockResolvedValueOnce(respond({
      ok: false, status: 403, text: async () => JSON.stringify({ detail: { token: "leak" } }),
    }));
    const { ApiError: E, fetchCsv } = await import("../api");
    await expect(
      fetchCsv({ apiUrl: "http://srv" } as any, "tok", MODEL_EXPORT, "fb.csv"),
    ).rejects.toThrow(/403/);
    mockFetch.mockResolvedValueOnce(respond({ ok: false, status: 500, text: async () => "<html>gateway</html>" }));
    await expect(
      fetchCsv({ apiUrl: "http://srv" } as any, "tok", MODEL_EXPORT, "fb.csv"),
    ).rejects.toBeInstanceOf(E);
  });

  it("raises a network ApiError that never carries the token", async () => {
    mockFetch.mockRejectedValueOnce(new Error("down at token=tok"));
    const { ApiError: E, fetchCsv } = await import("../api");
    const err = await fetchCsv({ apiUrl: "http://srv" } as any, "tok", MODEL_EXPORT, "fb.csv")
      .then(() => null).catch((e) => e);
    expect(err).toBeInstanceOf(E);
    expect(String(err?.detail)).not.toContain("tok");
  });

  it("returns the server body untouched (its BOM is the writer's, not ours)", async () => {
    mockFetch.mockResolvedValueOnce(respond({ text: async () => "﻿id\r\n1\r\n" }));
    const { fetchCsv } = await import("../api");
    const out = await fetchCsv({ apiUrl: "http://srv" } as any, null, MODEL_EXPORT, "fb.csv");
    expect(out.text.startsWith("﻿")).toBe(true);
  });
});
