# User Guide

Language: **English** | [Nederlands](README_users.nl.md)

## What this assistant can do

The FM assistant supports:

- building information (hours, access, spaces, policies)
- maintenance incidents (HVAC, plumbing, electrical, safety, general)
- follow-up guidance after initial reports
- automatic ticket creation when a real issue is detected

## What happens when you send a message

1. The backend retrieves relevant building documentation.
2. The LLM generates a structured answer (category, priority, response).
3. Business rules decide whether a ticket should be created.
4. You receive the response and ticket confirmation (if created).

## How to write effective reports

Include:

- exact location (building/floor/room)
- what happened
- when it started
- whether it is recurring
- any safety indicators (smell, smoke, leaks, sparks)

Example:

`Suite 305 heating stopped this morning. Third day in a row. Room temperature is 16C.`

## Informational vs ticket-worthy messages

- Informational requests usually should not create a ticket.
- Service incidents and faults should create a ticket.

## Follow-up behavior

Messages like `Any update on my AC issue?` should be treated as follow-up context, not a new fault report.

## Safety notice

For life-safety emergencies, follow emergency procedures first.
Use the assistant for logging and support, not as a replacement for emergency response.

## In-app pages you will use

- `/chat` - ask questions and report incidents
- `/dashboard` - review your tickets and statuses
- `/help` - in-app guidance

## Limits

- The assistant is limited to facility-management scope.
- If knowledge is missing in docs, the answer may be partial until admins update content and reindex.
