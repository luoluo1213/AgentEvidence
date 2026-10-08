import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, requestJson } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("requestJson", () => {
  it("surfaces the backend error envelope", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ error: { code: "validation_error", message: "PDF only." } }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    )));
    await expect(requestJson("/documents/upload")).rejects.toMatchObject({
      status: 422, code: "validation_error", message: "PDF only.",
    });
  });

  it("does not hide network failures as successful responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(requestJson("/health")).rejects.toMatchObject({ code: "network_error" });
  });
});
