import { useCallback, useEffect, useState } from "react";

import type { ScopeDescribeRequest, SearchMode } from "../api/types";
import {
  ACTIVITY_HISTORY_EVENT,
  ACTIVITY_HISTORY_KEY,
  addActivityHistoryEntry,
  clearActivityHistory,
  entriesForKind,
  readActivityHistory,
  removeActivityHistoryEntry,
  type ActivityHistoryKind,
} from "../utils/activityHistory";

export function useActivityHistory(kind: ActivityHistoryKind) {
  const [entries, setEntries] = useState(() => entriesForKind(readActivityHistory(), kind));
  const refresh = useCallback(() => setEntries(entriesForKind(readActivityHistory(), kind)), [kind]);

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key === ACTIVITY_HISTORY_KEY) refresh();
    };
    window.addEventListener("storage", handleStorage);
    window.addEventListener(ACTIVITY_HISTORY_EVENT, refresh);
    return () => {
      window.removeEventListener("storage", handleStorage);
      window.removeEventListener(ACTIVITY_HISTORY_EVENT, refresh);
    };
  }, [refresh]);

  return {
    entries,
    add: (input: { text: string; scope: ScopeDescribeRequest; mode?: SearchMode }) => {
      addActivityHistoryEntry({ kind, ...input });
      refresh();
    },
    remove: (id: string) => {
      removeActivityHistoryEntry(kind, id);
      refresh();
    },
    clear: () => {
      clearActivityHistory(kind);
      refresh();
    },
  };
}
