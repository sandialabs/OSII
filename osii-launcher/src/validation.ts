import type { ProfileDraft } from "./types";

export function coreImage(profile: Pick<ProfileDraft, "imagePrefix" | "imageTag">): string {
  return `${profile.imagePrefix.trim()}-core:${profile.imageTag.trim()}`;
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
  const baseUrl = profile.openaiBaseUrl.trim();
  if (baseUrl) {
    try {
      const url = new URL(baseUrl);
      if (!['http:', 'https:'].includes(url.protocol)) throw new Error("protocol");
    } catch {
      return "The OpenAI-compatible endpoint must be an HTTP or HTTPS URL.";
    }
  }
  return null;
}
