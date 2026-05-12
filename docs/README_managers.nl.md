# Manager/Admin Handleiding

Taal: [English](README_managers.md) | **Nederlands**

Deze handleiding vertaalt manager-verantwoordelijkheden naar de huidige `admin`-rol.

## Kerngebieden

- `/dashboard` - ticketmonitoring en operatie
- `/admin` - docs, users, lacunes, uploads, reindex
- `/admin/training` - review van trainingsvoorbeelden
- `/admin/training-quality` - evaluatie en promptkwaliteit
- `/admin/llm` - LLM-profielen en taaktoewijzingen

## Ticketoperaties (dagelijks)

In dashboard kun je:

- alle tickets bekijken
- filteren op categorie/prioriteit/status
- sorteren en pagineren
- detailpaneel openen
- status wijzigen (`Open`, `In Progress`, `Resolved`)
- gefilterde view exporteren naar CSV

## Dagelijkse KPI-checklist

- aantal `URGENT` tickets
- tickets die lang in `Open` staan
- pieken per categorie (Safety, Plumbing, HVAC, Electrical)
- terugkerende samenvattingen/patronen

## Kennisbeheer

In `/admin` kun je:

- FM-documenten beheren (CRUD)
- `.txt`, `.md`, `.csv`, `.pdf`, `.docx` uploaden
- reindex draaien na updates
- kennislacunes reviewen en oplossen

Aanbevolen volgorde:

1. nieuwe lacunes bekijken
2. ontbrekende/foute inhoud verifiëren
3. documentinhoud bijwerken
4. reindex uitvoeren
5. valideren met gerichte prompts of tests

## Gebruikers- en toegangsbeheer

Adminfuncties:

- rolwijziging (`user` / `admin`)
- activeren/deactiveren
- optionele e-mailmetadata

Guardrail: er moet altijd minimaal één actieve admin zijn.

Voor **privacy, bewaartermijnen en GDPR-gerichte verwijdering** van chat + trainingdata (niet tickets): [`gdpr_data_retention.md`](gdpr_data_retention.md).

## Training- en kwaliteitsflow

### Trainingreview (`/admin/training`)

- voorbeelden reviewen
- markeren als `approved`, `edited`, `rejected`
- `human_notes` toevoegen
- `ideal_output` corrigeren

### Kwaliteitsloop (`/admin/training-quality`)

- eval draaien
- mismatch-groepen inspecteren
- suggesties analyseren
- prompt overrides toepassen/terugdraaien/samenvoegen
- replay draaien op getroffen voorbeelden

Zie ook:

- [`docs/fine_tuning_data.md`](fine_tuning_data.md)
- [`backend/test_runbook.md`](../backend/test_runbook.md)
