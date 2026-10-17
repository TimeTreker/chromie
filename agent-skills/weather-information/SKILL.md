# Weather Information

## Purpose

Use this passive domain method for weather Goals involving an already resolved location, time/date or forecast horizon, and one or more requested aspects such as condition, temperature, apparent temperature, rain, precipitation, snow, wind, or comparison. Apply it together with `chromie.grounded-external-information` so evidence strategy and weather-specific interpretation remain distinct.

This Agent Skill does not resolve user references, geocode places, retry provider query forms, register `chromie.weather.lookup`, or authorize execution. Goal Association owns reference resolution and bindings. The Weather Capability adapter owns provider-compatible location forms and candidate validation.

## Weather method

- Preserve the canonical location exactly as resolved in the Goal.
- Preserve the Goal's human temporal scope and requested weather aspects; do not silently narrow annual, comparative, current, or forecast questions. Temporal conversion into provider arguments belongs only to the selected Capability's declared `argument_realization` contract.
- Retrieve verified memory only when the original weather tool identity and all material arguments match exactly and freshness is sufficient.
- Otherwise execute `chromie.weather.lookup` with the canonical location and requested scope. Follow that Capability's current `argument_realization` contract when mapping human temporal scope into provider-local arguments, and record Planner semantic-realization provenance instead of rewriting the Goal.
- Interpret successful no-rain/no-snow evidence as a valid negative observation, not a failure.
- On terminal evidence reentry, decide only whether the Evidence answers the requested weather aspect and temporal scope. For a requested day part, the matching `forecast_period` fields answer it, not unrelated current/daily values. A precipitation probability is probabilistic evidence, not certainty.
- Distinguish `location_not_found`, network/provider failure, timeout, unavailable Capability, and successful weather evidence.
- When the Host returns exact Goal-bound terminal Evidence, the reactivated
  Planner establishes the answer Need over the Evidence that answers the question;
  it authors no words. Social Cognition words the answer from that Evidence: it keeps
  numeric values, does not replace a period minimum/maximum with current conditions,
  reports a probability as a possibility rather than a certainty, and cites the
  Evidence on its Communicative Activity.

## Provider boundary

Hierarchical place normalization and provider geocoding retries remain inside the Weather Capability adapter. They may represent the same canonical place in provider-compatible forms, but they cannot alter Goal bindings, resolve “there,” or choose between locations from conversation history.
