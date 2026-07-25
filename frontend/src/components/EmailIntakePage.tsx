import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Ban,
  Check,
  CheckCircle2,
  Clipboard,
  Inbox,
  Mail,
  Paperclip,
  RefreshCw,
  Save,
  ShieldCheck,
  Sparkles
} from "lucide-react";

import {
  getEmailSettings,
  getInboundEmails,
  rotateEmailAddress,
  updateEmailSettings
} from "../lib/api";

type Props = {
  role: string;
};

const statusLabels: Record<string, string> = {
  PROCESSING: "Feldolgozás",
  PROCESSED: "Feldolgozva",
  PARTIAL: "Részben feldolgozva",
  REJECTED: "Elutasítva"
};

const attachmentStatusLabels: Record<string, string> = {
  ACCEPTED: "Átvéve",
  DUPLICATE: "Duplikátum",
  REJECTED: "Elutasítva"
};

function formatDateTime(value: string): string {
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

export default function EmailIntakePage({ role }: Props) {
  const queryClient = useQueryClient();
  const canManage = ["admin", "manager"].includes(role);
  const canRotate = role === "admin";
  const [settingsDraft, setSettingsDraft] = useState<{
    enabled: boolean;
    autoProcess: boolean;
    domains: string;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  const settingsQuery = useQuery({
    queryKey: ["email-settings"],
    queryFn: getEmailSettings
  });
  const messagesQuery = useQuery({
    queryKey: ["inbound-emails"],
    queryFn: getInboundEmails,
    refetchInterval: 10000
  });

  const enabled =
    settingsDraft?.enabled ?? settingsQuery.data?.enabled ?? true;
  const autoProcess =
    settingsDraft?.autoProcess ?? settingsQuery.data?.auto_process ?? true;
  const domains =
    settingsDraft?.domains ??
    settingsQuery.data?.allowed_sender_domains.join(", ") ??
    "";
  const updateDraft = (
    next: Partial<NonNullable<typeof settingsDraft>>
  ) =>
    setSettingsDraft({
      enabled,
      autoProcess,
      domains,
      ...next
    });

  const settingsMutation = useMutation({
    mutationFn: () =>
      updateEmailSettings({
        enabled,
        auto_process: autoProcess,
        allowed_sender_domains: domains
          .split(/[,\n;]/)
          .map((domain) => domain.trim())
          .filter(Boolean)
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["email-settings"], updated);
      setSettingsDraft(null);
    }
  });
  const rotateMutation = useMutation({
    mutationFn: rotateEmailAddress,
    onSuccess: (updated) =>
      queryClient.setQueryData(["email-settings"], updated)
  });

  const messages = useMemo(
    () => messagesQuery.data ?? [],
    [messagesQuery.data]
  );
  const metrics = useMemo(
    () => ({
      total: messages.length,
      accepted: messages.reduce(
        (sum, message) => sum + message.accepted_count,
        0
      ),
      duplicates: messages.reduce(
        (sum, message) => sum + message.duplicate_count,
        0
      ),
      attention: messages.filter((message) =>
        ["PARTIAL", "REJECTED"].includes(message.status)
      ).length
    }),
    [messages]
  );

  const copyAddress = async () => {
    const address = settingsQuery.data?.inbound_address;
    if (!address) return;
    await navigator.clipboard.writeText(address);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  const rotateAddress = () => {
    if (
      window.confirm(
        "A jelenlegi bejövő cím azonnal érvénytelenné válik. Biztosan új címet kérsz?"
      )
    ) {
      rotateMutation.mutate();
    }
  };

  return (
    <motion.div
      className="email-page"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32 }}
    >
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Automatikus dokumentumbeérkezés</p>
          <h1>E-mail postafiók</h1>
        </div>
        <div className="email-header-state">
          <span
            className={`status-dot ${
              settingsQuery.data?.enabled ? "" : "warning"
            }`}
          >
            {settingsQuery.data?.enabled ? "Fogadás aktív" : "Fogadás szünetel"}
          </span>
        </div>
      </header>

      <section className="email-address-band" aria-label="Bejövő dokumentumcím">
        <Mail aria-hidden="true" />
        <div>
          <span>Szervezeti dokumentumcím</span>
          {settingsQuery.isLoading ? (
            <strong>Cím betöltése…</strong>
          ) : (
            <strong>{settingsQuery.data?.inbound_address ?? "Nem érhető el"}</strong>
          )}
          <small>
            A PDF- vagy képmellékletek a meglévő biztonsági ellenőrzésbe érkeznek.
          </small>
        </div>
        <div className="email-address-actions">
          <button
            className="secondary-button"
            disabled={!settingsQuery.data}
            onClick={() => void copyAddress()}
          >
            {copied ? <Check aria-hidden="true" /> : <Clipboard aria-hidden="true" />}
            {copied ? "Másolva" : "Cím másolása"}
          </button>
          {canRotate && (
            <button
              className="text-button email-rotate"
              disabled={rotateMutation.isPending}
              onClick={rotateAddress}
            >
              <RefreshCw aria-hidden="true" />
              Új cím
            </button>
          )}
        </div>
      </section>

      <section className="email-summary" aria-label="E-mail feldolgozási összesítés">
        <div>
          <Inbox aria-hidden="true" />
          <span>Üzenet</span>
          <strong>{metrics.total}</strong>
        </div>
        <div>
          <CheckCircle2 aria-hidden="true" />
          <span>Átvett melléklet</span>
          <strong>{metrics.accepted}</strong>
        </div>
        <div>
          <ShieldCheck aria-hidden="true" />
          <span>Kiszűrt duplikátum</span>
          <strong>{metrics.duplicates}</strong>
        </div>
        <div className={metrics.attention ? "attention" : ""}>
          <AlertTriangle aria-hidden="true" />
          <span>Figyelmet kér</span>
          <strong>{metrics.attention}</strong>
        </div>
      </section>

      <section className="email-settings-section">
        <div className="section-heading">
          <div>
            <p className="section-label">Beérkezési szabályok</p>
            <h2>Feldolgozás és biztonság</h2>
          </div>
          {canManage && (
            <button
              className="primary-button"
              disabled={settingsMutation.isPending || settingsQuery.isLoading}
              onClick={() => settingsMutation.mutate()}
            >
              <Save aria-hidden="true" />
              Beállítások mentése
            </button>
          )}
        </div>

        <div className="email-settings-grid">
          <div className="email-control-list">
            <label className="email-toggle-row">
              <input
                type="checkbox"
                checked={enabled}
                disabled={!canManage}
                onChange={(event) =>
                  updateDraft({ enabled: event.target.checked })
                }
              />
              <span>
                <strong>Bejövő cím engedélyezve</strong>
                <small>Kikapcsolva a címre érkező levelek nem kerülnek feldolgozásra.</small>
              </span>
            </label>
            <label className="email-toggle-row">
              <input
                type="checkbox"
                checked={autoProcess}
                disabled={!canManage}
                onChange={(event) =>
                  updateDraft({ autoProcess: event.target.checked })
                }
              />
              <span>
                <strong>Automatikus AI-feldolgozás</strong>
                <small>
                  A biztonságosan átvett bizonylatok azonnal a tartós feldolgozási
                  sorba kerülnek.
                </small>
              </span>
            </label>
            <label className="email-domain-field">
              Engedélyezett feladó domainek
              <input
                value={domains}
                disabled={!canManage}
                placeholder="beszallito.hu, partner.sk"
                onChange={(event) =>
                  updateDraft({ domains: event.target.value })
                }
              />
              <small>Üresen minden érvényes feladói domain elfogadott.</small>
            </label>
          </div>

          <div className="email-security-list">
            <div>
              <ShieldCheck aria-hidden="true" />
              <span>
                <strong>Aláírt webhook</strong>
                <small>
                  {settingsQuery.data?.webhook_configured
                    ? "Konfigurálva, időablakos replay-védelemmel"
                    : "Nincs titok beállítva; a webhook zárva marad"}
                </small>
              </span>
              <b className={settingsQuery.data?.webhook_configured ? "ok" : ""}>
                {settingsQuery.data?.webhook_configured ? "Kész" : "Teendő"}
              </b>
            </div>
            <div>
              <RefreshCw aria-hidden="true" />
              <span>
                <strong>IMAP worker</strong>
                <small>
                  Opcionális tartalék csatorna olvasatlan levelek tartós átvételéhez
                </small>
              </span>
              <b className={settingsQuery.data?.imap_enabled ? "ok" : ""}>
                {settingsQuery.data?.imap_enabled ? "Aktív" : "Kikapcsolva"}
              </b>
            </div>
            <div>
              <Sparkles aria-hidden="true" />
              <span>
                <strong>AI továbbítás</strong>
                <small>Csak ellenőrzött PDF/JPG/PNG/TIFF melléklet kerülhet sorba</small>
              </span>
              <b className={autoProcess ? "ok" : ""}>
                {autoProcess ? "Automatikus" : "Kézi"}
              </b>
            </div>
          </div>
        </div>

        {(settingsQuery.error ||
          settingsMutation.error ||
          rotateMutation.error) && (
          <p className="form-error email-error">
            {settingsMutation.error?.message ||
              rotateMutation.error?.message ||
              settingsQuery.error?.message ||
              "Az e-mail beállítás nem érhető el."}
          </p>
        )}
      </section>

      <section className="email-log-section">
        <div className="section-heading">
          <div>
            <p className="section-label">Beérkezési napló</p>
            <h2>Legutóbbi e-mailek</h2>
          </div>
          <span className="muted-text">10 másodpercenként frissül</span>
        </div>

        {messagesQuery.isLoading && (
          <div className="empty-state">E-mailek betöltése…</div>
        )}
        {messagesQuery.isError && (
          <div className="empty-state error-state">
            <AlertTriangle aria-hidden="true" />
            A beérkezési napló most nem érhető el.
          </div>
        )}
        {!messagesQuery.isLoading &&
          !messagesQuery.isError &&
          messages.length === 0 && (
            <div className="empty-state">
              <Mail aria-hidden="true" />
              <strong>Még nem érkezett e-mail.</strong>
              <span>
                Küldj egy PDF-et vagy bizonylatfotót a szervezeti dokumentumcímre.
              </span>
            </div>
          )}

        {messages.length > 0 && (
          <div className="email-table-wrap">
            <table className="email-table">
              <thead>
                <tr>
                  <th>Levél</th>
                  <th>Mellékletek</th>
                  <th>Állapot</th>
                  <th>Érkezett</th>
                </tr>
              </thead>
              <tbody>
                {messages.map((message, index) => (
                  <motion.tr
                    key={message.id}
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: Math.min(index * 0.025, 0.18) }}
                  >
                    <td>
                      <div className="email-message-cell">
                        <span className="email-glyph">
                          <Mail aria-hidden="true" />
                        </span>
                        <span>
                          <strong>{message.subject || "Tárgy nélküli levél"}</strong>
                          <small>
                            {message.sender} · {message.provider}
                          </small>
                        </span>
                      </div>
                    </td>
                    <td>
                      <div className="email-attachments">
                        {message.attachments.length ? (
                          message.attachments.map((attachment) => (
                            <span
                              key={attachment.id}
                              className={attachment.status.toLowerCase()}
                              title={
                                attachment.rejection_code ??
                                attachment.content_sha256
                              }
                            >
                              {attachment.status === "REJECTED" ? (
                                <Ban aria-hidden="true" />
                              ) : (
                                <Paperclip aria-hidden="true" />
                              )}
                              <b>{attachment.filename}</b>
                              <small>
                                {attachmentStatusLabels[attachment.status] ??
                                  attachment.status}{" "}
                                · {formatBytes(attachment.size_bytes)}
                              </small>
                            </span>
                          ))
                        ) : (
                          <span className="none">Nincs átvehető melléklet</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span
                        className={`email-status ${message.status.toLowerCase()}`}
                      >
                        {message.status === "PROCESSED" ? (
                          <CheckCircle2 aria-hidden="true" />
                        ) : message.status === "REJECTED" ? (
                          <Ban aria-hidden="true" />
                        ) : (
                          <AlertTriangle aria-hidden="true" />
                        )}
                        {statusLabels[message.status] ?? message.status}
                      </span>
                    </td>
                    <td className="muted-text">
                      {formatDateTime(message.received_at)}
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </motion.div>
  );
}
