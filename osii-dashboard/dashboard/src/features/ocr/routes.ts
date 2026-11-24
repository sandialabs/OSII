export function buildOcrRoute(fileId: string) {
  return `/tools/ocr?${new URLSearchParams({ file_id: fileId })}`;
}
