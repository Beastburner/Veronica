import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { VoiceInterface } from "@/components/VoiceInterface";

describe("VoiceInterface", () => {
  it("renders the idle click-to-talk affordance", () => {
    render(<VoiceInterface onCommand={vi.fn()} speak="" />);
    expect(screen.getByText(/click to talk/i)).toBeInTheDocument();
  });

  it("shows the muted label after toggling voice off", async () => {
    render(<VoiceInterface onCommand={vi.fn()} speak="" />);
    const toggle = screen.getByTitle(/mute voice output/i);
    toggle.click();
    expect(await screen.findByText(/muted/i)).toBeInTheDocument();
  });
});
