import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ActionCard from "./ActionCard";
import type { Card } from "@/lib/api";

const card: Card = {
  id: "priority-1",
  priority: "P1",
  lane: "delegate",
  category: "Operations",
  title: "Resolve the operating blocker",
  context: "A decision is required today.",
  consequence: "The team remains blocked without a decision.",
  deadline: "Today",
  source: "Eli Agent",
  mission_alignment: "Protect focus",
  action: {
    label: "Ask Eli Agent to prepare the decision",
    kind: "eli_agent_queue",
    arguments: {},
    account: "none",
    recipients: [],
    reversible: true,
  },
};

describe("ActionCard", () => {
  it("labels queued actions as Eli Agent reviews", () => {
    render(<ActionCard card={card} onChanged={() => undefined} />);

    expect(screen.getByText("Eli Agent review")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve & act" })).toBeEnabled();
  });
});
