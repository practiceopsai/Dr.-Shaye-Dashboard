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

  it("keeps mission alignment internal until Omid approves displaying it", () => {
    render(<ActionCard card={card} onChanged={() => undefined} />);

    expect(screen.queryByText("Protect focus")).not.toBeInTheDocument();
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

  it("sends positive reinforcement when the action is marked useful and blocks a second submission", async () => {
    const user = userEvent.setup();
    vi.mocked(api.feedback).mockResolvedValue({ feedback_id: "feedback_2", status: "recorded", eli_agent_writeback: true, retriable: false, next_brief_refresh: false, detail: "Reinforced" });
    render(<ActionCard card={card} onChanged={() => undefined} />);

    await user.click(screen.getByRole("button", { name: "Useful" }));

    expect(api.feedback).toHaveBeenCalledWith({
      category: "positive_reinforcement",
      item_id: "priority-1",
      feedback: "The recommended action on this item was useful; reinforce similar recommendations.",
    });
    expect(await screen.findByRole("status")).toHaveTextContent(/recorded/i);
    expect(screen.getByRole("button", { name: "Useful" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Not useful" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Useful" }));
    expect(api.feedback).toHaveBeenCalledTimes(1);
  });

  it("sends a modify priority correction when the action is marked not useful", async () => {
    const user = userEvent.setup();
    vi.mocked(api.feedback).mockResolvedValue({ feedback_id: "feedback_3", status: "queued", eli_agent_writeback: false, retriable: true, next_brief_refresh: false, detail: "Safely queued" });
    render(<ActionCard card={card} onChanged={() => undefined} />);

    await user.click(screen.getByRole("button", { name: "Not useful" }));

    expect(api.feedback).toHaveBeenCalledWith({
      category: "priority_correction",
      item_id: "priority-1",
      disposition: "modify",
      feedback: "The recommended action on this item was not useful; reconsider this kind of recommendation.",
    });
    expect(await screen.findByRole("status")).toHaveTextContent(/queued/i);
  });

  it("shows an error and allows retrying when the usefulness signal fails", async () => {
    const user = userEvent.setup();
    vi.mocked(api.feedback).mockRejectedValueOnce(new Error("Feedback service unavailable"));
    vi.mocked(api.feedback).mockResolvedValueOnce({ feedback_id: "feedback_4", status: "recorded", eli_agent_writeback: true, retriable: false, next_brief_refresh: false, detail: "Recorded" });
    render(<ActionCard card={card} onChanged={() => undefined} />);

    await user.click(screen.getByRole("button", { name: "Useful" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Feedback service unavailable");

    await user.click(screen.getByRole("button", { name: "Useful" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/recorded/i);
    expect(api.feedback).toHaveBeenCalledTimes(2);
  });
});
