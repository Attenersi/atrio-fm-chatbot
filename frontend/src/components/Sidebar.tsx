"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n/I18nProvider";
import { getSession, logout } from "../lib/api";

type Role = "admin" | "user" | null;

type NavLink = { href: string; label: string };

type NavSection = { label?: string; links: NavLink[] };

type AdminNavModel = {
  mainLinks: NavLink[];
  administrationSubsections: NavSection[];
};

function linkIsActive(pathname: string, href: string): boolean {
  if (pathname === href) return true;
  if (
    href === "/admin/tickets" &&
    pathname.startsWith("/admin") &&
    !pathname.startsWith("/admin/login")
  ) {
    return true;
  }
  if (href === "/admin/knowledge/gaps" && pathname.startsWith("/admin/gaps")) {
    return true;
  }
  return pathname.startsWith(`${href}/`);
}

export function Sidebar() {
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [narrowViewport, setNarrowViewport] = useState(false);
  const [role, setRole] = useState<Role>(null);
  const [username, setUsername] = useState("");

  const navModel = useMemo(():
    | AdminNavModel
    | { kind: "flat"; links: NavLink[] } => {
    if (role === "admin") {
      return {
        mainLinks: [
          { href: "/chat", label: t("nav.chat") },
          { href: "/dashboard", label: t("nav.tickets") },
          { href: "/help", label: t("nav.help") },
        ],
        administrationSubsections: [
          {
            links: [{ href: "/admin/tickets", label: t("nav.adminConsole") }],
          },
        ],
      };
    }
    if (role === "user") {
      return {
        kind: "flat",
        links: [
          { href: "/chat", label: t("nav.chat") },
          { href: "/dashboard", label: t("nav.myTickets") },
          { href: "/help", label: t("nav.help") },
        ],
      };
    }
    return {
      kind: "flat",
      links: [{ href: "/", label: t("nav.signIn") }],
    };
  }, [role, t]);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 900px)");
    const sync = () => {
      const matches = mq.matches;
      setNarrowViewport(matches);
      if (!matches) setMobileOpen(false);
    };
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    getSession()
      .then((res) => {
        setRole(res.user.role);
        setUsername(res.user.username);
      })
      .catch(() => {
        setRole(null);
        setUsername("");
      });
  }, [pathname]);

  function closeMobileSidebar() {
    setMobileOpen(false);
  }

  async function onLogout() {
    await logout();
    closeMobileSidebar();
    setRole(null);
    setUsername("");
    router.replace("/");
  }

  function renderNavLinks(links: NavLink[]) {
    return links.map((link) => {
      const active = linkIsActive(pathname, link.href);
      return (
        <Link
          key={link.href}
          href={link.href}
          className={`sidebar-link${active ? " active" : ""}`}
          onClick={closeMobileSidebar}
        >
          {link.label}
        </Link>
      );
    });
  }

  return (
    <>
      <button
        type="button"
        className={`sidebar-mobile-trigger${narrowViewport && mobileOpen ? " hidden" : ""}`}
        onClick={() => {
          if (narrowViewport) setMobileOpen((prev) => !prev);
        }}
        aria-label={mobileOpen ? t("common.hideMenu") : t("common.showMenu")}
      >
        {narrowViewport && mobileOpen ? "←" : "→"}
      </button>
      {narrowViewport && mobileOpen ? (
        <button
          className="sidebar-backdrop"
          onClick={closeMobileSidebar}
          aria-label={t("common.closeMenuOverlay")}
        />
      ) : null}
      <aside className={`sidebar${mobileOpen ? " mobile-open" : ""}`}>
        <div className="sidebar-header-row">
          <div>
            <div className="sidebar-logo-wrap">
              <Image
                src="/atrio-brand-assets/atrio-logo-light.png?v=4"
                alt="Atrio"
                width={132}
                height={40}
                className="sidebar-logo"
                priority
              />
            </div>
            <p className="sidebar-subtitle">{t("common.facilityAssistant")}</p>
          </div>
          <button
            type="button"
            className="sidebar-collapse-btn"
            onClick={closeMobileSidebar}
            aria-label={t("common.collapseSidebar")}
          >
            ←
          </button>
        </div>
        <nav className="sidebar-nav">
          {"kind" in navModel && navModel.kind === "flat" ? (
            renderNavLinks(navModel.links)
          ) : (
            <>
              <div className="sidebar-nav-section sidebar-nav-section--main">
                {renderNavLinks(
                  (navModel as AdminNavModel).mainLinks
                )}
              </div>
              <div className="sidebar-nav-admin-block">
                <div className="sidebar-nav-block-title">
                  {t("nav.sectionAdministration")}
                </div>
                {(navModel as AdminNavModel).administrationSubsections.map(
                  (subsection, idx) => (
                    <div
                      key={subsection.label ?? subsection.links[0]?.href ?? idx}
                      className="sidebar-nav-section"
                    >
                      {subsection.label ? (
                        <div className="sidebar-nav-section-label">
                          {subsection.label}
                        </div>
                      ) : null}
                      {renderNavLinks(subsection.links)}
                    </div>
                  )
                )}
              </div>
            </>
          )}
        </nav>
        {role ? (
          <div className="sidebar-userbox">
            <p
              className="sidebar-subtitle"
              style={{
                margin: "0 0 8px",
                textTransform: "none",
                letterSpacing: 0,
              }}
            >
              {t("common.signedInAs")} <strong>{username}</strong> ({role})
            </p>
            <button
              type="button"
              className="btn sidebar-logout-btn"
              onClick={onLogout}
            >
              {t("common.logout")}
            </button>
          </div>
        ) : null}
      </aside>
    </>
  );
}
