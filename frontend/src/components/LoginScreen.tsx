import { FormEvent, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Boxes, KeyRound, ShieldCheck } from "lucide-react";

import { login } from "../lib/api";
import type { Session } from "../types";

type Props = {
  onAuthenticated: (session: Session) => void;
};

export default function LoginScreen({ onAuthenticated }: Props) {
  const [organization, setOrganization] = useState("mintabolt");
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onAuthenticated(await login(organization, email, password));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "A belépés sikertelen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-shell">
      <motion.section
        className="login-brand"
        initial={{ opacity: 0, x: -24 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.45, ease: "easeOut" }}
      >
        <div className="brand-mark">
          <Boxes aria-hidden="true" />
        </div>
        <div>
          <p className="eyebrow">AI Raktárkezelő</p>
          <h1>A készlet, amiben meg lehet bízni.</h1>
          <p className="login-lead">
            Minden bevételezés, korrekció és visszavonás egyetlen auditált
            mozgássorban.
          </p>
        </div>
        <div className="trust-line">
          <ShieldCheck aria-hidden="true" />
          <span>Tranzakciós készlet</span>
          <span>·</span>
          <span>Teljes audit</span>
        </div>
      </motion.section>

      <motion.section
        className="login-panel"
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.12 }}
      >
        <div className="login-panel-heading">
          <KeyRound aria-hidden="true" />
          <div>
            <h2>Belépés</h2>
            <p>Add meg a szervezeted és a felhasználói fiókod.</p>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <label>
            Szervezet
            <input
              value={organization}
              onChange={(event) => setOrganization(event.target.value)}
              autoComplete="organization"
              required
            />
          </label>
          <label>
            E-mail
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
            />
          </label>
          <label>
            Jelszó
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              placeholder="Legalább 8 karakter"
              required
            />
          </label>
          {error && <p className="form-error">{error}</p>}
          <button className="primary-button login-button" type="submit" disabled={busy}>
            <span>{busy ? "Ellenőrzés…" : "Belépés a raktárba"}</span>
            <ArrowRight aria-hidden="true" />
          </button>
        </form>
        <p className="version-label">Rendszerverzió 0.2.0</p>
      </motion.section>
    </main>
  );
}
