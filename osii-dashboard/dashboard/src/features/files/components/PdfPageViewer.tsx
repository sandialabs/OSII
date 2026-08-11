// src/features/files/components/PdfPageViewer.tsx
import { useEffect, useRef } from "react";
import { Box } from "@mui/material";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";

type PdfPageViewerProps = {
  pdf: PDFDocumentProxy;
  pageNumber: number;
  width?: number;
  regions?: PdfBoundingRegion[];
};

export type PdfBoundingRegion = {
  bbox: [number, number, number, number];
  text?: string | null;
  confidence?: number | null;
};

export function PdfPageViewer({
  pdf,
  pageNumber,
  width = 760,
  regions = [],
}: PdfPageViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    let renderTask: RenderTask | null = null;

    async function renderPage() {
      const page = await pdf.getPage(pageNumber);
      const unscaledViewport = page.getViewport({ scale: 1 });
      const scale = width / unscaledViewport.width;
      const viewport = page.getViewport({ scale });

      const canvas = canvasRef.current;
      if (!canvas || cancelled) return;

      const context = canvas.getContext("2d");
      if (!context) return;

      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);

      renderTask = page.render({
        canvasContext: context,
        viewport,
      });

      await renderTask.promise;
    }

    void renderPage();

    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [pdf, pageNumber, width]);

  return (
    <Box
      sx={{
        width: "100%",
        overflow: "auto",
        display: "flex",
        justifyContent: "center",
        backgroundColor: "#f1f5f9",
        py: 2,
      }}
    >
      <Box
        sx={{
          position: "relative",
          width,
          maxWidth: "100%",
          lineHeight: 0,
          boxShadow: "0 1px 3px rgba(0,0,0,0.12)",
        }}
      >
        <canvas
          ref={canvasRef}
          style={{
            display: "block",
            width: "100%",
            height: "auto",
            background: "#fff",
          }}
        />
        {regions.map((region, index) => {
          const [x1, y1, x2, y2] = region.bbox;
          return (
            <Box
              key={`${x1}-${y1}-${x2}-${y2}-${index}`}
              component="span"
              title={[
                region.text?.trim() || "OCR region",
                typeof region.confidence === "number"
                  ? `Confidence ${Math.round(region.confidence * 100)}%`
                  : null,
              ].filter(Boolean).join(" · ")}
              sx={{
                position: "absolute",
                left: `${x1 * 100}%`,
                top: `${y1 * 100}%`,
                width: `${Math.max(0, x2 - x1) * 100}%`,
                height: `${Math.max(0, y2 - y1) * 100}%`,
                border: "2px solid rgba(220, 38, 38, 0.82)",
                backgroundColor: "rgba(239, 68, 68, 0.08)",
                boxSizing: "border-box",
                pointerEvents: "none",
              }}
            />
          );
        })}
      </Box>
    </Box>
  );
}
