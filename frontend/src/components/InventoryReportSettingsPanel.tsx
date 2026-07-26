import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  CheckCircle2,
  Clock3,
  Download,
  FileText,
  Play,
  Save,
  Sparkles
} from "lucide-react";

import {
  generateInventoryReport,
  getInventoryReportSchedule,
  updateInventoryReportSchedule
} from "../lib/api";
import type {
  InventoryReportSchedule,
  InventoryReportScheduleUpdate
} from "../types";

type Props = {
  canWrite: boolean;
  canGenerate: boolean;
  onOpenDocuments: () => void;
};

const frequencyLabels: Record<InventoryReportSchedule["frequency"], string> = {
  DAILY: "Naponta",
  WEEKLY: "Hetente",
  MONTHLY: "Havonta"
};

const weekdayOptions = [
  ["MONDAY", "Hétfő"],
  ["TUESDAY", "Kedd"],
  ["WEDNESDAY", "Szerda"],
  ["THURSDAY", "Csütörtök"],
  ["FRIDAY", "Péntek"],
  ["SATURDAY", "Szombat"],
  ["SUNDAY", "Vasárnap"]
];

function formatDate(value: string | null): string {
  if (!value) return "Még nem futott";
  return new Intl.DateTimeFormat("hu-HU", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function scheduleForm(
  schedule: InventoryReportSchedule
): InventoryReportScheduleUpdate {
  return {
    enabled: schedule.enabled,
    frequency: schedule.frequency,
    generation_time: schedule.generation_time.slice(0, 5),
    timezone: schedule.timezone,
    weekly_day: schedule.weekly_day,
    monthly_rule: schedule.monthly_rule
  };
}

const defaultForm: InventoryReportScheduleUpdate = {
  enabled: false,
  frequency: "WEEKLY",
  generation_time: "06:00",
  timezone: "Europe/Bratislava",
  weekly_day: "MONDAY",
  monthly_rule: "LAST_DAY"
};

export default function InventoryReportSettingsPanel({
  canWrite,
  canGenerate,
  onOpenDocuments
}: Props) {
  const queryClient = useQueryClient();
  const [formDraft, setFormDraft] =
    useState<InventoryReportScheduleUpdate | null>(null);
  const [feedback, setFeedback] = useState("");
  const [generatedDocumentId, setGeneratedDocumentId] = useState<string | null>(
    null
  );

  const query = useQuery({
    queryKey: ["inventory-report-schedule"],
    queryFn: getInventoryReportSchedule
  });
  const schedule = query.data;
  const form = formDraft ?? (schedule ? scheduleForm(schedule) : defaultForm);
  const patchForm = (patch: Partial<InventoryReportScheduleUpdate>) =>
    setFormDraft((current) => ({ ...(current ?? form), ...patch }));

  const updateMutation = useMutation({
    mutationFn: updateInventoryReportSchedule,
    onSuccess: (schedule) => {
      queryClient.setQueryData(["inventory-report-schedule"], schedule);
      setFormDraft(scheduleForm(schedule));
      setFeedback(
        schedule.enabled
          ? "Az automatikus PDF-leltár ütemezése elmentve."
          : "Az automatikus PDF-leltár szüneteltetve."
      );
    }
  });
  const generateMutation = useMutation({
    mutationFn: generateInventoryReport,
    onSuccess: (document) => {
      setGeneratedDocumentId(document.id);
      setFeedback("A leltár PDF elkészült és bekerült a Dokumentumok közé.");
      queryClient.invalidateQueries({ queryKey: ["inventory-report-schedule"] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    }
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedback("");
    setGeneratedDocumentId(null);
    updateMutation.mutate({
      ...form,
      generation_time: form.generation_time.length === 5
        ? `${form.generation_time}:00`
        : form.generation_time
    });
  }

  const mutationError = updateMutation.error ?? generateMutation.error;

  return (
    <section
      className="inventory-report-settings"
      aria-labelledby="inventory-report-settings-title"
    >
      <div className="section-heading inventory-report-settings-heading">
        <div>
          <p className="section-label">Automatikus jelentések</p>
          <h2 id="inventory-report-settings-title">AI-leltár PDF-ben</h2>
        </div>
        <span
          className={`report-schedule-status ${schedule?.enabled ? "active" : ""}`}
          role="status"
        >
          {schedule?.enabled ? (
            <CheckCircle2 aria-hidden="true" />
          ) : (
            <Clock3 aria-hidden="true" />
          )}
          {schedule?.enabled ? "Automatika aktív" : "Automatika szünetel"}
        </span>
      </div>

      {query.isPending ? (
        <div className="report-settings-loading">Leltárütemezés betöltése…</div>
      ) : null}
      {query.error ? (
        <div className="report-settings-loading error-state">
          <span>{query.error.message}</span>
          <button className="secondary-button" onClick={() => query.refetch()}>
            Újrapróbálás
          </button>
        </div>
      ) : null}

      {schedule ? (
        <div className="inventory-report-panel">
          <div className="report-schedule-summary">
            <div className="report-summary-identity">
              <span className="report-summary-icon">
                <Sparkles aria-hidden="true" />
              </span>
              <span>
                <small>Gyakoriság</small>
                <strong>{frequencyLabels[schedule.frequency]}</strong>
                <em>{schedule.enabled ? "Automatikus generálás" : "Szüneteltetve"}</em>
              </span>
            </div>
            <div>
              <small>Következő PDF</small>
              <strong>
                {schedule.enabled
                  ? formatDate(schedule.next_run_at)
                  : "Nincs ütemezve"}
              </strong>
              <em>{schedule.timezone}</em>
            </div>
            <div>
              <small>Legutóbbi leltár</small>
              <strong>{formatDate(schedule.last_run_at)}</strong>
              <em>
                {schedule.last_document_id
                  ? "A Dokumentumok között letölthető"
                  : "Még nincs generált PDF"}
              </em>
            </div>
          </div>

          {canWrite ? (
            <form className="report-schedule-form" onSubmit={submit}>
              <div className="report-schedule-intro">
                <CalendarClock aria-hidden="true" />
                <span>
                  <strong>Automatikus készletpillanatkép</strong>
                  <small>
                    A rendszer a választott időpontban ellenőrzi a készletet,
                    PDF-et készít, majd a Dokumentumok közé helyezi.
                  </small>
                </span>
              </div>

              <label className="report-enabled-toggle">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(event) => patchForm({ enabled: event.target.checked })}
                />
                <span aria-hidden="true" />
                <span>
                  <strong>Automatikus leltár</strong>
                  <small>
                    {form.enabled
                      ? "A következő futás mentés után ütemezve lesz."
                      : "A kézi PDF-generálás továbbra is elérhető."}
                  </small>
                </span>
              </label>

              <div className="report-schedule-fields">
                <label>
                  <span>Gyakoriság</span>
                  <select
                    value={form.frequency}
                    onChange={(event) =>
                      patchForm({
                        frequency: event.target
                          .value as InventoryReportSchedule["frequency"]
                      })
                    }
                  >
                    <option value="DAILY">Naponta</option>
                    <option value="WEEKLY">Hetente</option>
                    <option value="MONTHLY">Havonta</option>
                  </select>
                </label>
                <label>
                  <span>Generálás ideje</span>
                  <input
                    type="time"
                    value={form.generation_time.slice(0, 5)}
                    onChange={(event) =>
                      patchForm({ generation_time: event.target.value })
                    }
                    required
                  />
                </label>
                {form.frequency === "WEEKLY" ? (
                  <label>
                    <span>Heti nap</span>
                    <select
                      value={form.weekly_day}
                      onChange={(event) =>
                        patchForm({ weekly_day: event.target.value })
                      }
                    >
                      {weekdayOptions.map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                {form.frequency === "MONTHLY" ? (
                  <label>
                    <span>Havi nap</span>
                    <select
                      value={form.monthly_rule}
                      onChange={(event) =>
                        patchForm({ monthly_rule: event.target.value })
                      }
                    >
                      <option value="LAST_DAY">A hónap utolsó napja</option>
                      {Array.from({ length: 28 }, (_, index) => index + 1).map(
                        (day) => (
                          <option key={day} value={String(day)}>
                            {day}. nap
                          </option>
                        )
                      )}
                    </select>
                  </label>
                ) : null}
              </div>

              {schedule.last_error_message ? (
                <p className="report-schedule-feedback error">
                  Legutóbbi automatikus futási hiba: {schedule.last_error_message}
                </p>
              ) : null}
              {feedback ? (
                <p className="report-schedule-feedback success">
                  <CheckCircle2 aria-hidden="true" />
                  {feedback}
                </p>
              ) : null}
              {mutationError ? (
                <p className="report-schedule-feedback error">
                  {mutationError.message}
                </p>
              ) : null}

              <div className="report-schedule-actions">
                {(generatedDocumentId || schedule.last_document_id) ? (
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={onOpenDocuments}
                  >
                    <Download aria-hidden="true" />
                    Dokumentumok megnyitása
                  </button>
                ) : null}
                {canGenerate ? (
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={generateMutation.isPending}
                    onClick={() => {
                      setFeedback("");
                      generateMutation.mutate();
                    }}
                  >
                    {generateMutation.isPending ? (
                      <FileText aria-hidden="true" />
                    ) : (
                      <Play aria-hidden="true" />
                    )}
                    {generateMutation.isPending
                      ? "PDF készítése…"
                      : "PDF készítése most"}
                  </button>
                ) : null}
                <button
                  className="primary-button"
                  type="submit"
                  disabled={updateMutation.isPending}
                >
                  <Save aria-hidden="true" />
                  {updateMutation.isPending ? "Mentés…" : "Ütemezés mentése"}
                </button>
              </div>
            </form>
          ) : (
            <div className="report-settings-readonly">
              <CalendarClock aria-hidden="true" />
              Az ütemezés megtekinthető, módosításához beállítás- és
              riportkezelési jogosultság szükséges.
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
