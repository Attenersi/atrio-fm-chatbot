"use client";

import { useEffect, useState } from "react";

export const THEME_KEY = "fm_theme";
type Theme = "light" | "dark";

export function ThemeToggle() {
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
    <button type="button" className="theme-toggle-fixed" onClick={toggleTheme} aria-label="Toggle color theme">
      Theme: {theme === "light" ? "Light" : "Dark"}
    </button>
  );
}
