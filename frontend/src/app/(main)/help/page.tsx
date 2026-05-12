"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getSession } from "../../../lib/api";
import helpEn from "../../../i18n/messages/help.en.json";
import helpNl from "../../../i18n/messages/help.nl.json";
import { useI18n } from "../../../i18n/I18nProvider";

type HelpSection = (typeof helpEn.tabOrder)[number];

function calloutTone(t: string): "info" | "warn" | "danger" {
  if (t === "warn" || t === "danger") return t;
  return "info";
}

function Callout({
  tone,
  title,
  children,
}: {
  tone: "info" | "warn" | "danger";
  title: string;
  children: ReactNode;
}) {
  const toneClass =
    tone === "warn"
      ? "help-callout--warn"
      : tone === "danger"
        ? "help-callout--danger"
        : "help-callout--info";
  return (
    <div className={`help-callout ${toneClass}`}>
      <strong className="help-callout__title">{title}</strong>
      {children}
    </div>
  );
}

function Steps({ items }: { items: string[] }) {
  return (
    <ol className="help-steps">
      {items.map((s) => (
        <li key={s}>{s}</li>
      ))}
    </ol>
  );
}

function DataTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="help-table-wrap">
      <table className="help-table">
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="help-surface-card">
      <div className="help-surface-card__label">{title}</div>
      <div className="help-surface-card__body">{children}</div>
    </div>
  );
}

