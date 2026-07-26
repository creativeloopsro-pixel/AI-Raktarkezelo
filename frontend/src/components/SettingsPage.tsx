import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ChevronRight,
  CloudUpload,
  FileSpreadsheet,
  Mail,
  Puzzle,
  ShieldCheck,
  SlidersHorizontal,
  UserCog,
  Wifi,
  WifiOff
} from "lucide-react";

import type { Session } from "../types";
import { APP_VERSION } from "../version";
import AiSettingsPanel from "./AiSettingsPanel";

export type SettingsTarget =
  | "identity"
  | "uploads"
  | "vrp"
  | "email"
  | "plugins";

type Props = {
  session: Session;
  focusAi?: boolean;
  onNavigate: (target: SettingsTarget) => void;
};

type SettingsCard = {
  target: SettingsTarget;
  eyebrow: string;
  title: string;
  description: string;
  action: string;
  icon: typeof ShieldCheck;
  visible: boolean;
};

export default function SettingsPage({
  session,
  focusAi = false,
  onNavigate
}: Props) {
  const [online, setOnline] = useState(() => navigator.onLine);
  const permissions = session.user.permissions ?? [];
  const can = (permission: string) => permissions.includes(permission);

  useEffect(() => {
    const updateConnectivity = () => setOnline(navigator.onLine);
    window.addEventListener("online", updateConnectivity);
    window.addEventListener("offline", updateConnectivity);
    return () => {
      window.removeEventListener("online", updateConnectivity);
      window.removeEventListener("offline", updateConnectivity);
    };
  }, []);

  useEffect(() => {
    if (!focusAi) return;
    window.requestAnimationFrame(() =>
      document.getElementById("ai-settings")?.scrollIntoView({
        behavior: "smooth",
        block: "start"
      })
    );
  }, [focusAi]);

  const cards: SettingsCard[] = [
      {
        target: "identity",
        eyebrow: "Fiók és hozzáférés",
        title: "Felhasználók és biztonság",
        description:
          "Saját MFA, aktív munkamenetek, szerepkörök, engedélyek és API-tokenek.",
        action: "Biztonság megnyitása",
        icon: UserCog,
        visible: true
      },
      {
        target: "uploads",
        eyebrow: "Helyi adatátvitel",
        title: "Offline feltöltések",
        description:
          "Dokumentum- és VRP-fájlok szüneteltethető, folytatható helyi várólistája.",
        action: "Feltöltési sor megnyitása",
        icon: CloudUpload,
        visible: can("documents.upload") || can("vrp.upload")
      },
      {
        target: "vrp",
        eyebrow: "Értékesítési import",
        title: "VRP automatizálás",
        description:
          "Importszabályok, ütemezés, automatikus feldolgozás és visszafordítás.",
        action: "VRP beállítások",
        icon: FileSpreadsheet,
        visible: can("vrp.read")
      },
      {
        target: "email",
        eyebrow: "Dokumentumbeérkezés",
        title: "E-mail csatorna",
        description:
          "Szervezeti fogadócím, feladói engedélylista és automatikus feldolgozás.",
        action: "E-mail beállítások",
        icon: Mail,
        visible: can("email.read")
      },
      {
        target: "plugins",
        eyebrow: "Bővítmények",
        title: "Plugin konfiguráció",
        description:
          "Telepített modulok, engedélyek, saját beállítások és futási napló.",
        action: "Pluginok kezelése",
        icon: Puzzle,
        visible: can("plugins.read")
      }
    ];

  const visibleCards = cards.filter((card) => card.visible);
  const pwaAvailable = "serviceWorker" in navigator;

  return (
    <motion.div
      className="settings-page"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <header className="workspace-header settings-header">
        <div>
          <p className="eyebrow">Rendszer és fiók</p>
          <h1>Beállítások</h1>
          <p className="page-lead">
            A hozzáférésedhez tartozó biztonsági és modulbeállítások egy helyen.
          </p>
        </div>
        <div
          className={`settings-connectivity ${online ? "online" : "offline"}`}
          role="status"
        >
          {online ? <Wifi aria-hidden="true" /> : <WifiOff aria-hidden="true" />}
          <span>
            <small>Kapcsolat</small>
            <strong>{online ? "Online" : "Offline mód"}</strong>
          </span>
        </div>
      </header>

      <section className="settings-status-strip" aria-label="Fiók- és rendszerállapot">
        <div>
          <span>Bejelentkezett fiók</span>
          <strong>{session.user.full_name}</strong>
          <small>{session.user.email}</small>
        </div>
        <div>
          <span>Szerepkör</span>
          <strong>{session.user.roles?.join(", ") || session.user.role}</strong>
          <small>{permissions.length} effektív engedély</small>
        </div>
        <div className={session.user.mfa_enabled ? "secured" : "attention"}>
          <span>MFA-védelem</span>
          <strong>{session.user.mfa_enabled ? "Aktív" : "Nincs beállítva"}</strong>
          <small>
            {session.user.mfa_enabled
              ? "A fiók többtényezős hitelesítést használ"
              : "A Biztonság oldalon kapcsolható be"}
          </small>
        </div>
        <div>
          <span>Alkalmazás</span>
          <strong>v{APP_VERSION}</strong>
          <small>{pwaAvailable ? "Offline PWA támogatás" : "Böngészős munkamenet"}</small>
        </div>
      </section>

      <section className="settings-section">
        <div className="section-heading">
          <div>
            <p className="section-label">Elérhető területek</p>
            <h2>Konfiguráció</h2>
          </div>
          <span className="settings-access-note">
            <ShieldCheck aria-hidden="true" />
            Jogosultság alapján szűrve
          </span>
        </div>

        <div className="settings-card-grid">
          {visibleCards.map((card) => {
            const Icon = card.icon;
            return (
              <button
                key={card.target}
                className="settings-card"
                onClick={() => onNavigate(card.target)}
                aria-label={`${card.title}: ${card.action}`}
              >
                <span className="settings-card-icon">
                  <Icon aria-hidden="true" />
                </span>
                <span className="settings-card-copy">
                  <small>{card.eyebrow}</small>
                  <strong>{card.title}</strong>
                  <span>{card.description}</span>
                  <em>
                    {card.action}
                    <ChevronRight aria-hidden="true" />
                  </em>
                </span>
              </button>
            );
          })}
        </div>
      </section>

      {can("settings.read") ? (
        <div id="ai-settings" className="settings-anchor-section">
          <AiSettingsPanel canWrite={can("settings.write")} />
        </div>
      ) : null}

      <section className="settings-runtime">
        <SlidersHorizontal aria-hidden="true" />
        <div>
          <strong>Modulonként kezelt beállítások</strong>
          <span>
            A módosítható üzleti értékek a hozzájuk tartozó modulban jelennek meg,
            és minden mentés a szervezeti jogosultságokkal védett.
          </span>
        </div>
      </section>
    </motion.div>
  );
}
