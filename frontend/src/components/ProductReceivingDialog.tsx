import {
  ChangeEvent,
  DragEvent,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Barcode,
  Boxes,
  Camera,
  CheckCircle2,
  Clock3,
  FileCheck2,
  FileText,
  ImagePlus,
  PackageCheck,
  ScanBarcode,
  Sparkles,
  UploadCloud,
  X
} from "lucide-react";

import {
  getDocuments,
  getProductByCode,
  receiveStock,
  uploadDocument
} from "../lib/api";
import type {
  Barcode as ProductBarcode,
  DocumentItem,
  PackagingUnit,
  Product,
  StockBalance
} from "../types";
import BarcodeScanner from "./BarcodeScanner";
import EanBarcode from "./EanBarcode";

type ReceiveMode = "delivery_note" | "barcode";

type ProductMatch = {
  product: Product;
  barcode: ProductBarcode;
  packagingUnit: PackagingUnit | null;
};

type Props = {
  open: boolean;
  initialMode: ReceiveMode;
  products: Product[];
  stock: StockBalance[];
  permissions: string[];
  onOpenChange: (open: boolean) => void;
};

type ConfirmationProps = {
  match: ProductMatch;
  stock: StockBalance[];
  onClose: () => void;
  onConfirmed: (product: Product, addition: number) => void;
};

const acceptedDocumentTypes = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/tiff"
];
const terminalDocumentStatuses = new Set([
  "COMPLETED",
  "NEEDS_REVIEW",
  "READY_FOR_CONFIRMATION",
  "FAILED"
]);
const formatter = new Intl.NumberFormat("hu-HU", {
  maximumFractionDigits: 3
});

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function resolveProductMatch(product: Product, code: string): ProductMatch | null {
  const barcode = product.barcodes.find((candidate) => candidate.code === code);
  if (!barcode) return null;
  const packagingUnit = barcode.packaging_unit_id
    ? product.packaging_units.find(
        (unit) => unit.id === barcode.packaging_unit_id
      ) ?? null
    : null;
  return { product, barcode, packagingUnit };
}

