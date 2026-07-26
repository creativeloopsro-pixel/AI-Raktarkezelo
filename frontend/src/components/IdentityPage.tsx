import { FormEvent, useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Copy,
  KeyRound,
  Laptop,
  LockKeyhole,
  Plus,
  Save,
  ShieldCheck,
  Smartphone,
  Trash2,
  Users,
  X
} from "lucide-react";

import {
  confirmMfa,
  createApiToken,
  createIdentityRole,
  createIdentityUser,
  deleteIdentityRole,
  getApiTokens,
  getIdentityPermissions,
  getIdentityRoles,
  getIdentityUsers,
  getRefreshSessions,
  revokeApiToken,
  revokeOtherSessions,
  revokeRefreshSession,
  saveSession,
  setupMfa,
  updateIdentityRole,
  updateIdentityUser
} from "../lib/api";
import type {
  CreatedApiToken,
  IdentityRole,
  IdentityUser,
  MfaSetup,
  PermissionItem,
  Session
} from "../types";

type Props = {
  session: Session;
  onSessionUpdated: (session: Session) => void;
};

type Tab = "users" | "roles" | "security" | "tokens";

const dateFormatter = new Intl.DateTimeFormat("hu-HU", {
  dateStyle: "medium",
  timeStyle: "short"
});

const permissionCategoryLabels: Record<string, string> = {
  identity: "Identity és hozzáférés",
  catalog: "Terméktörzs",
  inventory: "Készlet és leltár",
  documents: "Dokumentumok",
  reviews: "Ellenőrzések",
  vrp: "VRP-import",
  email: "E-mail",
  plugins: "Pluginok",
  reports: "Riportok",
  system: "Rendszer"
};

function groupPermissions(permissions: PermissionItem[]) {
  return permissions.reduce<Record<string, PermissionItem[]>>((groups, permission) => {
    (groups[permission.category] ??= []).push(permission);
    return groups;
  }, {});
}

