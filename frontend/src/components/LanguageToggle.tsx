"use client";

import { useI18n } from "../i18n/I18nProvider";
import type { Locale } from "../i18n/constants";

export function LanguageToggle() {
  const { locale, setLocale, t } = useI18n();

  function cycle() {
    const next: Locale = locale === "en" ? "nl" : "en";
    setLocale(next);
  }

  return (
    <button
      type="button"
      className="chrome-toggle-btn"
      onClick={cycle}
      aria-label={t("language.toggleAria")}
    >
      {t("language.label")}: {locale.toUpperCase()}
    </button>
  );
}
