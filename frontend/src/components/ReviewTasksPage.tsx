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

import { getReviewTasks, resolveReviewTask } from "../lib/api";
import type { ReviewTask } from "../types";

type Props = {
  onBack: () => void;
};

const reasonLabels: Record<string, string> = {
  CORRUPT_DOCUMENT: "A dokumentum sérült vagy nem olvasható",
  PASSWORD_PROTECTED_PDF: "A PDF jelszóval védett",
  MIME_TYPE_MISMATCH: "A fájl típusa eltér a megadott típustól",
  PAGE_LIMIT_EXCEEDED: "A dokumentum túllépi az oldalszámkorlátot"
};

export default function ReviewTasksPage({ onBack }: Props) {
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
            <strong>Nincs ellenőrzésre váró dokumentum.</strong>
            <span>Minden beérkezett fájl megfelelt a validációnak.</span>
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
              <span className="review-type">Dokumentumvalidáció</span>
              <h3>{task.context.filename ?? "Ismeretlen dokumentum"}</h3>
              <p>{reasonLabels[task.reason_code] ?? task.reason_code}</p>
            </div>
            <div className="review-row-meta">
              <span>{new Date(task.created_at).toLocaleString("hu-HU")}</span>
              <button className="primary-button" onClick={() => setSelectedTask(task)}>
                <ClipboardCheck aria-hidden="true" />
                Ellenőrzés
              </button>
            </div>
          </motion.article>
        ))}
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