function BarcodeStockConfirmation({
  match,
  stock,
  onClose,
  onConfirmed
}: ConfirmationProps) {
  const queryClient = useQueryClient();
  const [units, setUnits] = useState("1");
  const multiplier = Number(match.packagingUnit?.multiplier_to_base_unit ?? 1);
  const currentQuantity = Number(
    stock.find((item) => item.product_id === match.product.id)?.quantity ?? 0
  );
  const scannedUnits = Number(units);
  const addition =
    Number.isFinite(scannedUnits) && scannedUnits > 0
      ? scannedUnits * multiplier
      : 0;
  const resultingQuantity = currentQuantity + addition;

  const mutation = useMutation({
    mutationFn: () =>
      receiveStock(
        match.product.id,
        addition,
        `Vonalkódos bevételezés (${match.barcode.code})`
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["stock"] });
      onConfirmed(match.product, addition);
    }
  });

  return (
    <Dialog.Root open onOpenChange={(nextOpen) => !nextOpen && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay nested-dialog-overlay" />
        <Dialog.Content className="dialog-content compact barcode-confirm-dialog">
          <div className="dialog-heading">
            <div className="dialog-icon">
              <PackageCheck aria-hidden="true" />
            </div>
            <div>
              <Dialog.Title>Termék megtalálva</Dialog.Title>
              <Dialog.Description>
                Ellenőrizd a készletet és a hozzáadandó mennyiséget.
              </Dialog.Description>
            </div>
            <Dialog.Close className="icon-button" aria-label="Bezárás">
              <X aria-hidden="true" />
            </Dialog.Close>
          </div>

          <section className="matched-product-card">
            <div>
              <span>Azonosított termék</span>
              <h3>{match.product.name}</h3>
              <code>{match.product.internal_sku}</code>
            </div>
            <EanBarcode code={match.barcode.code} compact />
          </section>

          {match.packagingUnit ? (
            <p className="stock-conversion-hint">
              Beolvasott egység: <strong>{match.packagingUnit.name}</strong>. Egy
              egység {formatter.format(multiplier)} {match.product.base_unit}.
            </p>
          ) : null}

          <label className="confirm-quantity-field">
            {match.packagingUnit
              ? `${match.packagingUnit.name} darabszáma`
              : "Hozzáadandó mennyiség"}
            <input
              type="number"
              min="0.001"
              step="0.001"
              value={units}
              onChange={(event) => setUnits(event.target.value)}
            />
          </label>

          <section className="stock-change-preview" aria-label="Készletváltozás">
            <div>
              <span>Jelenleg</span>
              <strong>{formatter.format(currentQuantity)}</strong>
              <small>{match.product.base_unit}</small>
            </div>
            <ArrowRight aria-hidden="true" />
            <div className="addition">
              <span>Hozzáad</span>
              <strong>+{formatter.format(addition)}</strong>
              <small>{match.product.base_unit}</small>
            </div>
            <ArrowRight aria-hidden="true" />
            <div className="result">
              <span>Új készlet</span>
              <strong>{formatter.format(resultingQuantity)}</strong>
              <small>{match.product.base_unit}</small>
            </div>
          </section>

          {mutation.error ? (
            <p className="form-error">{mutation.error.message}</p>
          ) : null}

          <div className="dialog-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={onClose}
            >
              Mégse
            </button>
            <button
              className="primary-button"
              type="button"
              disabled={addition <= 0 || mutation.isPending}
              onClick={() => mutation.mutate()}
            >
              <PackageCheck aria-hidden="true" />
              {mutation.isPending
                ? "Bevételezés…"
                : `${formatter.format(addition)} hozzáadása`}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export default function ProductReceivingDialog({
  open,
  initialMode,
  products,
  stock,
  permissions,
  onOpenChange
}: Props) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<ReceiveMode>(initialMode);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState("");
  const [uploadedDocument, setUploadedDocument] =
    useState<DocumentItem | null>(null);
  const [match, setMatch] = useState<ProductMatch | null>(null);
  const [barcodeMessage, setBarcodeMessage] = useState("");
  const [barcodeMessageTone, setBarcodeMessageTone] =
    useState<"success" | "error">("error");
  const canReadDocuments = permissions.includes("documents.read");
  const allowDeliveryNote =
    permissions.includes("documents.upload") &&
    permissions.includes("documents.process") &&
    permissions.includes("receipts.confirm") &&
    permissions.includes("stock.receive");

  const barcodeIndex = useMemo(() => {
    const index = new Map<string, ProductMatch>();
    for (const product of products) {
      for (const barcode of product.barcodes) {
        const resolved = resolveProductMatch(product, barcode.code);
        if (resolved) index.set(barcode.code, resolved);
      }
    }
    return index;
  }, [products]);

  const uploadMutation = useMutation({
    mutationFn: (selectedFile: File) =>
      uploadDocument(selectedFile, "delivery_note", {
        autoProcess: true,
        autoConfirm: true
      }),
    onSuccess: async (document) => {
      setUploadedDocument(document);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (photoInputRef.current) photoInputRef.current.value = "";
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents"] }),
        queryClient.invalidateQueries({ queryKey: ["review-tasks"] })
      ]);
    }
  });

  const documentStatusQuery = useQuery({
    queryKey: ["delivery-note-auto-receipt", uploadedDocument?.id],
    queryFn: async () => {
      const documents = await getDocuments();
      return (
        documents.find((document) => document.id === uploadedDocument?.id) ??
        uploadedDocument
      );
    },
    enabled: Boolean(uploadedDocument && canReadDocuments),
    refetchInterval: (query) =>
      terminalDocumentStatuses.has(query.state.data?.status ?? "")
        ? false
        : 2500
  });
  const currentDocument =
    documentStatusQuery.data ?? uploadedDocument ?? undefined;

  useEffect(() => {
    if (currentDocument?.status === "COMPLETED") {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["stock"] }),
        queryClient.invalidateQueries({ queryKey: ["products"] }),
        queryClient.invalidateQueries({ queryKey: ["documents"] })
      ]);
    }
  }, [currentDocument?.status, queryClient]);

  const lookupMutation = useMutation({
    mutationFn: async (code: string) => {
      const localMatch = barcodeIndex.get(code);
      if (localMatch) return localMatch;
      const product = await getProductByCode(code);
      const resolved = resolveProductMatch(product, code);
      if (!resolved) {
        throw new Error("A kódhoz nem található termék.");
      }
      return resolved;
    },
    onSuccess: (resolved) => {
      setBarcodeMessage("");
      setMatch(resolved);
    },
    onError: (error) => {
      setBarcodeMessageTone("error");
      setBarcodeMessage(error.message || "A vonalkód nem található.");
    }
  });

  function selectFile(selectedFile?: File) {
    uploadMutation.reset();
    setUploadedDocument(null);
    setLocalError("");
    if (!selectedFile) return;
    if (!acceptedDocumentTypes.includes(selectedFile.type)) {
      setLocalError("Csak PDF, JPG, PNG vagy TIFF szállítólevél választható.");
      return;
    }
    if (selectedFile.size > 25 * 1024 * 1024) {
      setLocalError("A szállítólevél legfeljebb 25 MB lehet.");
      return;
    }
    setFile(selectedFile);
  }

  function handleInput(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0]);
  }

  function handleDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files?.[0]);
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen && !uploadMutation.isPending) {
      setFile(null);
      setLocalError("");
      setUploadedDocument(null);
      setMatch(null);
      setBarcodeMessage("");
      setBarcodeMessageTone("error");
      uploadMutation.reset();
      lookupMutation.reset();
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (photoInputRef.current) photoInputRef.current.value = "";
    }
    onOpenChange(nextOpen);
  }

  function renderProcessingState() {
    if (!currentDocument) return null;
    if (currentDocument.status === "COMPLETED") {
      return (
        <div className="ai-receipt-status completed">
          <CheckCircle2 aria-hidden="true" />
          <span>
            <strong>Automatikus bevételezés elkészült.</strong>
            Az AI által biztosan azonosított tételek készletre kerültek.
          </span>
        </div>
      );
    }
    if (
      ["NEEDS_REVIEW", "READY_FOR_CONFIRMATION", "FAILED"].includes(
        currentDocument.status
      )
    ) {
      return (
        <div className="ai-receipt-status attention">
          <AlertTriangle aria-hidden="true" />
          <span>
            <strong>Emberi ellenőrzés szükséges.</strong>
            A bizonytalan tételek nem kerültek automatikusan készletre.
          </span>
        </div>
      );
    }
    return (
      <div className="ai-receipt-status processing">
        <Clock3 aria-hidden="true" />
        <span>
          <strong>Az AI feldolgozza a szállítólevelet.</strong>
          A biztosan felismert termékeket automatikusan hozzáadja a készlethez.
        </span>
      </div>
    );
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content product-receiving-dialog">
          <div className="dialog-heading">
            <div className="dialog-icon">
              <Boxes aria-hidden="true" />
            </div>
            <div>
              <Dialog.Title>Készlet hozzáadása</Dialog.Title>
              <Dialog.Description>
                Szállítólevélből vagy vonalkód alapján.
              </Dialog.Description>
            </div>
            <Dialog.Close className="icon-button" aria-label="Bezárás">
              <X aria-hidden="true" />
            </Dialog.Close>
          </div>

          <div className="receiving-mode-switch" aria-label="Bevételezés módja">
            {allowDeliveryNote ? (
              <button
                type="button"
                className={mode === "delivery_note" ? "active" : ""}
                onClick={() => setMode("delivery_note")}
                aria-pressed={mode === "delivery_note"}
              >
                <FileText aria-hidden="true" />
                Szállítólevél
              </button>
            ) : null}
            <button
              type="button"
              className={mode === "barcode" ? "active" : ""}
              onClick={() => setMode("barcode")}
              aria-pressed={mode === "barcode"}
            >
              <ScanBarcode aria-hidden="true" />
              Vonalkód
            </button>
          </div>

          {mode === "delivery_note" && allowDeliveryNote ? (
            <div className="delivery-receipt-flow">
              {currentDocument ? (
                <>
                  {renderProcessingState()}
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => {
                      setUploadedDocument(null);
                      uploadMutation.reset();
                    }}
                  >
                    Másik szállítólevél
                  </button>
                </>
              ) : (
                <>
                  <div className="delivery-upload-actions">
                    <button
                      type="button"
                      className={`delivery-drop-zone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
                      onClick={() => fileInputRef.current?.click()}
                      onDragEnter={(event) => {
                        event.preventDefault();
                        setDragging(true);
                      }}
                      onDragOver={(event) => event.preventDefault()}
                      onDragLeave={() => setDragging(false)}
                      onDrop={handleDrop}
                    >
                      {file ? (
                        <>
                          <FileCheck2 aria-hidden="true" />
                          <span>
                            <strong>{file.name}</strong>
                            <small>{formatBytes(file.size)} · feldolgozásra kész</small>
                          </span>
                        </>
                      ) : (
                        <>
                          <UploadCloud aria-hidden="true" />
                          <span>
                            <strong>Szállítólevél kiválasztása</strong>
                            <small>PDF vagy képfájl feltöltése</small>
                          </span>
                        </>
                      )}
                    </button>
                    <button
                      type="button"
                      className="delivery-camera-button"
                      onClick={() => photoInputRef.current?.click()}
                    >
                      <Camera aria-hidden="true" />
                      <span>
                        <strong>Fénykép készítése</strong>
                        <small>A telefon hátlapi kamerájával</small>
                      </span>
                    </button>
                  </div>
                  <input
                    ref={fileInputRef}
                    className="sr-only"
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff"
                    onChange={handleInput}
                  />
                  <input
                    ref={photoInputRef}
                    className="sr-only"
                    type="file"
                    accept="image/jpeg,image/png,image/tiff"
                    capture="environment"
                    onChange={handleInput}
                  />
                  <div className="ai-auto-receive-note">
                    <Sparkles aria-hidden="true" />
                    <span>
                      <strong>AI-felismerés és automatikus készletre helyezés</strong>
                      Csak a legalább 98%-os, pontosan azonosított tételek kerülnek
                      automatikusan készletre. A többi ellenőrzésre vár.
                    </span>
                  </div>
                  {(localError || uploadMutation.error) ? (
                    <p className="form-error">
                      {localError ||
                        uploadMutation.error?.message ||
                        "A feltöltés sikertelen."}
                    </p>
                  ) : null}
                  <button
                    type="button"
                    className="primary-button delivery-process-button"
                    disabled={!file || uploadMutation.isPending}
                    onClick={() => file && uploadMutation.mutate(file)}
                  >
                    <ImagePlus aria-hidden="true" />
                    {uploadMutation.isPending
                      ? "Feltöltés és AI-feldolgozás…"
                      : "AI-bevételezés indítása"}
                  </button>
                </>
              )}
            </div>
          ) : (
            <div className="barcode-receive-flow">
              <div className="barcode-receive-heading">
                <Barcode aria-hidden="true" />
                <span>
                  <strong>Termék azonosítása</strong>
                  <small>
                    Kamera, Bluetooth-olvasó vagy kézi EAN-kód.
                  </small>
                </span>
              </div>
              <BarcodeScanner
                disabled={lookupMutation.isPending}
                onDetected={(code) => lookupMutation.mutate(code)}
              />
              {lookupMutation.isPending ? (
                <p className="scanner-message">Termék keresése…</p>
              ) : null}
              {barcodeMessage ? (
                <p className={`scanner-message ${barcodeMessageTone}`}>
                  {barcodeMessage}
                </p>
              ) : null}
              {barcodeMessage && barcodeMessageTone === "error" ? (
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setMode("delivery_note")}
                  disabled={!allowDeliveryNote}
                >
                  <FileText aria-hidden="true" />
                  Próbálom szállítólevélről
                </button>
              ) : null}
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>

      {match ? (
        <BarcodeStockConfirmation
          key={`${match.product.id}:${match.barcode.code}`}
          match={match}
          stock={stock}
          onClose={() => setMatch(null)}
          onConfirmed={(product, addition) => {
            setMatch(null);
            setBarcodeMessageTone("success");
            setBarcodeMessage(
              `${product.name}: ${formatter.format(addition)} hozzáadva a készlethez.`
            );
          }}
        />
      ) : null}
    </Dialog.Root>
  );
}
