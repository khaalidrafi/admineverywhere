/** The display helpers in src/lib/utils.ts, judged against the REAL module.
 *  Until now formatCell was only ever seen through DataTable.test.ts's stub
 *  (`String(v ?? "")` — never exercised, DataTable.test.ts tests each-keys in
 *  plain code) and through csv.test.ts's note that the 60-char ellipsis is a
 *  display rule that CSV must NOT copy. A stub cannot fail when the real
 *  rules drift, so every contract below is asserted on the shipped function. */
import { describe, expect, it, vi } from "vitest";
import { debounce, formatCell, toISOOrNull } from "../utils";

describe("formatCell — the table's display law", () => {
  it("renders absent values as the em dash, but never a zero", () => {
    expect(formatCell(null)).toBe("—");
    expect(formatCell(undefined)).toBe("—");
    expect(formatCell(0)).toBe("0");
    expect(formatCell(false)).toBe("No");
  });

  it("spells booleans Yes/No — a raw true/false is never shown", () => {
    expect(formatCell(true)).toBe("Yes");
  });

  it("trims datetimes to date + HH:MM and bare dates to the day", () => {
    expect(formatCell("2026-10-21T08:30:00.123456Z")).toBe("2026-10-21 08:30");
    expect(formatCell("2026-10-21")).toBe("2026-10-21");
    expect(formatCell("2026-10-21T08:30")).toBe("2026-10-21 08:30");
  });

  it("never re-flows a decimal — the string DRF sent is the string shown", () => {
    // DRF sends decimals as strings; a Number() round-trip here would silently
    // turn "19.9900" into "19.99" and disagree with the CSV twins' "decimals
    // never re-flowed" rule (docs/csv-export.md).
    expect(formatCell("19.9900")).toBe("19.9900");
    expect(formatCell("0.0000001")).toBe("0.0000001");
  });

  it("ellipsises long text at 57 + one char — exactly 60 stays whole", () => {
    const whole = "x".repeat(60);
    expect(formatCell(whole)).toBe(whole);
    expect(formatCell("x".repeat(61))).toBe("x".repeat(57) + "…");
  });

  it("shows objects as their JSON and survives a circular one", () => {
    expect(formatCell({ a: 1 })).toBe('{"a":1}');
    const circle: Record<string, any> = {};
    circle.self = circle;
    expect(() => formatCell(circle)).not.toThrow();
    expect(formatCell(circle)).toBe("[object Object]");
  });
});

describe("toISOOrNull — datetime-local to DRF", () => {
  it("pads the minute-only value datetime-local yields", () => {
    expect(toISOOrNull("2026-10-21T08:30")).toBe("2026-10-21T08:30:00Z");
  });

  it("passes an already-complete ISO string through untouched", () => {
    expect(toISOOrNull("2026-10-21T08:30:00Z")).toBe("2026-10-21T08:30:00Z");
  });

  it("answers null for empty input — never an empty string on the wire", () => {
    expect(toISOOrNull("")).toBeNull();
  });
});

describe("debounce — the search box coalescing (ModelPage.svelte:65, 300 ms)", () => {
  it("fires only the last call of a burst, with its own args", () => {
    vi.useFakeTimers();
    try {
      const seen: string[] = [];
      const onSearch = debounce((value: string) => seen.push(value), 300);
      onSearch("d");
      onSearch("dr");
      vi.advanceTimersByTime(200);
      onSearch("dro");
      expect(seen).toEqual([]); // nothing fired mid-burst
      vi.advanceTimersByTime(300);
      expect(seen).toEqual(["dro"]); // exactly one call, last args
      onSearch("droplets");
      vi.advanceTimersByTime(300);
      expect(seen).toEqual(["dro", "droplets"]); // later bursts still fire
    } finally {
      vi.useRealTimers();
    }
  });

  it("defaults to the 300 ms the shell uses when no delay is passed", () => {
    vi.useFakeTimers();
    try {
      const fn = vi.fn();
      debounce(fn)();
      vi.advanceTimersByTime(299);
      expect(fn).not.toHaveBeenCalled();
      vi.advanceTimersByTime(1);
      expect(fn).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
