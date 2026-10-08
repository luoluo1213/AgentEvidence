import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResearchPage } from "./ResearchPage";
import * as researchApi from "../api/streaming";
import * as documentsApi from "../api/documents";

vi.mock("../api/streaming", () => ({ streamResearch: vi.fn() }));
vi.mock("../api/research", () => ({ runResearch: vi.fn() }));
vi.mock("../api/documents", () => ({ listDocuments: vi.fn() }));

describe("ResearchPage cancellation", () => {
  beforeEach(() => {
    vi.mocked(documentsApi.listDocuments).mockResolvedValue([]);
    vi.mocked(researchApi.streamResearch).mockImplementation((_request, _onEvent, signal) => new Promise((_resolve, reject) => {
      signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));
  });

  it("aborts the current stream without recording a completed run", async () => {
    const onRunComplete = vi.fn();
    render(<ResearchPage onRunComplete={onRunComplete} />);
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "How does it work?" } });
    fireEvent.click(screen.getByLabelText("Start research"));
    fireEvent.click(await screen.findByLabelText("Cancel research"));
    expect(await screen.findByRole("alert")).toHaveTextContent("cancelled");
    await waitFor(() => expect(screen.getByLabelText("Start research")).toBeEnabled());
    expect(onRunComplete).not.toHaveBeenCalled();
  });
});
