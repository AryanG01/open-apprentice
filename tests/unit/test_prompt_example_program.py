"""The worked example shown to the model in every program prompt must itself be a valid, runnable program."""

import json
import re
from pathlib import Path

import pytest

from open_apprentice.concepts.bindings import BINDING_TOOLS
from open_apprentice.skills.interpreter import validate_program

PROMPTS = ["binding.md", "synth_program.md", "fresh_gap_row.md"]


@pytest.mark.parametrize("name", PROMPTS)
def test_worked_example_in_prompt_validates(name):
    text = (Path("prompts") / name).read_text()
    block = text.split("WORKED EXAMPLE", 1)[1]
    start = block.index("[{")
    end = block.index("Every expression is")
    program = json.loads(re.sub(r"\s*\n\s*", "", block[start:end].strip()))
    validate_program(program, frozenset(BINDING_TOOLS))
