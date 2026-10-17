A user corrected the result of a saved label-placement program on one diagram. Propose up to 3 DIFFERENT revised programs that
reproduce the user's correction, each with the SCOPE it applies to. Reply with ONE JSON object and nothing else:
{"candidates": [{"summary": "<one plain sentence>", "selector": "<one expression>", "patch_text": "<the movement for the selected labels>"}, ...]}

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

THE PATCH is a few statements for ONE label `o` (its node is `object(o.attached)`) that say where `o` goes. The system
applies the saved program first and then your patch to every label the selector names, so labels outside the selector keep
the saved behaviour. Do not write loops or a whole program. Example for the selector `o.role == "warning"`:
  let a = object(o.attached)
  move o to (a.x + (a.w - o.w) / 2, a.y + a.h + 12)

Each candidate must reproduce every corrected label exactly. If a candidate also changes some earlier approved examples,
say so in its summary; the user will be asked to approve those changes.

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