export default function HelpPage() {
  const router = useRouter();
  const { locale, t } = useI18n();
  const H = locale === "nl" ? helpNl : helpEn;
  const [ready, setReady] = useState(false);
  const [section, setSection] = useState<HelpSection>("overview");

  const tabs = useMemo(
    () =>
      H.tabOrder.map((id) => ({
        id,
        label: H.tabs[id as keyof typeof H.tabs],
      })),
    [H]
  );

  useEffect(() => {
    getSession()
      .then(() => setReady(true))
      .catch(() => router.replace("/"));
  }, [router]);

  const show = useCallback((id: HelpSection) => {
    setSection(id);
    if (typeof window !== "undefined" && window.history.replaceState) {
      window.history.replaceState(null, "", `#${id}`);
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    const hash = (window.location.hash || "").replace(/^#/, "") as HelpSection;
    const ok = H.tabOrder.includes(hash);
    if (ok) setSection(hash);
  }, [ready, H.tabOrder]);

  if (!ready) {
    return (
      <section className="page-shell">
        <p>{t("common.checkingSession")}</p>
      </section>
    );
  }

  return (
    <div className="content-narrow">
      <h1 className="page-title-lead">{H.title}</h1>
      <p className="help-prose text-muted" style={{ marginBottom: 20 }}>
        {H.subtitleBeforeRepo}{" "}
        <code style={{ fontSize: 13 }}>docs/admin_guide.md</code> or{" "}
        <code style={{ fontSize: 13 }}>docs/admin_guide.html</code>{" "}
        {H.subtitleAfterRepo}
      </p>

      <div className="pill-tab-row">
        {tabs.map((tab) => {
          const active = section === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => show(tab.id)}
              aria-current={active ? "true" : undefined}
              className={`pill-tab${active ? " pill-tab--active" : ""}`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {section === "overview" && (
        <div>
          <p className="help-prose">{H.overview.intro}</p>
          <div className="help-card-grid" style={{ margin: "16px 0" }}>
            {H.overview.cards.map((c) => (
              <Card key={c.title} title={c.title}>
                {c.body}
              </Card>
            ))}
          </div>
          <h2 className="help-h2">{H.overview.whereHeading}</h2>
          <DataTable
            headers={H.overview.whereTable.headers}
            rows={H.overview.whereTable.rows}
          />
          <Callout
            tone={calloutTone(H.overview.calloutSignIn.tone)}
            title={H.overview.calloutSignIn.title}
          >
            {H.overview.calloutSignIn.body}
          </Callout>
          <Callout
            tone={calloutTone(H.overview.calloutDaily.tone)}
            title={H.overview.calloutDaily.title}
          >
            {H.overview.calloutDaily.body}
          </Callout>
        </div>
      )}

      {section === "chat" && (
        <div>
          <p className="help-prose text-muted">
            <strong>{H.chat.routeLine}</strong> <code>/chat</code>
          </p>
          <h2 className="help-h2">{H.chat.howHeading}</h2>
          <Steps items={H.chat.steps} />
          <h2 className="help-h2">{H.chat.whenTicketHeading}</h2>
          <div className="help-card-grid">
            {H.chat.cards.map((c) => (
              <Card key={c.title} title={c.title}>
                {c.body}
              </Card>
            ))}
          </div>
          <h2 className="help-h2">{H.chat.prioritiesHeading}</h2>
          <DataTable
            headers={H.chat.prioritiesTable.headers}
            rows={H.chat.prioritiesTable.rows}
          />
          <h3 className="help-h3">{H.chat.createAnywayHeading}</h3>
          <p className="help-prose">{H.chat.createAnywayBody}</p>
          <h3 className="help-h3">{H.chat.newChatHeading}</h3>
          <p className="help-prose">{H.chat.newChatBody}</p>
          <Callout
            tone={calloutTone(H.chat.calloutRateLimit.tone)}
            title={H.chat.calloutRateLimit.title}
          >
            {H.chat.calloutRateLimit.body}
          </Callout>
          <Callout
            tone={calloutTone(H.chat.calloutDoNot.tone)}
            title={H.chat.calloutDoNot.title}
          >
            <ul className="help-callout-list">
              {H.chat.calloutDoNot.list.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </Callout>
        </div>
      )}

      {section === "dashboard" && (
        <div>
          <p className="help-prose text-muted">
            <strong>{H.dashboard.routeLine}</strong> <code>/dashboard</code>
          </p>
          <p className="help-prose">{H.dashboard.intro}</p>
          <h2 className="help-h2">{H.dashboard.changeStatusHeading}</h2>
          <Steps items={H.dashboard.changeStatusSteps} />
          <DataTable
            headers={H.dashboard.statusTable.headers}
            rows={H.dashboard.statusTable.rows}
          />
          <h2 className="help-h2">{H.dashboard.resolutionHeading}</h2>
          <p className="help-prose">{H.dashboard.resolutionBody}</p>
          <h2 className="help-h2">{H.dashboard.overrideHeading}</h2>
          <p className="help-prose">{H.dashboard.overrideBody}</p>
          <p className="help-prose">{H.dashboard.exportBody}</p>
          <Callout
            tone={calloutTone(H.dashboard.calloutDoNot.tone)}
            title={H.dashboard.calloutDoNot.title}
          >
            <ul className="help-callout-list">
              {H.dashboard.calloutDoNot.list.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </Callout>
        </div>
      )}

      {section === "gaps" && (
        <div>
          <p className="help-prose text-muted">
            <strong>{H.gaps.routeLine}</strong>{" "}
            <code>/admin/knowledge/gaps</code>
          </p>
          <p className="help-prose">{H.gaps.intro}</p>
          <h2 className="help-h2">{H.gaps.closeHeading}</h2>
          <Steps items={H.gaps.steps} />
          <Callout
            tone={calloutTone(H.gaps.calloutTip.tone)}
            title={H.gaps.calloutTip.title}
          >
            {H.gaps.calloutTip.body}
          </Callout>
          <Callout
            tone={calloutTone(H.gaps.calloutDoNot.tone)}
            title={H.gaps.calloutDoNot.title}
          >
            <ul className="help-callout-list">
              {H.gaps.calloutDoNot.list.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </Callout>
        </div>
      )}

      {section === "documents" && (
        <div>
          <p className="help-prose text-muted">
            <strong>{H.documents.routeLine}</strong>{" "}
            <code>/admin/knowledge/documents</code>
          </p>
          <p className="help-prose">{H.documents.intro}</p>
          <h2 className="help-h2">{H.documents.commonHeading}</h2>
          <DataTable
            headers={H.documents.filesTable.headers}
            rows={H.documents.filesTable.rows}
          />
          <h2 className="help-h2">{H.documents.uploadHeading}</h2>
          <p className="help-prose">{H.documents.uploadBody}</p>
          <Callout
            tone={calloutTone(H.documents.calloutMistake.tone)}
            title={H.documents.calloutMistake.title}
          >
            {H.documents.calloutMistake.body}
          </Callout>
        </div>
      )}

      {section === "training" && (
        <div>
          <p className="help-prose text-muted">
            <strong>{H.training.routeLine}</strong> <code>/admin/training</code>
          </p>
          <p className="help-prose">{H.training.intro}</p>
          <DataTable
            headers={H.training.filtersTable.headers}
            rows={H.training.filtersTable.rows}
          />
          <p className="help-prose">{H.training.keyboardBody}</p>
          <Callout
            tone={calloutTone(H.training.calloutDoNot.tone)}
            title={H.training.calloutDoNot.title}
          >
            {H.training.calloutDoNot.body}
          </Callout>
        </div>
      )}

      {section === "quality" && (
        <div>
          <p className="help-prose text-muted">
            <strong>{H.quality.routeLine}</strong>{" "}
            <code>/admin/training-quality</code>
          </p>
          <p className="help-prose">{H.quality.intro}</p>
          <h2 className="help-h2">{H.quality.workflowHeading}</h2>
          <Steps items={H.quality.workflowSteps} />
          <DataTable
            headers={H.quality.constraintsTable.headers}
            rows={H.quality.constraintsTable.rows}
          />
          <Callout
            tone={calloutTone(H.quality.calloutDoNot.tone)}
            title={H.quality.calloutDoNot.title}
          >
            <ul className="help-callout-list">
              {H.quality.calloutDoNot.list.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </Callout>
        </div>
      )}

      <footer className="help-footer">
        {H.footer} <code>docs/admin_guide.md</code>,{" "}
        <code>docs/admin_guide.html</code>
      </footer>
    </div>
  );
}
