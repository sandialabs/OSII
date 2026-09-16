import type { ProfileDraft } from "./types";

export function coreImage(profile: Pick<ProfileDraft, "imagePrefix" | "imageTag">): string {
  return `${profile.imagePrefix.trim()}-core:${profile.imageTag.trim()}`;
}

export function profileImages(profile: ProfileDraft): string[] {
  const imagePrefix = profile.imagePrefix.trim();
  const imageTag = profile.imageTag.trim();
  if (!imagePrefix || !imageTag) return [];

  const images = [
    `${imagePrefix}-core:${imageTag}`,
    `${imagePrefix}-dashboard:${imageTag}`,
    `${imagePrefix}-baseline-processors:${imageTag}`,
  ];
  if (profile.readableWiki || profile.conceptEntityWiki) {
    images.push(`${imagePrefix}-llm-wikis:${imageTag}`);
  }
  if (profile.tesseractOpenCv) {
    images.push(`${imagePrefix}-tesseract-opencv:${imageTag}`);
  }
  return images;
}

export function profileProblem(profile: ProfileDraft): string | null {
  if (!profile.name.trim()) return "Give this library a name.";
  if (!profile.sourceDir.trim()) return "Choose the shared folder to scan.";
  if (!/^[a-zA-Z0-9._/:@-]+$/.test(profile.imagePrefix.trim())) {
    return "Enter the full Quay image prefix, for example quay.example.com/team/osii.";
  }
  if (!/^[a-zA-Z0-9._-]+$/.test(profile.imageTag.trim())) {
    return "Enter an immutable image tag.";
  }
  if (profile.imageTag.trim().toLowerCase() === "latest") {
    return "Choose a pinned release tag instead of latest.";
  }
  return null;
}
