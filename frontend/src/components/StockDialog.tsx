import { FormEvent, useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDownToLine, Barcode, ClipboardCheck, X } from "lucide-react";

import { correctStock, receiveStock } from "../lib/api";
import type { Product } from "../types";
import BarcodeScanner from "./BarcodeScanner";

type Props = {
  mode: "receive" | "correct";
  products: Product[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export default function StockDialog({
  mode,
  products,
  open,
  onOpenChange
}: Props) {
  const queryClient = useQueryClient();
  const [productId, setProductId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState(mode === "receive" ? "Kézi bevételezés" : "Kézi számlálás");
  const [scannedBarcode, setScannedBarcode] = useState<string | null>(null);
  const [scannerMessage, setScannerMessage] = useState<string | null>(null);
  const receiving = mode === "receive";
  const barcodeIndex = useMemo(() => {
    const index = new Map<
      string,
      {
        product: Product;
        packagingUnitId: string | null;
      }
    >();
    for (const product of products) {
      for (const barcode of product.barcodes) {
        index.set(barcode.code, {
          product,
          packagingUnitId: barcode.packaging_unit_id
        });
      }
    }
    return index;
  }, [products]);
  const barcodeMatch = scannedBarcode
    ? barcodeIndex.get(scannedBarcode) ?? null
    : null;
  const packagingUnit = barcodeMatch?.packagingUnitId
    ? barcodeMatch.product.packaging_units.find(
        (unit) => unit.id === barcodeMatch.packagingUnitId
      ) ?? null
    : null;
  const conversionFactor = packagingUnit
    ? Number(packagingUnit.multiplier_to_base_unit)
    : 1;
  const bookedQuantity = Number(quantity || 0) * conversionFactor;

  const mutation = useMutation({
    mutationFn: () =>
      receiving
        ? receiveStock(productId, bookedQuantity, reason)
        : correctStock(productId, Number(quantity), reason),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["stock"] });
      setQuantity("");
      onOpenChange(false);
    }
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }

  function handleBarcodeDetected(code: string) {
    const match = barcodeIndex.get(code);
    setScannedBarcode(match ? code : null);
    if (!match) {
      setScannerMessage(`A(z) ${code} vonalkódhoz nem tartozik aktív termék.`);
      return;
    }
    setProductId(match.product.id);
    setReason("Vonalkódos bevételezés");
    const matchedPackaging = match.packagingUnitId
      ? match.product.packaging_units.find(
          (unit) => unit.id === match.packagingUnitId
        )
      : null;
    setScannerMessage(
      matchedPackaging
        ? `${match.product.name} · ${matchedPackaging.name} csomagolási egység felismerve.`
        : `${match.product.name} felismerve.`
    );
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content compact stock-dialog">
          <div className="dialog-heading">
            <div className="dialog-icon">
              {receiving ? <ArrowDownToLine aria-hidden="true" /> : <ClipboardCheck aria-hidden="true" />}
            </div>
            <div>
              <Dialog.Title>{receiving ? "Áru bevételezése" : "Készletellenőrzés"}</Dialog.Title>
              <Dialog.Description>
                {receiving
                  ? "A mennyiség hozzáadódik az aktuális készlethez."
                  : "A megadott tényleges mennyiség auditált korrekciót hoz létre."}
              </Dialog.Description>
            </div>
            <Dialog.Close className="icon-button" aria-label="Bezárás">
              <X aria-hidden="true" />
            </Dialog.Close>
          </div>
          <form className="dialog-form" onSubmit={submit}>
            {receiving && (
              <section className="stock-scanner-section" aria-label="Vonalkódos termékkeresés">
                <div className="stock-scanner-heading">
                  <Barcode aria-hidden="true" />
                  <span>
                    <strong>Termék beolvasása</strong>
                    <small>Kamera, Bluetooth olvasó vagy kézi kódbevitel</small>
                  </span>
                </div>
                <BarcodeScanner onDetected={(code) => handleBarcodeDetected(code)} />
                {scannerMessage && (
                  <p
                    className={`scanner-message ${
                      scannerMessage.includes("nem tartozik") ? "error" : ""
                    }`}
                  >
                    {scannerMessage}
                  </p>
                )}
              </section>
            )}
            <label>
              Termék
              <select
                value={productId}
                onChange={(event) => {
                  setProductId(event.target.value);
                  setScannedBarcode(null);
                  setScannerMessage(null);
                }}
                required
              >
                <option value="">Válassz terméket</option>
                {products.map((product) => (
                  <option key={product.id} value={product.id}>
                    {product.name} · {product.internal_sku}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {receiving
                ? `Beérkező mennyiség${packagingUnit ? ` (${packagingUnit.name})` : ""}`
                : "Tényleges mennyiség"}
              <input
                className="quantity-input"
                type="number"
                min={receiving ? "0.001" : "0"}
                step="0.001"
                inputMode="decimal"
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
                placeholder="0"
                required
              />
            </label>
            {receiving && packagingUnit && Number(quantity) > 0 && (
              <p className="stock-conversion-hint">
                1 {packagingUnit.name} = {conversionFactor}{" "}
                {barcodeMatch?.product.base_unit}; készletre kerül:{" "}
                <strong>
                  {bookedQuantity} {barcodeMatch?.product.base_unit}
                </strong>
              </p>
            )}
            <label>
              Indok
              <input value={reason} onChange={(event) => setReason(event.target.value)} required />
            </label>
            {mutation.error && <p className="form-error">{mutation.error.message}</p>}
            <div className="dialog-actions">
              <Dialog.Close className="secondary-button" type="button">
                Mégse
              </Dialog.Close>
              <button
                className="primary-button"
                type="submit"
                disabled={
                  mutation.isPending ||
                  !productId ||
                  !quantity ||
                  (receiving && bookedQuantity <= 0)
                }
              >
                {mutation.isPending ? "Rögzítés…" : receiving ? "Bevételezés" : "Korrekció rögzítése"}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
