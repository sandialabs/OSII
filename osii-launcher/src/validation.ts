import type { ProfileDraft } from "./types";

export function coreImage(profile: Pick<ProfileDraft, "imagePrefix" | "imageTag">): string {
  return `${profile.imagePrefix.trim()}-core:${profile.imageTag.trim()}`;
}

function normalizedModelName(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

export function suggestedModels(
  models: string[],
  currentEmbedding = "",
  currentChat = "",
): { embedding: string; chat: string } {
  const embedding = currentEmbedding.trim()
    || models.find((model) => normalizedModelName(model).includes("minilm"))
    || "";
  const chat = currentChat.trim()
    || models.find((model) => normalizedModelName(model).includes("gemma4"))
    || models.find((model) => normalizedModelName(model).includes("gemma"))
    || "";
  return { embedding, chat };
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
    if (!profile.openaiEmbeddingModel.trim()) {
      return "Find or select an embedding model for the corporate endpoint.";
    }
    if (!profile.openaiChatModel.trim()) {
      return "Find or select a chat model for the corporate endpoint.";
    }
  }
  return null;
}
