// src/app/providers/BrowsingScopeProvider.tsx
import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { FolderScopeDescriptor } from "../../api/types";
import type { BrowsingScope } from "../../domain/scopes";

type BrowsingScopeContextValue = {
  scope: BrowsingScope;
  setRootScope: () => void;
  setFolderScope: (folder: FolderScopeDescriptor) => void;
  setCollectionScope: (collectionId: string, label?: string) => void;
};

const BrowsingScopeContext = createContext<BrowsingScopeContextValue | undefined>(
  undefined,
);

export function BrowsingScopeProvider({ children }: { children: ReactNode }) {
  const [scope, setScope] = useState<BrowsingScope>({
    kind: "root",
    request: { scope_type: "root" },
  });

  const value = useMemo<BrowsingScopeContextValue>(
    () => ({
      scope,
      setRootScope: () =>
        setScope({
          kind: "root",
          request: { scope_type: "root" },
        }),
      setFolderScope: (folder: FolderScopeDescriptor) =>
        setScope({
          kind: "folder",
          request: { scope_type: "folder", folder_id: folder.folder_id },
          folder,
        }),
      setCollectionScope: (collectionId: string, label?: string) =>
        setScope({
          kind: "collection",
          request: { scope_type: "collection", collection_id: collectionId },
          collectionId,
          label,
        }),
    }),
    [scope],
  );

  return (
    <BrowsingScopeContext.Provider value={value}>
      {children}
    </BrowsingScopeContext.Provider>
  );
}

export function useBrowsingScope() {
  const value = useContext(BrowsingScopeContext);

  if (!value) {
    throw new Error("useBrowsingScope must be used within BrowsingScopeProvider");
  }

  return value;
}