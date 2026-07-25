const DATABASE_NAME = "ai-raktar-upload-queue-v1";
const DATABASE_VERSION = 1;
const UPLOAD_STORE = "uploads";

export type LocalUploadTarget = "DOCUMENT" | "VRP";
export type LocalUploadStatus =
  | "QUEUED"
  | "PREPARING"
  | "UPLOADING"
  | "PAUSED"
  | "FAILED"
  | "COMPLETED"
  | "CANCELLED";

export type LocalResumableUpload = {
  id: string;
  organization_id: string;
  target_type: LocalUploadTarget;
  filename: string;
  content_type: string;
  size_bytes: number;
  file: Blob;
  file_sha256: string | null;
  metadata: Record<string, string | number | boolean | null>;
  server_upload_id: string | null;
  received_chunks: number[];
  chunk_size: number | null;
  total_chunks: number | null;
  status: LocalUploadStatus;
  progress: number;
  attempts: number;
  last_error: string | null;
  result_entity_type: string | null;
  result_entity_id: string | null;
  created_at: string;
  updated_at: string;
};

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(UPLOAD_STORE)) {
        const store = database.createObjectStore(UPLOAD_STORE, {
          keyPath: "id"
        });
        store.createIndex("organization_id", "organization_id");
        store.createIndex("status", "status");
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function completeTransaction(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () =>
      reject(transaction.error ?? new Error("A feltöltési sor művelete megszakadt."));
    transaction.onerror = () =>
      reject(transaction.error ?? new Error("A feltöltési sor nem írható."));
  });
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function saveLocalUpload(
  upload: LocalResumableUpload
): Promise<void> {
  const database = await openDatabase();
  const transaction = database.transaction(UPLOAD_STORE, "readwrite");
  transaction.objectStore(UPLOAD_STORE).put(upload);
  await completeTransaction(transaction);
  database.close();
}

export async function listLocalUploads(
  organizationId: string
): Promise<LocalResumableUpload[]> {
  const database = await openDatabase();
  const transaction = database.transaction(UPLOAD_STORE, "readonly");
  const completed = completeTransaction(transaction);
  const uploads = (await requestResult(
    transaction.objectStore(UPLOAD_STORE).getAll()
  )) as LocalResumableUpload[];
  await completed;
  database.close();
  return uploads
    .filter((upload) => upload.organization_id === organizationId)
    .sort((left, right) => right.created_at.localeCompare(left.created_at));
}

export async function removeLocalUpload(uploadId: string): Promise<void> {
  const database = await openDatabase();
  const transaction = database.transaction(UPLOAD_STORE, "readwrite");
  transaction.objectStore(UPLOAD_STORE).delete(uploadId);
  await completeTransaction(transaction);
  database.close();
}

export async function sha256Hex(payload: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await payload.arrayBuffer());
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export function localUploadProgress(
  receivedChunks: number[],
  totalChunks: number | null
): number {
  if (!totalChunks) return 0;
  return Math.min(100, Math.round((receivedChunks.length / totalChunks) * 100));
}
