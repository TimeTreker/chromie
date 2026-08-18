# Weather Information

## Purpose

Use this passive domain method for weather Goals involving an already resolved location, time/date or forecast horizon, and one or more requested aspects such as condition, temperature, apparent temperature, rain, precipitation, snow, wind, or comparison. Apply it together with `chromie.grounded-external-information` so evidence strategy and weather-specific interpretation remain distinct.

This Agent Skill does not resolve user references, geocode places, retry provider query forms, register `chromie.weather.lookup`, or authorize execution. Goal Association owns reference resolution and bindings. The Weather Capability adapter owns provider-compatible location forms and candidate validation.

## Weather method

- Preserve the canonical location exactly as resolved in the Goal.
- Preserve time scope and requested weather aspects; do not silently narrow annual, comparative, current, or forecast questions. A relative expression such as “tonight” carries `date=today` plus `day_part=night`; neither dimension replaces the other.
- Retrieve verified memory only when the original weather tool identity and all material arguments match exactly and freshness is sufficient.
- Otherwise execute `chromie.weather.lookup` with the canonical location and requested scope. Copy an `entity_type=date` binding to `args.date` and an `entity_type=day_part` binding to `args.period`; when both exist, both arguments are required and their exact canonical values must be preserved.
- Interpret successful no-rain/no-snow evidence as a valid negative observation, not a failure.
- On terminal evidence reentry, answer only the requested weather aspect and temporal scope. For a requested day part, use the matching `forecast_period` fields rather than unrelated current/daily values. A precipitation probability is probabilistic evidence: report the probability or possibility and never strengthen it into certainty that rain will or will not occur.
- Distinguish `location_not_found`, network/provider failure, timeout, unavailable Capability, and successful weather evidence.
- When the Host returns exact Goal-bound terminal Evidence, the reactivated Fast
  Planner summarizes only the fields relevant to the question in natural
  user-focused speech, preserves numeric values without replacing a period
  minimum/maximum with current conditions, and carries the Evidence references on the Communicative
  Activity.

## Provider boundary

Hierarchical place normalization and provider geocoding retries remain inside the Weather Capability adapter. They may represent the same canonical place in provider-compatible forms, but they cannot alter Goal bindings, resolve “there,” or choose between locations from conversation history.
