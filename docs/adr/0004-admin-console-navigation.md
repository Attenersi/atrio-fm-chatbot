# ADR 0004: Single admin console for primary admin IA

## Status

Accepted

## Context

The app has multiple admin destinations: a **main sidebar** (for all authenticated layouts) and an **admin console** with its own sub-navigation (`/admin/tickets` and related routes). Some features are “ops” oriented (tickets, users, knowledge), others are “platform” oriented (LLM profiles, training review, RAG evaluation, training-quality analysis).

A possible alternative is **role-based sidebar sections**: show or hide groups of links based on coarse roles (`admin_ops`, `admin_ml`) or feature flags, so operators see fewer items than ML engineers.

That alternative requires **consistent permission data** from the backend (or env-driven flags) and ongoing maintenance of nav rules in the client.

## Decision

1. **Primary pattern: one admin console**  
   Use the console layout under `frontend/src/app/(main)/admin/(console)/layout.tsx` as the main hub for **day-to-day admin work**: tickets, knowledge gaps, documents, users.

2. **Power tools stay discoverable outside the console**  
   Training review, training quality, LLM profiles, and RAG answer testing remain reachable via the **main sidebar** (or bookmarks/deep links) until information architecture is revisited. This avoids overloading the console with infrequent or specialist flows.

3. **Reduce duplicate navigation**  
   Prefer a single path to a destination (sidebar **or** in-page link rows, not both for the same targets).

## Deferred alternative: role-based sidebar

**Not implemented now.** If product needs clearer separation by persona:

- Introduce **backend-supported roles or claims** (or feature flags) and map them to visible nav items.
- Consider moving “power tools” into a **permission-gated** console tab or a dedicated “Advanced” section instead of duplicating entries.

Tradeoffs: less clutter for restricted users vs. cost of auth model, tests, and drift between sidebar and direct URLs.

## Consequences

- New **ops/knowledge/user** features should default to living **under the console** unless there is a strong reason to expose them only from the sidebar.
- Specialist flows may remain on standalone routes with sidebar links until a second IA pass.
- Documentation should describe **console = primary admin hub** for operators.

## Links

- Console layout: `frontend/src/app/(main)/admin/(console)/layout.tsx`
- Sidebar: `frontend/src/components/Sidebar.tsx`
