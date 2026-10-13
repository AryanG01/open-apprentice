A user edited a diagram: some labels were moved next to the box (node) they describe. Propose up to 4 DIFFERENT general
rules that explain every demonstration and would also apply to other diagrams. Reply with ONE JSON object and nothing else:
{"candidates": [{"summary": "<one plain sentence>", "rule_text": "<the rule, in the small language below>"}, ...]}
(rule_text is a normal JSON string; use \n for line breaks.) If you believe NO rule in this language can reproduce the
evidence exactly, reply {"candidates": []} instead of guessing.

THE EVIDENCE. Each item has a `scene` with `objects` and a `canvas`, and `resulting_geometry`: the position and size of EVERY
object after the edit (objects that did not move are listed unchanged). Each object has: id, kind ("node" or "label"),
role (labels only, e.g. "note" or "warning"; empty for nodes), attached (for a label, the id of the node it describes),
and x y w h (top-left corner, width, height). The canvas size is canvas.w and canvas.h. Several evidence items may be given;
a rule must reproduce all of them. Rules apply to other diagrams with different numbers and arrangements of objects, so write
rules that LOOP over objects and test their kind, role and surroundings; do not rely on object ids or positions in the list.

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

EXAMPLE of the syntax on an UNRELATED task (every label of role "draft" is shifted left by half its own width):
for o in objects {
  if o.kind == "label" and o.role == "draft" {
    move o to (o.x - o.w / 2, o.y)
  }
}

HOW TO CHOOSE DIFFERENT CANDIDATES. A few demonstrations rarely pin the rule down. Things the evidence may leave open: which side
of the node the label goes on; how far (a fixed gap, or related to sizes); how it is aligned with the node; what happens when
the preferred spot is blocked (it would overlap another object or leave the canvas) and where the label goes instead; and WHICH
labels the rule applies to (all labels, or only some roles, or only some situations). Propose 3 or 4 candidates that differ in
these respects (not merely in the numbers), where each still reproduces ALL the evidence EXACTLY. Prefer simple rules and round
numbers. Make the candidates behave genuinely differently on OTHER diagrams. If earlier candidates were rejected, the message
lists each one with the reason: do not repeat those mistakes.
