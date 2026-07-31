// src/hooks/usePdfThumbnail.ts
import { useEffect, useState } from "react";

import { getCachedThumbnail, setCachedThumbnail } from "../utils/thumbnailCache";
import { generatePdfThumbnailDataUrl } from "../utils/pdfThumbnail";

type UsePdfThumbnailResult = {
  thumbnailUrl: string | null;
  isLoading: boolean;
  error: Error | null;
};

const MAX_CONCURRENT_THUMBNAILS = 2;
let activeThumbnailJobs = 0;
const thumbnailJobs: Array<() => void> = [];

function runNextThumbnailJob() {
  while (
    activeThumbnailJobs < MAX_CONCURRENT_THUMBNAILS
    && thumbnailJobs.length > 0
  ) {
    activeThumbnailJobs += 1;
    thumbnailJobs.shift()?.();
  }
}

function scheduleThumbnail<T>(work: () => Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    thumbnailJobs.push(() => {
      void work()
        .then(resolve, reject)
        .finally(() => {
          activeThumbnailJobs -= 1;
          runNextThumbnailJob();
        });
    });
    runNextThumbnailJob();
  });
}

export function usePdfThumbnail(
  sourceUrl: string | null,
  enabled = true,
): UsePdfThumbnailResult {
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(enabled);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      if (!enabled || !sourceUrl) {
        setThumbnailUrl(null);
        setIsLoading(false);
        setError(null);
        return;
      }

      setIsLoading(true);
      setError(null);

      const cacheKey = `pdf-thumb:${sourceUrl}`;

      try {
        const cached = await getCachedThumbnail(cacheKey);
        if (cached) {
          if (!cancelled) {
            setThumbnailUrl(cached);
            setIsLoading(false);
          }
          return;
        }

        const dataUrl = await scheduleThumbnail(() => {
          if (cancelled) {
            throw new Error("Thumbnail request was cancelled");
          }
          return generatePdfThumbnailDataUrl(sourceUrl);
        });
        await setCachedThumbnail(cacheKey, dataUrl);

        if (!cancelled) {
          setThumbnailUrl(dataUrl);
          setIsLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setThumbnailUrl(null);
          setIsLoading(false);
          setError(
            err instanceof Error
              ? err
              : new Error("Thumbnail generation failed"),
          );
        }
      }
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, [sourceUrl, enabled]);

  return {
    thumbnailUrl,
    isLoading,
    error,
  };
}
