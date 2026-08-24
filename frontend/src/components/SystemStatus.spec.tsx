import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SystemStatus from "./SystemStatus";

describe("SystemStatus", () => {
  it("shows the assistant connector as Eli", () => {
    render(<SystemStatus integrations={{ eli_agent: true, composio: true, anthropic: true }} />);

    expect(screen.getByText("Eli")).toBeInTheDocument();
    expect(screen.queryByText(/hermes/i)).not.toBeInTheDocument();
  });

  it("shows unavailable integrations without breaking the connector list", () => {
    render(<SystemStatus integrations={{}} />);

    expect(screen.getAllByText("Unavailable")).toHaveLength(3);
  });
});
