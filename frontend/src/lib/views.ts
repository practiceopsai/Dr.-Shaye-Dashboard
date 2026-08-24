import type { Card } from "./api";

export type ViewKey = "today" | "schedule" | "commitments" | "decisions";

export const viewLabels: Record<ViewKey, string> = {
  today: "Today",
  schedule: "Schedule",
  commitments: "Commitments",
  decisions: "Decisions",
};

export function cardsForView(cards: Card[], view: ViewKey): Card[] {
  if (view === "schedule")
    return cards.filter(card => Boolean(card.deadline) || /calendar|schedule/i.test(card.source));
  if (view === "commitments")
    return cards.filter(card => card.lane === "now" || card.lane === "delegate");
  if (view === "decisions")
    return cards.filter(card => ["P0", "P1", "P2"].includes(card.priority));
  return cards;
}
