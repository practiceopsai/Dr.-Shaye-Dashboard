import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, Card } from "@/lib/api";
import FeedbackPanel from "./FeedbackPanel";

vi.mock("@/lib/api", async importOriginal => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return { ...original, api: { ...original.api, feedback: vi.fn(), retryFeedback: vi.fn() } };
});

const card: Card = {
  id: "priority-1", priority: "P1", lane: "now", category: "Operations", title: "Resolve the operating blocker",
  context: "Context", consequence: "Consequence", source: "Eli", mission_alignment: "aligned",
  action: { label: "Prepare the decision", kind: "eli_agent_queue", arguments: {}, account: "personal", recipients: [], reversible: true },
};

describe("FeedbackPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders all feedback categories and disables an empty submission", () => {
    render(<FeedbackPanel cards={[]} onChanged={() => undefined} />);

    expect(screen.getByRole("radio", { name: /priority correction/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: /dashboard change/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /working well/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send feedback to eli/i })).toBeDisabled();
  });

  it("submits an optional item association and refreshes the brief", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    vi.mocked(api.feedback).mockResolvedValue({ feedback_id: "feedback_1", status: "recorded", eli_agent_writeback: true, retriable: false, next_brief_refresh: true, detail: "Applied to the next brief." });
    render(<FeedbackPanel cards={[card]} onChanged={onChanged} />);

    await user.selectOptions(screen.getByLabelText(/related item/i), "priority-1");
    await user.type(screen.getByLabelText(/feedback for eli/i), "This item should be lower priority.");
    await user.click(screen.getByRole("button", { name: /send feedback to eli/i }));

    await waitFor(() => expect(api.feedback).toHaveBeenCalledWith({ category: "priority_correction", feedback: "This item should be lower priority.", item_id: "priority-1", disposition: "modify" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Applied to the next brief.");
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("offers retry when Eli writeback is queued", async () => {
    const user = userEvent.setup();
    vi.mocked(api.feedback).mockResolvedValue({ feedback_id: "feedback_2", status: "queued", eli_agent_writeback: false, retriable: true, next_brief_refresh: true, detail: "Safely queued." });
    vi.mocked(api.retryFeedback).mockResolvedValue({ feedback_id: "feedback_2", status: "recorded", eli_agent_writeback: true, retriable: false, next_brief_refresh: true, detail: "Recorded after retry." });
    render(<FeedbackPanel cards={[]} onChanged={() => undefined} />);

    await user.click(screen.getByRole("radio", { name: /dashboard change/i }));
    await user.type(screen.getByLabelText(/feedback for eli/i), "Make the schedule easier to scan.");
    await user.click(screen.getByRole("button", { name: /send feedback to eli/i }));
    await user.click(await screen.findByRole("button", { name: /retry now/i }));

    expect(api.retryFeedback).toHaveBeenCalledWith("feedback_2");
    expect(await screen.findByRole("status")).toHaveTextContent("Recorded after retry.");
  });

  it("surfaces API errors without claiming the feedback was recorded", async () => {
    const user = userEvent.setup();
    vi.mocked(api.feedback).mockRejectedValue(new Error("Feedback service unavailable"));
    render(<FeedbackPanel cards={[]} onChanged={() => undefined} />);

    await user.type(screen.getByLabelText(/feedback for eli/i), "This priority order is incorrect.");
    await user.click(screen.getByRole("button", { name: /send feedback to eli/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Feedback service unavailable");
  });
});
