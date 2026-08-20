## Weather information method — Deep Planner

Choose a terminal plan for each weather Goal. Exact fresh verified memory may be retrieved explicitly when tool identity and every material binding match; mismatched location, date/horizon, aspect, unit, completion state, or freshness requires a fresh `chromie.weather.lookup`. An unresolved location/time reference requires clarification, not evidence reuse.

Keep the canonical location unchanged through the Plan. Preserve the Goal's human temporal scope and follow `chromie.weather.lookup`'s declared `argument_realization` contract when producing provider-local temporal arguments; record semantic-realization provenance rather than rewriting the Goal. Provider-specific geocoding adaptation is outside planning. Distinguish unavailable weather capability, `location_not_found`, provider/network/timeout failure, and a successful result. Multi-Goal turns may use memory for one Goal and fresh lookup for another without cross-contaminating bindings or evidence.

On terminal evidence, interpret the exact requested human temporal scope and aspect. Use a matching `forecast_period` only when the Planner's Capability-bound realization established that provider period, preserve returned numbers exactly, omit unrelated fields, and express precipitation probability as uncertainty rather than certain rain/no-rain.
