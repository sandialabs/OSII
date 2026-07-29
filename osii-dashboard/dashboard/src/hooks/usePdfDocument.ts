import { useEffect, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

const pdfCache = new Map<string, pdfjsLib.PDFDocumentProxy>();

type UsePdfDocumentResult = {
  pdf: pdfjsLib.PDFDocumentProxy | null;
  isLoading: boolean;
  error: Error | null;
};

export function usePdfDocument(sourceUrl: string | null): UsePdfDocumentResult {
  const [pdf, setPdf] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(Boolean(sourceUrl));
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!sourceUrl) {
        setPdf(null);
        setIsLoading(false);
        setError(null);
        return;
      }

      setIsLoading(true);
      setError(null);

      try {
        const cached = pdfCache.get(sourceUrl);
        if (cached) {
          if (!cancelled) {
            setPdf(cached);
            setIsLoading(false);
          }
          return;
        }

        const loadingTask = pdfjsLib.getDocument(sourceUrl);
        const loaded = await loadingTask.promise;
        pdfCache.set(sourceUrl, loaded);

        if (!cancelled) {
          setPdf(loaded);
          setIsLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setPdf(null);
          setIsLoading(false);
          setError(err instanceof Error ? err : new Error("Failed to load PDF."));
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [sourceUrl]);

  return { pdf, isLoading, error };
}