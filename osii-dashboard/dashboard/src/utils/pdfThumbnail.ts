import * as pdfjsLib from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

export class EmptyPdfThumbnailError extends Error {}

export async function generatePdfThumbnailDataUrl(
  pdfUrl: string,
  options?: {
    maxWidth?: number;
    scale?: number;
  },
): Promise<string> {
  const loadingTask = pdfjsLib.getDocument(pdfUrl);
  const pdf = await loadingTask.promise;
  try {
    const page = await pdf.getPage(1);

    const initialViewport = page.getViewport({ scale: 1 });
    const maxWidth = options?.maxWidth ?? 180;
    const computedScale = Math.min(maxWidth / initialViewport.width, options?.scale ?? 1.2);

    const viewport = page.getViewport({ scale: computedScale });

    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");

    if (!context) {
      throw new Error("Could not create canvas context for thumbnail rendering.");
    }

    canvas.width = Math.ceil(viewport.width);
    canvas.height = Math.ceil(viewport.height);

    await page.render({
      canvasContext: context,
      viewport,
    }).promise;

    const pixels=context.getImageData(0,0,canvas.width,canvas.height).data;
    let ink=0;for(let i=0;i<pixels.length;i+=4){if(pixels[i+3]>32&&Math.min(pixels[i],pixels[i+1],pixels[i+2])<225)ink++;}
    if(ink<canvas.width*canvas.height*0.001)throw new EmptyPdfThumbnailError("This page has no visible thumbnail content");
    return canvas.toDataURL("image/jpeg", 0.82);
  } finally {
    await pdf.destroy();
  }
}
