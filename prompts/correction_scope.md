A user corrected the result of a saved label-placement program on one diagram. Propose up to 3 DIFFERENT revised programs that
reproduce the user's correction, each with the SCOPE it applies to. Reply with ONE JSON object and nothing else:
{"candidates": [{"summary": "<one plain sentence>", "rule_text": "<the revised program>", "selector": "<one expression>"}, ...]}

THE EVIDENCE.
- `base_program`: the program that produced the result the user corrected (its text form).
- `corrected_scene`: the ORIGINAL diagram before the program ran (objects with id, kind, role, attached, x y w h; canvas w h).
- `corrected_labels`: the labels the user moved and their new top-left (x, y). ONLY these were corrected.
- Labels the user did NOT touch are not approvals of their current position; do not assume they are right or wrong.

THE SELECTOR names which labels the revision is meant to change: ONE boolean expression over the label `o` and its node
`object(o.attached)`, using only role, attachment and the ORIGINAL geometry, for example `o.role == "warning"` or
`o.w > object(o.attached).w` (a label wider than its node). No loops, no `let`, no `move`, no braces.
Compare values of the diagram with each other (a label's or node's sizes and positions) rather than with fixed numbers;
fixed sizes copied from the corrected diagram are rejected.

Each candidate must reproduce every corrected label exactly and change nothing outside its selector on other diagrams. If a
candidate also changes some earlier approved examples, say so in its summary; the user will be asked to approve those changes.

THE RULE LANGUAGE is the same as for learning (see the grammar section below).

THE RULE LANGUAGE (exact numbers only: integers or decimals like 0.5; strings in double quotes):
  let NAME = EXPR                                   define a value
  move V to (EXPR, EXPR)                            set the top-left (x, y) of an object (V is a loop variable or a name from let)
  for V in objects { ... }                          repeat for every object, in order
  if CONDITION { ... } else { ... }
EXPR uses + - * / ( ), comparisons < <= > >= == !=, and/or/not, min(a,b), max(a,b), numbers, strings, names defined with let,
V.x V.y V.w V.h, canvas.w canvas.h, and the text fields V.id V.kind V.role V.attached (compare text with == or !=).
object(EXPR) is the object whose id equals EXPR, for example  let a = object(V.attached)  then  a.x, a.w ...
Multiply or divide ONLY by constants (never value*value). Put each statement on its own line. A rule can only READ the
original positions; every `move` takes effect together at the end.
