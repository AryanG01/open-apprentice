# Product policy "product-1" (live sessions on the public site)

Live sessions on the public site run **product-1**: policy A, plus one change. When a reply is cut off at the completion
cap, the round ends with no candidates instead of stopping the session with an error (`StepConfig(tolerate_truncation=True)`;
`service.step_config`). Everything else matches A: the prompts, the 8-attempt budget, the single revision round, the
probes, the previews and the checks.

- **Why:** a live demo session on 2026-10-18 failed after 11 minutes on exactly this error (`provider: truncation`). The
  same error ended 10 of A's runs on the final split.
- **It is not the evaluated system.** The final results (`final_results.md`) are for policy A and stay as published. No
  product-1 result is claimed anywhere until it has been measured, and any measurement will be reported separately.
- **Offline sessions** (no model) are unaffected and run policy A.
- **Disclosure in the product:** a session's provenance line names its policy when it is not A
  (`Model: Live · Teacher: You · Policy: product-1`). Each session also records `policy` in its metadata.
- **Diagnostics:** every model call records its wall time (`usage.elapsed_s`) so that time to the first question can be
  measured.
