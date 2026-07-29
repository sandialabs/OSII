// src/features/browse/components/FileTile.tsx
import { FileCard } from "../../files/components/FileCard";
import type { FileCardModel } from "../../../domain/files";

type FileTileProps = {
  file: FileCardModel;
  onOpen: (fileId: string) => void;
};

export function FileTile({ file, onOpen }: FileTileProps) {
  return <FileCard file={file} onOpen={onOpen} />;
}