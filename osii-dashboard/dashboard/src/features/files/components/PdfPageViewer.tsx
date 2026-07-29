// src/features/files/components/PdfPageViewer.tsx
import { useEffect, useRef } from "react";
import { Box } from "@mui/material";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";

type PdfPageViewerProps = {
  pdf: PDFDocumentProxy;
  pageNumber: number;
  width?: number;
};

export function PdfPageViewer({
  pdf,
  pageNumber,
  width = 760,
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
      <canvas
        ref={canvasRef}
        style={{
          display: "block",
          maxWidth: "100%",
          height: "auto",
          background: "#fff",
          boxShadow: "0 1px 3px rgba(0,0,0,0.12)",
        }}
      />
    </Box>
  );
}