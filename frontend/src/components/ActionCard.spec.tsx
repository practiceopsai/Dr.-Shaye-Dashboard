import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ActionCard from "./ActionCard";
import { api, type Card } from "@/lib/api";

vi.mock("@/lib/api", async importOriginal => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return { ...original, api: { ...original.api, feedback: vi.fn(), approve: vi.fn(), execute: vi.fn() } };
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

  it("lets Dr. Shaye replace the suggestion and approves the exact alternative", async () => {
    const user = userEvent.setup();
    const alternative = "Ask Eli Agent to draft two options and bring them back for my review";
    vi.mocked(api.feedback).mockResolvedValue({ feedback_id: "feedback_5", status: "recorded", eli_agent_writeback: true, retriable: false, next_brief_refresh: true, detail: "Learned" });
    vi.mocked(api.approve).mockResolvedValue({ approval_id: "approval_1", payload_hash: "hash_1" });
    vi.mocked(api.execute).mockResolvedValue({ status: "queued_for_eli_agent" });
    render(<ActionCard card={card} onChanged={() => undefined} />);

    await user.click(screen.getByRole("button", { name: "Choose a different action" }));
    expect(screen.getByRole("button", { name: "Use this action" })).toBeDisabled();
    await user.type(screen.getByLabelText("What should Eli do instead?"), alternative);
    await user.click(screen.getByRole("button", { name: "Use this action" }));

    expect(api.feedback).toHaveBeenCalledWith({
      category: "priority_correction",
      item_id: "priority-1",
      disposition: "modify",
      feedback: `For this item, replace the suggested action "${card.action.label}" with Dr. Shaye's alternative: "${alternative}". Use this correction when recommending similar daily actions in future briefs.`,
    });
    expect(await screen.findByText(alternative)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/selected and learned/i);

    await user.click(screen.getByRole("button", { name: "Approve & act" }));
    expect(api.approve).toHaveBeenCalledWith(expect.objectContaining({
      id: "priority-1",
      action: expect.objectContaining({ label: alternative, kind: "eli_agent_queue", tool_name: null }),
    }));
    expect(api.execute).toHaveBeenCalledWith("approval_1", "hash_1");
  });

  it("keeps the alternative editor open when learning write-back fails", async () => {
    const user = userEvent.setup();
    vi.mocked(api.feedback).mockRejectedValue(new Error("Could not reach Eli Agent"));
    render(<ActionCard card={card} onChanged={() => undefined} />);

    await user.click(screen.getByRole("button", { name: "Choose a different action" }));
    await user.type(screen.getByLabelText("What should Eli do instead?"), "Prepare a shorter decision memo");
    await user.click(screen.getByRole("button", { name: "Use this action" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach Eli Agent");
    expect(screen.getByLabelText("What should Eli do instead?")).toBeInTheDocument();
  });
});
