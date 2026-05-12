"use client";

import { useEffect, useState } from "react";
import { useI18n } from "../../i18n/I18nProvider";
import { adminListUsers, adminUpdateUser, getSession, type AdminUserRow } from "../../lib/api";

type UserEdit = { email: string; role: "admin" | "user"; active: boolean };

export function AdminUsersPanel() {
  const { locale, t } = useI18n();
  const tr = (en: string, nl: string) => (locale === "nl" ? nl : en);
  const [adminUsername, setAdminUsername] = useState("");
  const [adminUserId, setAdminUserId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [userEdits, setUserEdits] = useState<Record<number, UserEdit>>({});
  const [userBusyId, setUserBusyId] = useState<number | null>(null);
  const [status, setStatus] = useState(
    tr("Sign in to load users.", "Log in om gebruikers te laden.")
  );

  const hasSession = Boolean(adminUsername);

  useEffect(() => {
    getSession()
      .then((res) => {
        if (res.user.role !== "admin") return;
        setAdminUsername(res.user.username);
        setAdminUserId(res.user.id);
      })
      .catch(() => {});
  }, []);

  async function loadUsers({ quiet }: { quiet?: boolean } = {}) {
    if (!hasSession) return;
    if (!quiet) setStatus("Loading users...");
    try {
      const res = await adminListUsers();
      setUsers(res.users);
      const next: Record<number, UserEdit> = {};
      for (const u of res.users) {
        next[u.id] = {
          email: u.email ?? "",
          role: u.role,
          active: Boolean(u.is_active),
        };
      }
      setUserEdits(next);
      if (!quiet) setStatus(`Loaded ${res.users.length} users.`);
    } catch (err) {
      setStatus(`Users load failed: ${(err as Error).message}`);
    }
  }

  useEffect(() => {
    if (!adminUsername) return;
    void loadUsers({ quiet: true });
  }, [adminUsername]);

  async function saveUserRow(userId: number) {
    const edit = userEdits[userId];
    if (!edit || !hasSession) return;
    setUserBusyId(userId);
    setStatus(`Saving user #${userId}...`);
    try {
      await adminUpdateUser(userId, {
        role: edit.role,
        is_active: edit.active,
        email: edit.email.trim() ? edit.email.trim() : null,
      });
      await loadUsers({ quiet: true });
      setStatus(`User #${userId} updated.`);
    } catch (err) {
      setStatus(`User update failed: ${(err as Error).message}`);
    } finally {
      setUserBusyId(null);
    }
  }

  return (
    <>
      <div className="card panel-grid">
        <h3>{t("adminSettings.tabsUsers")}</h3>
        <p style={{ margin: 0, color: "var(--muted)" }}>
          {tr(
            "Set roles, active flag, and optional email (for ticket status notifications). At least one active admin is required.",
            "Stel rollen, active-flag en optionele e-mail in (voor ticketstatusmeldingen). Minimaal één actieve admin is vereist."
          )}
        </p>
        <div className="toolbar">
          <button
            type="button"
            onClick={() => loadUsers()}
            disabled={busy || !hasSession}
          >
            {t("adminSettings.refresh")} {tr("users", "gebruikers")}
          </button>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th align="left">ID</th>
                <th align="left">{tr("Username", "Gebruikersnaam")}</th>
                <th align="left">{tr("Email", "E-mail")}</th>
                <th align="left">{tr("Role", "Rol")}</th>
                <th align="left">{tr("Active", "Actief")}</th>
                <th align="left">{tr("Action", "Actie")}</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const edit = userEdits[u.id];
                const self = adminUserId === u.id;
                return (
                  <tr key={u.id}>
                    <td>{u.id}</td>
                    <td>{u.username}</td>
                    <td>
                      <input
                        className="field"
                        style={{ minWidth: 180 }}
                        value={edit?.email ?? ""}
                        onChange={(e) =>
                          setUserEdits((prev) => ({
                            ...prev,
                            [u.id]: {
                              ...(prev[u.id] ?? {
                                email: "",
                                role: u.role,
                                active: !!u.is_active,
                              }),
                              email: e.target.value,
                            },
                          }))
                        }
                        placeholder={tr("optional", "optioneel")}
                      />
                    </td>
                    <td>
                      <select
                        className="field"
                        style={{ width: 120 }}
                        value={edit?.role ?? u.role}
                        onChange={(e) =>
                          setUserEdits((prev) => ({
                            ...prev,
                            [u.id]: {
                              ...(prev[u.id] ?? {
                                email: u.email ?? "",
                                role: u.role,
                                active: !!u.is_active,
                              }),
                              role: e.target.value as "admin" | "user",
                            },
                          }))
                        }
                      >
                        <option value="user">
                          {tr("user", "gebruiker")}
                        </option>
                        <option value="admin">admin</option>
                      </select>
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={edit?.active ?? !!u.is_active}
                        disabled={self}
                        title={
                          self
                            ? tr(
                                "Use another admin to deactivate this account",
                                "Gebruik een andere admin om dit account te deactiveren"
                              )
                            : undefined
                        }
                        onChange={(e) =>
                          setUserEdits((prev) => ({
                            ...prev,
                            [u.id]: {
                              ...(prev[u.id] ?? {
                                email: u.email ?? "",
                                role: u.role,
                                active: !!u.is_active,
                              }),
                              active: e.target.checked,
                            },
                          }))
                        }
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        onClick={() => saveUserRow(u.id)}
                        disabled={userBusyId !== null || !hasSession}
                      >
                        {userBusyId === u.id
                          ? tr("Saving...", "Opslaan...")
                          : t("adminSettings.save")}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {users.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ color: "var(--muted)" }}>
                    {t("adminSettings.noUsersLoaded")}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
      <p style={{ marginTop: 12 }}>{status}</p>
    </>
  );
}
