"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "../../../../../i18n/I18nProvider";
import {
  adminCreateLlmProfile,
  adminDeleteLlmProfile,
  adminGetLlmTaskDefaults,
  adminListLlmProfiles,
  adminPatchLlmProfile,
  adminProbeLlmProfile,
  adminPutLlmTaskDefaults,
  getSession,
  isLlmProfileProbeFull,
  type LlmModelProfile,
  type LlmProfileProbeFullResponse,
  type LlmProfileProbeQuickResponse,
} from "../../../../../lib/api";

const TASKS = [
  "chat",
  "analyzer",
  "analyzer_repair",
  "consolidator",
  "replay",
  "embed",
  "health",
] as const;

export default function AdminLlmPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [profiles, setProfiles] = useState<LlmModelProfile[]>([]);
  const [defaults, setDefaults] = useState<Record<string, number | null>>({});
  const [status, setStatus] = useState("");
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("https://integrate.api.nvidia.com/v1");
  const [model, setModel] = useState("meta/llama-3.1-70b-instruct");
  const [apiKey, setApiKey] = useState("");
  const [envAlias, setEnvAlias] = useState("");
  const [includeDisabled, setIncludeDisabled] = useState(false);

  useEffect(() => {
    getSession()
      .then((res) => {
        if (res.user.role !== "admin") {
          router.replace("/chat");
          return;
        }
        setReady(true);
      })
      .catch(() => router.replace("/"));
  }, [router]);

  async function refresh() {
    try {
      const [p, d] = await Promise.all([
        adminListLlmProfiles(includeDisabled),
        adminGetLlmTaskDefaults(),
      ]);
      setProfiles(p.profiles);
      setDefaults(d.defaults);
    } catch (e) {
      setStatus((e as Error).message || t("llm.loadFailed"));
    }
  }

  useEffect(() => {
    if (!ready) return;
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, includeDisabled]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setStatus(t("llm.creating"));
    try {
      await adminCreateLlmProfile({
        name: name.trim(),
        base_url: baseUrl.trim(),
        default_model: model.trim(),
        api_key: apiKey.trim() || undefined,
        env_alias: envAlias.trim() || undefined,
      });
      setName("");
      setApiKey("");
      setEnvAlias("");
      setStatus(t("llm.profileCreated"));
      await refresh();
    } catch (err) {
      setStatus((err as Error).message || t("llm.error"));
    }
  }

  async function onSaveDefaults() {
    setStatus(t("llm.savingDefaults"));
    try {
      await adminPutLlmTaskDefaults(defaults);
      setStatus(t("llm.defaultsSaved"));
      await refresh();
    } catch (err) {
      setStatus((err as Error).message || t("llm.error"));
    }
  }

  if (!ready)
    return <div className="admin-form-page">{t("llm.checkAccess")}</div>;

  return (
    <div className="admin-form-page">
      <header className="page-header-block">
        <h1 className="page-title-md">{t("llm.title")}</h1>
        <p className="text-subtle-meta" style={{ marginTop: 6, fontSize: "0.9rem" }}>
          {t("llm.introBefore")}{" "}
          <Link href="/admin/training-quality" className="auth-inline-link">
            {t("llm.introLink")}
          </Link>{" "}
          {t("llm.introAfter")}
        </p>
        <p className="text-subtle-meta" style={{ marginTop: 4, fontSize: "0.85rem" }}>
          {t("llm.storageHint")}
        </p>
      </header>

      {status ? (
        <p className="text-subtle" style={{ fontSize: "0.88rem", marginBottom: 12 }}>
          {status}
        </p>
      ) : null}

      <section className="card panel-grid u-mb-16">
        <h2 className="card-title-sm" style={{ marginTop: 0 }}>
          {t("llm.newProfile")}
        </h2>
        <p className="text-subtle-meta" style={{ fontSize: "0.84rem" }}>
          {t("llm.newProfileHint")}
        </p>
        <form onSubmit={onCreate} className="form-narrow">
          <label className="label-stack-sm">
            {t("llm.labelName")}
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </label>
          <label className="label-stack-sm">
            {t("llm.labelBaseUrl")}
            <input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              required
            />
          </label>
          <label className="label-stack-sm">
            {t("llm.labelDefaultModel")}
            <input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              required
            />
          </label>
          <label className="label-stack-sm">
            {t("llm.labelApiKey")}
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              autoComplete="off"
            />
          </label>
          <label className="label-stack-sm">
            {t("llm.labelEnvAlias")}
            <input
              value={envAlias}
              onChange={(e) => setEnvAlias(e.target.value)}
              placeholder="LLM_API_KEY"
            />
          </label>
          <button type="submit" className="btn btn-secondary btn-sm" style={{ justifySelf: "start" }}>
            {t("llm.createProfile")}
          </button>
        </form>
      </section>

      <section className="card panel-grid u-mb-16">
        <div className="profile-card-head">
          <h2 className="profile-card-title">{t("llm.defaultPerTask")}</h2>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => void onSaveDefaults()}
          >
            {t("llm.saveMapping")}
          </button>
        </div>
        <div className="stack-gap-8-mt">
          {TASKS.map((task) => (
            <label
              key={task}
              className="label-inline"
              style={{ flexWrap: "wrap", fontSize: "0.88rem", gap: 10 }}
            >
              <span className="w-fixed-140">{task}</span>
              <select
                value={defaults[task] ?? ""}
                onChange={(e) =>
                  setDefaults((d) => ({
                    ...d,
                    [task]: e.target.value ? Number(e.target.value) : null,
                  }))
                }
                className="field field-min-220"
              >
                <option value="">{t("llm.optionEnv")}</option>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      </section>

      <section className="card panel-grid">
        <div className="profile-card-head">
          <h2 className="profile-card-title">{t("llm.profilesHeading")}</h2>
          <label className="label-inline" style={{ fontSize: "0.86rem" }}>
            <input
              type="checkbox"
              checked={includeDisabled}
              onChange={(e) => setIncludeDisabled(e.target.checked)}
            />
            {t("llm.showDisabled")}
          </label>
        </div>
        <div className="rag-mt panel-grid">
          {profiles.length === 0 ? (
            <p className="text-subtle-meta">{t("llm.noProfiles")}</p>
          ) : (
            profiles.map((p) => (
              <ProfileRow
                key={p.id}
                profile={p}
                onChanged={() => void refresh()}
                onProbeMessage={(msg) => setStatus(msg)}
              />
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function ProfileRow(props: {
  profile: LlmModelProfile;
  onChanged: () => void;
  onProbeMessage: (msg: string) => void;
}) {
  const { profile: p, onChanged, onProbeMessage } = props;
  const { t } = useI18n();
  const [disabled, setDisabled] = useState(!!p.disabled);
  const [busy, setBusy] = useState(false);
  const [fullReport, setFullReport] = useState<LlmProfileProbeFullResponse | null>(
    null
  );
  const [rowNote, setRowNote] = useState<string | null>(null);

  useEffect(() => {
    setDisabled(!!p.disabled);
  }, [p.disabled]);

  useEffect(() => {
    setRowNote(null);
    setFullReport(null);
  }, [p.id]);

  async function toggleDisabled() {
    setBusy(true);
    try {
      await adminPatchLlmProfile(p.id, { disabled: !disabled });
      setDisabled((d) => !d);
      onChanged();
    } catch {
      /* parent refresh */
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(t("llm.deleteConfirm", { name: p.name }))) return;
    setBusy(true);
    try {
      await adminDeleteLlmProfile(p.id);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function probeQuick() {
    setBusy(true);
    setFullReport(null);
    setRowNote(null);
    onProbeMessage(t("llm.probeTesting", { id: p.id }));
    try {
      const r = await adminProbeLlmProfile(p.id, { mode: "quick" });
      if (isLlmProfileProbeFull(r)) {
        setFullReport(r);
        const line = r.summary;
        setRowNote(line);
        onProbeMessage(line);
        return;
      }
      const q = r as LlmProfileProbeQuickResponse;
      const line = t("llm.probeOk", {
        snippet: q.snippet || "—",
        baseUrl: q.base_url || "—",
        model: q.model || "—",
      });
      setRowNote(line);
      onProbeMessage(line);
    } catch (err) {
      const msg = (err as Error).message || t("llm.probeFailed");
      setRowNote(msg);
      onProbeMessage(msg);
    } finally {
      setBusy(false);
    }
  }

  async function probeFull() {
    setBusy(true);
    setFullReport(null);
    setRowNote(null);
    onProbeMessage(t("llm.probeFullRunning", { id: p.id }));
    try {
      const r = await adminProbeLlmProfile(p.id, { mode: "full" });
      if (!isLlmProfileProbeFull(r)) {
        const legacy =
          typeof r === "object" &&
          r !== null &&
          "snippet" in r &&
          !("base_url" in r) &&
          !("steps" in r);
        const msg = legacy
          ? t("llm.probeLegacyServer")
          : t("llm.probeFullUnexpected");
        setRowNote(msg);
        onProbeMessage(msg);
        return;
      }
      setFullReport(r);
      setRowNote(r.summary);
      onProbeMessage(r.summary);
    } catch (err) {
      const msg = (err as Error).message || t("llm.probeFailed");
      setRowNote(msg);
      onProbeMessage(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={`llm-profile-row${p.disabled ? " is-disabled" : ""}`}
    >
      <div className="llm-profile-title">
        #{p.id} {p.name}{" "}
        <span className="llm-profile-model">{p.default_model}</span>
      </div>
      <div className="llm-profile-url">{p.base_url}</div>
      <div className="llm-profile-keyline">
        {t("llm.keyLine", {
          keyState: p.has_api_key
            ? t("llm.keyConfigured")
            : t("llm.keyMissing"),
          env: p.env_alias || "—",
        })}
      </div>
      <div className="flex-gap-8-wrap u-mt-8">
        <button
          type="button"
          className="btn btn-surface btn-sm"
          onClick={() => void probeQuick()}
          disabled={busy}
        >
          {t("llm.probe")}
        </button>
        <button
          type="button"
          className="btn btn-surface btn-sm"
          onClick={() => void probeFull()}
          disabled={busy}
          title={t("llm.probeFullHint")}
        >
          {t("llm.probeFull")}
        </button>
        <button
          type="button"
          className="btn btn-surface btn-sm"
          onClick={() => void toggleDisabled()}
          disabled={busy}
        >
          {disabled ? t("llm.enable") : t("llm.disable")}
        </button>
        <button
          type="button"
          className="btn btn-danger btn-sm"
          onClick={() => void remove()}
          disabled={busy}
        >
          {t("llm.remove")}
        </button>
      </div>
      {rowNote ? (
        <p
          className="text-subtle-meta u-mt-8"
          style={{ fontSize: "0.82rem", lineHeight: 1.45, margin: 0 }}
        >
          {rowNote}
        </p>
      ) : null}
      {fullReport ? (
        <div
          className="card u-mt-10"
          style={{
            padding: "12px 14px",
            fontSize: "0.82rem",
            borderColor: "color-mix(in srgb, var(--color-border) 90%, transparent)",
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 8 }}>{t("llm.probeReportTitle")}</div>
          <p className="text-subtle-meta" style={{ margin: "0 0 8px" }}>
            {fullReport.summary}
          </p>
          <div className="text-subtle-meta" style={{ marginBottom: 4 }}>
            <strong>{t("llm.probeColUrl")}</strong> {fullReport.base_url}
          </div>
          <div className="text-subtle-meta" style={{ marginBottom: 4 }}>
            <strong>{t("llm.probeColChatModel")}</strong> {fullReport.model}
          </div>
          <div className="text-subtle-meta" style={{ marginBottom: 10 }}>
            <strong>{t("llm.probeColEmbedModel")}</strong> {fullReport.embed_model}{" "}
            <span style={{ opacity: 0.85 }}>({t("llm.probeEmbedFromEnv")})</span>
          </div>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "0.8rem",
            }}
          >
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid var(--color-border, #333)" }}>
                <th style={{ padding: "6px 8px 6px 0" }}>{t("llm.probeColStep")}</th>
                <th style={{ padding: "6px 8px" }}>{t("llm.probeColOk")}</th>
                <th style={{ padding: "6px 8px" }}>{t("llm.probeColMs")}</th>
                <th style={{ padding: "6px 0 6px 8px" }}>{t("llm.probeColDetail")}</th>
              </tr>
            </thead>
            <tbody>
              {fullReport.steps.map((s) => (
                <tr
                  key={s.id}
                  style={{ borderBottom: "1px solid color-mix(in srgb, var(--color-border) 50%, transparent)" }}
                >
                  <td style={{ padding: "6px 8px 6px 0", verticalAlign: "top" }}>{s.id}</td>
                  <td style={{ padding: "6px 8px", verticalAlign: "top" }}>
                    {s.ok ? t("llm.probeYes") : t("llm.probeNo")}
                  </td>
                  <td style={{ padding: "6px 8px", verticalAlign: "top" }}>{s.ms}</td>
                  <td style={{ padding: "6px 0 6px 8px", verticalAlign: "top", wordBreak: "break-word" }}>
                    {s.detail}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
