import { FormEvent, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Barcode, PackagePlus, X } from "lucide-react";

import { createProduct } from "../lib/api";

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
                symbology: "EAN_13",
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
      onOpenChange(false);
    }
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
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
            <label>
              <span className="label-with-icon">
                <Barcode aria-hidden="true" />
                Elsődleges EAN-kód
              </span>
              <input
                inputMode="numeric"
                value={barcode}
                onChange={(event) => setBarcode(event.target.value)}
                placeholder="Opcionális"
              />
            </label>
            {mutation.error && <p className="form-error">{mutation.error.message}</p>}
            <div className="dialog-actions">
              <Dialog.Close className="secondary-button" type="button">
                Mégse
              </Dialog.Close>
              <button className="primary-button" type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? "Mentés…" : "Termék létrehozása"}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

