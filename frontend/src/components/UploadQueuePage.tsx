import {
  ChangeEvent,
  DragEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  CloudUpload,
  FileText,
  FileSpreadsheet,
  Pause,
  Play,
  RefreshCw,
  Trash2,
  Wifi,
  WifiOff,
  X
} from "lucide-react";

import {
  cancelResumableUpload,
  completeResumableUpload,
  createResumableUpload,
  uploadResumableChunk
} from "../lib/api";
import {
  listLocalUploads,
  localUploadProgress,
  removeLocalUpload,
  saveLocalUpload,
  sha256Hex
} from "../lib/offlineUploads";
import type {
  LocalResumableUpload,
  LocalUploadTarget
} from "../lib/offlineUploads";

type Props = {
  organizationId: string;
  permissions: string[];
  onOpenResult: (upload: LocalResumableUpload) => void;
};

const statusLabels: Record<LocalResumableUpload["status"], string> = {
  QUEUED: "Várakozik",
  PREPARING: "Ellenőrzőösszeg",
  UPLOADING: "Feltöltés",
  PAUSED: "Szünetel",
  FAILED: "Újrapróbálható",
  COMPLETED: "Elkészült",
  CANCELLED: "Megszakítva"
};

const byteFormatter = new Intl.NumberFormat("hu-HU", {
  maximumFractionDigits: 1
});

