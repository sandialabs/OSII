const DB_NAME = "osii-dashboard-thumbnails";
const STORE_NAME = "pdf-thumbnails";
const DB_VERSION = 1;

type ThumbnailRecord = {
  key: string;
  dataUrl: string;
  createdAt: number;
};

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = window.indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => reject(request.error);

    request.onsuccess = () => resolve(request.result);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "key" });
      }
    };
  });
}

export async function getCachedThumbnail(key: string): Promise<string | null> {
  const db = await openDb();

  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const store = tx.objectStore(STORE_NAME);
    const request = store.get(key);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const record = request.result as ThumbnailRecord | undefined;
      resolve(record?.dataUrl ?? null);
    };
  });
}

export async function setCachedThumbnail(key: string, dataUrl: string): Promise<void> {
  const db = await openDb();

  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);

    const request = store.put({
      key,
      dataUrl,
      createdAt: Date.now(),
    } satisfies ThumbnailRecord);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
  });
}