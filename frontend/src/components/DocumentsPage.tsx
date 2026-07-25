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
  UploadCloud
} from "lucide-react";

import {
  downloadDocument,
  getDocuments,
  queueDocument
} from "../lib/api";
type Props = {
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
  FAILED: "Hiba"
};

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
  onUpload,
  onOpenReviews,
  onOpenReceipt
}: Props) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
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

  const filteredDocuments = documents.filter((document) => {
    const needle = search.trim().toLocaleLowerCase("hu");
    const matchesSearch =
      !needle ||
      document.original_filename.toLocaleLowerCase("hu").includes(needle) ||
      document.sha256_hash.includes(needle);
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
      <header className="workspace-header">
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
      </header>

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
                        {document.status === "NEEDS_REVIEW" ? (
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
                          className="icon-button"
                          aria-label={`${document.original_filename} letöltése`}
                          onClick={() => downloadMutation.mutate(document)}
                        >
                          <Download aria-hidden="true" />
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
                        {["READY_FOR_CONFIRMATION", "COMPLETED"].includes(document.status) && (
                          <button
                            className="text-button"
                            onClick={() => onOpenReceipt(document.id)}
                          >
                            {document.status === "COMPLETED" ? "Részletek" : "Előnézet"}
                          </button>
                        )}
                      </div>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {(processingMutation.error || downloadMutation.error) && (
          <p className="form-error document-error">
            {processingMutation.error?.message ||
              downloadMutation.error?.message ||
              "A művelet sikertelen."}
          </p>
        )}
      </section>
    </motion.div>
  );
}
