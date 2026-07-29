export function buildPdfViewerUrl(sourceUrl: string, page?: number | null): string {
  if (!page || page < 1) {
    return sourceUrl;
  }

  const separator = sourceUrl.includes("#") ? "&" : "#";
  return `${sourceUrl}${separator}page=${page}`;
}