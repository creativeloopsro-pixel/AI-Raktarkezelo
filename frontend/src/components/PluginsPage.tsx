import { useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Check,
  CheckCircle2,
  Clock3,
  Code2,
  Plus,
  Power,
  PowerOff,
  Puzzle,
  Radio,
  ShieldCheck,
  Wrench,
  X,
  Zap
} from "lucide-react";

import {
  disablePlugin,
  enablePlugin,
  getPluginJobs,
  getPlugins,
  installPlugin,
  updatePluginPermissions,
  updatePluginSettings
} from "../lib/api";
import type { PluginItem } from "../types";

type Props = {
  role: string;
};

const permissionLabels: Record<string, string> = {
  "products.read": "Terméktörzs olvasása",
  "products.mapping.write": "Külső termékpárosítás írása",
  "documents.read": "Hozzárendelt dokumentum olvasása",
  "documents.process": "Dokumentum feldolgozásának indítása",
  "stock.movements.create": "Készletmozgás a StockService-en át",
  "reports.generate": "Riportkérés indítása",
  "notifications.create": "Értesítés létrehozása",
  "settings.read": "Saját beállítások olvasása",
  "settings.write": "Saját beállítások írása"
};

const statusLabels: Record<string, string> = {
  PENDING: "Várakozik",
  RETRY: "Újrapróbálás",
  PROCESSING: "Fut",
  COMPLETED: "Kész",
  FAILED: "Hibás",
  CANCELLED: "Megszakítva"
};

