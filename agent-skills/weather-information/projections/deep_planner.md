## Weather information method — Deep Planner

Choose a terminal plan for each weather Goal. Exact fresh verified memory may be retrieved explicitly when tool identity and every material binding match; mismatched location, date/horizon, aspect, unit, completion state, or freshness requires a fresh `chromie.weather.lookup`. An unresolved location/time reference requires clarification, not evidence reuse.

Keep the canonical location unchanged through the Plan. Provider-specific geocoding adaptation is outside planning. Distinguish unavailable weather capability, `location_not_found`, provider/network/timeout failure, and a successful result. Multi-Goal turns may use memory for one Goal and fresh lookup for another without cross-contaminating bindings or evidence.
