import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Download,
  FileSearch,
  FileText,
  LoaderCircle,
  Search,
  ShieldCheck,
  Trash2,
  Undo2,
  UploadCloud
} from "lucide-react";

import {
  deleteDocument,
  downloadDocument,
  getDocuments,
  queueDocument
} from "../lib/api";
type Props = {
  embedded?: boolean;
  permissions: string[];
  onUpload: () => void;
  onOpenReviews: () => void;
  onOpenReceipt: (documentId: string) => void;
};

const statusLabels: Record<string, string> = {
  UPLOADED: "Feltöltve",
  NEEDS_REVIEW: "Ellenőrzendő",
  QUEUED: "Sorban áll",
  PROCESSING: "Feldolgozás",
  RETRY: "Újrapróbálás",
  READY_FOR_CONFIRMATION: "Jóváhagyható",
  COMPLETED: "Kész",
  FAILED: "Hiba",
  REVERSED: "Visszavonva"
};

const documentTypeLabels: Record<string, string> = {
  goods_receipt: "Szállítólevél",
  delivery_note: "Szállítólevél",
  inventory_report: "Automatikus AI-leltár"
};

const receiptDocumentTypes = new Set(["goods_receipt", "delivery_note"]);

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("hu-HU", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

export default function DocumentsPage({
  embedded = false,
  permissions,
  onUpload,
  onOpenReviews,
  onOpenReceipt
}: Props) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deleteFeedback, setDeleteFeedback] = useState("");
  const canDelete =
    permissions.includes("documents.upload") &&
    permissions.includes("documents.process");
  const documentsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: getDocuments,
    refetchInterval: 5000
  });
  const documents = useMemo(
    () => documentsQuery.data ?? [],
    [documentsQuery.data]
  );

  const processingMutation = useMutation({
    mutationFn: queueDocument,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] })
  });
  const downloadMutation = useMutation({ mutationFn: downloadDocument });
  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: async (_result, documentId) => {
      const deleted = documents.find((document) => document.id === documentId);
      setConfirmDeleteId(null);
      setDeleteFeedback(
        deleted
          ? `${deleted.original_filename} törölve.`
          : "A dokumentum törölve."
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents"] }),
        queryClient.invalidateQueries({ queryKey: ["review-tasks"] }),
        queryClient.invalidateQueries({
          queryKey: ["inventory-report-schedule"]
        })
      ]);
    }
  });

  const requestDelete = (documentId: string) => {
    setDeleteFeedback("");
    deleteMutation.reset();
    if (confirmDeleteId !== documentId) {
      setConfirmDeleteId(documentId);
      return;
    }
    deleteMutation.mutate(documentId);
  };

  const filteredDocuments = documents.filter((document) => {
    const needle = search.trim().toLocaleLowerCase("hu");
    const matchesSearch =
      !needle ||
      document.original_filename.toLocaleLowerCase("hu").includes(needle) ||
      document.sha256_hash.includes(needle) ||
      (documentTypeLabels[document.document_type] ?? document.document_type)
        .toLocaleLowerCase("hu")
        .includes(needle);
    return (
      matchesSearch &&
      (statusFilter === "ALL" || document.status === statusFilter)
    );
  });
  const reviewCount = documents.filter(
    (document) => document.status === "NEEDS_REVIEW"
  ).length;
  const queuedCount = documents.filter((document) =>
    ["QUEUED", "PROCESSING", "RETRY"].includes(document.status)
  ).length;
  const totalBytes = documents.reduce(
    (sum, document) => sum + document.size_bytes,
    0
  );

  return (
    <motion.div
      className="documents-page"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32 }}
    >
      {!embedded && <header className="workspace-header">
        <div>
          <p className="eyebrow">Bejövő bizonylatok</p>
          <h1>Dokumentumok</h1>
        </div>
        <div className="header-actions always-visible">
          <button className="secondary-button" onClick={onOpenReviews}>
            <FileSearch aria-hidden="true" />
            Ellenőrzési sor
            {reviewCount > 0 && <span className="button-count">{reviewCount}</span>}
          </button>
          <button className="primary-button" onClick={onUpload}>
            <UploadCloud aria-hidden="true" />
            Feltöltés
          </button>
        </div>
      </header>}

      <section className="document-summary" aria-label="Dokumentumstátuszok">
        <div>
          <FileText aria-hidden="true" />
          <span>Dokumentum</span>
          <strong>{documents.length}</strong>
        </div>
        <div className={reviewCount ? "attention" : ""}>
          <AlertTriangle aria-hidden="true" />
          <span>Ellenőrzendő</span>
          <strong>{reviewCount}</strong>
        </div>
        <div>
          <Clock3 aria-hidden="true" />
          <span>Feldolgozás alatt</span>
          <strong>{queuedCount}</strong>
        </div>
        <div>
          <ShieldCheck aria-hidden="true" />
          <span>Tárolt adat</span>
          <strong>{formatBytes(totalBytes)}</strong>
        </div>
      </section>

      <section className="documents-list-section">
        <div className="section-heading document-list-heading">
          <div>
            <p className="section-label">Beérkezési napló</p>
            <h2>Feltöltött dokumentumok</h2>
          </div>
          <div className="document-filters">
            <label className="search-field">
              <Search aria-hidden="true" />
              <span className="sr-only">Dokumentum keresése</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Fájlnév vagy hash"
              />
            </label>
            <select
              aria-label="Állapotszűrő"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="ALL">Minden állapot</option>
              <option value="UPLOADED">Feltöltve</option>
              <option value="NEEDS_REVIEW">Ellenőrzendő</option>
              <option value="QUEUED">Sorban áll</option>
              <option value="READY_FOR_CONFIRMATION">Jóváhagyható</option>
              <option value="COMPLETED">Kész</option>
            </select>
          </div>
        </div>

        {documentsQuery.isLoading && (
          <div className="empty-state">Dokumentumok betöltése…</div>
        )}
        {documentsQuery.isError && (
          <div className="empty-state error-state">
            <AlertTriangle aria-hidden="true" />
            A dokumentumlista most nem érhető el.
          </div>
        )}
        {!documentsQuery.isLoading &&
          !documentsQuery.isError &&
          filteredDocuments.length === 0 && (
            <div className="empty-state">
              <UploadCloud aria-hidden="true" />
              <strong>Még nincs feltöltött dokumentum.</strong>
              <span>PDF-et vagy bizonylatfotót a Feltöltés gombbal adhatsz hozzá.</span>
            </div>
          )}

        {filteredDocuments.length > 0 && (
          <div className="document-table-wrap">
            <table className="document-table">
              <thead>
                <tr>
                  <th>Dokumentum</th>
                  <th>Biztonság</th>
                  <th>Állapot</th>
                  <th>Érkezett</th>
                  <th aria-label="Műveletek" />
                </tr>
              </thead>
              <tbody>
                {filteredDocuments.map((document, index) => (
                  <motion.tr
                    key={document.id}
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: Math.min(index * 0.025, 0.2) }}
                  >
                    <td>
                      <div className="document-name-cell">
                        <span className="file-glyph">
                          <FileText aria-hidden="true" />
                        </span>
                        <span>
                          <strong>{document.original_filename}</strong>
                          <small>
                            {document.page_count || "–"} oldal · {formatBytes(document.size_bytes)}
                          </small>
                          <small className="document-type-label">
                            {documentTypeLabels[document.document_type] ??
                              document.document_type}
                          </small>
                        </span>
                      </div>
                    </td>
                    <td>
                      <span className="hash-line">
                        <ShieldCheck aria-hidden="true" />
                        {document.sha256_hash.slice(0, 10)}…
                      </span>
                    </td>
                    <td>
                      <span className={`document-status ${document.status.toLowerCase()}`}>
                        {document.status === "REVERSED" ? (
                          <Undo2 aria-hidden="true" />
                        ) : document.status === "NEEDS_REVIEW" ? (
                          <AlertTriangle aria-hidden="true" />
                        ) : ["UPLOADED", "READY_FOR_CONFIRMATION", "COMPLETED"].includes(
                            document.status
                          ) ? (
                          <CheckCircle2 aria-hidden="true" />
                        ) : (
                          <LoaderCircle aria-hidden="true" />
                        )}
                        {statusLabels[document.status] ?? document.status}
                      </span>
                    </td>
                    <td className="muted-text">{formatDate(document.created_at)}</td>
                    <td>
                      <div className="row-actions">
                        <button
                          className={
                            document.document_type === "inventory_report"
                              ? "text-button report-download-button"
                              : "icon-button"
                          }
                          aria-label={`${document.original_filename} letöltése`}
                          onClick={() => downloadMutation.mutate(document)}
                        >
                          <Download aria-hidden="true" />
                          {document.document_type === "inventory_report"
                            ? "PDF letöltése"
                            : null}
                        </button>
                        {document.status === "UPLOADED" && (
                          <button
                            className="text-button"
                            disabled={
                              processingMutation.isPending &&
                              processingMutation.variables === document.id
                            }
                            onClick={() => processingMutation.mutate(document.id)}
                          >
                            Feldolgozás
                          </button>
                        )}
                        {document.status === "NEEDS_REVIEW" && (
                          <button className="text-button attention" onClick={onOpenReviews}>
                            Ellenőrzés
                          </button>
                        )}
                        {receiptDocumentTypes.has(document.document_type) &&
                          ["READY_FOR_CONFIRMATION", "COMPLETED", "REVERSED"].includes(document.status) && (
                          <button
                            className="text-button"
                            onClick={() => onOpenReceipt(document.id)}
                          >
                            {document.status === "READY_FOR_CONFIRMATION"
                              ? "Előnézet"
                              : "Részletek"}
                          </button>
                        )}
                        {canDelete ? (
                          <button
                            type="button"
                            className={`icon-button danger ${
                              confirmDeleteId === document.id
                                ? "confirming"
                                : ""
                            }`}
                            aria-label={
                              confirmDeleteId === document.id
                                ? `${document.original_filename} törlésének megerősítése`
                                : `${document.original_filename} törlése`
                            }
                            title={
                              ["QUEUED", "PROCESSING", "RETRY"].includes(
                                document.status
                              )
                                ? "Feldolgozás alatt álló dokumentum nem törölhető"
                                : confirmDeleteId === document.id
                                  ? "Kattints újra a végleges törléshez"
                                  : "Dokumentum törlése"
                            }
                            disabled={
                              deleteMutation.isPending ||
                              ["QUEUED", "PROCESSING", "RETRY"].includes(
                                document.status
                              )
                            }
                            onClick={() => requestDelete(document.id)}
                          >
                            {deleteMutation.isPending &&
                            deleteMutation.variables === document.id ? (
                              <LoaderCircle className="spin" aria-hidden="true" />
                            ) : (
                              <Trash2 aria-hidden="true" />
                            )}
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {confirmDeleteId ? (
          <p className="row-delete-feedback warning" role="status">
            A végleges törléshez kattints újra a piros törlésgombra.
          </p>
        ) : null}
        {deleteFeedback ? (
          <p className="row-delete-feedback success" role="status">
            <CheckCircle2 aria-hidden="true" />
            {deleteFeedback}
          </p>
        ) : null}
        {(processingMutation.error ||
          downloadMutation.error ||
          deleteMutation.error) && (
          <p className="form-error document-error">
            {processingMutation.error?.message ||
              downloadMutation.error?.message ||
              deleteMutation.error?.message ||
              "A művelet sikertelen."}
          </p>
        )}
      </section>
    </motion.div>
  );
}