const sampleManifest = JSON.stringify(
  {
    id: "my-plugin",
    name: "Saját plugin",
    description: "Telepített szerveroldali handler manifestje.",
    version: "1.0.0",
    api_version: "1",
    entrypoint: "my_plugin.plugin:handle",
    permissions: ["products.read"],
    subscribes: ["stock.changed"],
    emits: []
  },
  null,
  2
);

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("hu-HU", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

export default function PluginsPage({ role }: Props) {
  const queryClient = useQueryClient();
  const canManage = role === "admin";
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [installOpen, setInstallOpen] = useState(false);
  const [manifestText, setManifestText] = useState(sampleManifest);
  const [manifestError, setManifestError] = useState("");

  const pluginsQuery = useQuery({
    queryKey: ["plugins"],
    queryFn: getPlugins,
    refetchInterval: 10000
  });
  const jobsQuery = useQuery({
    queryKey: ["plugin-jobs"],
    queryFn: getPluginJobs,
    refetchInterval: 5000
  });
  const plugins = useMemo(
    () => pluginsQuery.data?.plugins ?? [],
    [pluginsQuery.data]
  );
  const selected =
    plugins.find((plugin) => plugin.id === selectedId) ?? plugins[0] ?? null;
  const selectedJobs = useMemo(
    () =>
      (jobsQuery.data ?? [])
        .filter((job) => !selected || job.plugin_id === selected.id)
        .slice(0, 12),
    [jobsQuery.data, selected]
  );

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["plugins"] }),
      queryClient.invalidateQueries({ queryKey: ["plugin-jobs"] })
    ]);
  };
  const statusMutation = useMutation({
    mutationFn: ({
      plugin,
      enable
    }: {
      plugin: PluginItem;
      enable: boolean;
    }) => (enable ? enablePlugin(plugin.id) : disablePlugin(plugin.id)),
    onSuccess: refresh
  });
  const permissionMutation = useMutation({
    mutationFn: ({
      plugin,
      permission
    }: {
      plugin: PluginItem;
      permission: string;
    }) => {
      const granted = plugin.permissions
        .filter((item) =>
          item.permission === permission ? !item.granted : item.granted
        )
        .map((item) => item.permission);
      return updatePluginPermissions(plugin.id, granted);
    },
    onSuccess: refresh
  });
  const settingMutation = useMutation({
    mutationFn: ({
      plugin,
      key,
      value
    }: {
      plugin: PluginItem;
      key: string;
      value: unknown;
    }) => updatePluginSettings(plugin.id, { [key]: value }),
    onSuccess: refresh
  });
  const installMutation = useMutation({
    mutationFn: installPlugin,
    onSuccess: async (plugin) => {
      setSelectedId(plugin.id);
      setInstallOpen(false);
      setManifestError("");
      await refresh();
    }
  });

  const install = () => {
    try {
      const parsed = JSON.parse(manifestText) as Record<string, unknown>;
      setManifestError("");
      installMutation.mutate(parsed);
    } catch {
      setManifestError("A manifest nem érvényes JSON.");
    }
  };

  const failedJobs = pluginsQuery.data?.job_counts.FAILED ?? 0;
  const missingPermissions = plugins.reduce(
    (sum, plugin) =>
      sum + plugin.permissions.filter((permission) => !permission.granted).length,
    0
  );
  const operationError =
    statusMutation.error ||
    permissionMutation.error ||
    settingMutation.error ||
    installMutation.error;

  return (
    <motion.div
      className="plugins-page"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32 }}
    >
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Bővítmények és eseménybusz</p>
          <h1>Pluginok</h1>
        </div>
        {canManage && (
          <button className="primary-button" onClick={() => setInstallOpen(true)}>
            <Plus aria-hidden="true" />
            Manifest telepítése
          </button>
        )}
      </header>

      <section className="plugin-summary" aria-label="Plugin állapotok">
        <div>
          <Puzzle aria-hidden="true" />
          <span>Telepítve</span>
          <strong>{plugins.length}</strong>
        </div>
        <div>
          <Power aria-hidden="true" />
          <span>Engedélyezve</span>
          <strong>
            {plugins.filter((plugin) => plugin.status === "ENABLED").length}
          </strong>
        </div>
        <div className={missingPermissions ? "attention" : ""}>
          <ShieldCheck aria-hidden="true" />
          <span>Hiányzó engedély</span>
          <strong>{missingPermissions}</strong>
        </div>
        <div className={failedJobs ? "attention" : ""}>
          <AlertTriangle aria-hidden="true" />
          <span>Hibás job</span>
          <strong>{failedJobs}</strong>
        </div>
      </section>

      {pluginsQuery.isLoading && (
        <div className="empty-state">Pluginok betöltése…</div>
      )}
      {pluginsQuery.isError && (
        <div className="empty-state error-state">
          <AlertTriangle aria-hidden="true" />
          A plugin registry most nem érhető el.
        </div>
      )}

      {plugins.length > 0 && selected && (
        <section className="plugin-workbench">
          <div className="plugin-index" aria-label="Telepített pluginok">
            <div className="plugin-index-heading">
              <p className="section-label">Registry</p>
              <span>{plugins.length} manifest</span>
            </div>
            {plugins.map((plugin) => (
              <button
                key={plugin.id}
                className={selected.id === plugin.id ? "active" : ""}
                onClick={() => setSelectedId(plugin.id)}
              >
                <span className="plugin-list-icon">
                  {plugin.status === "ENABLED" ? (
                    <Zap aria-hidden="true" />
                  ) : (
                    <Puzzle aria-hidden="true" />
                  )}
                </span>
                <span>
                  <strong>{plugin.name}</strong>
                  <small>
                    {plugin.plugin_key} · v{plugin.active_version}
                  </small>
                </span>
                <i className={plugin.status.toLowerCase()}>
                  {plugin.status === "ENABLED" ? "Aktív" : "Tiltva"}
                </i>
              </button>
            ))}
          </div>

          <motion.div
            key={selected.id}
            className="plugin-inspector"
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <div className="plugin-inspector-header">
              <div>
                <span className="plugin-kind">
                  {selected.is_builtin ? "Beépített" : "Telepített"} · API{" "}
                  {selected.api_version}
                </span>
                <h2>{selected.name}</h2>
                <p>{selected.description}</p>
              </div>
              {canManage && (
                <button
                  className={
                    selected.status === "ENABLED"
                      ? "secondary-button"
                      : "primary-button"
                  }
                  disabled={statusMutation.isPending}
                  onClick={() =>
                    statusMutation.mutate({
                      plugin: selected,
                      enable: selected.status !== "ENABLED"
                    })
                  }
                >
                  {selected.status === "ENABLED" ? (
                    <PowerOff aria-hidden="true" />
                  ) : (
                    <Power aria-hidden="true" />
                  )}
                  {selected.status === "ENABLED" ? "Letiltás" : "Engedélyezés"}
                </button>
              )}
            </div>

            <div className="plugin-contract">
              <div>
                <Radio aria-hidden="true" />
                <span>
                  <strong>Feliratkozások</strong>
                  <small>
                    {selected.manifest.subscribes.join(" · ") ||
                      "Nincs eseményfeliratkozás"}
                  </small>
                </span>
              </div>
              <div>
                <Activity aria-hidden="true" />
                <span>
                  <strong>Kibocsátott események</strong>
                  <small>
                    {selected.manifest.emits.join(" · ") ||
                      "Nincs deklarált kimeneti esemény"}
                  </small>
                </span>
              </div>
              <div>
                <Code2 aria-hidden="true" />
                <span>
                  <strong>Entrypoint</strong>
                  <small>{selected.manifest.entrypoint || "Core adapter"}</small>
                </span>
              </div>
            </div>

            <div className="plugin-permissions">
              <div className="plugin-block-heading">
                <div>
                  <p className="section-label">Legkisebb jogosultság</p>
                  <h3>Deklarált engedélyek</h3>
                </div>
                <span>
                  {selected.permissions.filter((item) => item.granted).length}/
                  {selected.permissions.length} megadva
                </span>
              </div>
              <div className="plugin-permission-list">
                {selected.permissions.map((permission) => (
                  <label key={permission.permission}>
                    <input
                      type="checkbox"
                      checked={permission.granted}
                      disabled={!canManage || permissionMutation.isPending}
                      onChange={() =>
                        permissionMutation.mutate({
                          plugin: selected,
                          permission: permission.permission
                        })
                      }
                    />
                    <span>
                      <strong>
                        {permissionLabels[permission.permission] ??
                          permission.permission}
                      </strong>
                      <small>{permission.permission}</small>
                    </span>
                    {permission.granted && <Check aria-hidden="true" />}
                  </label>
                ))}
              </div>
            </div>

            {selected.settings.length > 0 && (
              <div className="plugin-settings">
                <div className="plugin-block-heading">
                  <div>
                    <p className="section-label">Saját konfiguráció</p>
                    <h3>Plugin beállítások</h3>
                  </div>
                </div>
                {selected.settings.map((setting) => (
                  <div key={setting.key} className="plugin-setting-row">
                    <span>
                      <strong>{setting.key}</strong>
                      <small>
                        {selected.manifest.settings_schema.properties?.[
                          setting.key
                        ]?.description ?? "Manifest által definiált beállítás"}
                      </small>
                    </span>
                    {typeof setting.value === "boolean" ? (
                      <button
                        role="switch"
                        aria-checked={setting.value}
                        className={setting.value ? "active" : ""}
                        disabled={!canManage || settingMutation.isPending}
                        onClick={() =>
                          settingMutation.mutate({
                            plugin: selected,
                            key: setting.key,
                            value: !setting.value
                          })
                        }
                      >
                        <i />
                      </button>
                    ) : (
                      <code>{String(setting.value)}</code>
                    )}
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        </section>
      )}

      <section className="plugin-jobs-section">
        <div className="section-heading">
          <div>
            <p className="section-label">Tartós végrehajtás</p>
            <h2>{selected ? `${selected.name} jobjai` : "Plugin jobok"}</h2>
          </div>
          <span className="muted-text">5 másodpercenként frissül</span>
        </div>
        {selectedJobs.length === 0 ? (
          <div className="empty-state">
            <Clock3 aria-hidden="true" />
            <strong>Még nincs pluginfutás.</strong>
            <span>Az eseménybusz jobjai itt jelennek meg.</span>
          </div>
        ) : (
          <div className="plugin-job-list">
            {selectedJobs.map((job) => (
              <div key={job.id}>
                <span
                  className={`plugin-job-status ${job.status.toLowerCase()}`}
                >
                  {job.status === "COMPLETED" ? (
                    <CheckCircle2 aria-hidden="true" />
                  ) : job.status === "FAILED" ? (
                    <AlertTriangle aria-hidden="true" />
                  ) : (
                    <Clock3 aria-hidden="true" />
                  )}
                  {statusLabels[job.status] ?? job.status}
                </span>
                <span>
                  <strong>{job.event_type}</strong>
                  <small>
                    {job.aggregate_type}:{job.aggregate_id.slice(0, 12)} ·{" "}
                    {job.attempts}/{job.max_attempts} próbálkozás
                  </small>
                </span>
                <time>{formatDate(job.created_at)}</time>
              </div>
            ))}
          </div>
        )}
      </section>

      {operationError && (
        <p className="form-error plugin-operation-error">
          {operationError.message}
        </p>
      )}

      <Dialog.Root open={installOpen} onOpenChange={setInstallOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content plugin-install-dialog">
            <div className="dialog-heading">
              <div>
                <p className="eyebrow">SDK manifest</p>
                <Dialog.Title>Plugin telepítése</Dialog.Title>
                <Dialog.Description>
                  Csak a szerveren már regisztrált handler manifestje
                  engedélyezhető.
                </Dialog.Description>
              </div>
              <Dialog.Close className="icon-button" aria-label="Bezárás">
                <X aria-hidden="true" />
              </Dialog.Close>
            </div>
            <label className="plugin-manifest-field">
              manifest.json
              <textarea
                value={manifestText}
                spellCheck={false}
                onChange={(event) => setManifestText(event.target.value)}
              />
            </label>
            {(manifestError || installMutation.error) && (
              <p className="form-error">
                {manifestError || installMutation.error?.message}
              </p>
            )}
            <div className="dialog-actions">
              <Dialog.Close className="secondary-button">Mégse</Dialog.Close>
              <button
                className="primary-button"
                disabled={installMutation.isPending}
                onClick={install}
              >
                <Wrench aria-hidden="true" />
                Manifest ellenőrzése és telepítése
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </motion.div>
  );
}
