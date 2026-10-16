/* SPDX-FileCopyrightText: 2026 BidWeave contributors
 * SPDX-License-Identifier: Apache-2.0
 * PKCE session integration; tokens stay in memory, never in localStorage.
 */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import Keycloak from "keycloak-js";
import { setTokenProvider } from "./api";

type AuthState = {
  ready: boolean;
  authenticated: boolean;
  error?: string;
  login: () => void;
  logout: () => void;
};
const AuthContext = createContext<AuthState | undefined>(undefined);
const staticSite = import.meta.env.VITE_STATIC_SITE === "true";
const base = `${window.location.origin}${import.meta.env.BASE_URL}`;
const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL || "http://localhost:8091",
  realm: import.meta.env.VITE_KEYCLOAK_REALM || "bidweave",
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT || "bidweave-web",
});
// A single initialization promise survives React StrictMode effect replay.
let initialized: Promise<boolean> | undefined;
export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    ready: staticSite,
    authenticated: false,
    login: () => {
      window.location.assign(`${base}app`);
    },
    logout: () => {
      void keycloak.logout({ redirectUri: base });
    },
  });
  useEffect(() => {
    if (staticSite) return;
    let alive = true;
    initialized ??= keycloak.init({
      onLoad: /\/app(?:\/|$)/.test(window.location.pathname)
        ? "login-required"
        : undefined,
      pkceMethod: "S256",
      checkLoginIframe: false,
    });
    initialized
      .then((authenticated) => {
        if (!alive) return;
        setTokenProvider(async () => {
          if (!keycloak.authenticated) return undefined;
          await keycloak.updateToken(30);
          return keycloak.token;
        });
        keycloak.onAuthLogout = () =>
          setState((s) => ({ ...s, authenticated: false }));
        setState((s) => ({ ...s, ready: true, authenticated }));
      })
      .catch((error) => {
        if (alive)
          setState((s) => ({
            ...s,
            ready: true,
            error:
              error instanceof Error
                ? error.message
                : "Không kết nối được dịch vụ định danh.",
          }));
      });
    return () => {
      alive = false;
    };
  }, []);
  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
}
export function useAuth() {
  const state = useContext(AuthContext);
  if (!state) throw new Error("AuthProvider is required");
  return state;
}
