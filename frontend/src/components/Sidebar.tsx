"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getSession, logout } from "../lib/api";

type Role = "admin" | "user" | null;

export function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [narrowViewport, setNarrowViewport] = useState(false);
  const [role, setRole] = useState<Role>(null);
  const [username, setUsername] = useState("");
  const links = role === "admin"
    ? [
        { href: "/chat", label: "Chat" },
        { href: "/dashboard", label: "Tickets" },
        { href: "/help", label: "Help" },
        { href: "/admin", label: "Admin Settings" },
        { href: "/admin/training", label: "Training Review" },
        { href: "/admin/training-quality", label: "Training Quality" },
      ]
    : role === "user"
      ? [
          { href: "/chat", label: "Chat" },
          { href: "/dashboard", label: "My Tickets" },
          { href: "/help", label: "Help" },
        ]
      : [{ href: "/", label: "Sign in" }];

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

  return (
    <>
      <button
        type="button"
        className={`sidebar-mobile-trigger${narrowViewport && mobileOpen ? " hidden" : ""}`}
        onClick={() => {
          if (narrowViewport) setMobileOpen((prev) => !prev);
        }}
        aria-label={mobileOpen ? "Hide menu" : "Show menu"}
      >
        {narrowViewport && mobileOpen ? "←" : "→"}
      </button>
      {narrowViewport && mobileOpen ? (
        <button className="sidebar-backdrop" onClick={closeMobileSidebar} aria-label="Close menu overlay" />
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
            <p className="sidebar-subtitle">Facility Management Assistant</p>
          </div>
          <button
            type="button"
            className="sidebar-collapse-btn"
            onClick={closeMobileSidebar}
            aria-label="Collapse sidebar"
          >
            ←
          </button>
        </div>
        <nav className="sidebar-nav">
          {links.map((link) => {
            const active = pathname === link.href;
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
          })}
        </nav>
        {role ? (
          <div className="sidebar-userbox">
            <p className="sidebar-subtitle" style={{ margin: "0 0 8px", textTransform: "none", letterSpacing: 0 }}>
              Signed in as <strong>{username}</strong> ({role})
            </p>
            <button type="button" className="btn sidebar-logout-btn" onClick={onLogout}>
              Logout
            </button>
          </div>
        ) : null}
      </aside>
    </>
  );
}
