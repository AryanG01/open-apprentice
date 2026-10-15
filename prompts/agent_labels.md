You are an agent learning a diagram-editing rule from demonstrations. A user moved some labels next to the box (node) they
describe. You will later be judged on NEW diagrams, so the rule you commit must be the one the user really means, not just one
that fits the examples. Do not commit to a guess when the examples leave the rule open: ask the teacher first.

THE EVIDENCE has `scene` objects (id, kind "node" or "label", role, attached = the id of the node a label describes, and
x y w h = top-left corner, width, height) and `labels_moved_to` (the new top-left of each label that moved; sizes never change and every other object stays where it was). BATCH lists further
diagrams, each with an index, that your rule will be applied to; they are shown WITHOUT the result.

YOUR MOVES. Reply with ONE JSON object and nothing else, with "action" set to one of:
  {"action": "ask", "batch_index": N}      the teacher shows the correct result on batch diagram N (at most 3 asks in total;
                                           pick diagrams where plausible rules would behave differently)
  {"action": "commit", "rule_text": "..."} your final rule in the language below; it is checked on every demonstration and every
                                           teacher answer, and you get exact feedback and may revise (at most 3 attempts)
  {"action": "abstain", "reason": "..."}   if no rule in this language can reproduce the evidence
(rule_text is a normal JSON string; use \n for line breaks.)

THE RULE LANGUAGE (exact numbers only: integers or decimals like 0.5; strings in double quotes):
  let NAME = EXPR                                   define a value
  move V to (EXPR, EXPR)                            set the top-left (x, y) of an object (V is a loop variable or a name from let)
  for V in objects { ... }                          repeat for every object, in order
  if CONDITION { ... } else { ... }
EXPR uses + - * / ( ), comparisons < <= > >= == !=, and/or/not, min(a,b), max(a,b), numbers, strings, names defined with let,
V.x V.y V.w V.h, canvas.w canvas.h, and the text fields V.id V.kind V.role V.attached (compare text with == or !=).
object(EXPR) is the object whose id equals EXPR, for example  let a = object(V.attached)  then  a.x, a.w ...
Multiply or divide ONLY by constants (never value*value). One statement per line. A rule only READS the original positions;
every `move` takes effect together at the end. Write general rules that loop over objects and test kind, role and
surroundings; do not rely on object ids or list positions.

EXAMPLE of the syntax on an UNRELATED task (every label of role "draft" is shifted left by half its own width):
for o in objects {
  if o.kind == "label" and o.role == "draft" {
    move o to (o.x - o.w / 2, o.y)
  }
}

EXAMPLE of a "blocked" test on another unrelated task (a badge goes to the right of its box unless another box is in the way,
then it goes above the box). Scan the other objects with a nested loop and remember the result in a flag:
for b in objects {
  if b.kind == "badge" {
    let t = object(b.attached)
    let blocked = 0
    for p in objects {
      if p.id != b.id and p.id != t.id and t.x + t.w + 5 < p.x + p.w and p.x < t.x + t.w + 5 + b.w and t.y < p.y + p.h and p.y < t.y + b.h {
        let blocked = 1
      }
    }
    if blocked == 1 {
      move b to (t.x, t.y - b.h - 5)
    } else {
      move b to (t.x + t.w + 5, t.y)
    }
  }
}
Compare positions with OTHER objects' positions, never with fixed numbers such as `w == 80` or `x < 50`, and never test ids.

Things the evidence may leave open: which side of the node the label goes on; how far (a fixed gap, or related to sizes); how it is
aligned; what happens when the preferred spot is blocked (it would overlap another object or leave the canvas) and where the label
goes instead; and WHICH labels the rule applies to (all, or only some roles). Ask the teacher about a batch diagram where plausible
rules would behave differently.
