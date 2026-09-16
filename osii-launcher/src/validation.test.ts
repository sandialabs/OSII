import { describe, expect, it } from "vitest";
import { coreImage, profileImages, profileProblem } from "./validation";
import type { ProfileDraft } from "./types";

const valid: ProfileDraft = {
  name: "Research drive",
  sourceDir: "/Volumes/research",
  imagePrefix: "quay.corp.example/osii/osii",
  imageTag: "2026.09.14",
  readableWiki: false,
  conceptEntityWiki: false,
  tesseractOpenCv: false,
};

describe("profile validation", () => {
  it("accepts a complete corporate profile", () => {
    expect(profileProblem(valid)).toBeNull();
  });

  it("requires a pinned container release", () => {
    expect(profileProblem({ ...valid, imageTag: "latest" })).toMatch(/pinned/);
  });

  it("builds the core image from the shared prefix and immutable tag", () => {
    expect(coreImage(valid)).toBe("quay.corp.example/osii/osii-core:2026.09.14");
  });

  it("lists baseline images and each selected optional image once", () => {
    expect(profileImages({ ...valid, readableWiki: true, conceptEntityWiki: true, tesseractOpenCv: true })).toEqual([
      "quay.corp.example/osii/osii-core:2026.09.14",
      "quay.corp.example/osii/osii-dashboard:2026.09.14",
      "quay.corp.example/osii/osii-baseline-processors:2026.09.14",
      "quay.corp.example/osii/osii-llm-wikis:2026.09.14",
      "quay.corp.example/osii/osii-tesseract-opencv:2026.09.14",
    ]);
  });
});
