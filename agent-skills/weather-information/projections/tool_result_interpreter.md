## Weather information method — Tool Result Interpreter

Use trusted weather evidence for the bound location and time scope. Select only fields relevant to the question: condition, temperature, apparent temperature, rain status, precipitation amount/probability, snow, wind, or forecast timing. Preserve units and distinguish measured/current values from forecast values.

A successful zero precipitation or explicit no-rain/no-snow result is a valid negative weather observation. `location_not_found` means the requested place could not be resolved by the provider; it is not evidence about weather. Network, timeout, provider, cancellation, and malformed-result failures are operational failures and must not become weather claims. Answer naturally for the user without exposing raw payloads, internal field names, provider implementation, or unrelated metrics.
