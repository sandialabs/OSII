import type { FileCardModel } from "./files";

export type FileFilters = {
  query: string;
  format: string;
  minMb: string;
  maxMb: string;
  after: string;
  before: string;
  text: string;
  summary: boolean;
  enrichment: boolean;
};
export const emptyFileFilters: FileFilters = {
  query: "",
  format: "",
  minMb: "",
  maxMb: "",
  after: "",
  before: "",
  text: "",
  summary: false,
  enrichment: false,
};
export function fileFormat(file: FileCardModel): string {
  const extension = file.title.match(/\.([^.\/]+)$/)?.[1];
  return extension ? extension.toLowerCase() : file.mime || "Unknown format";
}
export function filterFiles(files: FileCardModel[], filters: FileFilters) {
  const min = filters.minMb === "" ? 0 : Number(filters.minMb);
  const max = filters.maxMb === "" ? Infinity : Number(filters.maxMb);
  const after = filters.after
    ? Date.parse(`${filters.after}T00:00:00Z`)
    : -Infinity;
  const before = filters.before
    ? Date.parse(`${filters.before}T23:59:59.999Z`)
    : Infinity;
  if (
    !Number.isFinite(min) ||
    (filters.maxMb !== "" && !Number.isFinite(max)) ||
    min < 0 ||
    max < min
  )
    return {
      files: [],
      error: "Enter a valid size range; maximum must be at least minimum.",
    };
  if (Number.isNaN(after) || Number.isNaN(before) || after > before)
    return { files: [], error: "Enter a valid modification date range." };
  const terms = filters.query
    .trim()
    .toLocaleLowerCase()
    .split(/\s+/)
    .filter(Boolean);
  return {
    error: "",
    files: files.filter((file) => {
      const label =
        `${file.title} ${file.sourceFileRelpath || file.subtitle}`.toLocaleLowerCase();
      const modified = file.modifiedAt ? Date.parse(file.modifiedAt) : NaN;
      return (
        terms.every((term) => label.includes(term)) &&
        (!filters.format || fileFormat(file) === filters.format) &&
        ((!filters.minMb && !filters.maxMb) ||
          (file.sizeBytes !== null &&
            file.sizeBytes >= min * 1024 ** 2 &&
            file.sizeBytes <= max * 1024 ** 2)) &&
        ((!filters.after && !filters.before) ||
          (modified >= after && modified <= before)) &&
        (!filters.text || file.hasPreferredText === (filters.text === "yes")) &&
        (!filters.summary || file.hasSynthesis) &&
        (!filters.enrichment || file.hasEnrichments)
      );
    }),
  };
}
