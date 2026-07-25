import { useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CalendarClock,
  Check,
  Clock3,
  FileSpreadsheet,
  Play,
  RotateCcw,
  Save,
  Settings2,
  ShieldCheck,
  UploadCloud,
  X
} from "lucide-react";

import {
  getVrpImport,
  getVrpImports,
  getVrpSchedule,
  processVrpImport,
  reverseVrpImport,
  updateVrpItem,
  updateVrpSchedule,
  uploadVrpImport
} from "../lib/api";
import type {
  Product,
  VrpImportBatch,
  VrpImportItem,
  VrpSchedule,
  VrpScheduleUpdate
} from "../types";

type Props = {
  role: string;
  products: Product[];
  initialBatchId: string | null;
  onOpenReviews: () => void;
};

const statusLabels: Record<string, string> = {
  UPLOADED: "Feltöltve",
  VALIDATING: "Ellenőrzés",
  READY: "Indítható",
  SCHEDULED: "Ütemezve",
  PROCESSING: "Könyvelés",
  COMPLETED: "Könyvelve",
  NEEDS_REVIEW: "Ellenőrzést kér",
  OVERLAP: "Átfedés blokkolva",
  FAILED: "Sikertelen",
  REVERSED: "Visszafordítva"
};

const issueLabels: Record<string, string> = {
  UNKNOWN_PRODUCT: "Nincs mentett termékmegfeleltetés",
  MAPPING_REVIEW_REQUIRED: "A javasolt egyezést jóvá kell hagyni"
};

const frequencyLabels: Record<string, string> = {
  DAILY: "Naponta",
  WEEKLY: "Hetente",
  MONTHLY: "Havonta",
  MANUAL: "Kézi indítás"
};

const weekdayLabels: Record<string, string> = {
  MONDAY: "Hétfő",
  TUESDAY: "Kedd",
  WEDNESDAY: "Szerda",
  THURSDAY: "Csütörtök",
  FRIDAY: "Péntek",
  SATURDAY: "Szombat",
  SUNDAY: "Vasárnap"
};

function localDate(): string {
  return new Intl.DateTimeFormat("sv-SE").format(new Date());
}

function formatDateTime(value: string | null): string {
  if (!value) return "Nincs következő futás";
  return new Intl.DateTimeFormat("hu-HU", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function VrpLineEditor({
  batch,
  item,
  products,
  disabled
}: {
  batch: VrpImportBatch;
  item: VrpImportItem;
  products: Product[];
  disabled: boolean;
}) {
  const queryClient = useQueryClient();
  const [productId, setProductId] = useState(item.matched_product_id ?? "");
  const [factor, setFactor] = useState(item.conversion_factor ?? "1");
  const calculated =
    Number.isFinite(Number(factor)) && Number(factor) > 0
      ? Number(item.quantity) * Number(factor)
      : null;
  const mutation = useMutation({
    mutationFn: () =>
      updateVrpItem(batch.id, item.id, productId, Number(factor)),
    onSuccess: (updated) => {
      queryClient.setQueryData(["vrp-import", batch.id], updated);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["vrp-imports"] }),
        queryClient.invalidateQueries({ queryKey: ["review-tasks"] })
      ]);
    }
  });

  return (
    <motion.article
      className={`vrp-line ${item.status === "READY" ? "ready" : "attention"}`}
      initial={{ opacity: 0, y: 7 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(item.line_number * 0.025, 0.18) }}
    >
      <div className="vrp-line-source">
        <span>{String(item.line_number).padStart(2, "0")}</span>
        <div>
          <strong>{item.external_name}</strong>
          <small>
            {item.external_product_id || "Nincs külső azonosító"} ·{" "}
            {Number(item.quantity).toLocaleString("hu-HU")} {item.unit}
          </small>
        </div>
        <span className={`vrp-item-status ${item.status.toLowerCase()}`}>
          {item.status === "READY"
            ? item.match_method === "MANUAL_MAPPING"
              ? "Jóváhagyva"
              : "Egyezés"
            : item.status === "SKIPPED"
              ? "Kihagyva"
              : "Döntést kér"}
        </span>
      </div>
      <div className="vrp-line-fields">
        <label>
          Belső termék
          <select
            value={productId}
            disabled={disabled}
            onChange={(event) => setProductId(event.target.value)}
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
          Konverziós faktor
          <input
            type="number"
            min="0.001"
            step="0.001"
            value={factor}
            disabled={disabled}
            onChange={(event) => setFactor(event.target.value)}
          />
        </label>
        <div className="vrp-base-quantity">
          <span>Könyvelt alapegység</span>
          <strong>
            {calculated === null
              ? "–"
              : calculated.toLocaleString("hu-HU", {
                  maximumFractionDigits: 3
                })}
          </strong>
        </div>
      </div>
      <div className="vrp-line-footer">
        <div className="line-issues">
          {item.validation_issues.length ? (
            item.validation_issues.map((issue) => (
              <span key={issue}>
                <AlertTriangle aria-hidden="true" />
                {issueLabels[issue] ?? issue}
              </span>
            ))
          ) : (
            <span className="resolved">
              <Check aria-hidden="true" />
              {item.matched_product?.name ?? "Megfeleltetés rögzítve"}
            </span>
          )}
        </div>
        {!disabled && (
          <button
            className="text-button save-match"
            disabled={
              !productId ||
              !factor ||
              Number(factor) <= 0 ||
              mutation.isPending
            }
            onClick={() => mutation.mutate()}
          >
            <Save aria-hidden="true" />
            {mutation.isPending ? "Mentés…" : "Megfeleltetés mentése"}
          </button>
        )}
      </div>
      {mutation.error && <p className="form-error">{mutation.error.message}</p>}
    </motion.article>
  );
}

