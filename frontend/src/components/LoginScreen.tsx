import { FormEvent, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Boxes, KeyRound, ShieldCheck } from "lucide-react";

import { login, verifyMfa } from "../lib/api";
import type { Session } from "../types";
import { APP_VERSION } from "../version";

type Props = {
  onAuthenticated: (session: Session) => void;
};

export default function LoginScreen({ onAuthenticated }: Props) {
  const [organization, setOrganization] = useState("mintabolt");
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [challengeToken, setChallengeToken] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (challengeToken) {
        onAuthenticated(await verifyMfa(challengeToken, mfaCode));
      } else {
        const result = await login(organization, email, password);
        if ("mfa_required" in result) {
          setChallengeToken(result.challenge_token);
          setPassword("");
          return;
        }
        onAuthenticated(result);
      }
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
            <h2>{challengeToken ? "MFA ellenőrzés" : "Belépés"}</h2>
            <p>
              {challengeToken
                ? "Írd be a hitelesítő alkalmazás vagy egy helyreállító kód értékét."
                : "Add meg a szervezeted és a felhasználói fiókod."}
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          {challengeToken ? (
            <>
              <label>
                Egyszer használatos vagy helyreállító kód
                <input
                  value={mfaCode}
                  onChange={(event) => setMfaCode(event.target.value)}
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  placeholder="123456"
                  autoFocus
                  required
                />
              </label>
              <button
                className="text-button login-switch-account"
                type="button"
                onClick={() => {
                  setChallengeToken("");
                  setMfaCode("");
                  setError("");
                }}
              >
                Másik fiókkal lépek be
              </button>
            </>
          ) : (
            <>
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
            </>
          )}
          {error && <p className="form-error">{error}</p>}
          <button className="primary-button login-button" type="submit" disabled={busy}>
            <span>
              {busy
                ? "Ellenőrzés…"
                : challengeToken
                  ? "MFA megerősítése"
                  : "Belépés a raktárba"}
            </span>
            <ArrowRight aria-hidden="true" />
          </button>
        </form>
        <p className="version-label">Rendszerverzió {APP_VERSION}</p>
      </motion.section>
    </main>
  );
}
