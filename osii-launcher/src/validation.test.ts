import { describe, expect, it } from "vitest";
import { coreImage, profileProblem } from "./validation";
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
});
