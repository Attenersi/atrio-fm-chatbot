# ADR 0003: LLM provider abstraction and future local inference

## Status

Accepted (directional; incremental implementation)

## Context

The product uses **remote LLM APIs** for chat, classification, and related tasks. Configuration is expressed through **LLM profiles**, prompts, and task routing—not through training custom foundation models in the application. Navigation and copy should reflect **prompt and profile tuning** rather than implying users are training proprietary model weights.

Some deployments may later want **local or self-hosted inference** (on-prem GPUs, air-gapped environments, or cost controls) while keeping the same conversational and RAG behavior.

## Decision

1. **Provider-agnostic surface**  
   Keep LLM access behind a stable application boundary (profiles, task-to-model mapping, and HTTP or adapter-based backends). Avoid scattering vendor-specific request shapes through business logic.

2. **Portable configuration**  
   Treat prompts, profile metadata, and tunable parameters as **data** where practical so they can be versioned, exported, and reapplied across environments.

3. **Path to local inference**  
   Design for **swappable backends**: API clients today; optional local servers (e.g. OpenAI-compatible HTTP endpoints or other adapters) later, without rewriting RAG or ticket flows. Conversion from an API-centric setup to a local one should be primarily **configuration and connectivity**, not a full rewrite.

4. **Terminology**  
   Prefer language such as “system prompt tuning,” “profiles,” and “evaluation” over “model training” unless the feature is explicitly about fine-tuning or custom weights.

## Consequences

- New LLM-related features should go through the existing profile/config mechanisms when possible.
- Documentation and UI should stay aligned with **API + config** today and **optional local backends** tomorrow.
- If fine-tuning or custom weights are added later, they should be documented as a separate capability, not conflated with prompt and profile editing.

## Links

- LLM profiles and admin UI: backend and frontend `llm` / `llm_profiles` areas
- Related: [ADR 0001](0001-sqlite-operational-database.md) (operational data store for config and state)
