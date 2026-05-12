# Manager/Admin Guide

Language: **English** | [Nederlands](README_managers.nl.md)

This guide maps manager responsibilities to the current `admin` role.

## Core work areas

- `/dashboard` - ticket monitoring and operations
- `/admin` - docs, users, knowledge gaps, uploads, reindex
- `/admin/training` - training example review
- `/admin/training-quality` - evaluation and prompt-quality loop
- `/admin/llm` - LLM profile configuration by task

## Ticket operations (daily)

On dashboard you can:

- view all tickets
- filter by category/priority/status
- sort and paginate results
- open detailed ticket side panel
- change ticket status (`Open`, `In Progress`, `Resolved`)
- export current filtered view to CSV

## Daily KPI checklist

- count of `URGENT` tickets
- tickets stuck in `Open`
- spikes by category (Safety, Plumbing, HVAC, Electrical)
- recurring issue summaries

## Knowledge operations

In `/admin` you can:

- list/create/edit/delete FM docs
- upload `.txt`, `.md`, `.csv`, `.pdf`, `.docx`
- trigger reindex after content updates
- review/resolve knowledge gaps

Recommended sequence:

1. review new knowledge gaps
2. verify missing or incorrect policy/data
3. update document content
4. run reindex
5. validate by targeted prompts or test subset

## User and access management

Admin controls include:

- role changes (`user` / `admin`)
- activation/deactivation
- optional email metadata

Guardrail: there must always be at least one active admin account.

## Training and quality workflow

### Training review (`/admin/training`)

- review captured examples
- mark as `approved`, `edited`, or `rejected`
- add `human_notes`
- refine `ideal_output`

### Quality loop (`/admin/training-quality`)

- run evaluations
- inspect mismatch groups
- analyze suggestions
- apply/rollback/consolidate prompt overrides
- replay changes against affected examples

See also:

- [`docs/fine_tuning_data.md`](fine_tuning_data.md)
- [`backend/test_runbook.md`](../backend/test_runbook.md)

## Operational metrics

Track both:

- all-case pass rate (includes infra/API failures)
- `api_ok_only` pass rate (model and logic quality)
