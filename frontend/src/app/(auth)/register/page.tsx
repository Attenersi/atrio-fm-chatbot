"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getSession, register } from "../../../lib/api";

export default function RegisterPage() {
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

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setMessage("");
    if (!username.trim() || !password.trim()) {
      setMessage("Username and password are required.");
      return;
    }
    setBusy(true);
    try {
      await register(username.trim(), password);
      router.replace("/?registered=1");
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
        <h1 style={{ textAlign: "center", marginBottom: 0 }}>Create account</h1>
        <form onSubmit={onSubmit} className="panel-grid">
          <label htmlFor="reg-username">Username</label>
          <input id="reg-username" className="field" value={username} onChange={(e) => setUsername(e.target.value)} />
          <label htmlFor="reg-password">Password</label>
          <input id="reg-password" type="password" className="field" value={password} onChange={(e) => setPassword(e.target.value)} />
          {message ? <p style={{ margin: 0, color: "var(--color-action-danger)" }}>{message}</p> : null}
          <button type="submit" disabled={busy}>
            {busy ? "Please wait..." : "Create account"}
          </button>
        </form>
        <p style={{ margin: 0, textAlign: "center" }}>
          <Link href="/" className="auth-inline-link">
            Already have an account? Sign in
          </Link>
        </p>
      </div>
    </section>
  );
}
