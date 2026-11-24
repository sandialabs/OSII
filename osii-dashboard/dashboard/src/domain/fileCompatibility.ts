export type SourceTypes = {
  file_extensions?: readonly string[];
  media_types?: readonly string[];
};

export type FileFormat = { filename?: string | null; mime?: string | null };

export const sourceExtension = (filename?: string | null) =>
  filename?.toLowerCase().match(/[^/\\](\.[^./\\]+)$/)?.[1];

export function sourceCompatibility(file: FileFormat, types: SourceTypes): "supported" | "unsupported" | "undeclared" {
  const extensions = types.file_extensions?.map(extension => extension.trim().toLowerCase()).filter(Boolean) ?? [];
  const suffix = sourceExtension(file.filename);
  if (extensions.length) {
    return extensions.includes("*") || (suffix && extensions.includes(suffix)) ? "supported" : "unsupported";
  }

  const mime = file.mime?.split(";", 1)[0].trim().toLowerCase();
  const mediaTypes = types.media_types?.map(type => type.trim().toLowerCase()).filter(Boolean) ?? [];
  if (!mediaTypes.length) return "undeclared";
  return mediaTypes.some(type => type === "*/*" || (mime && (type === mime || type === mime.split("/", 1)[0] + "/*")))
    ? "supported"
    : "unsupported";
}

const legacyOcrTypes = {
  file_extensions: [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"],
};

type ExtractorCapabilities = SourceTypes & { output_kinds?: readonly string[] };
type ExtractorMethod = {
  id: string;
  capabilities?: ExtractorCapabilities;
  descriptor?: { capabilities?: ExtractorCapabilities } | null;
};

export function ocrSourceTypes(method: ExtractorMethod): SourceTypes | undefined {
  const capabilities = method.descriptor?.capabilities ?? method.capabilities;
  const legacy = ["local.tesseract-page-ocr", "toolbox.tesseract-opencv"].includes(method.id);
  if (!legacy && !capabilities?.output_kinds?.includes("ocr_text")) return undefined;
  if (capabilities?.file_extensions?.length || capabilities?.media_types?.length) return capabilities;
  return legacy ? legacyOcrTypes : undefined;
}
