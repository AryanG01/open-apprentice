"""Real-SVG lane (spec 6.8, EXPERIMENTAL): owner-authored SVG documents stay authoritative; edits are a typed, whitelisted `set_attribute` patch applied
to the ORIGINAL BYTES (so an export differs from the import only in the patched attributes). Nothing here executes or fetches anything."""
