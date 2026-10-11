You control a 2D drawing scene only through tools. You are shown TEACHING EVIDENCE: examples of a layout change a user
taught (geometry before and after, user choices among shown results, corrected examples), possibly with a short plain
summary of what was learned. Write ONE program that makes the same kind of change on the TASK scene.
Reply with ONE JSON object: {"diagnosis": "<short, evidence-based>", "program": [ ...statements... ]}. No other text.

The program receives inputs: selected_ids (list), prototype_id (string), canvas ({w,h}). Do NOT hard-code ids or numbers
copied from the task scene, so the program can be reused on other scenes: read geometry with the tools.
Task kinds: "concept_1" = apply the first taught change to the selected objects; "concept_2" = apply the second taught
change once per selected object (it creates a new object by cloning the prototype); "concept_1_then_concept_2" = do the
first change, then the second on the result. New objects MUST be created with clone_node using
new_id = "badge_" + <id of the object it belongs to>, built with the "name" op below.

TOOLS: inspect_scene() -> {nodes:[{id,x,y,width,height,...}]}; observe_geometry(node_ids:[...]) -> {bounds:[{id,left,top,
width,height}]} (actual rendered WORLD bounds - verify with it); measure_node(node_id); move_node(node_id,x,y);
resize_node(node_id,width,height); clone_node(node_id,new_id); inspect_node(node_id). Positions arguments may not mean
exactly what you assume: verify with observe_geometry and correct.

PROGRAM LANGUAGE (JSON AST only): Statements: let{name,value} | call{tool,args,bind} | for_each{var,over,body} |
if{cond,then,else} | assert{cond,message} | return{value}. Expressions: literal | {"ref":"inputs.selected_ids"} |
{"ref":"locals.NAME"} (dotted paths ok) | {"op":OP,"args":[...]} with OP in add sub mul div min max lt le gt ge eq ne and
or not len index get list name; {"op":"name","args":["badge_", E]} joins a string prefix with a string value.
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
