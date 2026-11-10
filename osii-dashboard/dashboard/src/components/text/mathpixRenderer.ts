import bundleUrl from "mathpix-markdown-it/es5/bundle.js?url";
type Task = {
  text: string;
  signal: AbortSignal;
  resolve: (value: string) => void;
  reject: (error: Error) => void;
};
const queue: Task[] = [];
let worker: Worker | null = null;
let running = false;

function drain() {
  if (running) return;
  const task = queue.shift();
  if (!task) return;
  if (task.signal.aborted) {
    task.reject(new Error("Cancelled"));
    drain();
    return;
  }
  running = true;
  try {
    worker ??= new Worker(new URL("./mathpix.worker.ts", import.meta.url));
  } catch {
    running = false;
    task.reject(new Error("Renderer unavailable"));
    drain();
    return;
  }
  const current = worker;
  const finish = (error?: Error, html?: string, terminate = false) => {
    clearTimeout(timer);
    task.signal.removeEventListener("abort", cancel);
    current.onmessage = null;
    current.onerror = null;
    if (terminate) {
      current.terminate();
      worker = null;
    }
    running = false;
    if (error) task.reject(error);
    else task.resolve(html!);
    drain();
  };
  const cancel = () => finish(new Error("Cancelled"), undefined, true);
  const timer = setTimeout(
    () => finish(new Error("Markup rendering timed out"), undefined, true),
    12_000,
  );
  task.signal.addEventListener("abort", cancel, { once: true });
  current.onmessage = (event) =>
    event.data.error
      ? finish(new Error("Invalid markup"))
      : finish(undefined, event.data.html);
  current.onerror = () =>
    finish(new Error("Renderer unavailable"), undefined, true);
  current.postMessage({
    text: task.text,
    bundleUrl: new URL(bundleUrl, location.href).href,
  });
}

export function renderMathpix(
  text: string,
  signal: AbortSignal,
): Promise<string> {
  return new Promise((resolve, reject) => {
    queue.push({ text, signal, resolve, reject });
    drain();
  });
}
