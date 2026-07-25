import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  FileWarning,
  X
} from "lucide-react";

import { getReviewTasks, queueDocument, resolveReviewTask } from "../lib/api";
import type { ReviewTask } from "../types";

type Props = {
  onBack: () => void;
  onOpenReceipt: (documentId: string) => void;
  onOpenVrp: (batchId: string) => void;
};

const reasonLabels: Record<string, string> = {
  CORRUPT_DOCUMENT: "A dokumentum sérült vagy nem olvasható",
  PASSWORD_PROTECTED_PDF: "A PDF jelszóval védett",
  MIME_TYPE_MISMATCH: "A fájl típusa eltér a megadott típustól",
  PAGE_LIMIT_EXCEEDED: "A dokumentum túllépi az oldalszámkorlátot",
  UNKNOWN_PRODUCT: "A tételhez nincs biztos termékegyezés",
  UNKNOWN_PACKAGING_UNIT: "A csomagolási egység nem azonosítható",
  LOW_CONFIDENCE: "Az AI bizonyossága a küszöbérték alatt van",
  QUANTITY_OUTLIER: "A felismert mennyiség szokatlanul nagy",
  ai_provider_unavailable: "Az AI-szolgáltató nem érhető el",
  ai_response_invalid: "Az AI-válasz nem felel meg a kötelező sémának",
  document_preprocessing_failed: "A dokumentum nem készíthető elő az AI számára",
  PERIOD_OVERLAP: "A riportidőszak átfed egy korábbi VRP-importtal",
  INVALID_REPORT_ROWS: "A VRP-riport hibás tételsorokat tartalmaz",
  MAPPING_REVIEW_REQUIRED: "A javasolt VRP-termékegyezést jóvá kell hagyni",
  NEGATIVE_STOCK_BLOCKED: "A negatívkészlet-szabály blokkolta a könyvelést"
};

