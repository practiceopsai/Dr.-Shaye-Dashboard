import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CalendarItem } from "@/lib/api";
import ScheduleCalendar, { calendarKey } from "./ScheduleCalendar";

function currentItem(): CalendarItem {
  const key = calendarKey(new Date().toISOString());
  return {
    id: "event-1",
    title: "Family dinner",
    start: `${key}T18:30:00-07:00`,
    end: `${key}T20:00:00-07:00`,
    all_day: false,
    source: "Personal calendar",
    kind: "calendar",
  };
}

describe("ScheduleCalendar", () => {
  it("renders dated items in a seven-day calendar", () => {
    render(<ScheduleCalendar items={[currentItem()]} />);

    expect(screen.getByRole("heading", { name: "Next seven days" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Family dinner/ })).toBeInTheDocument();
  });

  it("opens a dated item and shows its full details", async () => {
    const user = userEvent.setup();
    render(<ScheduleCalendar items={[currentItem()]} />);

    await user.click(screen.getByRole("button", { name: /Family dinner/ }));

    expect(screen.getByRole("dialog", { name: "Dated item details" })).toBeInTheDocument();
    expect(screen.getByText("Source: Personal calendar")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close item details" }));
    expect(screen.queryByRole("dialog", { name: "Dated item details" })).not.toBeInTheDocument();
  });

  it("expands into the full 30-day calendar and closes again", async () => {
    const user = userEvent.setup();
    render(<ScheduleCalendar items={[currentItem()]} />);

    await user.click(screen.getByRole("button", { name: "Open full calendar" }));
    expect(screen.getByRole("dialog", { name: "Next 30 days" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog", { name: "Next 30 days" })).not.toBeInTheDocument();
  });

  it("shows a clear empty state when the backend has no dated items", () => {
    render(<ScheduleCalendar items={[]} />);
    expect(screen.getByText(/No dated items are available/i)).toBeInTheDocument();
  });

  it("rejects an invalid calendar date", () => {
    expect(calendarKey("not-a-date")).toBe("");
  });
});
