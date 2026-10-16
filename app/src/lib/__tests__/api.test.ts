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
