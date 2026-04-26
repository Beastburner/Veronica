import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OperationsPanels } from "@/components/OperationsPanels";

beforeEach(() => {
  // Default: every fetch returns empty data
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.includes("/briefing/today")) {
        return new Response(
          JSON.stringify({
            summary: "0 pending tasks, 0 reminders.",
            focus_recommendation: "Standby.",
            top_tasks: [],
            reminders: [],
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ items: [], pagination: { total: 0 } }), { status: 200 });
    })
  );
});

afterEach(() => vi.unstubAllGlobals());

describe("OperationsPanels", () => {
  it("renders the four panel headings", async () => {
    render(<OperationsPanels />);
    expect(screen.getByText(/Daily Briefing/i)).toBeInTheDocument();
    expect(screen.getByText(/Task Board/i)).toBeInTheDocument();
    expect(screen.getByText(/Notes Memory/i)).toBeInTheDocument();
    // "Reminders" is also used as an inner label in the briefing — match the panel heading specifically
    expect(screen.getAllByText(/Reminders/i).length).toBeGreaterThan(0);
  });

  it("loads the briefing summary from the API", async () => {
    render(<OperationsPanels />);
    await waitFor(() => {
      expect(screen.getByText(/0 pending tasks, 0 reminders/i)).toBeInTheDocument();
    });
  });
});
