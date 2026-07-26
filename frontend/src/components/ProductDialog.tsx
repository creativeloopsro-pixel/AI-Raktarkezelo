import { FormEvent, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Barcode, Camera, PackagePlus, X } from "lucide-react";

import { createProduct } from "../lib/api";
import {
  getEanFormat,
  getEanValidationMessage,
  normalizeEan
} from "../lib/ean";
import BarcodeScanner from "./BarcodeScanner";
import EanBarcode from "./EanBarcode";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export default function ProductDialog({ open, onOpenChange }: Props) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [sku, setSku] = useState("");
  const [barcode, setBarcode] = useState("");
  const [minStock, setMinStock] = useState("0");
  const [scannerOpen, setScannerOpen] = useState(false);
  const [scannerMessage, setScannerMessage] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const eanError = getEanValidationMessage(barcode);

  const mutation = useMutation({
    mutationFn: () =>
      createProduct({
        name,
        internal_sku: sku,
        base_unit: "piece",
        min_stock: Number(minStock),
        packaging_units: [],
        barcodes: barcode
          ? [
              {
                code: barcode,
                symbology: getEanFormat(barcode) ?? "EAN_13",
                is_primary: true,
                packaging_unit_name: null
              }
            ]
          : []
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["products"] }),
        queryClient.invalidateQueries({ queryKey: ["stock"] })
      ]);
      setName("");
      setSku("");
      setBarcode("");
      setMinStock("0");
      setScannerOpen(false);
      setScannerMessage(null);
      setSubmitted(false);
      onOpenChange(false);
    }
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (eanError) return;
    mutation.mutate();
  }

  function handleDetected(code: string) {
    const normalized = code.trim();
    if (!/^(?:\d{8}|\d{13})$/.test(normalized)) {
      setScannerMessage(
        "A beolvasott kód nem EAN-8 vagy EAN-13 formátumú."
      );
      return;
    }
    const issue = getEanValidationMessage(normalized);
    if (issue) {
      setScannerMessage(`A beolvasott kód nem használható EAN-ként. ${issue}`);
      return;
    }
    setBarcode(normalized);
    setScannerMessage(`EAN-kód beolvasva: ${normalized}`);
    setScannerOpen(false);
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content">
          <div className="dialog-heading">
            <div className="dialog-icon">
              <PackagePlus aria-hidden="true" />
            </div>
            <div>
              <Dialog.Title>Új termék</Dialog.Title>
              <Dialog.Description>
                Alapadatok és elsődleges vonalkód rögzítése.
              </Dialog.Description>
            </div>
            <Dialog.Close className="icon-button" aria-label="Bezárás">
              <X aria-hidden="true" />
            </Dialog.Close>
          </div>
          <form className="dialog-form" onSubmit={submit}>
            <label>
              Terméknév
              <input value={name} onChange={(event) => setName(event.target.value)} required />
            </label>
            <div className="form-grid">
              <label>
                Belső SKU
                <input value={sku} onChange={(event) => setSku(event.target.value)} required />
              </label>
              <label>
                Minimumkészlet
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={minStock}
                  onChange={(event) => setMinStock(event.target.value)}
                  required
                />
              </label>
            </div>
            <div className="ean-entry-layout">
              <div className="ean-entry-control">
                <label htmlFor="primary-ean">
                  <span className="label-with-icon">
                    <Barcode aria-hidden="true" />
                    Elsődleges EAN-kód
                  </span>
                </label>
                <div className="ean-input-shell">
                  <input
                    id="primary-ean"
                    inputMode="numeric"
                    autoComplete="off"
                    value={barcode}
                    onChange={(event) => {
                      setBarcode(normalizeEan(event.target.value));
                      setScannerMessage(null);
                    }}
                    placeholder="8 vagy 13 számjegy"
                    aria-invalid={submitted && Boolean(eanError)}
                    aria-describedby={
                      submitted && eanError ? "primary-ean-error" : undefined
                    }
                    required
                  />
                  <button
                    type="button"
                    className={`ean-camera-button ${scannerOpen ? "active" : ""}`}
                    onClick={() => {
                      setScannerOpen((current) => !current);
                      setScannerMessage(null);
                    }}
                    aria-label={
                      scannerOpen
                        ? "EAN-kód kamera bezárása"
                        : "EAN-kód beolvasása kamerával"
                    }
                    title="EAN-kód beolvasása kamerával"
                  >
                    <Camera aria-hidden="true" />
                  </button>
                </div>
                {submitted && eanError ? (
                  <p id="primary-ean-error" className="field-error">
                    {eanError}
                  </p>
                ) : (
                  <small className="field-hint">
                    A kamera ikon beolvassa és automatikusan beírja a kódot.
                  </small>
                )}
              </div>
              <div className="ean-entry-preview" aria-live="polite">
                {barcode && !eanError ? (
                  <EanBarcode code={barcode} />
                ) : (
                  <span className="ean-preview-placeholder">
                    <Barcode aria-hidden="true" />
                    {barcode
                      ? "A helyes EAN előnézete itt jelenik meg."
                      : "Vizuális EAN-előnézet"}
                  </span>
                )}
              </div>
            </div>
            {scannerOpen ? (
              <section
                className="product-ean-scanner"
                aria-label="Elsődleges EAN-kód beolvasása"
              >
                <BarcodeScanner onDetected={handleDetected} />
              </section>
            ) : null}
            {scannerMessage ? (
              <p className="scanner-message" role="status">
                {scannerMessage}
              </p>
            ) : null}
            {mutation.error && <p className="form-error">{mutation.error.message}</p>}
            <div className="dialog-actions">
              <Dialog.Close className="secondary-button" type="button">
                Mégse
              </Dialog.Close>
              <button
                className="primary-button"
                type="submit"
                disabled={mutation.isPending}
              >
                {mutation.isPending ? "Mentés…" : "Termék létrehozása"}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
