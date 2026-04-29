"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getSession, login } from "../../lib/api";

export default function AuthHomePage() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    getSession()
      .then((res) => {
        router.replace(res.user.role === "admin" ? "/admin" : "/chat");
      })
      .catch(() => setChecking(false));
  }, [router]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const u = new URL(window.location.href);
    if (u.searchParams.get("registered") === "1") {
      setMessage("Account created. Sign in now.");
      u.searchParams.delete("registered");
      const next = u.pathname + (u.searchParams.toString() ? `?${u.searchParams}` : "");
      window.history.replaceState({}, "", next || u.pathname);
    }
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setMessage("");
    if (!username.trim() || !password.trim()) {
      setMessage("Username and password are required.");
      return;
    }
    setBusy(true);
    try {
      const res = await login(username.trim(), password);
      router.replace(res.user.role === "admin" ? "/admin" : "/chat");
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (checking) {
    return (
      <section className="page-shell auth-inline-center">
        <p className="text-muted">Loading...</p>
      </section>
    );
  }

  return (
    <section className="page-shell auth-center-shell">
      <div className="auth-header-strip" aria-hidden />
      <div className="card auth-card panel-grid">
        <h1 style={{ textAlign: "center", marginBottom: 0 }}>Sign in</h1>
        <form onSubmit={onSubmit} className="panel-grid">
          <label htmlFor="auth-username">Username</label>
          <input id="auth-username" className="field" value={username} onChange={(e) => setUsername(e.target.value)} />
          <label htmlFor="auth-password">Password</label>
          <input id="auth-password" type="password" className="field" value={password} onChange={(e) => setPassword(e.target.value)} />
          {message ? (
            <p
              style={{
                margin: 0,
                color: message.includes("created") ? "var(--color-success)" : "var(--color-action-danger)",
              }}
            >
              {message}
            </p>
          ) : null}
          <button type="submit" disabled={busy}>
            {busy ? "Please wait..." : "Sign in"}
          </button>
        </form>
        <p style={{ margin: 0, textAlign: "center" }}>
          <Link href="/register" className="auth-inline-link">
            Create an account
          </Link>
        </p>
        <p style={{ margin: 0, textAlign: "center", color: "var(--muted)" }}>
          Admin role is detected automatically after successful sign in.
        </p>
      </div>
    </section>
  );
}
