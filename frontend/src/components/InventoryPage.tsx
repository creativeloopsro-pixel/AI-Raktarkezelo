import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  CheckCheck,
  ChevronRight,
  CirclePause,
  CirclePlay,
  ClipboardCheck,
  CloudOff,
  History,
  Minus,
  PackageCheck,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Signal,
  Trash2,
  WifiOff
} from "lucide-react";

import {
  ApiError,
  approveInventorySession,
  cancelInventorySession,
  completeInventorySession,
  getCurrentInventorySession,
  getInventorySessions,
  getProductByCode,
  getProducts,
  getStock,
  recordInventoryCount,
  startInventorySession
} from "../lib/api";
import {
  enqueueInventoryOperation,
  isInventorySyncPaused,
  listInventoryOperations,
  readInventorySnapshot,
  removeInventoryOperation,
  setInventorySyncPaused,
  updateInventoryOperation,
  writeInventorySnapshot,
  type OfflineInventoryOperation
} from "../lib/offlineInventory";
import type {
  InventoryCount,
  InventoryCountPayload,
  InventoryReasonCode,
  InventorySession,
  Product,
  StockBalance
} from "../types";
import BarcodeScanner from "./BarcodeScanner";

type Props = {
  organizationId: string;
  role: string;
};

type WorkspaceData = {
  activeSession: InventorySession | null;
  sessions: InventorySession[];
  products: Product[];
  stock: StockBalance[];
  fromCache: boolean;
  cachedAt: string | null;
};

const reasonOptions: Array<{ value: InventoryReasonCode; label: string }> = [
  { value: "PHYSICAL_COUNT", label: "Fizikai újraszámolás" },
  { value: "DAMAGE", label: "Sérülés vagy selejt" },
  { value: "SHRINKAGE", label: "Hiány" },
  { value: "DATA_ERROR", label: "Korábbi adathiba" },
  { value: "OTHER", label: "Egyéb ok" }
];

const movementLabels: Record<string, string> = {
  GOODS_RECEIPT: "Utolsó bevételezés",
  VRP_SALE_IMPORT: "Utolsó VRP-import",
  INVENTORY_CORRECTION: "Utolsó korrekció"
};

const statusLabels: Record<string, string> = {
  OPEN: "Számlálás folyamatban",
  PENDING_APPROVAL: "Vezetői jóváhagyásra vár",
  COMPLETED: "Lezárva",
  CANCELLED: "Megszakítva"
};

const formatter = new Intl.NumberFormat("hu-HU", {
  maximumFractionDigits: 3
});

function useOnlineState() {
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const connected = () => setOnline(true);
    const disconnected = () => setOnline(false);
    window.addEventListener("online", connected);
    window.addEventListener("offline", disconnected);
    return () => {
      window.removeEventListener("online", connected);
      window.removeEventListener("offline", disconnected);
    };
  }, []);
  return online;
}

async function loadWorkspace(organizationId: string): Promise<WorkspaceData> {
  if (navigator.onLine) {
    try {
      const [activeSession, sessions, products, stock] = await Promise.all([
        getCurrentInventorySession(),
        getInventorySessions(),
        getProducts(),
        getStock()
      ]);
      await writeInventorySnapshot({
        organization_id: organizationId,
        active_session: activeSession,
        sessions,
        products,
        stock
      }).catch(() => undefined);
      return {
        activeSession,
        sessions,
        products,
        stock,
        fromCache: false,
        cachedAt: null
      };
    } catch (error) {
      const cached = await readInventorySnapshot(organizationId);
      if (!cached) throw error;
      return {
        activeSession: cached.active_session,
        sessions: cached.sessions,
        products: cached.products,
        stock: cached.stock,
        fromCache: true,
        cachedAt: cached.cached_at
      };
    }
  }
  const cached = await readInventorySnapshot(organizationId);
  if (!cached) {
    throw new Error("Nincs helyben mentett leltáradat.");
  }
  return {
    activeSession: cached.active_session,
    sessions: cached.sessions,
    products: cached.products,
    stock: cached.stock,
    fromCache: true,
    cachedAt: cached.cached_at
  };
}

