import { useRef } from "react";
import { createCollection, addCollectionMembers } from "../api/collections";
/** Retain a just-created descriptor when membership saving needs a retry. */
export function useCreateCollectionSelection() {
  const pending = useRef(new Map<string, string>());
  return async (name: string, ids: string[], description?: string) => {
    const key = JSON.stringify([name, ids, description]);
    let id = pending.current.get(key);
    if (!id) {
      id = (await createCollection({ name, description })).collection.id;
      pending.current.set(key, id);
    }
    await addCollectionMembers(id, { file_ids: ids });
    pending.current.delete(key);
  };
}
