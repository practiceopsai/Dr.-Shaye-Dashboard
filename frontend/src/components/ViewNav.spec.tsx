import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ViewNav from "./ViewNav";

describe("ViewNav", () => {
  it("exposes every command center section as an accessible tab", () => {
    render(<ViewNav current="today" onChange={() => undefined} />);

    expect(screen.getAllByRole("tab")).toHaveLength(4);
    expect(screen.getByRole("tab", { name: "Today" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Schedule" })).toHaveAttribute("aria-selected", "false");
  });

  it("opens the selected section", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ViewNav current="today" onChange={onChange} />);

    await user.click(screen.getByRole("tab", { name: "Schedule" }));

    expect(onChange).toHaveBeenCalledWith("schedule");
  });
});
