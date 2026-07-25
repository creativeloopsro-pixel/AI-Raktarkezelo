import { useState } from "react";
import type { CSSProperties } from "react";
import { motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  Check,
  CheckCircle2,
  Clock3,
  FileText,
  PackageCheck,
  Save,
  ScanSearch,
  ShieldCheck
} from "lucide-react";

import {
  confirmGoodsReceipt,
  getGoodsReceipt,
  updateGoodsReceiptItem
} from "../lib/api";
import type {
  GoodsReceiptDraft,
  GoodsReceiptItem,
  Product
} from "../types";

type Props = {
  documentId: string;
  products: Product[];
  onBack: () => void;
};

const issueLabels: Record<string, string> = {
  UNKNOWN_PRODUCT: "Nincs biztos termékegyezés",
  UNKNOWN_PACKAGING_UNIT: "Ismeretlen csomagolási egység",
  LOW_CONFIDENCE: "Alacsony AI-bizonyosság",
  QUANTITY_OUTLIER: "Szokatlanul nagy mennyiség",
  INVALID_SOURCE_PAGE: "Érvénytelen forrásoldal"
};

const statusLabels: Record<string, string> = {
  READY: "Jóváhagyható",
  NEEDS_REVIEW: "Ellenőrzést kér",
  CONFIRMED: "Könyvelve"
};

