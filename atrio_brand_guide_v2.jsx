import { useState } from "react";

const colors = {
  primary: { name: "Atrio Navy", hex: "#1E2B4F", use: "Logo, headers, primary buttons, nav, building icon" },
  primaryMid: { name: "Atrio Steel", hex: "#6B7A99", use: "Secondary text, borders, inactive states" },
  primaryLight: { name: "Atrio Mist", hex: "#EAECF2", use: "Page backgrounds, card hovers, light surfaces" },
  accent: { name: "Signal Orange", hex: "#E07B2A", use: "CTAs, active window, links, highlights, key actions" },
  accentLight: { name: "Orange Glow", hex: "#FDF0E2", use: "Warning backgrounds, notification cards, hover states" },
  success: { name: "Resolve Green", hex: "#2D8C5A", use: "Resolved tickets, success states, confirmations" },
  successLight: { name: "Green Mist", hex: "#E5F4EC", use: "Success backgrounds, resolved ticket cards" },
  urgent: { name: "Alert Red", hex: "#C9392C", use: "Urgent priority, errors, destructive actions" },
  urgentLight: { name: "Red Mist", hex: "#FCEAE8", use: "Error backgrounds, urgent ticket cards" },
  dark: { name: "Ink 900", hex: "#141824", use: "Body text, dark mode backgrounds, footer" },
  mid: { name: "Ink 400", hex: "#7C8298", use: "Descriptions, placeholders, timestamps" },
  light: { name: "Ink 50", hex: "#F5F6F8", use: "Page background, table rows, dividers" },
  white: { name: "White", hex: "#FFFFFF", use: "Card backgrounds, inputs, clean surfaces" },
};

const fonts = {
  display: { name: "DM Sans", weight: "700", size: "36px", use: "Hero headlines, landing page titles", sample: "Atrio" },
  heading: { name: "DM Sans", weight: "600", size: "20px", use: "Section titles, card headers, dashboard headings", sample: "Smart facility support" },
  body: { name: "DM Sans", weight: "400", size: "15px", use: "Body copy, descriptions, chat messages", sample: "Every maintenance request, intelligently routed to the right team." },
  mono: { name: "JetBrains Mono", weight: "400", size: "13px", use: "Ticket IDs, status codes, technical data, badges", sample: "TKT-2024-0847 · HVAC · URGENT" },
};

const toneExamples = [
  { label: "Welcome message", bad: "Hello! I am an AI-powered facility management assistant built with state-of-the-art language models. How may I assist you today?", good: "Hi — I'm Atrio, your building assistant. What needs fixing?" },
  { label: "Ticket created", bad: "Your maintenance request has been successfully submitted and assigned ticket number TKT-2024-0847. The relevant department will be notified shortly.", good: "Got it — ticket TKT-0847 created. Your HVAC team has been notified." },
  { label: "Knowledge answer", bad: "Based on the building documentation that I have access to, the visitor parking policy states that visitors may park in designated spots B1-B20.", good: "Visitor parking is in spots B1 through B20, level B1. No pass needed for stays under 4 hours." },
  { label: "Error state", bad: "An unexpected error has occurred. Please try again later or contact the system administrator for further assistance.", good: "Something went wrong on our end. Try again in a moment — if it persists, we're on it." },
  { label: "Ambiguous request", bad: "I'm sorry, I didn't understand your request. Could you please provide more details about the issue you are experiencing?", good: "I want to make sure I route this correctly — is this something that needs a repair, or are you looking for information?" },
];

const sections = ["story", "colors", "typography", "logo", "tone", "components"];
const sectionLabels = { story: "Brand story", colors: "Colors", typography: "Typography", logo: "Logo & icon", tone: "Voice & tone", components: "UI patterns" };

