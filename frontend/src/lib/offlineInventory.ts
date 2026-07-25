import type {
  InventoryCountPayload,
  InventorySession,
  Product,
  StockBalance
} from "../types";

const DATABASE_NAME = "ai-raktar-offline-v1";
const DATABASE_VERSION = 1;
const OPERATION_STORE = "inventory_operations";
const CACHE_STORE = "inventory_cache";

export type OfflineInventoryOperation = {
  id: string;
  organization_id: string;
  session_id: string;
  payload: InventoryCountPayload;
  created_at: string;
  attempts: number;
  last_error: string | null;
};

export type InventoryOfflineSnapshot = {
  key: string;
  organization_id: string;
  cached_at: string;
  active_session: InventorySession | null;
  sessions: InventorySession[];
  products: Product[];
  stock: StockBalance[];
};

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(OPERATION_STORE)) {
        const operations = database.createObjectStore(OPERATION_STORE, {
          keyPath: "id"
        });
        operations.createIndex("organization_id", "organization_id");
        operations.createIndex("session_id", "session_id");
      }
      if (!database.objectStoreNames.contains(CACHE_STORE)) {
        database.createObjectStore(CACHE_STORE, { keyPath: "key" });
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
      reject(transaction.error ?? new Error("Az offline tár művelete megszakadt."));
    transaction.onerror = () =>
      reject(transaction.error ?? new Error("Az offline tár nem írható."));
  });
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function enqueueInventoryOperation(
  operation: OfflineInventoryOperation
): Promise<void> {
  const database = await openDatabase();
  const transaction = database.transaction(OPERATION_STORE, "readwrite");
  transaction.objectStore(OPERATION_STORE).put(operation);
  await completeTransaction(transaction);
  database.close();
}

export async function listInventoryOperations(
  organizationId: string,
  sessionId?: string
): Promise<OfflineInventoryOperation[]> {
  const database = await openDatabase();
  const transaction = database.transaction(OPERATION_STORE, "readonly");
  const completed = completeTransaction(transaction);
  const store = transaction.objectStore(OPERATION_STORE);
  const operations = (await requestResult(
    store.getAll()
  )) as OfflineInventoryOperation[];
  await completed;
  database.close();
  return operations
    .filter(
      (operation) =>
        operation.organization_id === organizationId &&
        (!sessionId || operation.session_id === sessionId)
    )
    .sort((left, right) => left.created_at.localeCompare(right.created_at));
}

export async function updateInventoryOperation(
  operation: OfflineInventoryOperation
): Promise<void> {
  return enqueueInventoryOperation(operation);
}

export async function removeInventoryOperation(
  operationId: string
): Promise<void> {
  const database = await openDatabase();
  const transaction = database.transaction(OPERATION_STORE, "readwrite");
  transaction.objectStore(OPERATION_STORE).delete(operationId);
  await completeTransaction(transaction);
  database.close();
}

export async function writeInventorySnapshot(
  snapshot: Omit<InventoryOfflineSnapshot, "key" | "cached_at">
): Promise<void> {
  const database = await openDatabase();
  const transaction = database.transaction(CACHE_STORE, "readwrite");
  transaction.objectStore(CACHE_STORE).put({
    ...snapshot,
    key: `inventory:${snapshot.organization_id}`,
    cached_at: new Date().toISOString()
  } satisfies InventoryOfflineSnapshot);
  await completeTransaction(transaction);
  database.close();
}

export async function readInventorySnapshot(
  organizationId: string
): Promise<InventoryOfflineSnapshot | null> {
  const database = await openDatabase();
  const transaction = database.transaction(CACHE_STORE, "readonly");
  const completed = completeTransaction(transaction);
  const snapshot = (await requestResult(
    transaction
      .objectStore(CACHE_STORE)
      .get(`inventory:${organizationId}`)
  )) as InventoryOfflineSnapshot | undefined;
  await completed;
  database.close();
  return snapshot ?? null;
}

export function isInventorySyncPaused(organizationId: string): boolean {
  return (
    localStorage.getItem(`ai-raktar-inventory-sync-paused:${organizationId}`) ===
    "true"
  );
}

export function setInventorySyncPaused(
  organizationId: string,
  paused: boolean
): void {
  localStorage.setItem(
    `ai-raktar-inventory-sync-paused:${organizationId}`,
    String(paused)
  );
}
