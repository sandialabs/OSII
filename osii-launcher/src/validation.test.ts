import { describe, expect, it } from "vitest";
import { coreImage, profileProblem, suggestedModels } from "./validation";
import type { ProfileDraft } from "./types";

const valid: ProfileDraft = {
  name: "Research drive",
  sourceDir: "/Volumes/research",
  imagePrefix: "quay.corp.example/osii/osii",
  imageTag: "2026.09.14",
  openaiBaseUrl: "https://models.corp.example/v1",
  openaiEmbeddingModel: "embed",
  openaiChatModel: "chat",
};

describe("profile validation", () => {
  it("accepts a complete corporate profile", () => {
    expect(profileProblem(valid)).toBeNull();
  });

  it("rejects a non-http provider endpoint", () => {
    expect(profileProblem({ ...valid, openaiBaseUrl: "file:///secret" })).toMatch(/HTTP/);
  });

  it("requires a pinned container release", () => {
    expect(profileProblem({ ...valid, imageTag: "latest" })).toMatch(/pinned/);
  });

  it("builds the core image from the shared prefix and immutable tag", () => {
    expect(coreImage(valid)).toBe("quay.corp.example/osii/osii-core:2026.09.14");
  });

  it("suggests MiniLM embeddings and Gemma 4 chat from discovered models", () => {
    expect(suggestedModels([
      "corp/gemma-3-12b",
      "sentence-transformers/all-MiniLM-L6-v2",
      "corp/gemma-4-27b-it",
    ])).toEqual({
      embedding: "sentence-transformers/all-MiniLM-L6-v2",
      chat: "corp/gemma-4-27b-it",
    });
  });

  it("preserves explicit corporate model defaults", () => {
    expect(suggestedModels(["minilm-v2", "gemma-4"], "approved-embed", "approved-chat"))
      .toEqual({ embedding: "approved-embed", chat: "approved-chat" });
  });
});
