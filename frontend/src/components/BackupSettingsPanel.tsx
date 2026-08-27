import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Archive,
  CalendarClock,
  CheckCircle2,
  Clock3,
  DatabaseBackup,
  Download,
  Play,
  Save,
  Upload
} from "lucide-react";

import {
  downloadBackup,
  generateBackup,
  getBackupSchedule,
  restoreBackup,
  updateBackupSchedule
} from "../lib/api";
import type { BackupSchedule, BackupScheduleUpdate } from "../types";

type Props = {
  canWrite: boolean;
  canRestore: boolean;
};

const frequencyLabels: Record<BackupSchedule["frequency"], string> = {
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

function formatSize(value: number | null): string {
  if (value === null) return "Nincs mentés";
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function scheduleForm(schedule: BackupSchedule): BackupScheduleUpdate {
  return {
    enabled: schedule.enabled,
    frequency: schedule.frequency,
    backup_time: schedule.backup_time.slice(0, 5),
    timezone: schedule.timezone,
    weekly_day: schedule.weekly_day,
    monthly_rule: schedule.monthly_rule
  };
}

const defaultForm: BackupScheduleUpdate = {
  enabled: false,
  frequency: "WEEKLY",
  backup_time: "02:00",
  timezone: "Europe/Bratislava",
  weekly_day: "SUNDAY",
  monthly_rule: "LAST_DAY"
};

export default function BackupSettingsPanel({ canWrite, canRestore }: Props) {
  const queryClient = useQueryClient();
  const [formDraft, setFormDraft] =
    useState<BackupScheduleUpdate | null>(null);
  const [feedback, setFeedback] = useState("");
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [restoreConfirmation, setRestoreConfirmation] = useState("");
  const [restoreAcknowledged, setRestoreAcknowledged] = useState(false);
  const [restoreFeedback, setRestoreFeedback] = useState("");

  const query = useQuery({
    queryKey: ["backup-schedule"],
    queryFn: getBackupSchedule
  });
  const schedule = query.data;
  const form = formDraft ?? (schedule ? scheduleForm(schedule) : defaultForm);
  const patchForm = (patch: Partial<BackupScheduleUpdate>) =>
    setFormDraft((current) => ({ ...(current ?? form), ...patch }));

  const updateMutation = useMutation({
    mutationFn: updateBackupSchedule,
    onSuccess: (updated) => {
      queryClient.setQueryData(["backup-schedule"], updated);
      setFormDraft(scheduleForm(updated));
      setFeedback(
        updated.enabled
          ? "Az automatikus biztonsági mentés ütemezése elmentve."
          : "Az automatikus mentés szüneteltetve."
      );
    }
  });
  const generateMutation = useMutation({
    mutationFn: generateBackup,
    onSuccess: (updated) => {
      queryClient.setQueryData(["backup-schedule"], updated);
      setFeedback(
        "A mentés elkészült. A korábbi mentést felülírta, és letölthető."
      );
    }
  });
  const downloadMutation = useMutation({
    mutationFn: downloadBackup,
    onSuccess: () => setFeedback("A biztonsági mentés letöltése elindult.")
  });
  const restoreMutation = useMutation({
    mutationFn: restoreBackup,
    onSuccess: async (result) => {
      await queryClient.invalidateQueries();
      setRestoreFile(null);
      setRestoreConfirmation("");
      setRestoreAcknowledged(false);
      setRestoreFeedback(
        `A visszaállítás elkészült: ${result.restored_rows} rekord és ${result.restored_files} fájl állt vissza.`
      );
    }
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedback("");
    updateMutation.mutate({
      ...form,
      backup_time:
        form.backup_time.length === 5
          ? `${form.backup_time}:00`
          : form.backup_time
    });
  }

  const mutationError =
    updateMutation.error ?? generateMutation.error ?? downloadMutation.error;
  const busy =
    generateMutation.isPending ||
    schedule?.last_status === "QUEUED" ||
    schedule?.last_status === "PROCESSING";
  const restoreConfirmed =
    restoreAcknowledged &&
    restoreFile !== null &&
    restoreConfirmation.trim().toLocaleUpperCase("hu-HU") === "VISSZAÁLLÍTÁS";

  return (
    <section
      className="inventory-report-settings backup-settings"
      aria-labelledby="backup-settings-title"
    >
      <div className="section-heading inventory-report-settings-heading">
        <div>
          <p className="section-label">Adatvédelem és helyreállítás</p>
          <h2 id="backup-settings-title">Biztonsági mentés</h2>
        </div>
        <span
          className={`report-schedule-status ${
            schedule?.backup_available ? "active" : ""
          }`}
          role="status"
        >
          {schedule?.backup_available ? (
            <CheckCircle2 aria-hidden="true" />
          ) : (
            <Clock3 aria-hidden="true" />
          )}
          {schedule?.backup_available ? "Mentés elérhető" : "Még nincs mentés"}
        </span>
      </div>

      {query.isPending ? (
        <div className="report-settings-loading">Mentési beállítások betöltése…</div>
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
                <DatabaseBackup aria-hidden="true" />
              </span>
              <span>
                <small>Gyakoriság</small>
                <strong>{frequencyLabels[schedule.frequency]}</strong>
                <em>{schedule.enabled ? "Automatikus mentés" : "Szüneteltetve"}</em>
              </span>
            </div>
            <div>
              <small>Következő mentés</small>
              <strong>
                {schedule.enabled
                  ? formatDate(schedule.next_run_at)
                  : "Nincs ütemezve"}
              </strong>
              <em>{schedule.timezone}</em>
            </div>
            <div>
              <small>Legutóbbi sikeres mentés</small>
              <strong>{formatDate(schedule.last_run_at)}</strong>
              <em>
                {schedule.backup_available
                  ? `${formatSize(schedule.last_size_bytes)} · ZIP`
                  : "Készítsd el az első mentést"}
              </em>
            </div>
          </div>

          {canWrite ? (
            <form className="report-schedule-form" onSubmit={submit}>
              <div className="report-schedule-intro">
                <Archive aria-hidden="true" />
                <span>
                  <strong>Egyetlen, mindig friss mentés</strong>
                  <small>
                    Az üzleti adatok és feltöltött fájlok ZIP-be kerülnek. Az új
                    sikeres mentés automatikusan felülírja a korábbit.
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
                  <strong>Automatikus biztonsági mentés</strong>
                  <small>
                    {form.enabled
                      ? "A következő mentés az ütemezés szerint elkészül."
                      : "A kézi mentés és letöltés továbbra is használható."}
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
                          .value as BackupSchedule["frequency"]
                      })
                    }
                  >
                    <option value="DAILY">Naponta</option>
                    <option value="WEEKLY">Hetente</option>
                    <option value="MONTHLY">Havonta</option>
                  </select>
                </label>
                <label>
                  <span>Mentés ideje</span>
                  <input
                    type="time"
                    value={form.backup_time.slice(0, 5)}
                    onChange={(event) =>
                      patchForm({ backup_time: event.target.value })
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

              {schedule.last_sha256 ? (
                <p className="report-schedule-feedback">
                  Ellenőrző összeg: {schedule.last_sha256.slice(0, 16)}…
                </p>
              ) : null}
              {schedule.last_error_message ? (
                <p className="report-schedule-feedback error">
                  Legutóbbi mentési hiba: {schedule.last_error_message}
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
                {schedule.backup_available ? (
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={downloadMutation.isPending}
                    onClick={() => {
                      setFeedback("");
                      downloadMutation.mutate();
                    }}
                  >
                    <Download aria-hidden="true" />
                    {downloadMutation.isPending
                      ? "Letöltés…"
                      : "Legutóbbi mentés letöltése"}
                  </button>
                ) : null}
                <button
                  className="secondary-button"
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setFeedback("");
                    generateMutation.mutate();
                  }}
                >
                  {busy ? (
                    <DatabaseBackup aria-hidden="true" />
                  ) : (
                    <Play aria-hidden="true" />
                  )}
                  {busy ? "Mentés készítése…" : "Mentés készítése most"}
                </button>
                <button
                  className="primary-button"
                  type="submit"
                  disabled={updateMutation.isPending || busy}
                >
                  <Save aria-hidden="true" />
                  {updateMutation.isPending ? "Mentés…" : "Ütemezés mentése"}
                </button>
              </div>
            </form>
          ) : (
            <div className="report-settings-readonly">
              <CalendarClock aria-hidden="true" />
              <span>
                A mentés megtekinthető és letölthető, az ütemezés módosításához
                beállításkezelési jogosultság szükséges.
              </span>
              {schedule.backup_available ? (
                <button
                  className="secondary-button"
                  type="button"
                  disabled={downloadMutation.isPending}
                  onClick={() => downloadMutation.mutate()}
                >
                  <Download aria-hidden="true" />
                  Legutóbbi mentés letöltése
                </button>
              ) : null}
            </div>
          )}

          {canRestore ? (
            <div className="backup-restore-zone">
              <div className="backup-restore-heading">
                <AlertTriangle aria-hidden="true" />
                <span>
                  <strong>Adatok visszaállítása ZIP-mentésből</strong>
                  <small>
                    A jelenlegi üzleti adatok helyére a kiválasztott mentés kerül.
                    Előtte a rendszer automatikusan elkészíti és letölthetően
                    megtartja a jelenlegi állapot biztonsági pillanatképét.
                  </small>
                </span>
              </div>

              <label className="backup-restore-file">
                <span>Visszaállítandó ZIP-fájl</span>
                <input
                  type="file"
                  accept=".zip,application/zip"
                  disabled={restoreMutation.isPending}
                  onChange={(event) => {
                    setRestoreFile(event.target.files?.[0] ?? null);
                    setRestoreFeedback("");
                  }}
                />
                <small>
                  {restoreFile
                    ? `${restoreFile.name} · ${formatSize(restoreFile.size)}`
                    : "Válaszd ki az AI Raktárból letöltött biztonsági mentést."}
                </small>
              </label>

              <div className="backup-restore-preserved">
                <strong>Ezek nem változnak meg:</strong>
                <span>
                  felhasználók, jelszavak, szerepkörök, MFA, munkamenetek,
                  API-tokenek, plugin-titkok és AI API-kulcsok
                </span>
              </div>

              <label className="backup-restore-check">
                <input
                  type="checkbox"
                  checked={restoreAcknowledged}
                  onChange={(event) =>
                    setRestoreAcknowledged(event.target.checked)
                  }
                />
                <span>
                  Megértettem, hogy a jelenlegi termék-, készlet-, dokumentum-,
                  leltár- és VRP-adatok lecserélődnek.
                </span>
              </label>

              <label className="backup-restore-confirmation">
                <span>
                  Írd be a megerősítéshez: <strong>VISSZAÁLLÍTÁS</strong>
                </span>
                <input
                  type="text"
                  value={restoreConfirmation}
                  disabled={restoreMutation.isPending}
                  autoComplete="off"
                  onChange={(event) =>
                    setRestoreConfirmation(event.target.value)
                  }
                />
              </label>

              {restoreFeedback ? (
                <p className="report-schedule-feedback success">
                  <CheckCircle2 aria-hidden="true" />
                  {restoreFeedback}
                </p>
              ) : null}
              {restoreMutation.error ? (
                <p className="report-schedule-feedback error">
                  {restoreMutation.error.message}
                </p>
              ) : null}

              <div className="backup-restore-actions">
                <button
                  className="danger-button"
                  type="button"
                  disabled={!restoreConfirmed || restoreMutation.isPending || busy}
                  onClick={() => {
                    if (!restoreFile || !restoreConfirmed) return;
                    setRestoreFeedback("");
                    restoreMutation.mutate(restoreFile);
                  }}
                >
                  <Upload aria-hidden="true" />
                  {restoreMutation.isPending
                    ? "Visszaállítás folyamatban…"
                    : "Mentés visszaállítása"}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
