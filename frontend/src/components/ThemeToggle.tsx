"use client";

import { useEffect, useState } from "react";
import { useI18n } from "../i18n/I18nProvider";

export const THEME_KEY = "fm_theme";
type Theme = "light" | "dark";

export function ThemeToggle() {
  const { t } = useI18n();
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const saved = localStorage.getItem(THEME_KEY);
    const initial: Theme = saved === "dark" ? "dark" : "light";
    setTheme(initial);
    document.documentElement.setAttribute("data-theme", initial);
  }, []);

  function toggleTheme() {
    const next: Theme = theme === "light" ? "dark" : "light";
    setTheme(next);
    localStorage.setItem(THEME_KEY, next);
    document.documentElement.setAttribute("data-theme", next);
  }

  return (
    <button
      type="button"
      className="chrome-toggle-btn"
      onClick={toggleTheme}
      aria-label={t("theme.toggleAria")}
    >
      {t("theme.label")}:{" "}
      {theme === "light" ? t("theme.light") : t("theme.dark")}
    </button>
  );
}
