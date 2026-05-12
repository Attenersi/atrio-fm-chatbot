import type { CSSProperties } from "react";

export const DOC_NAME_REGEX = /^[a-zA-Z0-9._-]+\.(md|txt)$/i;

export function formatGapReason(notes: string): { title: string; detail?: string } {
  const n = (notes || "").trim();
  if (!n) return { title: "—" };
  if (n.includes("grounded=NO") && n.includes("informational")) {
    return {
      title: "Missing FM documentation (informational question)",
      detail: n,
    };
  }
  if (n.startsWith("resolved_in=")) {
    return { title: "Resolved into knowledge base", detail: n };
  }
  return { title: "System / audit note", detail: n };
}

export function priorityBadgeStyle(priority: string): CSSProperties {
  const p = (priority || "").toUpperCase();
  if (p === "URGENT") {
    return {
      border: "1px solid var(--chip-danger-border)",
      background: "var(--chip-danger-bg)",
      color: "var(--chip-danger-text)",
    };
  }
  if (p === "HIGH") {
    return {
      border: "1px solid var(--chip-warn-border)",
      background: "var(--chip-warn-bg)",
      color: "var(--chip-warn-text)",
    };
  }
  if (p === "LOW") {
    return {
      border: "1px solid var(--chip-success-border)",
      background: "var(--chip-success-bg)",
      color: "var(--chip-success-text)",
    };
  }
  return {
    border: "1px solid var(--chip-info-border)",
    background: "var(--chip-info-bg)",
    color: "var(--chip-info-text)",
  };
}