function Swatch({ color }) {
  const [copied, setCopied] = useState(false);
  const isLight = ["#EAECF2","#FDF0E2","#E5F4EC","#FCEAE8","#F5F6F8","#FFFFFF"].includes(color.hex);
  return (
    <div onClick={() => { navigator.clipboard.writeText(color.hex); setCopied(true); setTimeout(() => setCopied(false), 1200); }} style={{ cursor: "pointer" }}>
      <div style={{
        width: "100%", height: 52, borderRadius: 8,
        backgroundColor: color.hex,
        border: isLight ? "1px solid #E0E2E8" : "none",
        display: "flex", alignItems: "center", justifyContent: "center",
        transition: "transform 0.1s",
      }}>
        {copied && <span style={{ fontSize: 10, fontWeight: 600, color: isLight ? "#1E2B4F" : "#fff", letterSpacing: 1 }}>COPIED</span>}
      </div>
      <div style={{ marginTop: 5 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#141824" }}>{color.name}</div>
        <div style={{ fontSize: 11, color: "#7C8298", fontFamily: "'JetBrains Mono', monospace" }}>{color.hex}</div>
        <div style={{ fontSize: 10, color: "#9EA3B5", marginTop: 1, lineHeight: 1.3 }}>{color.use}</div>
      </div>
    </div>
  );
}

export default function AtrioBrandGuide() {
  const [active, setActive] = useState("story");

  const NavyBuilding = ({ size = 48, light = false }) => {
    const h = size * (52/36);
    const s = size / 36;
    if (light) {
      return (
        <svg viewBox="0 0 36 52" width={size} height={h}>
          <rect x="4" y="2" width="28" height="48" rx="4" fill="#CDD3E0"/>
          <rect x={10} y={7} width="5" height="4" rx="1" fill="#1E2B4F"/>
          <rect x={21} y={7} width="5" height="4" rx="1" fill="#1E2B4F"/>
          <rect x={10} y={15} width="5" height="4" rx="1" fill="#1E2B4F"/>
          <rect x={21} y={15} width="5" height="4" rx="1" fill="#1E2B4F"/>
          <rect x={10} y={23} width="5" height="4" rx="1" fill="#1E2B4F"/>
          <rect x={21} y={23} width="5" height="4" rx="1" fill="#1E2B4F"/>
          <rect x={10} y={31} width="5" height="4" rx="1" fill="#1E2B4F"/>
          <rect x={21} y={31} width="5" height="4" rx="1" fill="#E07B2A"/>
        </svg>
      );
    }
    return (
      <svg viewBox="0 0 36 52" width={size} height={h}>
        <rect x="4" y="2" width="28" height="48" rx="4" fill="#1E2B4F"/>
        <rect x={10} y={7} width="5" height="4" rx="1" fill="#fff" opacity="0.85"/>
        <rect x={21} y={7} width="5" height="4" rx="1" fill="#fff" opacity="0.85"/>
        <rect x={10} y={15} width="5" height="4" rx="1" fill="#fff" opacity="0.85"/>
        <rect x={21} y={15} width="5" height="4" rx="1" fill="#fff" opacity="0.85"/>
        <rect x={10} y={23} width="5" height="4" rx="1" fill="#fff" opacity="0.85"/>
        <rect x={21} y={23} width="5" height="4" rx="1" fill="#fff" opacity="0.85"/>
        <rect x={10} y={31} width="5" height="4" rx="1" fill="#fff" opacity="0.85"/>
        <rect x={21} y={31} width="5" height="4" rx="1" fill="#E07B2A"/>
      </svg>
    );
  };

  return (
    <div style={{ fontFamily: "'DM Sans', 'Segoe UI', system-ui, sans-serif", color: "#141824", maxWidth: "100%" }}>
      <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />

      {/* Header */}
      <div style={{ background: "#1E2B4F", borderRadius: 14, padding: "28px 28px 24px", marginBottom: 20, position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", top: -60, right: -30, width: 200, height: 200, borderRadius: "50%", border: "1px solid rgba(255,255,255,0.06)" }} />
        <div style={{ position: "absolute", top: -100, right: -70, width: 300, height: 300, borderRadius: "50%", border: "1px solid rgba(255,255,255,0.03)" }} />
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 14 }}>
          <svg viewBox="0 0 40 40" width="38" height="38">
            <rect x="0" y="0" width="40" height="40" rx="9" fill="rgba(255,255,255,0.12)"/>
            <rect x="10" y="4" width="5" height="3.5" rx="1" fill="#fff" opacity="0.8"/>
            <rect x="18" y="4" width="5" height="3.5" rx="1" fill="#fff" opacity="0.8"/>
            <rect x="10" y="11" width="5" height="3.5" rx="1" fill="#fff" opacity="0.8"/>
            <rect x="18" y="11" width="5" height="3.5" rx="1" fill="#fff" opacity="0.8"/>
            <rect x="10" y="18" width="5" height="3.5" rx="1" fill="#fff" opacity="0.8"/>
            <rect x="18" y="18" width="5" height="3.5" rx="1" fill="#fff" opacity="0.8"/>
            <rect x="10" y="25" width="5" height="3.5" rx="1" fill="#fff" opacity="0.8"/>
            <rect x="18" y="25" width="5" height="3.5" rx="1" fill="#E07B2A"/>
          </svg>
          <div>
            <div style={{ fontSize: 24, fontWeight: 700, color: "#fff", letterSpacing: -0.5 }}>atrio</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.45)", letterSpacing: 2, textTransform: "uppercase", marginTop: 1 }}>Brand Guide v2</div>
          </div>
        </div>
        <p style={{ color: "rgba(255,255,255,0.65)", fontSize: 14, lineHeight: 1.6, margin: 0, maxWidth: 500 }}>
          Complete identity system for Atrio — AI-powered facility intelligence. Colors, typography, voice, logo usage, and UI patterns.
        </p>
      </div>

      {/* Nav */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20, flexWrap: "wrap" }}>
        {sections.map(s => (
          <button key={s} onClick={() => setActive(s)} style={{
            padding: "7px 16px", borderRadius: 8, border: "none", cursor: "pointer", fontSize: 13, fontWeight: 500,
            fontFamily: "inherit",
            background: active === s ? "#1E2B4F" : "#F5F6F8",
            color: active === s ? "#fff" : "#6B7A99",
            transition: "all 0.15s",
          }}>{sectionLabels[s]}</button>
        ))}
      </div>

      {/* ===== STORY ===== */}
      {active === "story" && (
        <div>
          <div style={{ background: "#F5F6F8", borderRadius: 12, padding: "24px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 10 }}>Positioning</div>
            <p style={{ fontSize: 20, fontWeight: 700, lineHeight: 1.4, margin: "0 0 12px", color: "#1E2B4F" }}>
              Atrio is the AI front desk for every building.
            </p>
            <p style={{ fontSize: 14, color: "#6B7A99", lineHeight: 1.7, margin: 0 }}>
              Named after the atrium — the entrance hall where people come with questions, problems, and requests. Atrio is the intelligent first point of contact between tenants and facility management teams. It listens, classifies, routes, and responds — 24/7, for any size building.
            </p>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 14 }}>
            {[
              { label: "Target", value: "FM companies and building owners — from single buildings to 50+ portfolios" },
              { label: "Promise", value: "Every maintenance request, intelligently handled" },
              { label: "Personality", value: "Competent, warm, efficient — like the best office manager you've ever had" },
              { label: "Category", value: "AI-powered facility intelligence platform" },
            ].map(item => (
              <div key={item.label} style={{ background: "#fff", borderRadius: 10, padding: "14px 16px", border: "1px solid #E0E2E8" }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: "#E07B2A", textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>{item.label}</div>
                <div style={{ fontSize: 13, color: "#141824", lineHeight: 1.5 }}>{item.value}</div>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
            {[
              { label: "Atrio is", values: ["Helpful before asked", "Clear, never vague", "Fast to respond", "Data-driven", "Calm under pressure"] },
              { label: "Atrio is not", values: ["Overly formal or corporate", "Robotic or cold", "Jargon-heavy", "Slow or uncertain", "Apologetic without acting"] },
              { label: "Atrio sounds like", values: ["A capable colleague", "Someone who just handles it", "The person who always knows", "Professional but human", "Confident, not arrogant"] },
            ].map(col => (
              <div key={col.label} style={{ background: "#fff", border: "1px solid #E0E2E8", borderRadius: 10, padding: "14px 16px" }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "#1E2B4F", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>{col.label}</div>
                {col.values.map(v => (
                  <div key={v} style={{ fontSize: 12, color: "#6B7A99", padding: "3px 0", lineHeight: 1.5 }}>{v}</div>
                ))}
              </div>
            ))}
          </div>

          <div style={{ marginTop: 14, background: "#fff", border: "1px solid #E0E2E8", borderRadius: 10, padding: "14px 16px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#1E2B4F", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>Pricing tiers</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8 }}>
              {[
                { tier: "Free", price: "$0", desc: "1 building, 100 tickets/mo" },
                { tier: "Starter", price: "$49/mo", desc: "3 buildings, 500 tickets/mo" },
                { tier: "Pro", price: "$299/mo", desc: "10 buildings, 5000 tickets/mo" },
                { tier: "Enterprise", price: "Custom", desc: "Unlimited, CMMS integration" },
              ].map(t => (
                <div key={t.tier} style={{ background: "#F5F6F8", borderRadius: 8, padding: "10px 12px", textAlign: "center" }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", textTransform: "uppercase", letterSpacing: 0.5 }}>{t.tier}</div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "#1E2B4F", margin: "4px 0" }}>{t.price}</div>
                  <div style={{ fontSize: 10, color: "#7C8298", lineHeight: 1.4 }}>{t.desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ===== COLORS ===== */}
      {active === "colors" && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 10 }}>Primary palette</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 20 }}>
            <Swatch color={colors.primary} />
            <Swatch color={colors.primaryMid} />
            <Swatch color={colors.primaryLight} />
          </div>

          <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 10 }}>Semantic</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 20 }}>
            <Swatch color={colors.accent} />
            <Swatch color={colors.success} />
            <Swatch color={colors.urgent} />
            <Swatch color={colors.accentLight} />
            <Swatch color={colors.successLight} />
            <Swatch color={colors.urgentLight} />
          </div>

          <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 10 }}>Neutrals</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 12 }}>
            <Swatch color={colors.dark} />
            <Swatch color={colors.mid} />
            <Swatch color={colors.light} />
            <Swatch color={colors.white} />
          </div>

          <div style={{ marginTop: 16, background: "#F5F6F8", borderRadius: 10, padding: "14px 18px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", marginBottom: 8, textTransform: "uppercase" }}>Usage rules</div>
            <div style={{ fontSize: 12, color: "#6B7A99", lineHeight: 1.7 }}>
              Navy is dominant — it's the brand. Use for all primary UI elements, headers, and the building icon. Orange is the action color — CTAs, links, the "active window" in the logo, interactive highlights. Green is for resolved/success states only. Red is reserved strictly for urgency — errors, urgent tickets, destructive actions. Never use red for decoration. Click any swatch to copy its hex.
            </div>
          </div>
        </div>
      )}

      {/* ===== TYPOGRAPHY ===== */}
      {active === "typography" && (
        <div>
          {Object.entries(fonts).map(([key, font]) => (
            <div key={key} style={{ background: "#fff", border: "1px solid #E0E2E8", borderRadius: 12, padding: "18px 20px", marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
                <div>
                  <span style={{ fontSize: 11, fontWeight: 600, color: "#E07B2A", textTransform: "uppercase", letterSpacing: 1 }}>{key}</span>
                  <span style={{ fontSize: 11, color: "#9EA3B5", marginLeft: 8 }}>{font.use}</span>
                </div>
                <span style={{ fontSize: 11, color: "#9EA3B5", fontFamily: "'JetBrains Mono', monospace" }}>{font.name} {font.weight} / {font.size}</span>
              </div>
              <div style={{
                fontFamily: key === "mono" ? "'JetBrains Mono', monospace" : "'DM Sans', sans-serif",
                fontWeight: parseInt(font.weight),
                fontSize: parseInt(font.size),
                color: key === "mono" ? "#6B7A99" : "#141824",
                letterSpacing: key === "display" ? -1 : key === "mono" ? 0.5 : -0.3,
                lineHeight: 1.4,
              }}>
                {font.sample}
              </div>
            </div>
          ))}
          <div style={{ marginTop: 12, background: "#F5F6F8", borderRadius: 10, padding: "14px 18px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", marginBottom: 6, textTransform: "uppercase" }}>Full type scale</div>
            <div style={{ fontSize: 12, color: "#6B7A99", lineHeight: 1.7, fontFamily: "'JetBrains Mono', monospace" }}>
              Hero: 36px/700 · H1: 28px/700 · H2: 20px/600 · H3: 16px/600 · Body: 15px/400 · Small: 13px/400 · Mono: 13px/400 · Micro: 11px/500
            </div>
          </div>
        </div>
      )}

      {/* ===== LOGO ===== */}
      {active === "logo" && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 10 }}>Full logo</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 16 }}>
            <div style={{ background: "#fff", border: "1px solid #E0E2E8", borderRadius: 12, padding: "24px 20px", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <svg viewBox="0 0 180 52" width="170" height="49">
                <rect x="4" y="2" width="28" height="48" rx="4" fill="#1E2B4F"/>
                <rect x="10" y="7" width="5" height="4" rx="1" fill="#fff" opacity="0.85"/><rect x="21" y="7" width="5" height="4" rx="1" fill="#fff" opacity="0.85"/>
                <rect x="10" y="15" width="5" height="4" rx="1" fill="#fff" opacity="0.85"/><rect x="21" y="15" width="5" height="4" rx="1" fill="#fff" opacity="0.85"/>
                <rect x="10" y="23" width="5" height="4" rx="1" fill="#fff" opacity="0.85"/><rect x="21" y="23" width="5" height="4" rx="1" fill="#fff" opacity="0.85"/>
                <rect x="10" y="31" width="5" height="4" rx="1" fill="#fff" opacity="0.85"/><rect x="21" y="31" width="5" height="4" rx="1" fill="#E07B2A"/>
                <text x="42" y="35" fontFamily="'DM Sans',system-ui,sans-serif" fontSize="28" fontWeight="700" fill="#141824" letterSpacing="-0.8">atrio</text>
              </svg>
            </div>
            <div style={{ background: "#141824", borderRadius: 12, padding: "24px 20px", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <svg viewBox="0 0 180 52" width="170" height="49">
                <rect x="4" y="2" width="28" height="48" rx="4" fill="#CDD3E0"/>
                <rect x="10" y="7" width="5" height="4" rx="1" fill="#1E2B4F"/><rect x="21" y="7" width="5" height="4" rx="1" fill="#1E2B4F"/>
                <rect x="10" y="15" width="5" height="4" rx="1" fill="#1E2B4F"/><rect x="21" y="15" width="5" height="4" rx="1" fill="#1E2B4F"/>
                <rect x="10" y="23" width="5" height="4" rx="1" fill="#1E2B4F"/><rect x="21" y="23" width="5" height="4" rx="1" fill="#1E2B4F"/>
                <rect x="10" y="31" width="5" height="4" rx="1" fill="#1E2B4F"/><rect x="21" y="31" width="5" height="4" rx="1" fill="#E07B2A"/>
                <text x="42" y="35" fontFamily="'DM Sans',system-ui,sans-serif" fontSize="28" fontWeight="700" fill="#fff" letterSpacing="-0.8">atrio</text>
              </svg>
            </div>
          </div>

          <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 10 }}>Icon, avatar, favicon</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 16 }}>
            <div style={{ background: "#fff", border: "1px solid #E0E2E8", borderRadius: 12, padding: "20px", display: "flex", alignItems: "center", justifyContent: "center", gap: 20 }}>
              <NavyBuilding size={44} />
              <svg viewBox="0 0 40 40" width="44" height="44">
                <rect x="0" y="0" width="40" height="40" rx="9" fill="#1E2B4F"/>
                <rect x="10" y="4" width="5" height="3.5" rx="1" fill="#fff" opacity="0.85"/><rect x="18" y="4" width="5" height="3.5" rx="1" fill="#fff" opacity="0.85"/>
                <rect x="10" y="11" width="5" height="3.5" rx="1" fill="#fff" opacity="0.85"/><rect x="18" y="11" width="5" height="3.5" rx="1" fill="#fff" opacity="0.85"/>
                <rect x="10" y="18" width="5" height="3.5" rx="1" fill="#fff" opacity="0.85"/><rect x="18" y="18" width="5" height="3.5" rx="1" fill="#fff" opacity="0.85"/>
                <rect x="10" y="25" width="5" height="3.5" rx="1" fill="#fff" opacity="0.85"/><rect x="18" y="25" width="5" height="3.5" rx="1" fill="#E07B2A"/>
              </svg>
              <svg viewBox="0 0 32 32" width="32" height="32">
                <rect x="0" y="0" width="32" height="32" rx="6" fill="#1E2B4F"/>
                <rect x="8" y="3" width="4" height="3" rx="0.8" fill="#fff" opacity="0.85"/><rect x="14.5" y="3" width="4" height="3" rx="0.8" fill="#fff" opacity="0.85"/>
                <rect x="8" y="9" width="4" height="3" rx="0.8" fill="#fff" opacity="0.85"/><rect x="14.5" y="9" width="4" height="3" rx="0.8" fill="#fff" opacity="0.85"/>
                <rect x="8" y="15" width="4" height="3" rx="0.8" fill="#fff" opacity="0.85"/><rect x="14.5" y="15" width="4" height="3" rx="0.8" fill="#fff" opacity="0.85"/>
                <rect x="8" y="21" width="4" height="3" rx="0.8" fill="#fff" opacity="0.85"/><rect x="14.5" y="21" width="4" height="3" rx="0.8" fill="#E07B2A"/>
              </svg>
              <svg viewBox="0 0 32 32" width="16" height="16">
                <rect x="0" y="0" width="32" height="32" rx="6" fill="#1E2B4F"/>
                <rect x="8" y="3" width="4" height="3" rx="0.8" fill="#fff" opacity="0.85"/><rect x="14.5" y="3" width="4" height="3" rx="0.8" fill="#fff" opacity="0.85"/>
                <rect x="8" y="9" width="4" height="3" rx="0.8" fill="#fff" opacity="0.85"/><rect x="14.5" y="9" width="4" height="3" rx="0.8" fill="#fff" opacity="0.85"/>
                <rect x="8" y="15" width="4" height="3" rx="0.8" fill="#fff" opacity="0.85"/><rect x="14.5" y="15" width="4" height="3" rx="0.8" fill="#fff" opacity="0.85"/>
                <rect x="8" y="21" width="4" height="3" rx="0.8" fill="#fff" opacity="0.85"/><rect x="14.5" y="21" width="4" height="3" rx="0.8" fill="#E07B2A"/>
              </svg>
            </div>
            <div style={{ background: "#141824", borderRadius: 12, padding: "20px", display: "flex", alignItems: "center", justifyContent: "center", gap: 20 }}>
              <NavyBuilding size={44} light />
              <svg viewBox="0 0 40 40" width="44" height="44">
                <rect x="0" y="0" width="40" height="40" rx="9" fill="#1E2B4F"/>
                <rect x="10" y="4" width="5" height="3.5" rx="1" fill="#fff" opacity="0.85"/><rect x="18" y="4" width="5" height="3.5" rx="1" fill="#fff" opacity="0.85"/>
                <rect x="10" y="11" width="5" height="3.5" rx="1" fill="#fff" opacity="0.85"/><rect x="18" y="11" width="5" height="3.5" rx="1" fill="#fff" opacity="0.85"/>
                <rect x="10" y="18" width="5" height="3.5" rx="1" fill="#fff" opacity="0.85"/><rect x="18" y="18" width="5" height="3.5" rx="1" fill="#fff" opacity="0.85"/>
                <rect x="10" y="25" width="5" height="3.5" rx="1" fill="#fff" opacity="0.85"/><rect x="18" y="25" width="5" height="3.5" rx="1" fill="#E07B2A"/>
              </svg>
            </div>
          </div>

          <div style={{ background: "#F5F6F8", borderRadius: 10, padding: "14px 18px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", marginBottom: 6, textTransform: "uppercase" }}>Logo anatomy</div>
            <div style={{ fontSize: 12, color: "#6B7A99", lineHeight: 1.7 }}>
              Navy building with 4 floors, 8 windows. 7 windows are white/light (quiet floors), 1 is orange (active issue being handled). The orange window is always bottom-right. On dark backgrounds, the building inverts to light with navy windows — orange stays. Minimum clear space around logo: half the building width on all sides.
            </div>
          </div>
        </div>
      )}

      {/* ===== TONE ===== */}
      {active === "tone" && (
        <div>
          <div style={{ background: "#F5F6F8", borderRadius: 12, padding: "18px 20px", marginBottom: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 10 }}>Voice principles</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {[
                { title: "Direct", desc: "Say it in fewer words. No filler, no corporate padding. 'Your HVAC team has been notified' not 'The relevant department will be informed shortly.'" },
                { title: "Warm", desc: "Professional doesn't mean cold. 'Got it' is better than 'Acknowledged.' Be human, be helpful." },
                { title: "Confident", desc: "We handled it. Not 'we'll try to look into it.' Atrio acts, then reports — never hedges." },
                { title: "Specific", desc: "Name the team, the ticket number, the timeframe. 'HVAC team notified, avg response 2h' beats 'someone will be in touch.'" },
              ].map(p => (
                <div key={p.title} style={{ background: "#fff", borderRadius: 8, padding: "12px 14px", border: "1px solid #E0E2E8" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#1E2B4F", marginBottom: 4 }}>{p.title}</div>
                  <div style={{ fontSize: 12, color: "#6B7A99", lineHeight: 1.6 }}>{p.desc}</div>
                </div>
              ))}
            </div>
          </div>

          {toneExamples.map((ex, i) => (
            <div key={i} style={{ background: "#fff", border: "1px solid #E0E2E8", borderRadius: 12, padding: "16px 20px", marginBottom: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", textTransform: "uppercase", letterSpacing: 1, marginBottom: 12 }}>{ex.label}</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: "#C9392C", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Don't</div>
                  <div style={{ fontSize: 13, color: "#7C8298", lineHeight: 1.6, fontStyle: "italic" }}>{ex.bad}</div>
                </div>
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: "#2D8C5A", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Do</div>
                  <div style={{ fontSize: 13, color: "#141824", lineHeight: 1.6 }}>{ex.good}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ===== COMPONENTS ===== */}
      {active === "components" && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 10 }}>Buttons</div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 20 }}>
            <button style={{ padding: "10px 22px", background: "#1E2B4F", color: "#fff", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, fontFamily: "inherit", cursor: "pointer" }}>Submit ticket</button>
            <button style={{ padding: "10px 22px", background: "#E07B2A", color: "#fff", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, fontFamily: "inherit", cursor: "pointer" }}>Book a demo</button>
            <button style={{ padding: "10px 22px", background: "transparent", color: "#1E2B4F", border: "1.5px solid #1E2B4F", borderRadius: 8, fontSize: 13, fontWeight: 600, fontFamily: "inherit", cursor: "pointer" }}>View dashboard</button>
            <button style={{ padding: "10px 22px", background: "#FCEAE8", color: "#C9392C", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, fontFamily: "inherit", cursor: "pointer" }}>Cancel</button>
          </div>

          <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 10 }}>Ticket badges</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            {[
              { label: "URGENT", bg: "#FCEAE8", color: "#C9392C" },
              { label: "HIGH", bg: "#FDF0E2", color: "#B56A1E" },
              { label: "NORMAL", bg: "#EAECF2", color: "#1E2B4F" },
              { label: "LOW", bg: "#F5F6F8", color: "#7C8298" },
              { label: "RESOLVED", bg: "#E5F4EC", color: "#2D8C5A" },
            ].map(b => (
              <span key={b.label} style={{ padding: "4px 12px", borderRadius: 6, fontSize: 11, fontWeight: 600, fontFamily: "'JetBrains Mono', monospace", letterSpacing: 0.5, background: b.bg, color: b.color }}>{b.label}</span>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 20 }}>
            {[
              { label: "HVAC", bg: "#EAECF2", color: "#1E2B4F" },
              { label: "Electrical", bg: "#FDF0E2", color: "#B56A1E" },
              { label: "Plumbing", bg: "#E0ECFA", color: "#2558A6" },
              { label: "Safety", bg: "#FCEAE8", color: "#C9392C" },
              { label: "General", bg: "#F5F6F8", color: "#7C8298" },
            ].map(b => (
              <span key={b.label} style={{ padding: "4px 12px", borderRadius: 6, fontSize: 11, fontWeight: 500, background: b.bg, color: b.color }}>{b.label}</span>
            ))}
          </div>

          <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 10 }}>Chat bubble</div>
          <div style={{ background: "#F5F6F8", borderRadius: 12, padding: 20, maxWidth: 420 }}>
            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 10 }}>
              <div style={{ background: "#1E2B4F", color: "#fff", padding: "10px 16px", borderRadius: "12px 12px 4px 12px", fontSize: 13, lineHeight: 1.5, maxWidth: "80%" }}>
                The AC in room 204 is making a loud noise and blowing warm air
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <div style={{ width: 28, height: 28, borderRadius: 8, background: "#1E2B4F", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <svg viewBox="0 0 20 20" width="14" height="14">
                  <rect x="3" y="1" width="10" height="17" rx="2" fill="rgba(255,255,255,0.85)"/>
                  <rect x="5" y="3" width="2.5" height="2" rx="0.5" fill="#1E2B4F"/>
                  <rect x="8.5" y="3" width="2.5" height="2" rx="0.5" fill="#1E2B4F"/>
                  <rect x="5" y="7" width="2.5" height="2" rx="0.5" fill="#1E2B4F"/>
                  <rect x="8.5" y="7" width="2.5" height="2" rx="0.5" fill="#1E2B4F"/>
                  <rect x="5" y="11" width="2.5" height="2" rx="0.5" fill="#1E2B4F"/>
                  <rect x="8.5" y="11" width="2.5" height="2" rx="0.5" fill="#E07B2A"/>
                </svg>
              </div>
              <div style={{ background: "#fff", border: "1px solid #E0E2E8", padding: "10px 16px", borderRadius: "12px 12px 12px 4px", fontSize: 13, lineHeight: 1.5, maxWidth: "80%" }}>
                <div>Got it — I've created ticket <span style={{ fontFamily: "'JetBrains Mono'", fontSize: 12, color: "#1E2B4F", fontWeight: 500 }}>TKT-0847</span> for room 204.</div>
                <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                  <span style={{ padding: "3px 8px", borderRadius: 5, fontSize: 10, fontWeight: 600, fontFamily: "'JetBrains Mono'", background: "#EAECF2", color: "#1E2B4F" }}>HVAC</span>
                  <span style={{ padding: "3px 8px", borderRadius: 5, fontSize: 10, fontWeight: 600, fontFamily: "'JetBrains Mono'", background: "#FDF0E2", color: "#B56A1E" }}>HIGH</span>
                </div>
              </div>
            </div>
          </div>

          <div style={{ marginTop: 16, background: "#F5F6F8", borderRadius: 10, padding: "14px 18px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7A99", marginBottom: 6, textTransform: "uppercase" }}>Design tokens</div>
            <div style={{ fontSize: 12, color: "#6B7A99", lineHeight: 1.8 }}>
              Border radius: 8px default, 12px cards/modals. Borders: 1px solid #E0E2E8. No shadows except subtle on floating elements (0 1px 3px rgba(0,0,0,0.08)). Padding: 16-24px in cards. White space is your friend. Font: DM Sans everywhere, JetBrains Mono for data/codes.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