export default function IdentityPage({ session, onSessionUpdated }: Props) {
  const [tab, setTab] = useState<Tab>(
    session.mfa_setup_required ? "security" : "users"
  );
  const canReadUsers = session.user.permissions.includes("users.read");
  const canWriteUsers = session.user.permissions.includes("users.write");
  const canReadRoles = session.user.permissions.includes("roles.read");
  const canWriteRoles = session.user.permissions.includes("roles.write");
  const canReadTokens = session.user.permissions.includes("tokens.read");
  const canCreateTokens = session.user.permissions.includes("tokens.create");
  const identityUnlocked = !session.mfa_setup_required;
  const queryClient = useQueryClient();

  const usersQuery = useQuery({
    queryKey: ["identity-users"],
    queryFn: getIdentityUsers,
    enabled: identityUnlocked && canReadUsers
  });
  const rolesQuery = useQuery({
    queryKey: ["identity-roles"],
    queryFn: getIdentityRoles,
    enabled: identityUnlocked && canReadRoles
  });
  const permissionsQuery = useQuery({
    queryKey: ["identity-permissions"],
    queryFn: getIdentityPermissions,
    enabled: identityUnlocked && canReadRoles
  });
  const sessionsQuery = useQuery({
    queryKey: ["auth-sessions"],
    queryFn: getRefreshSessions
  });
  const tokensQuery = useQuery({
    queryKey: ["api-tokens"],
    queryFn: getApiTokens,
    enabled: identityUnlocked && canReadTokens
  });

  const tabs = [
    { id: "users" as const, label: "Felhasználók", icon: Users, visible: canReadUsers },
    {
      id: "roles" as const,
      label: "Szerepkörök",
      icon: ShieldCheck,
      visible: canReadRoles
    },
    { id: "security" as const, label: "Biztonság", icon: LockKeyhole, visible: true },
    {
      id: "tokens" as const,
      label: "API-tokenek",
      icon: KeyRound,
      visible: canReadTokens
    }
  ].filter((item) => item.visible);

  return (
    <motion.div
      className="identity-page"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <header className="workspace-header identity-header">
        <div>
          <p className="eyebrow">Identity és hozzáférés</p>
          <h1>Felhasználók és biztonság</h1>
          <p className="page-lead">
            Szerepkörök, munkamenetek, többtényezős hitelesítés és
            integrációs hozzáférések egy auditált helyen.
          </p>
        </div>
        <div className="identity-posture">
          <ShieldCheck aria-hidden="true" />
          <span>
            <small>Aktív védelem</small>
            <strong>
              {session.user.mfa_enabled ? "MFA bekapcsolva" : "MFA beállítandó"}
            </strong>
          </span>
        </div>
      </header>

      <nav className="identity-tabs" aria-label="Identity területek">
        {tabs.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              className={tab === item.id ? "active" : ""}
              disabled={session.mfa_setup_required && item.id !== "security"}
              onClick={() => setTab(item.id)}
            >
              <Icon aria-hidden="true" />
              {item.label}
            </button>
          );
        })}
      </nav>

      {tab === "users" && (
        <UsersPanel
          users={usersQuery.data ?? []}
          roles={rolesQuery.data ?? []}
          loading={usersQuery.isLoading || rolesQuery.isLoading}
          canWrite={canWriteUsers}
          onChanged={() =>
            void queryClient.invalidateQueries({ queryKey: ["identity-users"] })
          }
        />
      )}
      {tab === "roles" && (
        <RolesPanel
          roles={rolesQuery.data ?? []}
          permissions={permissionsQuery.data ?? []}
          loading={rolesQuery.isLoading || permissionsQuery.isLoading}
          canWrite={canWriteRoles}
          onChanged={() => {
            void queryClient.invalidateQueries({ queryKey: ["identity-roles"] });
            void queryClient.invalidateQueries({ queryKey: ["identity-users"] });
          }}
        />
      )}
      {tab === "security" && (
        <SecurityPanel
          session={session}
          sessions={sessionsQuery.data ?? []}
          loading={sessionsQuery.isLoading}
          onSessionUpdated={onSessionUpdated}
          onChanged={() =>
            void queryClient.invalidateQueries({ queryKey: ["auth-sessions"] })
          }
        />
      )}
      {tab === "tokens" && (
        <TokensPanel
          tokens={tokensQuery.data ?? []}
          permissions={permissionsQuery.data ?? []}
          loading={tokensQuery.isLoading}
          canCreate={canCreateTokens}
          onChanged={() =>
            void queryClient.invalidateQueries({ queryKey: ["api-tokens"] })
          }
        />
      )}
    </motion.div>
  );
}

