"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Locale } from "./constants";
import { LOCALE_KEY } from "./constants";
import en from "./messages/en.json";
import nl from "./messages/nl.json";

const MESSAGES: Record<Locale, Record<string, unknown>> = {
  en: en as Record<string, unknown>,
  nl: nl as Record<string, unknown>,
};

function getByPath(obj: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((cur, key) => {
    if (cur && typeof cur === "object" && key in cur) {
      return (cur as Record<string, unknown>)[key];
    }
    return undefined;
  }, obj);
}

function interpolate(
  template: string,
  params?: Record<string, string | number>
): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) =>
    String(params[k] ?? `{${k}}`)
  );
}

export type TranslateFn = (
  key: string,
  params?: Record<string, string | number>
) => string;

type I18nContextValue = {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: TranslateFn;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem(LOCALE_KEY);
    if (saved === "nl" || saved === "en") setLocaleState(saved);
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    document.documentElement.lang = locale === "nl" ? "nl" : "en";
    localStorage.setItem(LOCALE_KEY, locale);
  }, [locale, hydrated]);

  const setLocale = useCallback((l: Locale) => setLocaleState(l), []);

  const t = useCallback(
    (key: string, params?: Record<string, string | number>) => {
      const fromEn = getByPath(MESSAGES.en, key);
      const fromNl = getByPath(MESSAGES.nl, key);
      const raw =
        locale === "nl"
          ? typeof fromNl === "string"
            ? fromNl
            : typeof fromEn === "string"
              ? fromEn
              : key
          : typeof fromEn === "string"
            ? fromEn
            : typeof fromNl === "string"
              ? fromNl
              : key;
      return interpolate(raw, params);
    },
    [locale]
  );

  const value = useMemo(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
