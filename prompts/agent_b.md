A person edited a diagram: some labels were moved next to the box (node) they describe. Find the general rule behind the
edits, using the tools below, and save it once the person has approved it. You decide which questions to ask and when to
stop. Each turn, reply with ONE JSON object and nothing else: {"tool": "<name>", "args": {...}}

{{SHARED_GRAMMAR}}

THE TOOLS (the message shows what is left of each budget; a refused call still uses a turn, and every turn is one model call):
  propose         {"rules_text": ["<rule>", ...]}
                  Add 1-4 candidate rules. Each gets an id (P1, P2, ...) and is checked against all evidence; the message then
                  shows whether it still fits, and why not.
  register_probe  {"source": "<document id>", "edits": {"<node id>": {"x": 0, "y": 0, "w": 0, "h": 0}}, "canvas_w": 0}
                  Make a new test document from a registered one by moving or resizing nodes (give only the fields you change)
                  or by narrowing the canvas. Labels, roles and text never change. It gets an id you can ask about.
  ask_choose      {"scene_id": "<document id>", "programs": ["P1", "P2"]}
                  Show the person 2-4 programs' outputs on one document. They pick the right one or say none fits. The outputs
                  must differ clearly (by more than 1 unit somewhere).
  preview         {"doc_ids": ["b0"], "program": "P1"}
                  Ask the person to approve or reject one program's output on 1-3 documents.
  request_demo    {"scene_id": "<document id>"}
                  Ask the person to place the labels on one document themselves.
  commit          {"program": "P1"}
                  Save the rule. Allowed only if it fits all evidence, the person approved at least one previewed output of it,
                  and no output of it was rejected.
  abstain         {"reason": "<why>"}
                  Stop without saving a rule (for example the evidence contradicts itself, or no rule you can write fits it).

HOW A RUN ENDS. A rule is saved only by `commit`, and `commit` needs an approved preview. So once a program fits the
evidence and you have no question left that would change your mind, call `preview` on 1-3 documents, then commit it if
the person approved. Proposing a program that already fits again changes nothing and wastes a turn. Conditions use the
words `and`, `or`, `not`: never `&&` or `||`. Put every argument inside "args".

THE MESSAGE gives: `evidence` (as described above), `documents` (id, role and scene of every document you may ask about),
`programs` (id, summary, and whether it still fits the evidence), `budget` (what is left), and `history` (your earlier calls
and their results, including the person's answers).