function LineEditor({
  draft,
  item,
  products,
  disabled
}: {
  draft: GoodsReceiptDraft;
  item: GoodsReceiptItem;
  products: Product[];
  disabled: boolean;
}) {
  const queryClient = useQueryClient();
  const [productId, setProductId] = useState(item.matched_product_id ?? "");
  const [packagingId, setPackagingId] = useState(item.packaging_unit_id ?? "");
  const [quantity, setQuantity] = useState(item.quantity);
  const selectedProduct = products.find((product) => product.id === productId);
  const confidence = Math.round(Number(item.confidence) * 100);

  const updateMutation = useMutation({
    mutationFn: () =>
      updateGoodsReceiptItem(
        draft.id,
        item.id,
        productId,
        packagingId || null,
        Number(quantity)
      ),
    onSuccess: (updated) => {
      queryClient.setQueryData(["goods-receipt", draft.document_id], updated);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents"] }),
        queryClient.invalidateQueries({ queryKey: ["review-tasks"] })
      ]);
    }
  });

  return (
    <motion.article
      className={`receipt-line ${item.status === "READY" ? "ready" : "attention"}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: Math.min(item.line_number * 0.035, 0.2) }}
    >
      <div className="receipt-line-source">
        <span>{String(item.line_number).padStart(2, "0")}</span>
        <div>
          <strong>{item.description}</strong>
          <small>
            {item.barcode || "Nincs vonalkód"} · {item.source_page}. oldal
          </small>
        </div>
      </div>

      <div className={`confidence-meter ${confidence < 90 ? "low" : ""}`}>
        <span>AI confidence</span>
        <strong>{confidence}%</strong>
        <i style={{ "--confidence": `${confidence}%` } as CSSProperties} />
      </div>

      <div className="receipt-line-fields">
        <label>
          Belső termék
          <select
            value={productId}
            disabled={disabled}
            onChange={(event) => {
              setProductId(event.target.value);
              setPackagingId("");
            }}
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
          Egység
          <select
            value={packagingId}
            disabled={disabled || !selectedProduct}
            onChange={(event) => setPackagingId(event.target.value)}
          >
            <option value="">
              {selectedProduct ? selectedProduct.base_unit : "Alapegység"}
            </option>
            {selectedProduct?.packaging_units.map((packaging) => (
              <option key={packaging.id} value={packaging.id}>
                {packaging.name} · ×{Number(packaging.multiplier_to_base_unit)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Mennyiség
          <input
            type="number"
            min="0.001"
            step="0.001"
            value={quantity}
            disabled={disabled}
            onChange={(event) => setQuantity(event.target.value)}
          />
        </label>
        <div className="base-quantity">
          <span>Alapegység</span>
          <strong>{item.base_quantity ?? "–"}</strong>
        </div>
      </div>

      <div className="receipt-line-footer">
        <div className="line-issues">
          {item.validation_issues.length === 0 ? (
            <span className="resolved">
              <Check aria-hidden="true" />
              Párosítás ellenőrizve
            </span>
          ) : (
            item.validation_issues.map((issue) => (
              <span key={issue}>
                <AlertTriangle aria-hidden="true" />
                {issueLabels[issue] ?? issue}
              </span>
            ))
          )}
        </div>
        {!disabled && (
          <button
            className="text-button save-match"
            disabled={
              !productId ||
              !quantity ||
              Number(quantity) <= 0 ||
              updateMutation.isPending
            }
            onClick={() => updateMutation.mutate()}
          >
            <Save aria-hidden="true" />
            {updateMutation.isPending ? "Mentés…" : "Párosítás mentése"}
          </button>
        )}
      </div>
      {updateMutation.error && (
        <p className="form-error">{updateMutation.error.message}</p>
      )}
    </motion.article>
  );
}

export default function ReceiptReviewPage({
  documentId,
  products,
  onBack
}: Props) {
  const queryClient = useQueryClient();
  const receiptQuery = useQuery({
    queryKey: ["goods-receipt", documentId],
    queryFn: () => getGoodsReceipt(documentId)
  });
  const draft = receiptQuery.data;
  const confirmMutation = useMutation({
    mutationFn: (draftId: string) => confirmGoodsReceipt(draftId),
    onSuccess: async (confirmed) => {
      queryClient.setQueryData(["goods-receipt", documentId], confirmed);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents"] }),
        queryClient.invalidateQueries({ queryKey: ["review-tasks"] }),
        queryClient.invalidateQueries({ queryKey: ["stock"] })
      ]);
    }
  });

  if (receiptQuery.isLoading) {
    return <div className="empty-state receipt-loading">AI-eredmény betöltése…</div>;
  }
  if (receiptQuery.isError || !draft) {
    return (
      <div className="receipt-error-page">
        <button className="back-link" onClick={onBack}>
          <ArrowLeft aria-hidden="true" />
          Dokumentumok
        </button>
        <div className="empty-state error-state">
          <AlertTriangle aria-hidden="true" />
          <strong>Az AI-eredmény még nem érhető el.</strong>
          <span>A dokumentum feldolgozása vagy technikai ellenőrzése még folyamatban lehet.</span>
        </div>
      </div>
    );
  }

  const confidence = Math.round(Number(draft.ai_result.overall_confidence) * 100);
  const readOnly = draft.status === "CONFIRMED";

  return (
    <motion.div
      className="receipt-review-page"
      initial={{ opacity: 0, x: 10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3 }}
    >
      <header className="workspace-header receipt-header">
        <div>
          <button className="back-link" onClick={onBack}>
            <ArrowLeft aria-hidden="true" />
            Dokumentumok
          </button>
          <p className="eyebrow">AI-bevételezési előnézet</p>
          <h1>{draft.document_number || "Szám nélküli bizonylat"}</h1>
        </div>
        <span className={`receipt-status ${draft.status.toLowerCase()}`}>
          {draft.status === "CONFIRMED" ? (
            <CheckCircle2 aria-hidden="true" />
          ) : draft.status === "READY" ? (
            <ShieldCheck aria-hidden="true" />
          ) : (
            <AlertTriangle aria-hidden="true" />
          )}
          {statusLabels[draft.status] ?? draft.status}
        </span>
      </header>

      <section className="receipt-meta" aria-label="AI-feldolgozás adatai">
        <div>
          <Bot aria-hidden="true" />
          <span>Modell</span>
          <strong>{draft.ai_result.request.model_name}</strong>
        </div>
        <div>
          <ScanSearch aria-hidden="true" />
          <span>Promptverzió</span>
          <strong>{draft.ai_result.request.prompt_version}</strong>
        </div>
        <div className={confidence < 90 ? "attention" : ""}>
          <ShieldCheck aria-hidden="true" />
          <span>Legkisebb confidence</span>
          <strong>{confidence}%</strong>
        </div>
        <div>
          <Clock3 aria-hidden="true" />
          <span>Feldolgozási idő</span>
          <strong>
            {draft.ai_result.request.duration_ms !== null
              ? `${draft.ai_result.request.duration_ms} ms`
              : "–"}
          </strong>
        </div>
      </section>

      {draft.validation_issues.length > 0 && (
        <div className="receipt-warning">
          <AlertTriangle aria-hidden="true" />
          <div>
            <strong>{draft.validation_issues.length} ellenőrzési ok</strong>
            <span>
              Javítsd vagy erősítsd meg az érintett sorokat a jóváhagyás előtt.
            </span>
          </div>
        </div>
      )}

      <section className="receipt-lines-section">
        <div className="section-heading receipt-lines-heading">
          <div>
            <p className="section-label">Kinyert tételsorok</p>
            <h2>Termékpárosítás és mennyiség</h2>
          </div>
          <div className="receipt-document-meta">
            <FileText aria-hidden="true" />
            <span>{draft.document_date || "Dátum nem olvasható"}</span>
            <strong>{draft.items.length} tétel</strong>
          </div>
        </div>

        <div className="receipt-lines">
          {draft.items.map((item) => (
            <LineEditor
              key={item.id}
              draft={draft}
              item={item}
              products={products}
              disabled={readOnly}
            />
          ))}
        </div>
      </section>

      <footer className="receipt-approval-bar">
        <div>
          <PackageCheck aria-hidden="true" />
          <span>
            <strong>
              {readOnly
                ? "A készletmozgások könyvelve"
                : draft.status === "READY"
                  ? "Minden tétel jóváhagyható"
                  : "Van még ellenőrzendő tétel"}
            </strong>
            <small>A jóváhagyás minden sort egyetlen tranzakcióban rögzít.</small>
          </span>
        </div>
        {!readOnly && (
          <button
            className="primary-button"
            disabled={draft.status !== "READY" || confirmMutation.isPending}
            onClick={() => confirmMutation.mutate(draft.id)}
          >
            <CheckCircle2 aria-hidden="true" />
            {confirmMutation.isPending ? "Könyvelés…" : "Bevételezés jóváhagyása"}
          </button>
        )}
      </footer>
      {confirmMutation.error && (
        <p className="form-error receipt-confirm-error">
          {confirmMutation.error.message}
        </p>
      )}
    </motion.div>
  );
}
