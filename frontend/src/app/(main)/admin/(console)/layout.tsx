"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useI18n } from "../../../../i18n/I18nProvider";
import { getSession } from "../../../../lib/api";

function subNavActive(pathname: string, href: string): boolean {
  if (href === "/admin/knowledge/gaps") {
    return pathname === href || pathname.startsWith("/admin/gaps/");
  }
  return pathname === href;
}

export default function AdminConsoleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useI18n();
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
    return (
      <section>
        <h1>{t("adminSettings.title")}</h1>
        <p>{t("adminSettings.checkingSession")}</p>
      </section>
    );
  }

  const items = [
    { href: "/admin/tickets", label: t("adminSettings.tabsTickets") },
    { href: "/admin/knowledge/gaps", label: t("adminSettings.tabsKnowledge") },
    {
      href: "/admin/knowledge/documents",
      label: t("adminSettings.tabsDocuments"),
    },
    { href: "/admin/users", label: t("adminSettings.tabsUsers") },
    { href: "/admin/rag-eval", label: t("nav.ragEval") },
    { href: "/admin/training", label: t("nav.trainingReview") },
    { href: "/admin/training-quality", label: t("nav.trainingQuality") },
    { href: "/admin/llm", label: t("nav.llmModels") },
  ];

  return (
    <section className="page-shell">
      <h1>{t("adminSettings.title")}</h1>
      <div className="card panel-grid console-subnav-card">
        <div className="toolbar">
          {items.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`btn btn-ghost${subNavActive(pathname, item.href) ? " is-active" : ""}`}
            >
              {item.label}
            </Link>
          ))}
        </div>
      </div>
      {children}
    </section>
  );
}
