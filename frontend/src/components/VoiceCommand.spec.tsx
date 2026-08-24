import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import VoiceCommand from "./VoiceCommand";

vi.mock("@/lib/api", async importOriginal => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return { ...original, api: { ...original.api, voice: vi.fn() } };
});

type ResultHandler = (event: { results: { transcript: string }[][] }) => void;
let recognition: FakeRecognition;

class FakeRecognition {
  continuous = false;
  interimResults = false;
  lang = "";
  onresult: ResultHandler | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  start = vi.fn();
  stop = vi.fn();

  constructor() {
    recognition = this;
  }
}

const recordedResponse = {
  command_id: "voice_1",
  status: "recorded" as const,
  intent: "dashboard_change" as const,
  message: "I recorded that as a tracked dashboard improvement.",
  eli_agent_writeback: true,
  retriable: false,
  next_brief_refresh: true,
};

describe("VoiceCommand", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete (window as typeof window & { SpeechRecognition?: typeof FakeRecognition }).SpeechRecognition;
    delete (window as typeof window & { webkitSpeechRecognition?: typeof FakeRecognition }).webkitSpeechRecognition;
  });

  it("should send a typed request, show Eli's reply, and refresh the brief", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    vi.mocked(api.voice).mockResolvedValue(recordedResponse);
    render(<VoiceCommand onChanged={onChanged} />);

    await user.click(screen.getByRole("button", { name: "Talk to Eli" }));
    await user.type(screen.getByLabelText("Message Eli"), "Make the priority widget clearer.");
    await user.click(screen.getByRole("button", { name: "Send to Eli" }));

    expect(api.voice).toHaveBeenCalledWith("Make the priority widget clearer.");
    expect(await screen.findByText(recordedResponse.message)).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("should transcribe microphone speech and return a chat response", async () => {
    const user = userEvent.setup();
    (window as typeof window & { webkitSpeechRecognition?: typeof FakeRecognition }).webkitSpeechRecognition = FakeRecognition;
    vi.mocked(api.voice).mockResolvedValue({ ...recordedResponse, intent: "priority_feedback", message: "I recorded that as priority guidance." });
    render(<VoiceCommand onChanged={() => undefined} />);

    await user.click(screen.getByRole("button", { name: "Talk to Eli" }));
    await user.click(screen.getByRole("button", { name: "Speak to Eli" }));
    expect(recognition.start).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Stop listening" })).toBeInTheDocument();

    recognition.onresult?.({ results: [[{ transcript: "Family should rank higher." }]] });

    expect(api.voice).toHaveBeenCalledWith("Family should rank higher.");
    expect(await screen.findByText("I recorded that as priority guidance.")).toBeInTheDocument();
  });

  it("should keep typed chat available when browser speech recognition is unavailable", async () => {
    const user = userEvent.setup();
    render(<VoiceCommand onChanged={() => undefined} />);

    await user.click(screen.getByRole("button", { name: "Talk to Eli" }));
    await user.click(screen.getByRole("button", { name: "Speak to Eli" }));

    expect(screen.getByText(/Microphone input is not supported/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Message Eli")).toBeEnabled();
  });

  it("should show a backend error as an Eli chat message", async () => {
    const user = userEvent.setup();
    vi.mocked(api.voice).mockRejectedValue(new Error("Eli Agent is temporarily busy"));
    render(<VoiceCommand onChanged={() => undefined} />);

    await user.click(screen.getByRole("button", { name: "Talk to Eli" }));
    await user.type(screen.getByLabelText("Message Eli"), "Please prepare the agenda.");
    await user.click(screen.getByRole("button", { name: "Send to Eli" }));

    expect(await screen.findByText("Eli Agent is temporarily busy")).toBeInTheDocument();
  });

  it("should stop the microphone when the chat closes", async () => {
    const user = userEvent.setup();
    (window as typeof window & { SpeechRecognition?: typeof FakeRecognition }).SpeechRecognition = FakeRecognition;
    render(<VoiceCommand onChanged={() => undefined} />);

    await user.click(screen.getByRole("button", { name: "Talk to Eli" }));
    await user.click(screen.getByRole("button", { name: "Speak to Eli" }));
    await user.click(screen.getByRole("button", { name: "Close Talk to Eli" }));

    expect(recognition.stop).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog", { name: "Talk to Eli" })).not.toBeInTheDocument();
  });
});
