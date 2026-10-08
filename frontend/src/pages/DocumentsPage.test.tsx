import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DocumentRecord } from "../api/types";
import { DocumentsPage } from "./DocumentsPage";
import * as documentsApi from "../api/documents";

vi.mock("../api/documents", () => ({
  listDocuments: vi.fn(),
  getDocument: vi.fn(),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
}));

const document: DocumentRecord = {
  document_id: "doc_1", source_id: "research:upload_1", filename: "paper.pdf",
  content_type: "application/pdf", size_bytes: 1200, status: "completed", chunk_count: 3,
  error: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", duplicate: false,
};

describe("DocumentsPage upload", () => {
  beforeEach(() => {
    vi.mocked(documentsApi.listDocuments).mockResolvedValue([]);
    vi.mocked(documentsApi.uploadDocument).mockResolvedValue(document);
    vi.mocked(documentsApi.getDocument).mockResolvedValue(document);
  });

  it("validates type and uploads using the real interaction path", async () => {
    const { container } = render(<DocumentsPage />);
    await screen.findByText("No managed documents");
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    fireEvent.change(input, { target: { files: [new File(["text"], "notes.txt", { type: "text/plain" })] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Only PDF files");
    expect(documentsApi.uploadDocument).not.toHaveBeenCalled();

    vi.mocked(documentsApi.listDocuments).mockResolvedValue([document]);
    const pdf = new File(["%PDF-test"], "paper.pdf", { type: "application/pdf" });
    fireEvent.change(input, { target: { files: [pdf] } });
    await waitFor(() => expect(documentsApi.uploadDocument).toHaveBeenCalledWith(pdf));
    expect(await screen.findByText("paper.pdf was uploaded and indexed.")).toBeInTheDocument();
  });
});
