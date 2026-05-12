# Gebruikershandleiding

Taal: [English](README_users.md) | **Nederlands**

## Wat deze assistent kan

De FM-assistent ondersteunt:

- gebouwinformatie (uren, toegang, ruimtes, beleid)
- onderhoudsincidenten (HVAC, loodgieter, elektra, veiligheid, algemeen)
- opvolgvragen na een eerdere melding
- automatische ticketaanmaak bij echte storingen

## Wat gebeurt er als je een bericht stuurt

1. De backend haalt relevante documentatie op.
2. Het model maakt een gestructureerd antwoord.
3. Business rules bepalen of er een ticket moet komen.
4. Je ziet antwoord + ticketbevestiging (indien aangemaakt).

## Zo meld je issues goed

Vermeld:

- exacte locatie (gebouw/verdieping/kamer)
- wat er is gebeurd
- wanneer het begon
- of het terugkeert
- veiligheidssignalen (geur, rook, lekkage, vonken)

Voorbeeld:

`Suite 305 heeft sinds vanochtend geen verwarming. Derde dag op rij. Temperatuur is 16C.`

## Informatievraag vs ticketwaardige melding

- Informatieve vragen maken meestal geen ticket.
- Operationele storingen en incidenten moeten wel een ticket opleveren.

## Follow-up gedrag

Berichten als `Statusupdate over mijn AC-melding?` horen als follow-up context verwerkt te worden, niet als nieuwe fout.

## Veiligheidsmelding

Bij levensgevaar: volg eerst je noodprocedures.
Gebruik de assistent voor logging/ondersteuning, niet als vervanging van noodrespons.

## Pagina's die je gebruikt

- `/chat` - vragen stellen en incidenten melden
- `/dashboard` - je tickets en statussen bekijken
- `/help` - in-app uitleg

## Beperkingen

- De assistent is beperkt tot FM-scope.
- Bij ontbrekende kennis kan antwoord onvolledig zijn tot admins docs updaten en herindexeren.