function UsersPanel({
  users,
  roles,
  loading,
  canWrite,
  onChanged
}: {
  users: IdentityUser[];
  roles: IdentityRole[];
  loading: boolean;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<IdentityUser | null>(null);

  return (
    <section className="identity-section">
      <div className="section-heading">
        <div>
          <p className="section-label">Szervezeti fiókok</p>
          <h2>Felhasználók</h2>
        </div>
        {canWrite && (
          <button
            className="primary-button"
            onClick={() => {
              setEditing(null);
              setOpen(true);
            }}
          >
            <Plus aria-hidden="true" />
            Új felhasználó
          </button>
        )}
      </div>
      {loading ? (
        <div className="empty-state">Felhasználók betöltése…</div>
      ) : (
        <div className="identity-table-wrap">
          <table className="identity-table">
            <thead>
              <tr>
                <th>Felhasználó</th>
                <th>Szerepkörök</th>
                <th>MFA</th>
                <th>Állapot</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>
                    <div className="identity-user-cell">
                      <span>{user.full_name.slice(0, 2).toUpperCase()}</span>
                      <div>
                        <strong>{user.full_name}</strong>
                        <small>{user.email}</small>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div className="role-chip-list">
                      {user.roles.map((role) => (
                        <span key={role}>{role}</span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <span className={`status-dot ${user.mfa_enabled ? "" : "warning"}`}>
                      {user.mfa_enabled ? "Aktív" : "Nincs"}
                    </span>
                  </td>
                  <td>
                    <span className={`status-dot ${user.is_active ? "" : "danger"}`}>
                      {user.is_active ? "Aktív" : "Letiltva"}
                    </span>
                  </td>
                  <td className="identity-row-action">
                    {canWrite && (
                      <button
                        className="text-button"
                        onClick={() => {
                          setEditing(user);
                          setOpen(true);
                        }}
                      >
                        Szerkesztés
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <UserDialog
        key={`${editing?.id ?? "new"}:${open ? "open" : "closed"}`}
        open={open}
        onOpenChange={setOpen}
        user={editing}
        roles={roles}
        onSaved={onChanged}
      />
    </section>
  );
}

function UserDialog({
  open,
  onOpenChange,
  user,
  roles,
  onSaved
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: IdentityUser | null;
  roles: IdentityRole[];
  onSaved: () => void;
}) {
  const [email, setEmail] = useState(user?.email ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [password, setPassword] = useState("");
  const [roleIds, setRoleIds] = useState<string[]>(
    user?.role_ids ?? roles.slice(0, 1).map((role) => role.id)
  );
  const [active, setActive] = useState(user?.is_active ?? true);
  const [error, setError] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      user
        ? updateIdentityUser(user.id, {
            email,
            full_name: fullName,
            role_ids: roleIds,
            is_active: active,
            password: password || null
          })
        : createIdentityUser({
            email,
            full_name: fullName,
            role_ids: roleIds,
            password
          }),
    onSuccess: () => {
      onSaved();
      onOpenChange(false);
    },
    onError: (requestError) =>
      setError(requestError instanceof Error ? requestError.message : "A mentés sikertelen.")
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    mutation.mutate();
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content identity-dialog">
          <Dialog.Close className="dialog-close" aria-label="Bezárás">
            <X aria-hidden="true" />
          </Dialog.Close>
          <Dialog.Title>{user ? "Felhasználó szerkesztése" : "Új felhasználó"}</Dialog.Title>
          <Dialog.Description>
            A jogosultságokat a kiválasztott szerepkörök összege adja.
          </Dialog.Description>
          <form onSubmit={submit}>
            <div className="form-grid">
              <label>
                Teljes név
                <input
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  required
                />
              </label>
              <label>
                E-mail
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </label>
            </div>
            <label>
              {user ? "Új jelszó (opcionális)" : "Kezdeti jelszó"}
              <input
                type="password"
                value={password}
                minLength={user ? undefined : 12}
                onChange={(event) => setPassword(event.target.value)}
                required={!user}
                autoComplete="new-password"
              />
            </label>
            <fieldset className="role-selector">
              <legend>Szerepkörök</legend>
              {roles.map((role) => (
                <label key={role.id}>
                  <input
                    type="checkbox"
                    checked={roleIds.includes(role.id)}
                    onChange={(event) =>
                      setRoleIds((current) =>
                        event.target.checked
                          ? [...current, role.id]
                          : current.filter((id) => id !== role.id)
                      )
                    }
                  />
                  <span>
                    <strong>{role.name}</strong>
                    <small>{role.permission_codes.length} jogosultság</small>
                  </span>
                </label>
              ))}
            </fieldset>
            {user && (
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={active}
                  onChange={(event) => setActive(event.target.checked)}
                />
                <span>
                  <strong>Aktív felhasználó</strong>
                  <small>Letiltva a meglévő munkamenetek sem használhatók.</small>
                </span>
              </label>
            )}
            {error && <p className="form-error">{error}</p>}
            <button
              className="primary-button"
              type="submit"
              disabled={mutation.isPending || roleIds.length === 0}
            >
              <Save aria-hidden="true" />
              {mutation.isPending ? "Mentés…" : "Mentés"}
            </button>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function RolesPanel({
  roles,
  permissions,
  loading,
  canWrite,
  onChanged
}: {
  roles: IdentityRole[];
  permissions: PermissionItem[];
  loading: boolean;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(roles[0]?.id ?? null);
  const [creating, setCreating] = useState(false);
  const selected = roles.find((role) => role.id === selectedId) ?? roles[0] ?? null;

  if (loading) return <div className="empty-state">Szerepkörök betöltése…</div>;

  return (
    <section className="identity-section role-workspace">
      <aside className="role-list">
        <div className="role-list-heading">
          <div>
            <p className="section-label">Hozzáférési profilok</p>
            <h2>Szerepkörök</h2>
          </div>
          {canWrite && (
            <button
              className="icon-button"
              title="Új szerepkör"
              onClick={() => setCreating(true)}
            >
              <Plus aria-hidden="true" />
            </button>
          )}
        </div>
        {roles.map((role) => (
          <button
            key={role.id}
            className={selected?.id === role.id ? "active" : ""}
            onClick={() => {
              setSelectedId(role.id);
              setCreating(false);
            }}
          >
            <span>
              <strong>{role.name}</strong>
              <small>{role.user_count} felhasználó</small>
            </span>
            <span>{role.permission_codes.length}</span>
          </button>
        ))}
      </aside>
      <RoleEditor
        key={creating ? "new" : selected?.id}
        role={creating ? null : selected}
        permissions={permissions}
        canWrite={canWrite}
        onSaved={(role) => {
          onChanged();
          setCreating(false);
          setSelectedId(role.id);
        }}
        onDeleted={() => {
          onChanged();
          setSelectedId(null);
        }}
      />
    </section>
  );
}

function RoleEditor({
  role,
  permissions,
  canWrite,
  onSaved,
  onDeleted
}: {
  role: IdentityRole | null;
  permissions: PermissionItem[];
  canWrite: boolean;
  onSaved: (role: IdentityRole) => void;
  onDeleted: () => void;
}) {
  const [name, setName] = useState(role?.name ?? "");
  const [slug, setSlug] = useState(role?.slug ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [selected, setSelected] = useState<string[]>(role?.permission_codes ?? []);
  const [error, setError] = useState("");
  const groups = groupPermissions(permissions);

  const saveMutation = useMutation({
    mutationFn: () =>
      role
        ? updateIdentityRole(role.id, {
            name,
            description,
            permission_codes: selected
          })
        : createIdentityRole({
            name,
            slug,
            description,
            permission_codes: selected
          }),
    onSuccess: onSaved,
    onError: (requestError) =>
      setError(requestError instanceof Error ? requestError.message : "A mentés sikertelen.")
  });
  const deleteMutation = useMutation({
    mutationFn: () => (role ? deleteIdentityRole(role.id) : Promise.resolve()),
    onSuccess: onDeleted,
    onError: (requestError) =>
      setError(requestError instanceof Error ? requestError.message : "A törlés sikertelen.")
  });

  if (!role && !canWrite) {
    return <div className="empty-state">Nincs kiválasztott szerepkör.</div>;
  }

  return (
    <div className="role-editor">
      <div className="role-editor-heading">
        <div>
          <p className="section-label">{role?.is_system ? "Beépített szerepkör" : "Egyedi szerepkör"}</p>
          <h2>{role ? role.name : "Új szerepkör"}</h2>
        </div>
        {role && !role.is_system && canWrite && (
          <button
            className="icon-button danger"
            title="Szerepkör törlése"
            onClick={() => deleteMutation.mutate()}
            disabled={role.user_count > 0}
          >
            <Trash2 aria-hidden="true" />
          </button>
        )}
      </div>
      <div className="form-grid">
        <label>
          Megnevezés
          <input value={name} onChange={(event) => setName(event.target.value)} disabled={!canWrite} />
        </label>
        <label>
          Azonosító
          <input
            value={slug}
            onChange={(event) => setSlug(event.target.value)}
            disabled={Boolean(role) || !canWrite}
            placeholder="pl. muszakvezeto"
          />
        </label>
      </div>
      <label>
        Leírás
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          disabled={!canWrite}
        />
      </label>
      <div className="permission-groups">
        {Object.entries(groups).map(([category, items]) => (
          <fieldset key={category}>
            <legend>{permissionCategoryLabels[category] ?? category}</legend>
            {items.map((permission) => (
              <label key={permission.code}>
                <input
                  type="checkbox"
                  checked={selected.includes(permission.code)}
                  disabled={!canWrite || (role?.slug === "admin" && permission.code === "system.admin")}
                  onChange={(event) =>
                    setSelected((current) =>
                      event.target.checked
                        ? [...current, permission.code]
                        : current.filter((code) => code !== permission.code)
                    )
                  }
                />
                <span>
                  <strong>{permission.name}</strong>
                  <small>{permission.code}</small>
                </span>
              </label>
            ))}
          </fieldset>
        ))}
      </div>
      {error && <p className="form-error">{error}</p>}
      {canWrite && (
        <button
          className="primary-button"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending || selected.length === 0}
        >
          <Save aria-hidden="true" />
          {saveMutation.isPending ? "Mentés…" : "Jogosultságok mentése"}
        </button>
      )}
    </div>
  );
}

function SecurityPanel({
  session,
  sessions,
  loading,
  onSessionUpdated,
  onChanged
}: {
  session: Session;
  sessions: Awaited<ReturnType<typeof getRefreshSessions>>;
  loading: boolean;
  onSessionUpdated: (session: Session) => void;
  onChanged: () => void;
}) {
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [code, setCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [error, setError] = useState("");

  const setupMutation = useMutation({
    mutationFn: setupMfa,
    onSuccess: setSetup,
    onError: (requestError) =>
      setError(requestError instanceof Error ? requestError.message : "Az MFA indítása sikertelen.")
  });
  const confirmMutation = useMutation({
    mutationFn: () => confirmMfa(code),
    onSuccess: (result) => {
      saveSession(result.session);
      onSessionUpdated(result.session);
      setRecoveryCodes(result.recovery_codes);
      setSetup(null);
      setCode("");
      onChanged();
    },
    onError: (requestError) =>
      setError(requestError instanceof Error ? requestError.message : "A kód ellenőrzése sikertelen.")
  });
  const revokeMutation = useMutation({
    mutationFn: revokeRefreshSession,
    onSuccess: onChanged
  });
  const revokeOthersMutation = useMutation({
    mutationFn: revokeOtherSessions,
    onSuccess: onChanged
  });

  return (
    <section className="identity-security-grid">
      <div className="mfa-panel">
        <div className="security-panel-heading">
          <div className="security-icon">
            <Smartphone aria-hidden="true" />
          </div>
          <div>
            <p className="section-label">Többtényezős hitelesítés</p>
            <h2>Hitelesítő alkalmazás</h2>
          </div>
          <span className={`status-dot ${session.user.mfa_enabled ? "" : "warning"}`}>
            {session.user.mfa_enabled ? "Aktív" : "Beállítandó"}
          </span>
        </div>
        {session.user.mfa_enabled ? (
          <p className="security-explainer">
            A jelszó után minden új belépéshez egyszer használatos kód szükséges.
            Az adminisztratív munkamenet MFA-állapota szerveroldalon is ellenőrzött.
          </p>
        ) : setup ? (
          <div className="mfa-setup-flow">
            <div className="mfa-step">
              <span>1</span>
              <div>
                <strong>Add hozzá az alkalmazáshoz</strong>
                <small>Google Authenticator, Microsoft Authenticator vagy kompatibilis TOTP alkalmazás.</small>
              </div>
            </div>
            <div className="secret-copy">
              <code>{setup.secret}</code>
              <button
                className="icon-button"
                title="Titok másolása"
                onClick={() => void navigator.clipboard.writeText(setup.secret)}
              >
                <Copy aria-hidden="true" />
              </button>
            </div>
            <a className="text-button mfa-uri" href={setup.otpauth_uri}>
              Megnyitás hitelesítő alkalmazásban
            </a>
            <div className="mfa-step">
              <span>2</span>
              <div>
                <strong>Ellenőrizd az első kóddal</strong>
                <small>A kód 30 másodpercenként változik.</small>
              </div>
            </div>
            <div className="mfa-confirm-row">
              <input
                value={code}
                onChange={(event) => setCode(event.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="123456"
              />
              <button
                className="primary-button"
                onClick={() => confirmMutation.mutate()}
                disabled={confirmMutation.isPending || code.length < 6}
              >
                <Check aria-hidden="true" />
                Megerősítés
              </button>
            </div>
          </div>
        ) : (
          <>
            <p className="security-explainer">
              Adminisztrátoroknál kötelező. A beállítás után egyszer megjelenő
              helyreállító kódokat biztonságos helyen kell tárolni.
            </p>
            <button
              className="primary-button"
              onClick={() => setupMutation.mutate()}
              disabled={setupMutation.isPending}
            >
              <ShieldCheck aria-hidden="true" />
              MFA beállítása
            </button>
          </>
        )}
        {error && <p className="form-error">{error}</p>}
        {recoveryCodes.length > 0 && (
          <div className="recovery-code-panel">
            <div>
              <strong>Helyreállító kódok</strong>
              <span>Mindegyik egyszer használható. Ez az egyetlen megjelenítés.</span>
            </div>
            <div className="recovery-code-grid">
              {recoveryCodes.map((recoveryCode) => (
                <code key={recoveryCode}>{recoveryCode}</code>
              ))}
            </div>
            <button
              className="secondary-button"
              onClick={() => void navigator.clipboard.writeText(recoveryCodes.join("\n"))}
            >
              <Copy aria-hidden="true" />
              Összes másolása
            </button>
          </div>
        )}
      </div>

      <div className="session-panel">
        <div className="security-panel-heading">
          <div className="security-icon">
            <Laptop aria-hidden="true" />
          </div>
          <div>
            <p className="section-label">Munkamenet-védelem</p>
            <h2>Bejelentkezett eszközök</h2>
          </div>
          <button
            className="text-button"
            onClick={() => revokeOthersMutation.mutate()}
          >
            Többi visszavonása
          </button>
        </div>
        {loading ? (
          <div className="empty-state">Munkamenetek betöltése…</div>
        ) : (
          <div className="session-list">
            {sessions.map((item) => (
              <div key={item.id} className={item.revoked_at ? "revoked" : ""}>
                <span className="session-device">
                  <Laptop aria-hidden="true" />
                </span>
                <div>
                  <strong>
                    {item.current ? "Ez az eszköz" : item.user_agent || "Ismeretlen eszköz"}
                  </strong>
                  <small>
                    {item.ip_address || "Ismeretlen IP"} ·{" "}
                    {dateFormatter.format(new Date(item.last_seen_at))}
                  </small>
                  <span>
                    {item.revoked_at
                      ? `Visszavonva · ${item.revoke_reason ?? "ismeretlen ok"}`
                      : item.mfa_verified
                        ? "MFA-hitelesített"
                        : "Jelszavas munkamenet"}
                  </span>
                </div>
                {!item.revoked_at && (
                  <button
                    className="icon-button danger"
                    title="Munkamenet visszavonása"
                    onClick={() => revokeMutation.mutate(item.id)}
                  >
                    <X aria-hidden="true" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function TokensPanel({
  tokens,
  permissions,
  loading,
  canCreate,
  onChanged
}: {
  tokens: Awaited<ReturnType<typeof getApiTokens>>;
  permissions: PermissionItem[];
  loading: boolean;
  canCreate: boolean;
  onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [expiry, setExpiry] = useState("");
  const [scopes, setScopes] = useState<string[]>([]);
  const [created, setCreated] = useState<CreatedApiToken | null>(null);
  const [error, setError] = useState("");
  const grouped = useMemo(() => groupPermissions(permissions), [permissions]);

  const createMutation = useMutation({
    mutationFn: () =>
      createApiToken({
        name,
        scopes,
        expires_at: expiry ? new Date(`${expiry}T23:59:59`).toISOString() : null
      }),
    onSuccess: (result) => {
      setCreated(result);
      setName("");
      setExpiry("");
      setScopes([]);
      onChanged();
    },
    onError: (requestError) =>
      setError(requestError instanceof Error ? requestError.message : "A token létrehozása sikertelen.")
  });
  const revokeMutation = useMutation({
    mutationFn: revokeApiToken,
    onSuccess: onChanged
  });

  return (
    <section className="token-workspace">
      <div className="token-list-panel">
        <div className="section-heading">
          <div>
            <p className="section-label">Visszavonható hozzáférések</p>
            <h2>API-tokenek</h2>
          </div>
        </div>
        {loading ? (
          <div className="empty-state">Tokenek betöltése…</div>
        ) : tokens.length === 0 ? (
          <div className="empty-state">Még nincs API-token.</div>
        ) : (
          <div className="token-list">
            {tokens.map((token) => (
              <div key={token.id} className={token.revoked_at ? "revoked" : ""}>
                <span className="token-key">
                  <KeyRound aria-hidden="true" />
                </span>
                <div>
                  <strong>{token.name}</strong>
                  <code>{token.token_prefix}…</code>
                  <small>
                    {token.scopes.length} scope ·{" "}
                    {token.last_used_at
                      ? `utoljára ${dateFormatter.format(new Date(token.last_used_at))}`
                      : "még nem használt"}
                  </small>
                </div>
                {!token.revoked_at && (
                  <button
                    className="icon-button danger"
                    title="Token visszavonása"
                    onClick={() => revokeMutation.mutate(token.id)}
                  >
                    <Trash2 aria-hidden="true" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      {canCreate && (
        <div className="token-create-panel">
          <p className="section-label">Új integráció</p>
          <h2>Hatókör kijelölése</h2>
          <label>
            Token neve
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="pl. Készletolvasó BI"
            />
          </label>
          <label>
            Lejárat
            <input
              type="date"
              value={expiry}
              onChange={(event) => setExpiry(event.target.value)}
            />
          </label>
          <div className="token-scope-groups">
            {Object.entries(grouped).map(([category, items]) => (
              <fieldset key={category}>
                <legend>{permissionCategoryLabels[category] ?? category}</legend>
                {items.map((permission) => (
                  <label key={permission.code}>
                    <input
                      type="checkbox"
                      checked={scopes.includes(permission.code)}
                      onChange={(event) =>
                        setScopes((current) =>
                          event.target.checked
                            ? [...current, permission.code]
                            : current.filter((code) => code !== permission.code)
                        )
                      }
                    />
                    <span>{permission.name}</span>
                  </label>
                ))}
              </fieldset>
            ))}
          </div>
          {error && <p className="form-error">{error}</p>}
          <button
            className="primary-button"
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending || !name || scopes.length === 0}
          >
            <Plus aria-hidden="true" />
            Token létrehozása
          </button>
          {created && (
            <div className="raw-token-panel">
              <strong>Másold ki most</strong>
              <span>Biztonsági okból később nem jeleníthető meg újra.</span>
              <code>{created.raw_token}</code>
              <button
                className="secondary-button"
                onClick={() => void navigator.clipboard.writeText(created.raw_token)}
              >
                <Copy aria-hidden="true" />
                Másolás
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
