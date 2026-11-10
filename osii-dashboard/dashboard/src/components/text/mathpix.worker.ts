// Use the official browser bundle in a classic worker. Its legacy AsciiMath
// dependency cannot run in strict ES modules. The UI enforces cancellation/timeouts.
const rendererScope = self as unknown as {
  window: typeof self;
  importScripts: (url: string) => void;
  markdownToHTML: (text: string, options: Record<string, unknown>) => string;
};
rendererScope.window = self;
self.onmessage = (event: MessageEvent<{ text: string; bundleUrl: string }>) => {
  try {
    if (!rendererScope.markdownToHTML)
      rendererScope.importScripts(event.data.bundleUrl);
    const html = rendererScope.markdownToHTML(event.data.text, {
      htmlTags: false,
      breaks: true,
      linkify: false,
      typographer: false,
      nonumbers: true,
      width: 800,
    });
    self.postMessage({ html });
  } catch {
    self.postMessage({ error: true });
  }
};
