/** chat.ts tests — SSE parser edge cases (network chunking is hostile). */
import { describe, expect, it, vi } from "vitest";
import { chatEndpoint, createSSEParser, systemPrompt } from "../chat";

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

describe("systemPrompt", () => {
  it("is schema-aware", () => {
    const p = systemPrompt("Freshorama Admin", "- Product [/api/products/]: name(text)");
    expect(p).toContain("Freshorama Admin");
    expect(p).toContain("Product");
    expect(p).toContain("Never invent fields");
  });
});
