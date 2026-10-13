"""Write the task rows (JSONL) for the calibrated-asking environment. Each row: the prompt the model sees (demonstration + tool
descriptions, identical wording for every task, no hint about whether a task is ambiguous) plus the episode fields the server uses.

Usage (from the gym/ folder, with the repo's src on the path):  python resources_servers/oa_calibrated_asking/create_dataset.py
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from open_apprentice.evaluation.asking_env import MAX_ASKS, AskingEnv  # noqa: E402

TOOLS = [
    {
        "type": "function",
        "name": "ask",
        "description": f"Ask the teacher to show the true outcome of the hidden rule on a new input. At most {MAX_ASKS} questions; each one costs. badge: card_widths has exactly one width; spacing: 2 to 5 widths. Widths are integers from 24 to 512.",
        "parameters": {
            "type": "object",
            "properties": {"card_widths": {"type": "array", "items": {"type": "integer"}}},
            "required": ["card_widths"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "commit",
        "description": "Commit your final rule, written as text in the rule grammar. It is final once it parses and evaluates; a rule that does not parse is returned to you with the error.",
        "parameters": {
            "type": "object",
            "properties": {"rule": {"type": "string"}},
            "required": ["rule"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "abstain",
        "description": "Decline to commit a rule.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def prompt_for(env: AskingEnv) -> str:
    obs = env.observation()
    return (
        "A teacher showed you ONE example of a layout rule you cannot see. Work out the rule and commit it.\n"
        "Your rule will be tested on many other inputs, not only this one. You may ask the teacher to show the true outcome on new inputs, "
        f"but at most {MAX_ASKS} times and every question has a cost. Decide for yourself whether you need to ask. "
        "When you are ready call commit with your rule, or call abstain if you cannot.\n\n"
        f"EXAMPLE ({obs['demonstration']['kind']}):\n"
        f"before = {json.dumps(obs['demonstration']['before'])}\n"
        f"after = {json.dumps(obs['demonstration']['after'])}\n"
        f"({obs['demonstration']['note']})\n\n"
        f"RULE GRAMMAR:\n{obs['rule_grammar']}\n"
    )


def rows(split: str = "development", seed: int = 0, episodes: int = 12) -> list[dict]:
    out = []
    for index in range(episodes):
        for kind in ("badge", "spacing"):
            env = AskingEnv(split, seed, index, kind)
            out.append(
                {
                    "responses_create_params": {
                        "input": [{"role": "user", "content": prompt_for(env)}],
                        "tools": TOOLS,
                        "parallel_tool_calls": False,
                    },
                    "split": split,
                    "seed": seed,
                    "index": index,
                    "kind": kind,
                }
            )
    return out


if __name__ == "__main__":
    here = pathlib.Path(__file__).parent / "data"
    here.mkdir(exist_ok=True)
    all_rows = rows()
    (here / "development.jsonl").write_text("\n".join(json.dumps(r) for r in all_rows) + "\n")
    (here / "example.jsonl").write_text("\n".join(json.dumps(r) for r in all_rows[:3]) + "\n")
    print(f"wrote {len(all_rows)} rows (3 in example.jsonl)")
