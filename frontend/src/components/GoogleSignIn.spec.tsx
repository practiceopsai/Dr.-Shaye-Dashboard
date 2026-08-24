import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import GoogleSignIn from "./GoogleSignIn";

vi.mock("next/script", () => ({
  default: ({ onReady }: { onReady?: () => void }) => {
    setTimeout(() => onReady?.(), 0);
    return null;
  },
}));

describe("GoogleSignIn", () => {
  const initialize = vi.fn();
  const renderButton = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_CLIENT_ID", "web-client.apps.googleusercontent.com");
    window.google = { accounts: { id: { initialize, renderButton, disableAutoSelect: vi.fn() } } };
  });

  it("renders Google's official button with the configured client ID", async () => {
    render(<GoogleSignIn onCredential={() => undefined} />);

    expect(await screen.findByLabelText("Sign in with Google")).toBeInTheDocument();
    await vi.waitFor(() => expect(initialize).toHaveBeenCalledTimes(1));
    expect(initialize.mock.calls[0][0]).toMatchObject({
      client_id: "web-client.apps.googleusercontent.com",
      auto_select: false,
    });
    expect(renderButton).toHaveBeenCalledWith(expect.any(HTMLElement), expect.objectContaining({ text: "signin_with" }));
  });

  it("returns the signed credential from Google", async () => {
    const onCredential = vi.fn();
    render(<GoogleSignIn onCredential={onCredential} />);
    await vi.waitFor(() => expect(initialize).toHaveBeenCalledTimes(1));

    initialize.mock.calls[0][0].callback({ credential: "signed-google-jwt" });

    expect(onCredential).toHaveBeenCalledWith("signed-google-jwt");
  });
});
