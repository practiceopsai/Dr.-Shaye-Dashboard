import { describe, expect, it } from "vitest";
import type { Card } from "./api";
import { cardsForView } from "./views";

function card(overrides: Partial<Card>): Card {
  return {
    id: "card",
    priority: "P3",
    lane: "protect",
    category: "Focus",
    title: "Protect family time",
    context: "Keep the evening clear.",
    consequence: "Important time would be displaced.",
    source: "priority rules",
    mission_alignment: "aligned",
    action: { label: "Ask Eli Agent to protect the block", kind: "eli_agent_queue", arguments: {}, account: "personal", recipients: [], reversible: true },
    ...overrides,
  };
}

const cards = [
  card({ id: "scheduled", deadline: "Today at 3 PM" }),
  card({ id: "calendar", source: "personal calendar" }),
  card({ id: "commitment", lane: "now" }),
  card({ id: "delegated", lane: "delegate" }),
  card({ id: "decision", priority: "P2" }),
  card({ id: "protected", priority: "P3", lane: "protect" }),
];

describe("cardsForView", () => {
  it("returns the complete matrix for Today", () => expect(cardsForView(cards, "today")).toEqual(cards));
  it("returns only time-bound or calendar cards for Schedule", () => expect(cardsForView(cards, "schedule").map(c => c.id)).toEqual(["scheduled", "calendar"]));
  it("returns current and delegated work for Commitments", () => expect(cardsForView(cards, "commitments").map(c => c.id)).toEqual(["commitment", "delegated"]));
  it("returns only P0-P2 cards for Decisions", () => expect(cardsForView(cards, "decisions").map(c => c.id)).toEqual(["decision"]));
  it("handles an empty dashboard", () => expect(cardsForView([], "schedule")).toEqual([]));
});
