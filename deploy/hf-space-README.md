---
title: Open Apprentice
emoji: 🧩
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Teach a layout rule once; it asks when unsure and proves what it did.
---

# Open Apprentice (live demo)

Teach an agent a layout rule by placing a badge on a card. It finds an input where candidate rules disagree, asks you by picture, seals the rule with a hash, carries it to a
second graphics engine, repairs only the native procedure when a tool silently changes, and ships an evidence package you can re-check offline.

This Space runs the whole product in one container (API, web app, and a Chromium-driven Konva/Fabric engine). **Reference mode uses no model and costs nothing.**
Nemotron mode (if enabled by the operator) is capped and metered. Source and honest results: see the repository README and `docs/status.md`.
