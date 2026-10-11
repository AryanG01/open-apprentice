A user demonstrated one layout change on a 2D scene. Propose up to 4 DIFFERENT general rules that explain it and
would also apply to other sizes and positions. Reply with ONE JSON object and nothing else:
{"candidates": [{"summary": "<one plain sentence>", "rule_text": "<the rule, in the small language below>"}, ...]}
(rule_text is a normal JSON string; use \n for line breaks.)

HOW THE EVIDENCE MAPS TO THE RULE. Each evidence item has a `scene` with `objects` (a list, in order) and a `canvas`.
In a rule, the K-th entry of that list (0-based) is objects[K]; you may also write the id shown in the FIRST evidence scene
(it means the object at that same position, so the rule applies to other scenes by position). Fields: .x .y .w .h
(top-left corner, width, height). The canvas size is canvas.w and canvas.h. In `resulting_geometry`, a key that is NOT
in scene.objects is a NEW object (a copy) created by the change: produce it with `clone`.

THE RULE LANGUAGE (exact numbers only: integers or decimals like 0.08; no other functions):
  let NAME = EXPR                                   define a value
  move OBJ to (EXPR, EXPR)                          set the top-left (x, y) of an existing object
  resize OBJ to (EXPR, EXPR)                        set width and height
  clone OBJ as NAME at (EXPR, EXPR)                 a NEW copy of OBJ whose top-left is (x, y)
  for V in objects { ... }                          repeat for every object, in order (optionally: for V in objects with I { ... })
  if CONDITION { ... } else { ... }
OBJ is objects[K] or a loop variable. EXPR uses + - * / ( ), comparisons < <= > >= == !=, and/or/not, min(a,b), max(a,b),
numbers, names defined with let, objects[K].x, V.w, canvas.w. Multiply or divide ONLY by constants (never value*value).
Put each statement on its own line.

EXAMPLE of the syntax on an UNRELATED task (shift the first object right by three eighths of its own width, same height):
let shift = 0.375 * objects[0].w
move objects[0] to (objects[0].x + shift, objects[0].y)

Make the candidates genuinely different in how they behave on OTHER inputs, not rewordings. Prefer simple rules.
If earlier candidates were rejected, the message lists each one with the reason: do not repeat those mistakes.
