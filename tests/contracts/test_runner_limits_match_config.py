import yaml

from open_apprentice.evaluation.runner import EPISODE_LIMITS


def test_runner_limits_equal_every_protocol_config():
    for name in ("dev", "pilot", "counterexample", "portable", "final"):
        b = yaml.safe_load(open(f"configs/{name}.yaml"))["budgets"]
        assert (
            b["episode_total_tokens"],
            b["episode_provider_calls"],
            b["episode_primitive_actions"],
        ) == (EPISODE_LIMITS.tokens, EPISODE_LIMITS.calls, EPISODE_LIMITS.actions), name
