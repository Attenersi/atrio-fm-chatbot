"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "../../../../../i18n/I18nProvider";
import {
  adminGetTrainingQualitySystemPromptHead,
  adminPutTrainingQualitySystemPromptHead,
  getSession,
  type SystemPromptHeadInfo,
} from "../../../../../lib/api";

function SystemPromptHeadEditor({ onSaved }: { onSaved: () => void }) {
  const { t } = useI18n();
  const [info, setInfo] = useState<SystemPromptHeadInfo | null>(null);
  const [draft, setDraft] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  async function load() {
    setStatus("");
    try {
      const d = await adminGetTrainingQualitySystemPromptHead();
      setInfo(d);
      setDraft(d.effective);
      setIsEditing(false);
    } catch {
      setInfo(null);
      setStatus(t("trainingQuality.systemPromptHead.loadError"));
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    setBusy(true);
    setStatus("");
    try {
      await adminPutTrainingQualitySystemPromptHead(draft);
      await load();
      setIsEditing(false);
      onSaved();
      setStatus(t("trainingQuality.systemPromptHead.saved"));
    } catch (err) {
      setStatus(
        `${t("trainingQuality.systemPromptHead.saveError")} ${(err as Error).message}`
      );
    } finally {
      setBusy(false);
    }
  }

  async function clearOverride() {
    if (!window.confirm(t("trainingQuality.systemPromptHead.clearConfirm"))) {
      return;
    }
    setBusy(true);
    setStatus("");
    try {
      await adminPutTrainingQualitySystemPromptHead("");
      await load();
      setIsEditing(false);
      onSaved();
      setStatus(t("trainingQuality.systemPromptHead.cleared"));
    } catch (err) {
      setStatus(
        `${t("trainingQuality.systemPromptHead.saveError")} ${(err as Error).message}`
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2 className="section-title-sm">
        {t("trainingQuality.systemPromptHead.title")}
      </h2>
      <p className="text-subtle-meta">
        {t("trainingQuality.systemPromptHead.intro")}
      </p>
      <p className="text-subtle-meta u-mt-6">
        {t("trainingQuality.systemPromptHead.rulesHint")}
      </p>
      {!info ? (
        <p className="text-subtle-meta u-mt-8">
          {status || t("trainingQuality.systemPromptHead.loading")}
        </p>
      ) : (
        <>
          <div className="u-mt-8 flex-gap-8-wrap">
            <span
              className={
                info.override_active
                  ? "training-badge training-badge--info"
                  : "training-badge training-badge--ok"
              }
            >
              {info.override_active
                ? t("trainingQuality.systemPromptHead.badgeOverride")
                : t("trainingQuality.systemPromptHead.badgeBuiltin")}
            </span>
            <span className="text-subtle-meta">
              {t("trainingQuality.systemPromptHead.chars", {
                count: draft.length,
              })}
            </span>
          </div>
          {!isEditing && (
            <p className="text-subtle-meta u-mt-8 u-mb-0">
              {t("trainingQuality.systemPromptHead.viewOnlyHint")}
            </p>
          )}
          <textarea
            className={`textarea-tq u-mt-10${!isEditing ? " textarea-tq--readonly" : ""}`}
            rows={20}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            readOnly={!isEditing}
            disabled={busy}
            spellCheck={false}
            aria-readonly={!isEditing}
          />
          <div className="flex-gap-8-wrap-mt8">
            {!isEditing ? (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={busy}
                onClick={() => setIsEditing(true)}
              >
                {t("trainingQuality.systemPromptHead.edit")}
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={busy}
                  onClick={() => void save()}
                >
                  {busy
                    ? t("trainingQuality.systemPromptHead.saving")
                    : t("trainingQuality.systemPromptHead.save")}
                </button>
                <button
                  type="button"
                  className="btn btn-surface btn-sm"
                  disabled={busy || !info}
                  onClick={() => {
                    if (info) setDraft(info.effective);
                    setIsEditing(false);
                  }}
                >
                  {t("trainingQuality.systemPromptHead.cancelEdit")}
                </button>
                <button
                  type="button"
                  className="btn btn-surface btn-sm"
                  disabled={busy || !info}
                  onClick={() => {
                    if (info) setDraft(info.builtin_default);
                  }}
                >
                  {t("trainingQuality.systemPromptHead.fillBuiltin")}
                </button>
                <button
                  type="button"
                  className="btn btn-surface btn-sm"
                  disabled={busy || !info}
                  onClick={() => {
                    if (info) setDraft(info.effective);
                  }}
                >
                  {t("trainingQuality.systemPromptHead.resetEditor")}
                </button>
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  disabled={busy || !info?.override_active}
                  onClick={() => void clearOverride()}
                >
                  {t("trainingQuality.systemPromptHead.clearButton")}
                </button>
              </>
            )}
          </div>
          {!!status && (
            <p className="text-subtle-meta u-mt-8 u-mb-0">{status}</p>
          )}
        </>
      )}
    </section>
  );
}

export default function AdminTrainingQualityPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [ready, setReady] = useState(false);

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

  if (!ready) {
    return <div className="u-p-24">{t("common.checkingAccess")}</div>;
  }

  return (
    <div className="admin-form-page--1100">
      <header className="tq-page-header">
        <h1 className="tq-page-title">{t("nav.trainingQuality")}</h1>
      </header>
      <SystemPromptHeadEditor onSaved={() => undefined} />
    </div>
  );
}
