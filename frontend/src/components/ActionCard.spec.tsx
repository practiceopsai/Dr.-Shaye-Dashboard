import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ActionCard from "./ActionCard";
import { api, type Card } from "@/lib/api";

vi.mock("@/lib/api", async importOriginal => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return { ...original, api: { ...original.api, feedback: vi.fn() } };
});

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
  beforeEach(() => vi.clearAllMocks());

  it("labels queued actions as Eli Agent reviews", () => {
    render(<ActionCard card={card} onChanged={() => undefined} />);

    expect(screen.getByText("Eli Agent review")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve & act" })).toBeEnabled();
  });

  it("sends a priority correction when an item is marked not relevant", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    vi.mocked(api.feedback).mockResolvedValue({ feedback_id: "feedback_1", status: "recorded", eli_agent_writeback: true, retriable: false, next_brief_refresh: true, detail: "Recorded" });
    render(<ActionCard card={card} onChanged={onChanged} />);

    await user.click(screen.getByRole("button", { name: "Not relevant" }));

    expect(api.feedback).toHaveBeenCalledWith({
      category: "priority_correction",
      item_id: "priority-1",
      disposition: "not_relevant",
      feedback: "Not relevant for today's command center; reduce recurrence unless circumstances materially change.",
    });
    expect(onChanged).toHaveBeenCalledTimes(1);
  });
});
