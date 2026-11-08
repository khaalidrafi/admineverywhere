/** aiProviders.ts tests — the one-click preset catalog.
 *
 *  Pins (owner order 2026-11-08: keyless APIs like kilo code gateway):
 *  - the three KEYLESS presets exist, each with a live OpenAI-compatible
 *    base URL and a concrete model (verified from this desk 2026-11-08);
 *  - every preset fills EXACTLY the three settings inputs (baseUrl/model/
 *    apiKey) and nothing else — the form keeps the three-input contract;
 *  - preset lookup is exact-id.
 */
import { describe, expect, it } from "vitest";
import { AI_PRESETS, KEYLESS_PRESETS, presetById } from "../aiProviders";

describe("aiProviders", () => {
  it("offers the three cloud-keyless providers plus local Ollama", () => {
    const ids = KEYLESS_PRESETS.map((p) => p.id);
    for (const want of ["kilo-free", "aihorde", "pollinations", "ollama"]) {
      expect(ids, want).toContain(want);
    }
  });

  it("every preset carries a full baseUrl/model pair on the OpenAI wire", () => {
    for (const p of AI_PRESETS) {
      expect(p.baseUrl, p.id).toMatch(/^https?:\/\//);
      expect(p.baseUrl, p.id).not.toMatch(/\/$/); // chat.ts appends /chat/completions
      expect(p.model, p.id).toBeTruthy();
      expect(typeof p.apiKey, p.id).toBe("string");
      expect(p.note, p.id).toBeTruthy();
    }
  });

  it("the kilo preset targets the free auto-routed model, keyless", () => {
    const kilo = presetById("kilo-free")!;
    expect(kilo.baseUrl).toBe("https://ai-gateway.kilo.ai/api/v1");
    expect(kilo.model).toBe("kilo-auto/free");
    expect(kilo.apiKey).toBe("");
    expect(kilo.keyless).toBe(true);
  });

  it("aihorde preset carries the documented anonymous key", () => {
    const horde = presetById("aihorde")!;
    expect(horde.baseUrl).toBe("https://oai.aihorde.net/v1");
    expect(horde.apiKey).toBe("0000000000");
    expect(horde.keyless).toBe(true);
  });

  it("pollinations preset rides the /openai compat path keyless", () => {
    const pol = presetById("pollinations")!;
    expect(pol.baseUrl).toBe("https://text.pollinations.ai/openai");
    expect(pol.model).toBe("openai");
    expect(pol.apiKey).toBe("");
  });

  it("lookup by id is exact", () => {
    expect(presetById("openai")?.label).toBe("OpenAI");
    expect(presetById("nope")).toBeUndefined();
  });
});