function formatBytes(value: number): string {
  if (value < 1024 * 1024) {
    return `${byteFormatter.format(value / 1024)} KB`;
  }
  return `${byteFormatter.format(value / (1024 * 1024))} MB`;
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function UploadQueuePage({
  organizationId,
  permissions,
  onOpenResult
}: Props) {
  const [uploads, setUploads] = useState<LocalResumableUpload[]>([]);
  const [online, setOnline] = useState(navigator.onLine);
  const [targetType, setTargetType] = useState<LocalUploadTarget>("DOCUMENT");
  const [file, setFile] = useState<File | null>(null);
  const [documentType, setDocumentType] = useState("goods_receipt");
  const [periodStart, setPeriodStart] = useState(today());
  const [periodEnd, setPeriodEnd] = useState(today());
  const [externalReportId, setExternalReportId] = useState("");
  const [dragging, setDragging] = useState(false);
  const [formError, setFormError] = useState("");
  const [queueMessage, setQueueMessage] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const syncing = useRef(false);
  const pauseRequested = useRef(new Set<string>());

  const canDocument = permissions.includes("documents.upload");
  const canVrp = permissions.includes("vrp.upload");

  const refreshQueue = useCallback(async () => {
    setUploads(await listLocalUploads(organizationId));
  }, [organizationId]);

  useEffect(() => {
    let cancelled = false;
    void listLocalUploads(organizationId).then((items) => {
      if (!cancelled) {
        setUploads(items);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [organizationId]);

  useEffect(() => {
    const connected = () => setOnline(true);
    const disconnected = () => setOnline(false);
    window.addEventListener("online", connected);
    window.addEventListener("offline", disconnected);
    return () => {
      window.removeEventListener("online", connected);
      window.removeEventListener("offline", disconnected);
    };
  }, []);

  const syncOne = useCallback(
    async (initial: LocalResumableUpload) => {
      if (pauseRequested.current.has(initial.id)) return;
      let current: LocalResumableUpload = {
        ...initial,
        status: "PREPARING",
        last_error: null,
        updated_at: new Date().toISOString()
      };
      await saveLocalUpload(current);
      await refreshQueue();

      const fileSha256 = current.file_sha256 ?? (await sha256Hex(current.file));
      current = { ...current, file_sha256: fileSha256 };
      let serverUploadId = current.server_upload_id;
      let receivedChunks = current.received_chunks;
      let chunkSize = current.chunk_size;
      let totalChunks = current.total_chunks;

      if (!serverUploadId) {
        const server = await createResumableUpload({
          client_upload_id: current.id,
          target_type: current.target_type,
          filename: current.filename,
          declared_content_type: current.content_type || null,
          total_size: current.size_bytes,
          file_sha256: fileSha256,
          metadata: current.metadata
        });
        serverUploadId = server.id;
        receivedChunks = server.received_chunks;
        chunkSize = server.chunk_size;
        totalChunks = server.total_chunks;
      }
      if (!chunkSize || !totalChunks || !serverUploadId) {
        throw new Error("A szerver nem adott vissza érvényes darabolási tervet.");
      }

      current = {
        ...current,
        server_upload_id: serverUploadId,
        received_chunks: receivedChunks,
        chunk_size: chunkSize,
        total_chunks: totalChunks,
        status: "UPLOADING",
        progress: localUploadProgress(receivedChunks, totalChunks),
        updated_at: new Date().toISOString()
      };
      await saveLocalUpload(current);
      await refreshQueue();

      for (let index = 0; index < totalChunks; index += 1) {
        if (receivedChunks.includes(index)) continue;
        if (pauseRequested.current.has(current.id) || !navigator.onLine) {
          current = {
            ...current,
            status: "PAUSED",
            updated_at: new Date().toISOString()
          };
          await saveLocalUpload(current);
          await refreshQueue();
          return;
        }
        const start = index * chunkSize;
        const chunk = current.file.slice(
          start,
          Math.min(start + chunkSize, current.size_bytes)
        );
        const chunkHash = await sha256Hex(chunk);
        const server = await uploadResumableChunk(
          serverUploadId,
          index,
          chunk,
          chunkHash
        );
        receivedChunks = server.received_chunks;
        current = {
          ...current,
          received_chunks: receivedChunks,
          progress: localUploadProgress(receivedChunks, totalChunks),
          status: "UPLOADING",
          updated_at: new Date().toISOString()
        };
        await saveLocalUpload(current);
        await refreshQueue();
      }

      const result = await completeResumableUpload(serverUploadId, fileSha256);
      current = {
        ...current,
        status: "COMPLETED",
        progress: 100,
        result_entity_type: result.entity_type,
        result_entity_id: result.entity_id,
        last_error: null,
        updated_at: new Date().toISOString()
      };
      await saveLocalUpload(current);
      await refreshQueue();
    },
    [refreshQueue]
  );

  const syncAll = useCallback(async () => {
    if (!navigator.onLine || syncing.current) return;
    syncing.current = true;
    try {
      const currentUploads = await listLocalUploads(organizationId);
      for (const upload of currentUploads) {
        if (
          ["PAUSED", "COMPLETED", "CANCELLED"].includes(upload.status) ||
          pauseRequested.current.has(upload.id)
        ) {
          continue;
        }
        try {
          await syncOne(upload);
        } catch (error) {
          const latest =
            (await listLocalUploads(organizationId)).find(
              (item) => item.id === upload.id
            ) ?? upload;
          const failed: LocalResumableUpload = {
            ...latest,
            status: "FAILED",
            attempts: latest.attempts + 1,
            last_error:
              error instanceof Error ? error.message : "A feltöltés sikertelen.",
            updated_at: new Date().toISOString()
          };
          await saveLocalUpload(failed);
          await refreshQueue();
        }
      }
    } finally {
      syncing.current = false;
    }
  }, [organizationId, refreshQueue, syncOne]);

  useEffect(() => {
    if (online) void syncAll();
  }, [online, syncAll]);

  const stats = useMemo(
    () => ({
      pending: uploads.filter((upload) =>
        ["QUEUED", "PREPARING", "UPLOADING", "PAUSED", "FAILED"].includes(
          upload.status
        )
      ).length,
      completed: uploads.filter((upload) => upload.status === "COMPLETED")
        .length,
      bytes: uploads
        .filter((upload) => upload.status !== "CANCELLED")
        .reduce((sum, upload) => sum + upload.size_bytes, 0)
    }),
    [uploads]
  );

  function selectFile(selected?: File) {
    if (!selected) return;
    setFile(selected);
    setFormError("");
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0]);
  }

  function onDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files?.[0]);
  }

  async function addToQueue() {
    setFormError("");
    setQueueMessage("");
    if (!file) {
      setFormError("Válassz ki egy fájlt.");
      return;
    }
    if (targetType === "VRP" && (!periodStart || !periodEnd)) {
      setFormError("A VRP időszak kezdete és vége kötelező.");
      return;
    }
    const allowed = targetType === "DOCUMENT" ? canDocument : canVrp;
    if (!allowed) {
      setFormError("Ehhez a feltöltési típushoz nincs jogosultságod.");
      return;
    }
    const timestamp = new Date().toISOString();
    const upload: LocalResumableUpload = {
      id: crypto.randomUUID(),
      organization_id: organizationId,
      target_type: targetType,
      filename: file.name,
      content_type: file.type || "application/octet-stream",
      size_bytes: file.size,
      file,
      file_sha256: null,
      metadata:
        targetType === "DOCUMENT"
          ? { document_type: documentType }
          : {
              period_start: periodStart,
              period_end: periodEnd,
              external_report_id: externalReportId || null
            },
      server_upload_id: null,
      received_chunks: [],
      chunk_size: null,
      total_chunks: null,
      status: "QUEUED",
      progress: 0,
      attempts: 0,
      last_error: null,
      result_entity_type: null,
      result_entity_id: null,
      created_at: timestamp,
      updated_at: timestamp
    };
    await saveLocalUpload(upload);
    setFile(null);
    if (fileInput.current) fileInput.current.value = "";
    setExternalReportId("");
    setQueueMessage(
      navigator.onLine
        ? "A fájl bekerült a sorba, a feltöltés elindult."
        : "A fájl helyben elmentve; kapcsolódáskor automatikusan elindul."
    );
    await refreshQueue();
    void syncAll();
  }

  async function togglePause(upload: LocalResumableUpload) {
    if (upload.status === "PAUSED" || upload.status === "FAILED") {
      pauseRequested.current.delete(upload.id);
      await saveLocalUpload({
        ...upload,
        status: "QUEUED",
        last_error: null,
        updated_at: new Date().toISOString()
      });
      await refreshQueue();
      void syncAll();
      return;
    }
    pauseRequested.current.add(upload.id);
    await saveLocalUpload({
      ...upload,
      status: "PAUSED",
      updated_at: new Date().toISOString()
    });
    await refreshQueue();
  }

  async function cancel(upload: LocalResumableUpload) {
    pauseRequested.current.add(upload.id);
    if (navigator.onLine && upload.server_upload_id) {
      await cancelResumableUpload(upload.server_upload_id).catch(() => undefined);
    }
    await saveLocalUpload({
      ...upload,
      status: "CANCELLED",
      last_error: null,
      updated_at: new Date().toISOString()
    });
    await refreshQueue();
  }

  async function remove(upload: LocalResumableUpload) {
    await removeLocalUpload(upload.id);
    pauseRequested.current.delete(upload.id);
    setQueueMessage("");
    await refreshQueue();
  }

  return (
    <motion.div
      className="upload-queue-page"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <header className="workspace-header upload-queue-header">
        <div>
          <p className="eyebrow">Offline fájlátadás</p>
          <h1>Feltöltési sor</h1>
          <p className="page-lead">
            A dokumentum és VRP-fájl a készüléken vár, darabonként folytatható,
            és csak a teljes fájl után kerül feldolgozásra.
          </p>
        </div>
        <span className={`connectivity-badge ${online ? "" : "offline"}`}>
          {online ? <Wifi aria-hidden="true" /> : <WifiOff aria-hidden="true" />}
          {online ? "Online szinkron" : "Offline várólista"}
        </span>
      </header>

      <section className="upload-metrics" aria-label="Feltöltési mutatók">
        <div>
          <span>Függőben</span>
          <strong>{stats.pending}</strong>
        </div>
        <div>
          <span>Elkészült</span>
          <strong>{stats.completed}</strong>
        </div>
        <div>
          <span>Helyi fájlméret</span>
          <strong>{formatBytes(stats.bytes)}</strong>
        </div>
      </section>

      <section className="upload-composer">
        <div className="upload-composer-copy">
          <p className="section-label">Új fájl</p>
          <h2>Mit szeretnél sorba állítani?</h2>
          <p>
            A böngésző bezárása után is megmarad. A küldés szüneteltethető,
            majd ugyanattól a fájldarabtól folytatható.
          </p>
        </div>
        <div className="upload-composer-form">
          <div className="upload-target-switch" aria-label="Feltöltés típusa">
            <button
              className={targetType === "DOCUMENT" ? "active" : ""}
              onClick={() => setTargetType("DOCUMENT")}
              disabled={!canDocument}
            >
              <FileText aria-hidden="true" />
              Dokumentum
            </button>
            <button
              className={targetType === "VRP" ? "active" : ""}
              onClick={() => setTargetType("VRP")}
              disabled={!canVrp}
            >
              <FileSpreadsheet aria-hidden="true" />
              VRP-riport
            </button>
          </div>

          <button
            type="button"
            className={`upload-dropzone compact ${dragging ? "dragging" : ""}`}
            onClick={() => fileInput.current?.click()}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <CloudUpload aria-hidden="true" />
            {file ? (
              <span>
                <strong>{file.name}</strong>
                <small>{formatBytes(file.size)}</small>
              </span>
            ) : (
              <span>
                <strong>Fájl kiválasztása</strong>
                <small>vagy húzd ide</small>
              </span>
            )}
          </button>
          <input
            ref={fileInput}
            className="sr-only"
            type="file"
            accept={
              targetType === "DOCUMENT"
                ? ".pdf,.jpg,.jpeg,.png,.tif,.tiff"
                : ".csv,.xlsx"
            }
            onChange={onFileChange}
          />

          {targetType === "DOCUMENT" ? (
            <label>
              Dokumentumtípus
              <select
                value={documentType}
                onChange={(event) => setDocumentType(event.target.value)}
              >
                <option value="goods_receipt">Bejövő bizonylat</option>
                <option value="delivery_note">Szállítólevél</option>
                <option value="inventory_attachment">Leltármelléklet</option>
              </select>
            </label>
          ) : (
            <div className="upload-period-fields">
              <label>
                <CalendarDays aria-hidden="true" />
                Időszak kezdete
                <input
                  type="date"
                  value={periodStart}
                  onChange={(event) => setPeriodStart(event.target.value)}
                />
              </label>
              <label>
                <CalendarDays aria-hidden="true" />
                Időszak vége
                <input
                  type="date"
                  value={periodEnd}
                  onChange={(event) => setPeriodEnd(event.target.value)}
                />
              </label>
              <label className="wide">
                Külső riportazonosító
                <input
                  value={externalReportId}
                  onChange={(event) => setExternalReportId(event.target.value)}
                  placeholder="Opcionális"
                />
              </label>
            </div>
          )}

          {formError && <p className="form-error">{formError}</p>}
          {queueMessage && <p className="form-success">{queueMessage}</p>}
          <button className="primary-button" type="button" onClick={addToQueue}>
            <CloudUpload aria-hidden="true" />
            Hozzáadás a sorhoz
          </button>
        </div>
      </section>

      <section className="upload-list-section">
        <div className="section-heading">
          <div>
            <p className="section-label">Helyi és szerveroldali állapot</p>
            <h2>Fájlok</h2>
          </div>
          <button
            className="secondary-button"
            onClick={() => void syncAll()}
            disabled={!online || stats.pending === 0}
          >
            <RefreshCw aria-hidden="true" />
            Szinkronizálás
          </button>
        </div>

        {uploads.length === 0 ? (
          <div className="empty-state upload-empty">
            <CloudUpload aria-hidden="true" />
            <strong>A feltöltési sor üres.</strong>
            <span>Az első fájlt a fenti területen adhatod hozzá.</span>
          </div>
        ) : (
          <div className="upload-list">
            {uploads.map((upload) => {
              const active = ["PREPARING", "UPLOADING"].includes(upload.status);
              const retryable = ["PAUSED", "FAILED"].includes(upload.status);
              return (
                <motion.article
                  layout
                  key={upload.id}
                  className={`upload-row ${upload.status.toLowerCase()}`}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                >
                  <div className="upload-file-icon">
                    {upload.target_type === "DOCUMENT" ? (
                      <FileText aria-hidden="true" />
                    ) : (
                      <FileSpreadsheet aria-hidden="true" />
                    )}
                  </div>
                  <div className="upload-row-main">
                    <div className="upload-row-title">
                      <div>
                        <strong>{upload.filename}</strong>
                        <span>
                          {upload.target_type === "DOCUMENT"
                            ? "Dokumentum"
                            : "VRP-riport"}{" "}
                          · {formatBytes(upload.size_bytes)}
                        </span>
                      </div>
                      <span className={`upload-status ${upload.status.toLowerCase()}`}>
                        {upload.status === "COMPLETED" && (
                          <CheckCircle2 aria-hidden="true" />
                        )}
                        {upload.status === "FAILED" && (
                          <AlertTriangle aria-hidden="true" />
                        )}
                        {statusLabels[upload.status]}
                      </span>
                    </div>
                    <div className="upload-progress-track" aria-label={`${upload.progress}%`}>
                      <motion.span
                        initial={false}
                        animate={{ width: `${upload.progress}%` }}
                      />
                    </div>
                    <div className="upload-row-meta">
                      <span>{upload.progress}%</span>
                      {upload.total_chunks && (
                        <span>
                          {upload.received_chunks.length}/{upload.total_chunks} darab
                        </span>
                      )}
                      {upload.last_error && (
                        <span className="error-copy">{upload.last_error}</span>
                      )}
                    </div>
                  </div>
                  <div className="upload-row-actions">
                    {upload.status === "COMPLETED" && (
                      <button
                        className="text-button"
                        onClick={() => onOpenResult(upload)}
                      >
                        Megnyitás
                      </button>
                    )}
                    {(active || upload.status === "QUEUED") && (
                      <button
                        className="icon-button"
                        title="Szüneteltetés"
                        onClick={() => void togglePause(upload)}
                      >
                        <Pause aria-hidden="true" />
                      </button>
                    )}
                    {retryable && (
                      <button
                        className="icon-button"
                        title="Folytatás"
                        onClick={() => void togglePause(upload)}
                      >
                        <Play aria-hidden="true" />
                      </button>
                    )}
                    {!["COMPLETED", "CANCELLED"].includes(upload.status) && (
                      <button
                        className="icon-button danger"
                        title="Megszakítás"
                        onClick={() => void cancel(upload)}
                      >
                        <X aria-hidden="true" />
                      </button>
                    )}
                    {["COMPLETED", "CANCELLED"].includes(upload.status) && (
                      <button
                        className="icon-button"
                        title="Eltávolítás a helyi listából"
                        onClick={() => void remove(upload)}
                      >
                        <Trash2 aria-hidden="true" />
                      </button>
                    )}
                  </div>
                </motion.article>
              );
            })}
          </div>
        )}
      </section>
    </motion.div>
  );
}
