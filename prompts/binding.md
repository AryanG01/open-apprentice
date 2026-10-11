You write a small PROGRAM that makes a drawing backend realise a list of TARGETS using only its tools.
Reply with ONE JSON object: {"candidates": [{"diagnosis": "<short note>", "program": [ ...statements... ]}, ...]}
with at most 3 DIFFERENT candidates. No other text.

The program receives `inputs.targets`: a list of objects with desired WORLD top-left geometry:
  {"kind":"move_existing","id":ID,"x":..,"y":..,"w":..,"h":..}       move an existing node so its top-left is (x,y)
  {"kind":"resize_existing","id":ID,"x":..,"y":..,"w":..,"h":..}     resize an existing node to w x h
  {"kind":"clone_place","symbol":S,"proto":ID,"x":..,"y":..,"w":..,"h":..}   create a copy of node ID, named S, with top-left (x,y)
After running, observe_geometry must report each target's left/top/width/height. Do not assume a tool
interprets x,y the way you expect: the documentation may not tell the whole story, so VERIFY with
observe_geometry and correct if needed.

PROGRAM LANGUAGE (JSON AST only):
Statements: {"op":"let","name":N,"value":E} | {"op":"call","tool":T,"args":{k:E},"bind":N} |
{"op":"for_each","var":V,"over":E,"body":[...]} | {"op":"if","cond":E,"then":[...],"else":[...]} |
{"op":"assert","cond":E,"message":S} | {"op":"return","value":E}
Expressions: literal | {"ref":"inputs.targets"} | {"ref":"locals.NAME"} (dotted paths ok, e.g. "locals.t.x") |
{"op":OP,"args":[...]} with OP in add sub mul div min max lt le gt ge eq ne and or not len index get list
(list builds an array from expressions, e.g. {"op":"list","args":[{"ref":"locals.nid"}]}, at most 16 elements).
Tools and the EXACT shape of what they return (access results with dotted paths):
  observe_geometry(node_ids: LIST) -> {"bounds": [{"id","left","top","width","height"}, ...]}   e.g. locals.obs.bounds.0.left
  measure_node(node_id) -> {"x","y","width","height","frame"}   (the backend's own frame; verify with observe_geometry)
  move_node(node_id,x,y) / resize_node(node_id,width,height) / clone_node(node_id,new_id) -> an object describing the node
  inspect_node(node_id), inspect_scene() -> {"nodes": [...]}
node_ids must be a LIST: build one with {"op":"list","args":[E]}. A wrong path or a non-list is a runtime error and fails the program.
Limits: 64 statements, nesting depth 8, loops over <=16 items, 100 tool calls.

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
