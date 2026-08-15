## Weather information method — Goal Association

Represent a weather Goal with explicit bindings for location and time/date or forecast horizon, plus the requested weather aspects and any comparison or answer-shape qualifiers. For a resolved local day part, use the provider-neutral semantic binding `entity_type=day_part` with one canonical value: `morning`, `afternoon`, `evening`, or `tonight`; preserve the user's natural wording in the Goal description. A direct place mention becomes the location binding. Resolve “there,” “that place,” or similar references before this method is applied, using current discourse and scoped referents rather than prior weather evidence.

A correction such as replacing one city with another supersedes the earlier referent for the current Goal; the old result remains historical only. If location or time scope is ambiguous, clarify specifically. Do not turn provider-recognized spellings or geocoding candidates into semantic bindings.
