"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "../../../../../i18n/I18nProvider";
import {
  adminGetRagEvalJob,
  adminStartRagEvalJob,
  getSession,
  type RagEvalJob,
  type RagEvalResultRow,
} from "../../../../../lib/api";

function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function AdminRagEvalPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState("");
  const [suiteKind, setSuiteKind] = useState<"builtin" | "json" | "csv">(
    "builtin"
  );
  const [suiteFile, setSuiteFile] = useState<File | null>(null);
  const [compareFile, setCompareFile] = useState<File | null>(null);
  const [caseIds, setCaseIds] = useState("");
  const [runId, setRunId] = useState("");
  const [sourceRef, setSourceRef] = useState("");
  const [sleepBetween, setSleepBetween] = useState("15");
  const [maxRetries, setMaxRetries] = useState("3");
  const [retryWait, setRetryWait] = useState("10");
  const [timeoutSec, setTimeoutSec] = useState("240");
  const [minApiOkRate, setMinApiOkRate] = useState("");
  const [minApiOkCount, setMinApiOkCount] = useState("0");
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<RagEvalJob | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => stopPoll();
  }, [stopPoll]);

  async function startJob() {
    setStatus("");
    if (suiteKind !== "builtin" && !suiteFile) {
      setStatus(t("ragEval.chooseSuiteFile"));
      return;
    }
    const form = new FormData();
    form.append("suite", suiteKind);
    form.append("case_ids", caseIds.trim());
    form.append("run_id", runId.trim());
    form.append("source_ref", sourceRef.trim());
    form.append("sleep_between_seconds", sleepBetween.trim() || "15");
    form.append("max_retries", maxRetries.trim() || "3");
    form.append("retry_wait_seconds", retryWait.trim() || "10");
    form.append(
      "per_request_timeout_seconds",
      timeoutSec.trim() || "240"
    );
    form.append("min_api_ok_pass_rate", minApiOkRate.trim());
    form.append("min_api_ok_count", minApiOkCount.trim() || "0");
    if (suiteFile) {
      form.append("suite_file", suiteFile);
    }
    if (compareFile) {
      form.append("compare_file", compareFile);
    }
    try {
      const res = await adminStartRagEvalJob(form);
      setJobId(res.job_id);
      setJob(null);
      setStatus(`Job started: ${res.job_id}`);
      stopPoll();
      pollRef.current = setInterval(async () => {
        try {
          const j = await adminGetRagEvalJob(res.job_id);
          setJob(j.job);
          if (j.job.status === "completed" || j.job.status === "failed") {
            stopPoll();
            if (j.job.status === "failed") {
              setStatus(`Job failed: ${j.job.error || "unknown error"}`);
            } else {
              setStatus(
                j.job.gate_ok === false
                  ? `Completed with gate warning: ${j.job.gate_message || ""}`
                  : "Completed."
              );
            }
          }
        } catch (e) {
          setStatus(`Poll error: ${(e as Error).message}`);
          stopPoll();
        }
      }, 1500);
    } catch (e) {
      setStatus(`Start failed: ${(e as Error).message}`);
    }
  }

  if (!ready) {
    return (
      <section className="page-shell">
        <h1>{t("ragEval.pageTitle")}</h1>
        <p>{t("common.checkingSession")}</p>
      </section>
    );
  }

  const rows: RagEvalResultRow[] = job?.results ?? [];
  const report = job?.report;

  return (
    <section className="page-shell">
      <h1>{t("ragEval.pageTitle")}</h1>
      <p className="text-subtle-meta" style={{ maxWidth: 720 }}>
        {t("ragEval.pageSubtitle")}
      </p>

      <div className="card">
        <h2 className="card-title-sm">{t("ragEval.suiteHeading")}</h2>
        <div className="flex-wrap-gap">
          <label className="label-inline">
            <input
              type="radio"
              name="suite"
              checked={suiteKind === "builtin"}
              onChange={() => setSuiteKind("builtin")}
            />
            {t("ragEval.suiteBuiltin")}
          </label>
          <label className="label-inline">
            <input
              type="radio"
              name="suite"
              checked={suiteKind === "json"}
              onChange={() => setSuiteKind("json")}
            />
            {t("ragEval.suiteJson")}
          </label>
          <label className="label-inline">
            <input
              type="radio"
              name="suite"
              checked={suiteKind === "csv"}
              onChange={() => setSuiteKind("csv")}
            />
            {t("ragEval.suiteCsv")}
          </label>
        </div>
        {suiteKind !== "builtin" && (
          <div className="rag-mt">
            <input
              type="file"
              accept={
                suiteKind === "json" ? ".json,application/json" : ".csv,text/csv"
              }
              onChange={(e) => setSuiteFile(e.target.files?.[0] ?? null)}
            />
          </div>
        )}
        <div className="rag-mt">
          <span className="text-subtle-meta" style={{ display: "block", marginBottom: 4 }}>
            {t("ragEval.compareHint")}
          </span>
          <input
            type="file"
            accept=".json,application/json"
            onChange={(e) => setCompareFile(e.target.files?.[0] ?? null)}
          />
        </div>
      </div>

      <div className="card">
        <h2 className="card-title-sm">{t("ragEval.optionsHeading")}</h2>
        <div className="form-grid-options">
          <label className="label-stack">
            <span className="text-subtle-meta">{t("ragEval.labels.caseIds")}</span>
            <input
              className="field"
              value={caseIds}
              onChange={(e) => setCaseIds(e.target.value)}
              placeholder={t("ragEval.placeholders.caseIds")}
            />
          </label>
          <label className="label-stack">
            <span className="text-subtle-meta">{t("ragEval.labels.runId")}</span>
            <input
              className="field"
              value={runId}
              onChange={(e) => setRunId(e.target.value)}
            />
          </label>
          <label className="label-stack">
            <span className="text-subtle-meta">{t("ragEval.labels.sourceRef")}</span>
            <input
              className="field"
              value={sourceRef}
              onChange={(e) => setSourceRef(e.target.value)}
              placeholder={t("ragEval.placeholders.sourceRef")}
            />
          </label>
          <label className="label-stack">
            <span className="text-subtle-meta">{t("ragEval.labels.sleepBetween")}</span>
            <input
              className="field"
              value={sleepBetween}
              onChange={(e) => setSleepBetween(e.target.value)}
            />
          </label>
          <label className="label-stack">
            <span className="text-subtle-meta">{t("ragEval.labels.maxRetries")}</span>
            <input
              className="field"
              value={maxRetries}
              onChange={(e) => setMaxRetries(e.target.value)}
            />
          </label>
          <label className="label-stack">
            <span className="text-subtle-meta">{t("ragEval.labels.retryWait")}</span>
            <input
              className="field"
              value={retryWait}
              onChange={(e) => setRetryWait(e.target.value)}
            />
          </label>
          <label className="label-stack">
            <span className="text-subtle-meta">{t("ragEval.labels.timeout")}</span>
            <input
              className="field"
              value={timeoutSec}
              onChange={(e) => setTimeoutSec(e.target.value)}
            />
          </label>
          <label className="label-stack">
            <span className="text-subtle-meta">{t("ragEval.labels.minPassRate")}</span>
            <input
              className="field"
              value={minApiOkRate}
              onChange={(e) => setMinApiOkRate(e.target.value)}
              placeholder={t("ragEval.placeholders.optional")}
            />
          </label>
          <label className="label-stack">
            <span className="text-subtle-meta">{t("ragEval.labels.minCount")}</span>
            <input
              className="field"
              value={minApiOkCount}
              onChange={(e) => setMinApiOkCount(e.target.value)}
            />
          </label>
        </div>
        <div className="rag-mt">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void startJob()}
          >
            {t("ragEval.startJob")}
          </button>
        </div>
        {status ? (
          <p className="text-subtle-meta rag-mt" style={{ marginBottom: 0 }}>
            {status}
          </p>
        ) : null}
        {jobId ? (
          <p className="text-muted" style={{ marginTop: 8, fontSize: "0.86rem" }}>
            Job ID: <code>{jobId}</code>
            {job ? (
              <>
                {" "}
                — status: <strong>{job.status}</strong>
                {job.progress ? (
                  <>
                    {" "}
                    ({job.progress.done}/{job.progress.total})
                  </>
                ) : null}
              </>
            ) : null}
          </p>
        ) : null}
      </div>

      {report && job?.status === "completed" && (
        <div className="card">
          <div className="flex-wrap-gap-sm">
            <h2 className="card-title-sm" style={{ margin: 0, flex: "1 1 auto" }}>
              {t("ragEval.summaryHeading")}
            </h2>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => downloadJson(`rag-eval-${job.id}.json`, report)}
            >
              {t("ragEval.downloadReport")}
            </button>
          </div>
          <pre className="pre-json">{JSON.stringify(report.summary, null, 2)}</pre>
          {report.diff ? (
            <p style={{ fontSize: "0.86rem", marginTop: 10 }}>
              Diff: improved {report.diff.improved.length}, regressed{" "}
              {report.diff.regressed.length}, still failed{" "}
              {report.diff.still_failed.length}
            </p>
          ) : null}
        </div>
      )}

      {rows.length > 0 && (
        <div className="card">
          <h2 className="card-title-sm">
            {t("ragEval.resultsHeading", { count: rows.length })}
          </h2>
          <div className="panel-grid">
            {rows.map((r) => (
              <details
                key={`${r.id}-${r.processed_index}`}
                className={`details-result${r.pass ? " details-result--pass" : " details-result--fail"}`}
              >
                <summary style={{ cursor: "pointer", fontWeight: 600 }}>
                  {r.pass ? "PASS" : "FAIL"} — {r.id}
                  {!r.api_ok ? " (api error)" : ""}
                </summary>
                <p className="text-subtle-meta" style={{ marginTop: 8 }}>
                  {r.message}
                </p>
                {r.failures.length > 0 && (
                  <ul style={{ margin: "6px 0", paddingLeft: 18, fontSize: "0.86rem" }}>
                    {r.failures.map((f) => (
                      <li key={f}>{f}</li>
                    ))}
                  </ul>
                )}
                <pre
                  style={{
                    marginTop: 8,
                    fontSize: "0.78rem",
                    whiteSpace: "pre-wrap",
                    maxHeight: 160,
                    overflow: "auto",
                  }}
                >
                  {String((r.actual as { response?: string })?.response ?? "")}
                </pre>
              </details>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