function UploadDialog({
  open,
  onOpenChange,
  onUploaded
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUploaded: (batch: VrpImportBatch) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [periodStart, setPeriodStart] = useState(localDate());
  const [periodEnd, setPeriodEnd] = useState(localDate());
  const [reportId, setReportId] = useState("");
  const mutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("Válassz VRP-riportot.");
      return uploadVrpImport(file, periodStart, periodEnd, reportId);
    },
    onSuccess: (batch) => {
      onUploaded(batch);
      onOpenChange(false);
      setFile(null);
      setReportId("");
    }
  });

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content upload-dialog">
          <div className="dialog-heading">
            <div className="dialog-icon">
              <FileSpreadsheet aria-hidden="true" />
            </div>
            <div>
              <Dialog.Title>VRP eladási riport feltöltése</Dialog.Title>
              <Dialog.Description>
                CSV, XLSX vagy géppel olvasható PDF · legfeljebb 15 MB
              </Dialog.Description>
            </div>
            <Dialog.Close className="icon-button" aria-label="Bezárás">
              <X aria-hidden="true" />
            </Dialog.Close>
          </div>
          <label className={`drop-zone ${file ? "has-file" : ""}`}>
            <UploadCloud aria-hidden="true" />
            <strong>{file?.name ?? "Válassz vagy húzz ide egy riportot"}</strong>
            <span>
              {file
                ? formatBytes(file.size)
                : "Az ár- és adóoszlopokat a rendszer figyelmen kívül hagyja."}
            </span>
            <input
              className="sr-only"
              type="file"
              accept=".csv,.xlsx,.pdf"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <div className="form-grid vrp-upload-fields">
            <label>
              Időszak kezdete
              <input
                type="date"
                value={periodStart}
                onChange={(event) => setPeriodStart(event.target.value)}
              />
            </label>
            <label>
              Időszak vége
              <input
                type="date"
                value={periodEnd}
                onChange={(event) => setPeriodEnd(event.target.value)}
              />
            </label>
            <label className="full-width">
              Külső riportazonosító <small>nem kötelező</small>
              <input
                maxLength={160}
                value={reportId}
                placeholder="Például VRP-2026-07-25"
                onChange={(event) => setReportId(event.target.value)}
              />
            </label>
          </div>
          <div className="upload-safety">
            <ShieldCheck aria-hidden="true" />
            <span>
              A fájl aláírás-, vírus-, duplikáció- és időszakátfedés-ellenőrzésen
              megy át, mielőtt könyvelhetővé válik.
            </span>
          </div>
          {mutation.error && <p className="form-error">{mutation.error.message}</p>}
          <div className="dialog-actions">
            <Dialog.Close className="secondary-button">Mégse</Dialog.Close>
            <button
              className="primary-button"
              disabled={
                !file ||
                !periodStart ||
                !periodEnd ||
                periodStart > periodEnd ||
                mutation.isPending
              }
              onClick={() => mutation.mutate()}
            >
              {mutation.isPending ? "Ellenőrzés…" : "Riport feltöltése"}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function ScheduleDialog({
  schedule,
  open,
  onOpenChange
}: {
  schedule: VrpSchedule;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<VrpScheduleUpdate>({
    frequency: schedule.frequency,
    processing_time: schedule.processing_time.slice(0, 5),
    timezone: schedule.timezone,
    weekly_day: schedule.weekly_day,
    monthly_rule: schedule.monthly_rule,
    auto_process: schedule.auto_process,
    unknown_product_policy: schedule.unknown_product_policy,
    negative_stock_policy: schedule.negative_stock_policy,
    overlap_policy: "BLOCK"
  });
  const set = <K extends keyof VrpScheduleUpdate>(
    field: K,
    value: VrpScheduleUpdate[K]
  ) => setForm((current) => ({ ...current, [field]: value }));
  const mutation = useMutation({
    mutationFn: () => updateVrpSchedule(form),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["vrp-schedule"] }),
        queryClient.invalidateQueries({ queryKey: ["vrp-imports"] })
      ]);
      onOpenChange(false);
    }
  });

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content vrp-schedule-dialog">
          <div className="dialog-heading">
            <div className="dialog-icon">
              <CalendarClock aria-hidden="true" />
            </div>
            <div>
              <Dialog.Title>VRP-feldolgozás ütemezése</Dialog.Title>
              <Dialog.Description>
                A jóváhagyható riportok automatikus könyvelési szabályai
              </Dialog.Description>
            </div>
            <Dialog.Close className="icon-button" aria-label="Bezárás">
              <X aria-hidden="true" />
            </Dialog.Close>
          </div>
          <div className="form-grid">
            <label>
              Gyakoriság
              <select
                value={form.frequency}
                onChange={(event) => {
                  const frequency = event.target
                    .value as VrpScheduleUpdate["frequency"];
                  set("frequency", frequency);
                  if (frequency === "MANUAL") set("auto_process", false);
                }}
              >
                <option value="DAILY">Naponta</option>
                <option value="WEEKLY">Hetente</option>
                <option value="MONTHLY">Havonta</option>
                <option value="MANUAL">Csak kézi indítás</option>
              </select>
            </label>
            <label>
              Feldolgozási idő
              <input
                type="time"
                value={form.processing_time}
                onChange={(event) => set("processing_time", event.target.value)}
              />
            </label>
            {form.frequency === "WEEKLY" && (
              <label>
                Heti nap
                <select
                  value={form.weekly_day}
                  onChange={(event) => set("weekly_day", event.target.value)}
                >
                  {Object.entries(weekdayLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {form.frequency === "MONTHLY" && (
              <label>
                Havi nap
                <select
                  value={form.monthly_rule}
                  onChange={(event) => set("monthly_rule", event.target.value)}
                >
                  <option value="LAST_DAY">Hónap utolsó napja</option>
                  {Array.from({ length: 28 }, (_, index) => index + 1).map(
                    (day) => (
                      <option key={day} value={day}>
                        {day}. nap
                      </option>
                    )
                  )}
                </select>
              </label>
            )}
            <label>
              Ismeretlen termék
              <select
                value={form.unknown_product_policy}
                onChange={(event) =>
                  set(
                    "unknown_product_policy",
                    event.target
                      .value as VrpScheduleUpdate["unknown_product_policy"]
                  )
                }
              >
                <option value="STOP">Teljes import megállítása</option>
                <option value="PROCESS_KNOWN">Ismert tételek feldolgozása</option>
                <option value="CREATE_REVIEW">Ellenőrzési feladat létrehozása</option>
              </select>
            </label>
            <label>
              Negatív készlet
              <select
                value={form.negative_stock_policy}
                onChange={(event) =>
                  set(
                    "negative_stock_policy",
                    event.target
                      .value as VrpScheduleUpdate["negative_stock_policy"]
                  )
                }
              >
                <option value="ALLOW_WITH_WARNING">Engedélyezés figyelmeztetéssel</option>
                <option value="STOP">Könyvelés megállítása</option>
              </select>
            </label>
            <label>
              Időzóna
              <input
                value={form.timezone}
                maxLength={80}
                onChange={(event) => set("timezone", event.target.value)}
              />
            </label>
          </div>
          <label className="vrp-toggle">
            <input
              type="checkbox"
              checked={form.auto_process}
              disabled={form.frequency === "MANUAL"}
              onChange={(event) => set("auto_process", event.target.checked)}
            />
            <span>
              <strong>Automatikus feldolgozás</strong>
              <small>Csak a hibamentes, átfedés nélküli riportok futnak.</small>
            </span>
          </label>
          <div className="vrp-policy-note">
            <ShieldCheck aria-hidden="true" />
            Az időszakátfedés mindig blokkolt; ez a biztonsági szabály nem
            kapcsolható ki.
          </div>
          {mutation.error && <p className="form-error">{mutation.error.message}</p>}
          <div className="dialog-actions">
            <Dialog.Close className="secondary-button">Mégse</Dialog.Close>
            <button
              className="primary-button"
              disabled={
                !form.processing_time ||
                !form.timezone.trim() ||
                mutation.isPending
              }
              onClick={() => mutation.mutate()}
            >
              {mutation.isPending ? "Mentés…" : "Ütemezés mentése"}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export default function VrpImportsPage({
  role,
  products,
  initialBatchId,
  onOpenReviews
}: Props) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(initialBatchId);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [reverseOpen, setReverseOpen] = useState(false);
  const [reverseReason, setReverseReason] = useState(
    "Hibás VRP-riport visszafordítása."
  );
  const canOperate = role === "admin" || role === "manager";
  const canAdmin = role === "admin";
  const importsQuery = useQuery({
    queryKey: ["vrp-imports"],
    queryFn: getVrpImports,
    refetchInterval: 5000
  });
  const scheduleQuery = useQuery({
    queryKey: ["vrp-schedule"],
    queryFn: getVrpSchedule
  });
  const batchQuery = useQuery({
    queryKey: ["vrp-import", selectedId],
    queryFn: () => getVrpImport(selectedId as string),
    enabled: Boolean(selectedId),
    refetchInterval: selectedId ? 5000 : false
  });
  const imports = useMemo(() => importsQuery.data ?? [], [importsQuery.data]);
  const batch = batchQuery.data;
  const invalidate = async (updated?: VrpImportBatch) => {
    if (updated) queryClient.setQueryData(["vrp-import", updated.id], updated);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["vrp-imports"] }),
      queryClient.invalidateQueries({ queryKey: ["review-tasks"] }),
      queryClient.invalidateQueries({ queryKey: ["stock"] })
    ]);
  };
  const processMutation = useMutation({
    mutationFn: processVrpImport,
    onSuccess: (updated) => invalidate(updated)
  });
  const reverseMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      reverseVrpImport(id, reason),
    onSuccess: async (updated) => {
      await invalidate(updated);
      setReverseOpen(false);
    }
  });
  const metrics = {
    total: imports.length,
    review: imports.filter((item) =>
      ["NEEDS_REVIEW", "OVERLAP", "FAILED"].includes(item.status)
    ).length,
    scheduled: imports.filter((item) => item.status === "SCHEDULED").length,
    completed: imports.filter((item) => item.status === "COMPLETED").length
  };

  if (selectedId) {
    if (batchQuery.isLoading) {
      return <div className="empty-state">VRP-import betöltése…</div>;
    }
    if (batchQuery.isError || !batch) {
      return (
        <div className="vrp-detail-page">
          <button className="back-link" onClick={() => setSelectedId(null)}>
            <ArrowLeft aria-hidden="true" />
            VRP-importok
          </button>
          <div className="empty-state error-state">
            <AlertTriangle aria-hidden="true" />
            A kiválasztott import nem érhető el.
          </div>
        </div>
      );
    }
    const editable =
      canOperate &&
      !["COMPLETED", "REVERSED", "PROCESSING", "OVERLAP"].includes(
        batch.status
      );
    return (
      <motion.div
        className="vrp-detail-page"
        initial={{ opacity: 0, x: 10 }}
        animate={{ opacity: 1, x: 0 }}
      >
        <header className="workspace-header receipt-header">
          <div>
            <button className="back-link" onClick={() => setSelectedId(null)}>
              <ArrowLeft aria-hidden="true" />
              VRP-importok
            </button>
            <p className="eyebrow">VRP2 · Report predaja</p>
            <h1>{batch.original_filename}</h1>
          </div>
          <span className={`vrp-status ${batch.status.toLowerCase()}`}>
            {statusLabels[batch.status] ?? batch.status}
          </span>
        </header>

        <section className="vrp-progress" aria-label="Importfolyamat">
          {["UPLOADED", "VALIDATING", "READY", "PROCESSING", "COMPLETED"].map(
            (step) => (
              <span
                key={step}
                className={
                  step === batch.status ||
                  (batch.status === "SCHEDULED" && step === "READY") ||
                  ["COMPLETED", "REVERSED"].includes(batch.status)
                    ? "active"
                    : ""
                }
              >
                <i />
                {statusLabels[step]}
              </span>
            )
          )}
        </section>

        <section className="receipt-meta vrp-meta">
          <div>
            <CalendarClock aria-hidden="true" />
            <span>Riportidőszak</span>
            <strong>
              {batch.period_start} – {batch.period_end}
            </strong>
          </div>
          <div>
            <FileSpreadsheet aria-hidden="true" />
            <span>Tételsor</span>
            <strong>{batch.items.length}</strong>
          </div>
          <div>
            <ShieldCheck aria-hidden="true" />
            <span>Parser</span>
            <strong>{batch.parser_version}</strong>
          </div>
          <div>
            <Clock3 aria-hidden="true" />
            <span>Feldolgozás</span>
            <strong>
              {batch.scheduled_for
                ? formatDateTime(batch.scheduled_for)
                : batch.processed_at
                  ? formatDateTime(batch.processed_at)
                  : "Kézi indítás"}
            </strong>
          </div>
        </section>

        {(batch.errors.length > 0 ||
          ["NEEDS_REVIEW", "OVERLAP", "FAILED"].includes(batch.status)) && (
          <div className="receipt-warning">
            <AlertTriangle aria-hidden="true" />
            <span>
              <strong>
                {batch.status === "OVERLAP"
                  ? "A riport időszaka átfed egy korábbi importtal."
                  : "A riport kézi ellenőrzést kér."}
              </strong>
              <span>
                {batch.errors.length
                  ? `${batch.errors.length} hibás sor miatt javított riportot kell feltölteni.`
                  : "Ellenőrizd és mentsd a termékmegfeleltetéseket."}
              </span>
            </span>
          </div>
        )}

        <section className="receipt-lines-section">
          <div className="section-heading receipt-lines-heading">
            <div>
              <p className="section-label">Készletre gyakorolt hatás</p>
              <h2>Termékek és konverziós faktorok</h2>
            </div>
            <span className="vrp-file-hash">
              SHA-256 · {batch.file_hash.slice(0, 12)}
            </span>
          </div>
          <div className="vrp-lines">
            {batch.items.map((item) => (
              <VrpLineEditor
                key={item.id}
                batch={batch}
                item={item}
                products={products}
                disabled={!editable}
              />
            ))}
          </div>
        </section>

        {canOperate && (
          <div className="receipt-approval-bar">
            <div>
              <ShieldCheck aria-hidden="true" />
              <span>
                <strong>
                  {batch.status === "COMPLETED"
                    ? "A riport készletmozgásai könyvelve vannak."
                    : "Egy riport minden tétele egy közös tranzakcióban könyvelődik."}
                </strong>
                <small>Ismételt indítás nem hoz létre dupla mozgást.</small>
              </span>
            </div>
            {batch.status === "COMPLETED" && canAdmin ? (
              <button
                className="secondary-button danger-button"
                onClick={() => setReverseOpen(true)}
              >
                <RotateCcw aria-hidden="true" />
                Visszafordítás
              </button>
            ) : (
              <button
                className="primary-button"
                disabled={
                  !["READY", "SCHEDULED"].includes(batch.status) ||
                  processMutation.isPending
                }
                onClick={() => processMutation.mutate(batch.id)}
              >
                <Play aria-hidden="true" />
                {processMutation.isPending ? "Könyvelés…" : "Import indítása"}
              </button>
            )}
          </div>
        )}
        {processMutation.error && (
          <p className="form-error receipt-confirm-error">
            {processMutation.error.message}
          </p>
        )}

        <Dialog.Root open={reverseOpen} onOpenChange={setReverseOpen}>
          <Dialog.Portal>
            <Dialog.Overlay className="dialog-overlay" />
            <Dialog.Content className="dialog-content compact">
              <div className="dialog-heading">
                <div className="dialog-icon warning">
                  <RotateCcw aria-hidden="true" />
                </div>
                <div>
                  <Dialog.Title>Import visszafordítása</Dialog.Title>
                  <Dialog.Description>
                    Ellenmozgások állítják vissza a könyvelés előtti készletet.
                  </Dialog.Description>
                </div>
                <Dialog.Close className="icon-button" aria-label="Bezárás">
                  <X aria-hidden="true" />
                </Dialog.Close>
              </div>
              <label className="textarea-label">
                Indoklás
                <textarea
                  rows={4}
                  value={reverseReason}
                  onChange={(event) => setReverseReason(event.target.value)}
                />
              </label>
              {reverseMutation.error && (
                <p className="form-error">{reverseMutation.error.message}</p>
              )}
              <div className="dialog-actions">
                <Dialog.Close className="secondary-button">Mégse</Dialog.Close>
                <button
                  className="primary-button"
                  disabled={
                    reverseReason.trim().length < 3 ||
                    reverseMutation.isPending
                  }
                  onClick={() =>
                    reverseMutation.mutate({
                      id: batch.id,
                      reason: reverseReason.trim()
                    })
                  }
                >
                  {reverseMutation.isPending
                    ? "Visszafordítás…"
                    : "Ellenmozgások létrehozása"}
                </button>
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </motion.div>
    );
  }

  return (
    <motion.div
      className="vrp-imports-page"
      initial={{ opacity: 0, y: 9 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <header className="workspace-header">
        <div>
          <p className="eyebrow">VRP2 értékesítési riportok</p>
          <h1>VRP-importok</h1>
        </div>
        <div className="header-actions always-visible">
          <button className="secondary-button" onClick={onOpenReviews}>
            <AlertTriangle aria-hidden="true" />
            Ellenőrzési sor
            {metrics.review > 0 && (
              <span className="button-count">{metrics.review}</span>
            )}
          </button>
          {canOperate && (
            <button className="primary-button" onClick={() => setUploadOpen(true)}>
              <UploadCloud aria-hidden="true" />
              Riport feltöltése
            </button>
          )}
        </div>
      </header>

      <section className="document-summary vrp-summary">
        <div>
          <span>Összes import</span>
          <strong>{metrics.total}</strong>
          <small>naplózott riport</small>
        </div>
        <div className={metrics.review ? "attention" : ""}>
          <span>Ellenőrzendő</span>
          <strong>{metrics.review}</strong>
          <small>kézi döntést kér</small>
        </div>
        <div>
          <span>Ütemezve</span>
          <strong>{metrics.scheduled}</strong>
          <small>következő futásra</small>
        </div>
        <div>
          <span>Könyvelve</span>
          <strong>{metrics.completed}</strong>
          <small>aktív import</small>
        </div>
      </section>

      <section className="vrp-schedule-band">
        <div className="vrp-schedule-icon">
          <CalendarClock aria-hidden="true" />
        </div>
        <div>
          <span>Feldolgozási rend</span>
          <strong>
            {scheduleQuery.data
              ? frequencyLabels[scheduleQuery.data.frequency]
              : "Betöltés…"}
            {scheduleQuery.data?.frequency === "WEEKLY"
              ? ` · ${weekdayLabels[scheduleQuery.data.weekly_day]}`
              : ""}
            {scheduleQuery.data?.frequency === "MONTHLY"
              ? ` · ${
                  scheduleQuery.data.monthly_rule === "LAST_DAY"
                    ? "utolsó nap"
                    : `${scheduleQuery.data.monthly_rule}. nap`
                }`
              : ""}
          </strong>
        </div>
        <div>
          <span>Következő automatikus futás</span>
          <strong>{formatDateTime(scheduleQuery.data?.next_run_at ?? null)}</strong>
        </div>
        <div className="vrp-schedule-state">
          <span
            className={`status-dot ${
              scheduleQuery.data?.auto_process ? "" : "warning"
            }`}
          >
            {scheduleQuery.data?.auto_process ? "Automatikus" : "Kézi"}
          </span>
          {canAdmin && scheduleQuery.data && (
            <button
              className="text-button"
              onClick={() => setScheduleOpen(true)}
            >
              <Settings2 aria-hidden="true" />
              Szabályok
            </button>
          )}
        </div>
      </section>

      <section className="vrp-list-section">
        <div className="section-heading">
          <div>
            <p className="section-label">Ellenőrizhető előzmények</p>
            <h2>Feltöltött riportok</h2>
          </div>
        </div>
        {importsQuery.isLoading && (
          <div className="empty-state">VRP-importok betöltése…</div>
        )}
        {importsQuery.isError && (
          <div className="empty-state error-state">
            <AlertTriangle aria-hidden="true" />
            A VRP-importlista nem érhető el.
          </div>
        )}
        {!importsQuery.isLoading &&
          !importsQuery.isError &&
          imports.length === 0 && (
            <div className="empty-state">
              <FileSpreadsheet aria-hidden="true" />
              <strong>Még nincs feltöltött VRP-riport.</strong>
              <span>
                A Report predaja CSV, XLSX vagy szöveges PDF exportjával
                kezdheted.
              </span>
            </div>
          )}
        <div className="vrp-import-list">
          {imports.map((item, index) => (
            <motion.button
              key={item.id}
              className="vrp-import-row"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(index * 0.035, 0.25) }}
              onClick={() => setSelectedId(item.id)}
            >
              <span className="file-glyph">
                <FileSpreadsheet aria-hidden="true" />
              </span>
              <span className="vrp-import-name">
                <strong>{item.original_filename}</strong>
                <small>
                  {item.period_start} – {item.period_end} · {item.items.length} tétel
                </small>
              </span>
              <span>
                <small>Feltöltve</small>
                <strong>{formatDateTime(item.created_at)}</strong>
              </span>
              <span className={`vrp-status ${item.status.toLowerCase()}`}>
                {statusLabels[item.status] ?? item.status}
              </span>
            </motion.button>
          ))}
        </div>
      </section>

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={(uploaded) => {
          queryClient.setQueryData(["vrp-import", uploaded.id], uploaded);
          void invalidate(uploaded);
          setSelectedId(uploaded.id);
        }}
      />
      {scheduleOpen && scheduleQuery.data && (
        <ScheduleDialog
          key={scheduleQuery.data.updated_at}
          schedule={scheduleQuery.data}
          open={scheduleOpen}
          onOpenChange={setScheduleOpen}
        />
      )}
    </motion.div>
  );
}
