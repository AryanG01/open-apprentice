"""Learner side of the Plan 5 evaluation: one isolated process per episode. Never imports the evaluator."""

from open_apprentice.teaching.probes import Probe, ProbeResult


def synthetic_render(probe: Probe) -> ProbeResult:
    """Battery scenes are exact rational geometry: the probe's selection geometry is what is shown."""
    return ProbeResult(ok=True, scene_id=probe.probe_id, scene=probe.scene)
