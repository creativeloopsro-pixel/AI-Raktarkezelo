import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Cpu,
  Eye,
  EyeOff,
  KeyRound,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2
} from "lucide-react";

import {
  clearAiSettings,
  getAiSettings,
  updateAiSettings
} from "../lib/api";

type Props = {
  canWrite: boolean;
};

export default function AiSettingsPanel({ canWrite }: Props) {
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [feedback, setFeedback] = useState("");

  const query = useQuery({
    queryKey: ["ai-settings"],
    queryFn: getAiSettings
  });
  const updateMutation = useMutation({
    mutationFn: updateAiSettings,
    onSuccess: (settings) => {
      queryClient.setQueryData(["ai-settings"], settings);
      setApiKey("");
      setShowKey(false);
      setConfirmClear(false);
      setFeedback("Az AI API-kulcs biztonságosan elmentve.");
    }
  });
  const clearMutation = useMutation({
    mutationFn: clearAiSettings,
    onSuccess: (settings) => {
      queryClient.setQueryData(["ai-settings"], settings);
      setConfirmClear(false);
      setFeedback("A szervezeti AI API-kulcs eltávolítva.");
    }
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedback("");
    updateMutation.mutate(apiKey.trim());
  }

  function clearKey() {
    setFeedback("");
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    clearMutation.mutate();
  }

  const settings = query.data;
  const normalizedKey = apiKey.trim();
  const keyValid =
    normalizedKey.length >= 8 &&
    !Array.from(normalizedKey).some((character) => /\s/.test(character));
  const mutationError = updateMutation.error ?? clearMutation.error;

  return (
    <section className="ai-settings-section" aria-labelledby="ai-settings-title">
      <div className="section-heading ai-settings-heading">
        <div>
          <p className="section-label">AI-kapcsolat</p>
          <h2 id="ai-settings-title">API-kulcs és szolgáltató</h2>
        </div>
        <span
          className={`ai-connection-status ${
            settings?.provider_enabled ? "configured" : ""
          }`}
          role="status"
        >
          {settings?.provider_enabled ? (
            <CheckCircle2 aria-hidden="true" />
          ) : (
            <KeyRound aria-hidden="true" />
          )}
          {settings?.provider_enabled ? "AI aktív" : "Beállítás szükséges"}
        </span>
      </div>

      {query.isPending ? (
        <div className="ai-settings-loading">AI-beállítások betöltése…</div>
      ) : null}
      {query.error ? (
        <div className="ai-settings-loading error-state">
          <span>{query.error.message}</span>
          <button className="secondary-button" onClick={() => query.refetch()}>
            Újrapróbálás
          </button>
        </div>
      ) : null}

      {settings ? (
        <div className="ai-settings-panel">
          <div className="ai-provider-summary">
            <div className="ai-provider-identity">
              <span className="ai-provider-icon">
                <Sparkles aria-hidden="true" />
              </span>
              <span>
                <small>Szolgáltató</small>
                <strong>Ollama Cloud</strong>
                <em>{settings.base_url}</em>
              </span>
            </div>
            <div>
              <small>Modell</small>
              <strong>{settings.model}</strong>
              <em>Multimodális dokumentumfelismerés</em>
            </div>
            <div>
              <small>API-kulcs</small>
              <strong>
                {settings.api_key_configured
                  ? settings.api_key_hint ?? "Környezeti kulcs"
                  : "Nincs megadva"}
              </strong>
              <em>
                {settings.api_key_source === "organization"
                  ? "Titkosított szervezeti beállítás"
                  : settings.api_key_source === "environment"
                    ? "Szerverkörnyezeti beállítás"
                    : "Az AI jelenleg nem használható"}
              </em>
            </div>
          </div>

          {canWrite ? (
            <form className="ai-key-form" onSubmit={submit}>
              <div className="ai-key-form-copy">
                <ShieldCheck aria-hidden="true" />
                <span>
                  <strong>
                    {settings.api_key_configured
                      ? "API-kulcs cseréje"
                      : "API-kulcs megadása"}
                  </strong>
                  <small>
                    A kulcs titkosítva kerül a szerverre, és mentés után nem
                    olvasható vissza.
                  </small>
                </span>
              </div>
              <label className="ai-key-field">
                <span>Új AI API-kulcs</span>
                <span className="ai-key-input-shell">
                  <input
                    type={showKey ? "text" : "password"}
                    value={apiKey}
                    onChange={(event) => {
                      setApiKey(event.target.value);
                      setFeedback("");
                      updateMutation.reset();
                    }}
                    placeholder="API-kulcs beillesztése"
                    autoComplete="new-password"
                    spellCheck={false}
                    aria-describedby="ai-key-help"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((visible) => !visible)}
                    aria-label={showKey ? "API-kulcs elrejtése" : "API-kulcs megjelenítése"}
                  >
                    {showKey ? (
                      <EyeOff aria-hidden="true" />
                    ) : (
                      <Eye aria-hidden="true" />
                    )}
                  </button>
                </span>
                <small id="ai-key-help">
                  Legalább 8 karakter, szóköz nélkül. A mentés automatikusan
                  aktiválja az Ollama AI-feldolgozást ennél a szervezetnél.
                </small>
              </label>

              {feedback ? (
                <p className="ai-key-feedback success">
                  <CheckCircle2 aria-hidden="true" />
                  {feedback}
                </p>
              ) : null}
              {mutationError ? (
                <p className="ai-key-feedback error">
                  {mutationError.message}
                </p>
              ) : null}
              {confirmClear ? (
                <p className="ai-key-feedback warning">
                  Az eltávolításhoz kattints újra a törlés gombra.
                </p>
              ) : null}

              <div className="ai-key-actions">
                {settings.api_key_source === "organization" ? (
                  <button
                    className={`secondary-button danger-button ${
                      confirmClear ? "confirming" : ""
                    }`}
                    type="button"
                    disabled={clearMutation.isPending}
                    onClick={clearKey}
                  >
                    <Trash2 aria-hidden="true" />
                    {clearMutation.isPending
                      ? "Eltávolítás…"
                      : confirmClear
                        ? "Törlés megerősítése"
                        : "Kulcs eltávolítása"}
                  </button>
                ) : null}
                <button
                  className="primary-button"
                  type="submit"
                  disabled={!keyValid || updateMutation.isPending}
                >
                  <Save aria-hidden="true" />
                  {updateMutation.isPending ? "Mentés…" : "API-kulcs mentése"}
                </button>
              </div>
            </form>
          ) : (
            <div className="ai-settings-readonly">
              <Cpu aria-hidden="true" />
              <span>
                Az AI-kapcsolat állapota megtekinthető, módosításához
                beállításkezelési jogosultság szükséges.
              </span>
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
