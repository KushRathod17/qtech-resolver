import { describe, it, expect } from "vitest";

import { fuzzyScore, scoreItem } from "./CommandPalette";

const TICKETS = [
  { key: "QTR-2", title: "Add Apple Pay to checkout" },
  { key: "QTR-3", title: "Card form rejects valid AMEX numbers" },
  { key: "QTR-4", title: "Migrate session store to Redis" },
  { key: "QTR-7", title: "Rate-limit the login endpoint" },
  { key: "QTR-10", title: "Investigate slow board load" },
  { key: "QTR-19", title: "Sprint 12 — work item 4" },
  { key: "QTR-40", title: "Something else entirely" },
];

const items = TICKETS.map((t) => ({ label: `${t.key}  ${t.title}`, ticket: t }));

/** What the palette would actually show at the top. */
function topMatch(query) {
  const ranked = items
    .map((i) => ({ i, s: scoreItem(query, i) }))
    .filter((x) => x.s >= 0)
    .sort((a, b) => b.s - a.s);
  return ranked[0]?.i.ticket.key ?? null;
}

describe("fuzzyScore", () => {
  it("matches a subsequence", () => {
    expect(fuzzyScore("apay", "Add Apple Pay to checkout")).toBeGreaterThan(0);
  });

  it("returns -1 when the letters aren't there in order", () => {
    expect(fuzzyScore("zzzq", "Add Apple Pay to checkout")).toBe(-1);
  });

  it("scores a contiguous run above a scattered one", () => {
    const tight = fuzzyScore("redis", "Migrate session store to Redis");
    const loose = fuzzyScore("redis", "Rate-limit the login endpoint is");
    expect(tight).toBeGreaterThan(loose);
  });
});

describe("scoreItem — ticket key handling", () => {
  /**
   * The bug this guards against: "qtr4" ranked "QTR-19 — Sprint 12 work item 4"
   * ABOVE QTR-4, because q-t-r-4 genuinely does appear in order in that string.
   * A naive subsequence match is technically right and practically useless.
   * Typing a ticket key must find THAT ticket.
   */
  it("finds the ticket when you type its key without punctuation", () => {
    expect(topMatch("qtr4")).toBe("QTR-4");
  });

  it("finds the ticket when you type its key with punctuation", () => {
    expect(topMatch("QTR-4")).toBe("QTR-4");
    expect(topMatch("qtr-4")).toBe("QTR-4");
  });

  it("prefers an exact key over a longer key with the same prefix", () => {
    // qtr4 must not lose to qtr40.
    expect(topMatch("qtr4")).toBe("QTR-4");
  });

  it("still finds multi-digit keys", () => {
    expect(topMatch("qtr10")).toBe("QTR-10");
    expect(topMatch("qtr19")).toBe("QTR-19");
  });

  it("still matches on title text", () => {
    expect(topMatch("apple")).toBe("QTR-2");
    expect(topMatch("amex")).toBe("QTR-3");
    expect(topMatch("redis")).toBe("QTR-4");
    expect(topMatch("ratelimit")).toBe("QTR-7");
  });

  it("returns nothing for nonsense rather than garbage", () => {
    expect(topMatch("zzzzqqq")).toBe(null);
  });

  it("does not give a key bonus to non-ticket rows", () => {
    const command = { label: "Go to Board" };
    expect(scoreItem("qtr4", command)).toBe(fuzzyScore("qtr4", "Go to Board"));
  });
});
