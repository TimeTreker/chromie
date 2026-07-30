## Weather information method — Fast Planner

For a fully bound weather Goal, consider exact verified memory first. Use `chromie.memory.retrieve_verified_tool_result` only when the indexed original tool is `chromie.weather.lookup`, the canonical location and all material time/aspect/unit arguments exactly match, the result completed successfully, and freshness satisfies the request. The index itself is not weather evidence.

Otherwise execute `chromie.weather.lookup`. Keep `args.location` exactly equal to the canonical Goal binding. Optional `location_context` may describe the same place but cannot select a different one. Preserve current/forecast/comparison scope and requested aspects such as rain, temperature, apparent temperature, precipitation, snow, wind, or condition. Never answer from an older location's result or narrow the question to fit available fields.
