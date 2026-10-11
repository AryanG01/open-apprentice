You control a 2D drawing scene only through a small set of tools. Solve the task by replying with ONE JSON
object: {"diagnosis": "<short, evidence-based note>", "program": [ ...statements... ]}. No other text.

TOOLS (call with named args; results are objects):
- inspect_scene() -> {nodes:[{id,type,parent,x,y,width,height,scaleX,scaleY,fill}]}  (x,y are in the node's parent frame)
- observe_geometry(node_ids:[...]) -> {bounds:[{id,left,top,width,height}]}  (actual rendered WORLD geometry)
- measure_node(node_id) -> {x,y,width,height,frame}
- move_node(node_id,x,y)   resize_node(node_id,width,height)   inspect_node(node_id)   finish(summary)
Verify with observe_geometry rather than assuming how a tool interprets its arguments.

PROGRAM LANGUAGE (JSON AST; nothing else is allowed):
Statements: {"op":"let","name":N,"value":E} | {"op":"call","tool":T,"args":{k:E},"bind":N} |
{"op":"for_each","var":V,"over":E,"body":[...]} | {"op":"if","cond":E,"then":[...],"else":[...]} |
{"op":"assert","cond":E,"message":S} | {"op":"return","value":E}
Expressions: a literal (number/string/bool/list), {"ref":"locals.NAME"} (dotted paths allowed, e.g. "locals.m.width"),
{"op":OP,"args":[E,...]} with OP in add sub mul div min max len index get lt le gt ge eq ne and or not.
Limits: 64 statements, nesting depth 8, loops over <=16 items, 500 expression evaluations, 100 tool calls.
Program-writing rules that matter (violations fail the program at run time):
  - add, sub, mul, div take EXACTLY 2 arguments; nest them for more terms (min and max accept any number). A branch that only runs when a check
    fails still must be valid: it is executed the first time the backend behaves differently from what you expected.
  - EVERY tool call costs one native action and the total is capped. Observe ALL nodes you need with ONE observe_geometry call (a list), not one call per node.
  - A correction must be derived from the observed geometry of THAT node versus its target (e.g. move by target minus observed), re-checked once;
    do not hard-code constants or assume the error is the same for every size, position or object.


WORKED EXAMPLE of a valid program (a different, trivial task: move every target, then check one node). Copy the STRUCTURE, not the logic:
[{"op":"for_each","var":"t","over":{"ref":"inputs.targets"},"body":[
  {"op":"call","tool":"move_node","args":{"node_id":{"ref":"locals.t.id"},"x":{"ref":"locals.t.x"},"y":{"ref":"locals.t.y"}}},
  {"op":"call","tool":"observe_geometry","args":{"node_ids":{"op":"list","args":[{"ref":"locals.t.id"}]}},"bind":"obs"},
  {"op":"let","name":"left","value":{"ref":"locals.obs.bounds.0.left"}},
  {"op":"if","cond":{"op":"ne","args":[{"ref":"locals.left"},{"ref":"locals.t.x"}]},"then":[
    {"op":"call","tool":"move_node","args":{"node_id":{"ref":"locals.t.id"},"x":{"op":"add","args":[{"ref":"locals.t.x"},{"op":"sub","args":[{"ref":"locals.t.x"},{"ref":"locals.left"}]}]},"y":{"ref":"locals.t.y"}}}]}]}]
Every expression is either a plain number/string, {"ref":...}, or {"op":...,"args":[...]}; there is no other form (no "filter", "map", "lambda", "fn").
