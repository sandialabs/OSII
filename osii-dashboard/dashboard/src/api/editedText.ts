// src/api/editedText.ts
import { apiJson } from "./client";
import type {
  EditedTextDeleteResponse,
  EditedTextReadResponse,
  EditedTextWriteRequest,
  EditedTextWriteResponse,
} from "./types";

export async function getEditedObjectText(
  fileId: string,
): Promise<EditedTextReadResponse> {
  return apiJson<EditedTextReadResponse>(
    `/api/objects/${encodeURIComponent(fileId)}/texts/edited`,
  );
}

export async function putEditedObjectText(
  fileId: string,
  payload: EditedTextWriteRequest,
): Promise<EditedTextWriteResponse> {
  return apiJson<EditedTextWriteResponse>(
    `/api/objects/${encodeURIComponent(fileId)}/texts/edited`,
    {
      method: "PUT",
      json: payload,
    },
  );
}

export async function deleteEditedObjectText(
  fileId: string,
  version?: { expected_revision?: string | null; expected_state?: string },
): Promise<EditedTextDeleteResponse> {
  return apiJson<EditedTextDeleteResponse>(
    `/api/objects/${encodeURIComponent(fileId)}/texts/edited`,
    {
      method: "DELETE",
      ...(version ? { json: version } : {}),
    },
  );
}