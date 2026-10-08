import { describe, expect, it } from "vitest";
import type { DocumentRecord, ResearchSource } from "../api/types";
import { displaySourceName, sourceIsIncomplete } from "./format";

const source: ResearchSource = { source_id: "research:upload_123", source_title: "research:upload_123", source_type: "paper", evidence_ids: [], sections: [] };

describe("source display", () => {
  it("uses uploaded document metadata when source title is an internal id", () => {
    const document = { source_id: source.source_id, filename: "paper.pdf" } as DocumentRecord;
    expect(displaySourceName(source, [document])).toBe("paper.pdf");
    expect(sourceIsIncomplete(source, [document])).toBe(false);
  });

  it("shows the source id without inventing a paper title", () => {
    expect(displaySourceName(source, [])).toBe(source.source_id);
    expect(sourceIsIncomplete(source, [])).toBe(true);
  });
});
