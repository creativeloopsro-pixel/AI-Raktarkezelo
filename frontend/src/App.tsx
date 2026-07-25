import { useEffect, useState } from "react";

import Dashboard from "./components/Dashboard";
import LoginScreen from "./components/LoginScreen";
import { clearSession, logout, readSession, saveSession } from "./lib/api";
import type { Session } from "./types";

export default function App() {
  const [session, setSession] = useState<Session | null>(() => readSession());

  useEffect(() => {
    const expire = () => setSession(null);
    window.addEventListener("session-expired", expire);
    return () => window.removeEventListener("session-expired", expire);
  }, []);

  if (!session) {
    return (
      <LoginScreen
        onAuthenticated={(nextSession) => {
          saveSession(nextSession);
          setSession(nextSession);
        }}
      />
    );
  }

  return (
    <Dashboard
      session={session}
      onLogout={() => {
        void logout().catch(() => undefined);
        clearSession();
        setSession(null);
      }}
    />
  );
}