export default function ReviewTasksPage({
  onBack,
  onOpenReceipt,
  onOpenVrp
}: Props) {
  const queryClient = useQueryClient();
  const [selectedTask, setSelectedTask] = useState<ReviewTask | null>(null);
  const [note, setNote] = useState("Kézzel ellenőrizve és elfogadva.");
  const tasksQuery = useQuery({
    queryKey: ["review-tasks"],
    queryFn: getReviewTasks
  });
  const tasks = tasksQuery.data ?? [];
  const resolveMutation = useMutation({
    mutationFn: ({ taskId, resolutionNote }: { taskId: string; resolutionNote: string }) =>
      resolveReviewTask(taskId, resolutionNote),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["review-tasks"] }),
        queryClient.invalidateQueries({ queryKey: ["documents"] })
      ]);
      setSelectedTask(null);
    }
  });
  const retryMutation = useMutation({
    mutationFn: queueDocument,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["review-tasks"] }),
        queryClient.invalidateQueries({ queryKey: ["documents"] })
      ]);
      onBack();
    }
  });

  return (
    <motion.div
      className="review-page"
      initial={{ opacity: 0, x: 10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.28 }}
    >
      <header className="workspace-header">
        <div>
          <button className="back-link" onClick={onBack}>
            <ArrowLeft aria-hidden="true" />
            Dokumentumok
          </button>
          <p className="eyebrow">Kézi döntés szükséges</p>
          <h1>Ellenőrzési sor</h1>
        </div>
        <div className="review-total">
          <span>Nyitott feladat</span>
          <strong>{tasks.length}</strong>
        </div>
      </header>

      <section className="review-list">
        <div className="section-heading">
          <div>
            <p className="section-label">Prioritási sorrend</p>
            <h2>Dokumentumvalidáció</h2>
          </div>
        </div>
        {tasksQuery.isLoading && (
          <div className="empty-state">Ellenőrzési feladatok betöltése…</div>
        )}
        {!tasksQuery.isLoading && tasks.length === 0 && (
          <div className="empty-state">
            <CheckCircle2 aria-hidden="true" />
            <strong>Nincs nyitott ellenőrzési feladat.</strong>
            <span>Minden fájl és kinyert tételsor feldolgozható állapotban van.</span>
          </div>
        )}
        {tasks.map((task, index) => (
          <motion.article
            className="review-row"
            key={task.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.04 }}
          >
            <span className="review-severity">
              <FileWarning aria-hidden="true" />
            </span>
            <div className="review-row-main">
              <span className="review-type">
                {task.task_type === "GOODS_RECEIPT_REVIEW"
                  ? "AI-termékpárosítás"
                  : task.task_type === "VRP_IMPORT_REVIEW"
                    ? "VRP-import ellenőrzés"
                  : task.task_type === "AI_PROCESSING_FAILURE"
                    ? "AI-feldolgozási hiba"
                    : "Dokumentumvalidáció"}
              </span>
              <h3>{task.context.filename ?? "Ismeretlen dokumentum"}</h3>
              <p>{reasonLabels[task.reason_code] ?? task.reason_code}</p>
            </div>
            <div className="review-row-meta">
              <span>{new Date(task.created_at).toLocaleString("hu-HU")}</span>
              <button
                className="primary-button"
                onClick={() => {
                  if (
                    task.task_type === "GOODS_RECEIPT_REVIEW" &&
                    task.context.document_id
                  ) {
                    onOpenReceipt(task.context.document_id);
                  } else if (
                    task.task_type === "VRP_IMPORT_REVIEW" &&
                    task.context.batch_id
                  ) {
                    onOpenVrp(task.context.batch_id);
                  } else if (task.task_type === "DOCUMENT_VALIDATION") {
                    setSelectedTask(task);
                  } else if (task.context.document_id) {
                    retryMutation.mutate(task.context.document_id);
                  } else {
                    onBack();
                  }
                }}
              >
                <ClipboardCheck aria-hidden="true" />
                {task.task_type === "GOODS_RECEIPT_REVIEW"
                  ? "Tételek"
                  : task.task_type === "VRP_IMPORT_REVIEW"
                    ? "Import"
                  : task.task_type === "DOCUMENT_VALIDATION"
                    ? "Ellenőrzés"
                    : "Újrapróbálás"}
              </button>
            </div>
          </motion.article>
        ))}
        {retryMutation.error && (
          <p className="form-error">{retryMutation.error.message}</p>
        )}
      </section>

      <Dialog.Root
        open={selectedTask !== null}
        onOpenChange={(open) => !open && setSelectedTask(null)}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content compact">
            <div className="dialog-heading">
              <div className="dialog-icon warning">
                <AlertTriangle aria-hidden="true" />
              </div>
              <div>
                <Dialog.Title>Validáció felülvizsgálata</Dialog.Title>
                <Dialog.Description>
                  {selectedTask?.context.filename}
                </Dialog.Description>
              </div>
              <Dialog.Close className="icon-button" aria-label="Bezárás">
                <X aria-hidden="true" />
              </Dialog.Close>
            </div>
            <div className="review-detail">
              <span>Észlelt probléma</span>
              <strong>
                {selectedTask
                  ? reasonLabels[selectedTask.reason_code] ?? selectedTask.reason_code
                  : ""}
              </strong>
            </div>
            <label className="textarea-label">
              Ellenőrzési megjegyzés
              <textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={4}
              />
            </label>
            {resolveMutation.error && (
              <p className="form-error">{resolveMutation.error.message}</p>
            )}
            <div className="dialog-actions">
              <Dialog.Close className="secondary-button">Mégse</Dialog.Close>
              <button
                className="primary-button"
                disabled={!selectedTask || note.trim().length < 3 || resolveMutation.isPending}
                onClick={() =>
                  selectedTask &&
                  resolveMutation.mutate({
                    taskId: selectedTask.id,
                    resolutionNote: note.trim()
                  })
                }
              >
                {resolveMutation.isPending ? "Mentés…" : "Ellenőrzés lezárása"}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </motion.div>
  );
}