export default function InventoryPage({ organizationId, role }: Props) {
  const queryClient = useQueryClient();
  const online = useOnlineState();
  const syncingRef = useRef(false);
  const [paused, setPaused] = useState(() =>
    isInventorySyncPaused(organizationId)
  );
  const [operations, setOperations] = useState<OfflineInventoryOperation[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [sessionName, setSessionName] = useState(
    () =>
      `Kézi leltár · ${new Intl.DateTimeFormat("hu-HU", {
        month: "short",
        day: "numeric"
      }).format(new Date())}`
  );
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [expectedQuantity, setExpectedQuantity] = useState(0);
  const [countedQuantity, setCountedQuantity] = useState(0);
  const [scannedCode, setScannedCode] = useState<string | null>(null);
  const [reasonCode, setReasonCode] = useState<InventoryReasonCode | "">("");
  const [reasonNote, setReasonNote] = useState("");
  const [productSearch, setProductSearch] = useState("");
  const [scannerMessage, setScannerMessage] = useState<string | null>(null);
  const [completionNote, setCompletionNote] = useState("");

  const workspaceQuery = useQuery({
    queryKey: ["inventory-workspace", organizationId],
    queryFn: () => loadWorkspace(organizationId),
    refetchInterval: online && !paused ? 10_000 : false,
    retry: 1
  });
  const data = workspaceQuery.data;
  const activeSession = data?.activeSession ?? null;
  const products = useMemo(() => data?.products ?? [], [data?.products]);
  const stock = useMemo(() => data?.stock ?? [], [data?.stock]);

  const refreshOperations = useCallback(async () => {
    const stored = await listInventoryOperations(organizationId);
    setOperations(stored);
    return stored;
  }, [organizationId]);

  const syncQueue = useCallback(async () => {
    if (!online || paused || syncingRef.current) return;
    syncingRef.current = true;
    setSyncing(true);
    setSyncError(null);
    try {
      const queued = await listInventoryOperations(organizationId);
      for (const operation of queued) {
        try {
          await recordInventoryCount(operation.session_id, operation.payload);
          await removeInventoryOperation(operation.id);
        } catch (error) {
          const message =
            error instanceof Error ? error.message : "A szinkronizáció sikertelen.";
          await updateInventoryOperation({
            ...operation,
            attempts: operation.attempts + 1,
            last_error: message
          });
          setSyncError(message);
          break;
        }
      }
      await refreshOperations();
      await queryClient.invalidateQueries({
        queryKey: ["inventory-workspace", organizationId]
      });
      await queryClient.invalidateQueries({ queryKey: ["stock"] });
    } finally {
      syncingRef.current = false;
      setSyncing(false);
    }
  }, [
    online,
    organizationId,
    paused,
    queryClient,
    refreshOperations
  ]);

  useEffect(() => {
    let cancelled = false;
    void listInventoryOperations(organizationId).then((stored) => {
      if (!cancelled) setOperations(stored);
    });
    return () => {
      cancelled = true;
    };
  }, [organizationId]);

  useEffect(() => {
    if (online && !paused) {
      void syncQueue();
    }
  }, [online, paused, syncQueue]);

  const startMutation = useMutation({
    mutationFn: () => startInventorySession(sessionName),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["inventory-workspace", organizationId]
      });
    }
  });
  const completeMutation = useMutation({
    mutationFn: (session: InventorySession) =>
      completeInventorySession(session.id, completionNote),
    onSuccess: async () => {
      setSelectedProduct(null);
      await queryClient.invalidateQueries({
        queryKey: ["inventory-workspace", organizationId]
      });
      await queryClient.invalidateQueries({ queryKey: ["stock"] });
    }
  });
  const approveMutation = useMutation({
    mutationFn: (session: InventorySession) =>
      approveInventorySession(session.id, completionNote),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["inventory-workspace", organizationId]
      });
      await queryClient.invalidateQueries({ queryKey: ["stock"] });
    }
  });
  const cancelMutation = useMutation({
    mutationFn: (session: InventorySession) =>
      cancelInventorySession(
        session.id,
        completionNote.trim() || "A leltármenet megszakítva."
      ),
    onSuccess: async () => {
      setSelectedProduct(null);
      await queryClient.invalidateQueries({
        queryKey: ["inventory-workspace", organizationId]
      });
    }
  });

  const stockByProduct = useMemo(
    () => new Map(stock.map((item) => [item.product_id, item])),
    [stock]
  );
  const latestPendingByProduct = useMemo(() => {
    const pending = new Map<string, OfflineInventoryOperation>();
    for (const operation of operations) {
      if (
        activeSession &&
        operation.session_id === activeSession.id
      ) {
        pending.set(operation.payload.product_id, operation);
      }
    }
    return pending;
  }, [activeSession, operations]);
  const countedProductIds = useMemo(
    () =>
      new Set([
        ...(activeSession?.counts.map((count) => count.product_id) ?? []),
        ...latestPendingByProduct.keys()
      ]),
    [activeSession, latestPendingByProduct]
  );

  const selectProduct = useCallback(
    (product: Product, code: string | null, increment = 0) => {
      const stockItem = stockByProduct.get(product.id);
      const serverCount = activeSession?.counts.find(
        (count) => count.product_id === product.id
      );
      const pendingCount = latestPendingByProduct.get(product.id);
      const existingCount = pendingCount
        ? pendingCount.payload.counted_quantity
        : serverCount
          ? Number(serverCount.counted_quantity)
          : 0;
      setSelectedProduct(product);
      setExpectedQuantity(Number(stockItem?.quantity ?? 0));
      setCountedQuantity(Math.max(0, existingCount + increment));
      setScannedCode(code);
      setReasonCode(
        (pendingCount?.payload.reason_code ??
          serverCount?.reason_code ??
          "") as InventoryReasonCode | ""
      );
      setReasonNote(
        pendingCount?.payload.reason_note ?? serverCount?.reason_note ?? ""
      );
      setProductSearch("");
    },
    [activeSession, latestPendingByProduct, stockByProduct]
  );

  const handleDetected = useCallback(
    async (code: string, format: string) => {
      setScannerMessage(null);
      let product = products.find((candidate) =>
        candidate.barcodes.some((barcode) => barcode.code === code)
      );
      if (!product && online) {
        try {
          product = await getProductByCode(code);
        } catch {
          product = undefined;
        }
      }
      if (!product) {
        setScannerMessage(
          `A(z) ${code} kódhoz nem tartozik aktív termék.`
        );
        return;
      }
      const barcode = product.barcodes.find((item) => item.code === code);
      const packaging = barcode?.packaging_unit_id
        ? product.packaging_units.find(
            (unit) => unit.id === barcode.packaging_unit_id
          )
        : null;
      const increment = Number(packaging?.multiplier_to_base_unit ?? 1);
      selectProduct(product, code, increment);
      setScannerMessage(
        `${product.name} felismerve · +${formatter.format(increment)} ${product.base_unit} · ${format}`
      );
    },
    [online, products, selectProduct]
  );

  const difference = countedQuantity - expectedQuantity;
  const selectedCount = activeSession?.counts.find(
    (count) => count.product_id === selectedProduct?.id
  );
  const filteredProducts = products
    .filter((product) => {
      const needle = productSearch.trim().toLocaleLowerCase("hu");
      return (
        needle &&
        (product.name.toLocaleLowerCase("hu").includes(needle) ||
          product.internal_sku.toLocaleLowerCase("hu").includes(needle) ||
          product.barcodes.some((barcode) => barcode.code.includes(needle)))
      );
    })
    .slice(0, 6);

  async function queueCount() {
    if (!activeSession || !selectedProduct) return;
    if (difference !== 0 && !reasonCode) {
      setScannerMessage("Eltérés esetén válassz korrekciós okot.");
      return;
    }
    const operationId = crypto.randomUUID();
    const payload: InventoryCountPayload = {
      product_id: selectedProduct.id,
      counted_quantity: countedQuantity,
      client_operation_id: operationId,
      client_recorded_at: new Date().toISOString(),
      client_expected_quantity: expectedQuantity,
      scanned_code: scannedCode,
      reason_code: difference === 0 ? null : reasonCode || null,
      reason_note: reasonNote.trim() || null
    };
    await enqueueInventoryOperation({
      id: operationId,
      organization_id: organizationId,
      session_id: activeSession.id,
      payload,
      created_at: payload.client_recorded_at,
      attempts: 0,
      last_error: null
    });
    setScannerMessage(
      online && !paused
        ? "Számlálás mentve, szinkronizáció folyamatban."
        : "Számlálás biztonságosan az offline sorba került."
    );
    await refreshOperations();
    if (online && !paused) {
      void syncQueue();
    }
  }

  const lastCompleted = data?.sessions.find(
    (session) => session.status === "COMPLETED"
  );
  const operationFailure =
    startMutation.error ??
    completeMutation.error ??
    approveMutation.error ??
    cancelMutation.error;

  if (workspaceQuery.isLoading) {
    return <div className="empty-state inventory-loading">Leltár betöltése…</div>;
  }
  if (workspaceQuery.isError || !data) {
    return (
      <div className="empty-state error-state inventory-loading">
        <WifiOff aria-hidden="true" />
        <strong>A leltár most nem nyitható meg.</strong>
        <span>
          Első használatkor internetkapcsolat szükséges a termékadatok
          mentéséhez.
        </span>
        <button
          className="secondary-button"
          onClick={() => workspaceQuery.refetch()}
        >
          <RefreshCw aria-hidden="true" />
          Újrapróbálás
        </button>
      </div>
    );
  }

  return (
    <motion.div
      className="inventory-page"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <header className="workspace-header inventory-header">
        <div>
          <p className="eyebrow">Kamerás készletellenőrzés</p>
          <h1>Kézi leltár</h1>
        </div>
        <div
          className={`connection-state ${
            online && !data.fromCache ? "online" : "offline"
          }`}
        >
          {online && !data.fromCache ? (
            <Signal aria-hidden="true" />
          ) : (
            <CloudOff aria-hidden="true" />
          )}
          <span>
            {online && !data.fromCache
              ? "Online"
              : `Offline adat${data.cachedAt ? ` · ${new Date(data.cachedAt).toLocaleTimeString("hu-HU", { hour: "2-digit", minute: "2-digit" })}` : ""}`}
          </span>
        </div>
      </header>

      <section className="inventory-status-strip" aria-label="Leltár állapota">
        <div>
          <ClipboardCheck aria-hidden="true" />
          <span>Menet</span>
          <strong>
            {activeSession
              ? statusLabels[activeSession.status]
              : "Nincs aktív leltár"}
          </strong>
        </div>
        <div>
          <PackageCheck aria-hidden="true" />
          <span>Megszámolva</span>
          <strong>{countedProductIds.size} termék</strong>
        </div>
        <div className={operations.length ? "attention" : ""}>
          <RefreshCw aria-hidden="true" className={syncing ? "spin" : ""} />
          <span>Offline sor</span>
          <strong>{operations.length} művelet</strong>
        </div>
      </section>

      {!activeSession && (
        <section className="inventory-start-panel">
          <div>
            <p className="section-label">Új számlálás</p>
            <h2>Indíts leltármenetet</h2>
            <p>
              A termékadatok és az elvárt készlet helyben is elérhető marad.
              A számlálások kapcsolat nélkül az offline sorba kerülnek.
            </p>
          </div>
          <div className="inventory-start-actions">
            <label>
              <span>Menet neve</span>
              <input
                value={sessionName}
                onChange={(event) => setSessionName(event.target.value)}
                maxLength={160}
              />
            </label>
            <button
              className="primary-button"
              disabled={!online || startMutation.isPending || !sessionName.trim()}
              onClick={() => startMutation.mutate()}
            >
              <ClipboardCheck aria-hidden="true" />
              {startMutation.isPending ? "Indítás…" : "Leltár indítása"}
            </button>
            {!online && (
              <small>Új menet indításához rövid internetkapcsolat szükséges.</small>
            )}
          </div>
          {lastCompleted && (
            <div className="last-inventory">
              <CheckCheck aria-hidden="true" />
              <span>
                Utolsó lezárás
                <strong>{lastCompleted.name}</strong>
              </span>
              <time>
                {new Date(
                  lastCompleted.completed_at ?? lastCompleted.updated_at
                ).toLocaleString("hu-HU")}
              </time>
            </div>
          )}
        </section>
      )}

      {activeSession?.status === "OPEN" && (
        <>
          <section className="inventory-workbench">
            <div className="inventory-scan-column">
              <div className="inventory-section-heading">
                <div>
                  <p className="section-label">1 · Azonosítás</p>
                  <h2>Termék beolvasása</h2>
                </div>
                <span>{products.length} helyi termék</span>
              </div>
              <BarcodeScanner onDetected={handleDetected} />
              <div className="inventory-product-search">
                <Search aria-hidden="true" />
                <input
                  value={productSearch}
                  onChange={(event) => setProductSearch(event.target.value)}
                  placeholder="Terméknév, SKU vagy kód"
                />
              </div>
              {filteredProducts.length > 0 && (
                <div className="inventory-search-results">
                  {filteredProducts.map((product) => (
                    <button
                      key={product.id}
                      onClick={() => selectProduct(product, null)}
                    >
                      <span>
                        <strong>{product.name}</strong>
                        <small>{product.internal_sku}</small>
                      </span>
                      <ChevronRight aria-hidden="true" />
                    </button>
                  ))}
                </div>
              )}
              {scannerMessage && (
                <p
                  className={`scanner-message ${
                    scannerMessage.includes("nem tartozik") ||
                    scannerMessage.includes("válassz")
                      ? "error"
                      : ""
                  }`}
                >
                  {scannerMessage}
                </p>
              )}
            </div>

            <div className="inventory-count-column">
              <div className="inventory-section-heading">
                <div>
                  <p className="section-label">2 · Számlálás</p>
                  <h2>Tényleges mennyiség</h2>
                </div>
              </div>
              {!selectedProduct ? (
                <div className="count-placeholder">
                  <ClipboardCheck aria-hidden="true" />
                  <strong>Először olvass be egy terméket.</strong>
                  <span>
                    Kamera, Bluetooth olvasó vagy kézi keresés is használható.
                  </span>
                </div>
              ) : (
                <motion.div
                  key={selectedProduct.id}
                  className="count-editor"
                  initial={{ opacity: 0, x: 12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.22 }}
                >
                  <div className="count-product">
                    <span>{selectedProduct.internal_sku}</span>
                    <h3>{selectedProduct.name}</h3>
                    {scannedCode && <code>{scannedCode}</code>}
                  </div>
                  <div className="expected-quantity">
                    <span>Elvárt készlet</span>
                    <strong>{formatter.format(expectedQuantity)}</strong>
                    <small>{selectedProduct.base_unit}</small>
                  </div>
                  <div className="count-stepper">
                    <button
                      aria-label="Mennyiség csökkentése"
                      onClick={() =>
                        setCountedQuantity((value) => Math.max(0, value - 1))
                      }
                    >
                      <Minus aria-hidden="true" />
                    </button>
                    <label>
                      <span>Ténylegesen megszámolva</span>
                      <input
                        type="number"
                        min="0"
                        step="0.001"
                        value={countedQuantity}
                        onChange={(event) =>
                          setCountedQuantity(
                            Math.max(0, Number(event.target.value))
                          )
                        }
                      />
                      <small>{selectedProduct.base_unit}</small>
                    </label>
                    <button
                      aria-label="Mennyiség növelése"
                      onClick={() => setCountedQuantity((value) => value + 1)}
                    >
                      <Plus aria-hidden="true" />
                    </button>
                  </div>
                  <div
                    className={`count-difference ${
                      difference === 0
                        ? "balanced"
                        : Math.abs(difference) > 100
                          ? "danger"
                          : "changed"
                    }`}
                  >
                    <span>Eltérés</span>
                    <strong>
                      {difference > 0 ? "+" : ""}
                      {formatter.format(difference)}
                    </strong>
                    <small>
                      {difference === 0
                        ? "A készlet egyezik"
                        : "Korrekció készül lezáráskor"}
                    </small>
                  </div>
                  {difference !== 0 && (
                    <div className="count-reason">
                      <label>
                        <span>Korrekció oka</span>
                        <select
                          value={reasonCode}
                          onChange={(event) =>
                            setReasonCode(
                              event.target.value as InventoryReasonCode | ""
                            )
                          }
                        >
                          <option value="">Válassz okot…</option>
                          {reasonOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>Megjegyzés</span>
                        <textarea
                          value={reasonNote}
                          onChange={(event) => setReasonNote(event.target.value)}
                          placeholder="Opcionális részlet"
                          maxLength={500}
                        />
                      </label>
                    </div>
                  )}
                  <button className="primary-button count-save" onClick={queueCount}>
                    <Check aria-hidden="true" />
                    Számlálás mentése
                  </button>

                  {selectedCount?.recent_movements.length ? (
                    <div className="inventory-history">
                      <div>
                        <History aria-hidden="true" />
                        <strong>Utolsó készletműveletek</strong>
                      </div>
                      {selectedCount.recent_movements.map((movement) => (
                        <p key={movement.id}>
                          <span>
                            {movementLabels[movement.movement_type] ??
                              movement.movement_type}
                          </span>
                          <strong>
                            {Number(movement.quantity_delta) > 0 ? "+" : ""}
                            {formatter.format(Number(movement.quantity_delta))}
                          </strong>
                          <time>
                            {new Date(movement.created_at).toLocaleDateString(
                              "hu-HU"
                            )}
                          </time>
                        </p>
                      ))}
                    </div>
                  ) : null}
                </motion.div>
              )}
            </div>
          </section>

          <section className="inventory-counts-section">
            <div className="inventory-section-heading">
              <div>
                <p className="section-label">3 · Ellenőrzés</p>
                <h2>Rögzített termékek</h2>
              </div>
              <span>{countedProductIds.size} tétel</span>
            </div>
            {activeSession.counts.length === 0 &&
            latestPendingByProduct.size === 0 ? (
              <div className="inventory-empty-ledger">
                Még nincs mentett számlálás ebben a menetben.
              </div>
            ) : (
              <div className="inventory-count-list">
                {activeSession.counts.map((count) => (
                  <CountRow
                    key={count.id}
                    count={count}
                    pending={latestPendingByProduct.has(count.product_id)}
                    onSelect={() => {
                      const product = products.find(
                        (item) => item.id === count.product_id
                      );
                      if (product) selectProduct(product, count.scanned_code);
                    }}
                  />
                ))}
                {[...latestPendingByProduct.values()]
                  .filter(
                    (operation) =>
                      !activeSession.counts.some(
                        (count) =>
                          count.product_id === operation.payload.product_id
                      )
                  )
                  .map((operation) => {
                    const product = products.find(
                      (item) => item.id === operation.payload.product_id
                    );
                    return product ? (
                      <button
                        key={operation.id}
                        className="inventory-count-row pending"
                        onClick={() =>
                          selectProduct(
                            product,
                            operation.payload.scanned_code
                          )
                        }
                      >
                        <span>
                          <strong>{product.name}</strong>
                          <small>{product.internal_sku}</small>
                        </span>
                        <span>
                          <strong>
                            {formatter.format(
                              operation.payload.counted_quantity
                            )}
                          </strong>
                          <small>offline sorban</small>
                        </span>
                        <RefreshCw aria-hidden="true" />
                      </button>
                    ) : null;
                  })}
              </div>
            )}
          </section>

          <section className="inventory-finish-panel">
            <div>
              <p className="section-label">4 · Lezárás</p>
              <h2>Kész a számlálás?</h2>
              <p>
                Lezáráskor az eltérések egyetlen tranzakcióban, auditált
                korrekciós mozgásként könyvelődnek.
              </p>
            </div>
            <label>
              <span>Lezárási megjegyzés</span>
              <textarea
                value={completionNote}
                onChange={(event) => setCompletionNote(event.target.value)}
                placeholder="Opcionális megjegyzés"
              />
            </label>
            <div className="inventory-finish-actions">
              <button
                className="secondary-button danger-button"
                disabled={!online || operations.length > 0}
                onClick={() => cancelMutation.mutate(activeSession)}
              >
                <Trash2 aria-hidden="true" />
                Megszakítás
              </button>
              <button
                className="primary-button"
                disabled={
                  !online ||
                  operations.length > 0 ||
                  countedProductIds.size === 0 ||
                  completeMutation.isPending
                }
                onClick={() => completeMutation.mutate(activeSession)}
              >
                <CheckCheck aria-hidden="true" />
                {completeMutation.isPending
                  ? "Lezárás…"
                  : "Leltár lezárása"}
              </button>
            </div>
            {operations.length > 0 && (
              <small>
                Lezárás előtt szinkronizáld a(z) {operations.length} függő
                műveletet.
              </small>
            )}
          </section>
        </>
      )}

      {activeSession?.status === "PENDING_APPROVAL" && (
        <section className="inventory-approval-panel">
          <ShieldCheck aria-hidden="true" />
          <div>
            <p className="section-label">Nagy készleteltérés</p>
            <h2>Vezetői jóváhagyás szükséges</h2>
            <p>
              A számlálás lezárult, de a készlet még nem változott. Admin vagy
              manager jóváhagyása után jönnek létre a korrekciós mozgások.
            </p>
            <strong>{activeSession.counts.length} megszámolt termék</strong>
          </div>
          <label>
            <span>Jóváhagyási megjegyzés</span>
            <textarea
              value={completionNote}
              onChange={(event) => setCompletionNote(event.target.value)}
              placeholder="Az ellenőrzés eredménye"
            />
          </label>
          <div>
            <button
              className="secondary-button danger-button"
              disabled={!online || !["admin", "manager"].includes(role)}
              onClick={() => cancelMutation.mutate(activeSession)}
            >
              <Trash2 aria-hidden="true" />
              Elutasítás
            </button>
            <button
              className="primary-button"
              disabled={
                !online ||
                !["admin", "manager"].includes(role) ||
                approveMutation.isPending
              }
              onClick={() => approveMutation.mutate(activeSession)}
            >
              <ShieldCheck aria-hidden="true" />
              Jóváhagyás és könyvelés
            </button>
          </div>
        </section>
      )}

      <section className={`offline-sync-bar ${operations.length ? "active" : ""}`}>
        <div>
          {online ? <Signal aria-hidden="true" /> : <CloudOff aria-hidden="true" />}
          <span>
            <strong>
              {operations.length
                ? `${operations.length} függő művelet`
                : "Az offline sor üres"}
            </strong>
            <small>
              {syncError ??
                (paused
                  ? "Az automatikus szinkronizáció szünetel."
                  : online
                    ? "Kapcsolat esetén automatikus és idempotens."
                    : "Újracsatlakozáskor automatikusan folytatódik.")}
            </small>
          </span>
        </div>
        <div>
          <button
            title={paused ? "Automatikus szinkron folytatása" : "Szinkron szüneteltetése"}
            onClick={() => {
              const next = !paused;
              setPaused(next);
              setInventorySyncPaused(organizationId, next);
            }}
          >
            {paused ? (
              <CirclePlay aria-hidden="true" />
            ) : (
              <CirclePause aria-hidden="true" />
            )}
            {paused ? "Folytatás" : "Szünet"}
          </button>
          <button
            disabled={!online || paused || syncing || operations.length === 0}
            onClick={() => syncQueue()}
          >
            <RefreshCw aria-hidden="true" className={syncing ? "spin" : ""} />
            Újraküldés
          </button>
        </div>
      </section>

      {(operationFailure || syncError) && (
        <p className="form-error inventory-operation-error">
          <AlertTriangle aria-hidden="true" />
          {operationFailure instanceof ApiError || operationFailure instanceof Error
            ? operationFailure.message
            : syncError}
        </p>
      )}
    </motion.div>
  );
}

function CountRow({
  count,
  pending,
  onSelect
}: {
  count: InventoryCount;
  pending: boolean;
  onSelect: () => void;
}) {
  const difference = Number(count.quantity_difference);
  return (
    <button
      className={`inventory-count-row ${pending ? "pending" : ""}`}
      onClick={onSelect}
    >
      <span>
        <strong>{count.product_name}</strong>
        <small>{count.internal_sku}</small>
      </span>
      <span>
        <small>Elvárt</small>
        <strong>{formatter.format(Number(count.expected_quantity))}</strong>
      </span>
      <span className={difference === 0 ? "balanced" : "changed"}>
        <small>Számolt</small>
        <strong>{formatter.format(Number(count.counted_quantity))}</strong>
      </span>
      <span className={difference === 0 ? "balanced" : "changed"}>
        <small>Eltérés</small>
        <strong>
          {difference > 0 ? "+" : ""}
          {formatter.format(difference)}
        </strong>
      </span>
      {pending ? (
        <RefreshCw aria-label="Offline sorban" />
      ) : (
        <Check aria-label="Szinkronizálva" />
      )}
    </button>
  );
}
