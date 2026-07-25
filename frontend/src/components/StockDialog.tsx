import { FormEvent, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDownToLine, ClipboardCheck, X } from "lucide-react";

import { correctStock, receiveStock } from "../lib/api";
import type { Product } from "../types";

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

  const mutation = useMutation({
    mutationFn: () =>
      mode === "receive"
        ? receiveStock(productId, Number(quantity), reason)
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

  const receiving = mode === "receive";

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content compact">
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
            <label>
              Termék
              <select
                value={productId}
                onChange={(event) => setProductId(event.target.value)}
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
              {receiving ? "Beérkező mennyiség" : "Tényleges mennyiség"}
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
            <label>
              Indok
              <input value={reason} onChange={(event) => setReason(event.target.value)} required />
            </label>
            {mutation.error && <p className="form-error">{mutation.error.message}</p>}
            <div className="dialog-actions">
              <Dialog.Close className="secondary-button" type="button">
                Mégse
              </Dialog.Close>
              <button className="primary-button" type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? "Rögzítés…" : receiving ? "Bevételezés" : "Korrekció rögzítése"}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
