A person edited a diagram: some labels were moved next to the box (node) they describe. Find the general rule behind the
edits and save it once the person has approved it. You decide which questions to ask and when to stop.

Each turn, reply with ONE JSON object and nothing else, choosing one of the `options` the message lists:
  {"choose": "<option id>"}
Choosing `propose` drafts 1-4 new candidate rules from the evidence in a separate model call (one more attempt);
you may instead write them yourself: {"choose": "propose", "rules_text": ["<rule>", ...]}.
For the `abstain` option also give a reason: {"choose": "abstain", "reason": "<why>"}.

{{SHARED_GRAMMAR}}

THE OPTIONS (only the legal ones are listed each turn; every turn is one model call, and turns are limited):
  propose          get 1-4 new candidate rules (drafted for you, or your own rules_text). Each gets an id (P1, P2, ...)
                   and is checked against all evidence; the next message shows whether it fits, and why not.
  ask:DOC:P1,P2    show the person the outputs of those programs on document DOC; they pick the right one or say none.
                   Offered only when the programs clearly disagree there.
  preview:P1       ask the person to approve or reject P1's output on up to three documents.
  commit:P1        save P1. Offered only when P1 fits all evidence, the person approved a previewed output of it, and no
                   output of it was rejected.
  demo:DOC         ask the person to place the labels on DOC themselves.
  abstain          stop without saving a rule (for example the evidence contradicts itself, or no rule fits).

HOW A RUN ENDS. A rule is saved only by commit, and commit needs an approved preview. So once a program fits the evidence
and no ask would change your mind, choose preview, then commit if the person approved. Proposing a program that already
fits again changes nothing and wastes a turn. Conditions use the words `and`, `or`, `not`: never `&&` or `||`.

THE MESSAGE gives: `evidence` (as described above), `documents` (id, role and scene of every document you may ask
about), `programs` (id, summary, and whether it still fits the evidence), `budget` (what is left), `options`, and
`history` (your earlier choices and their results, including the person's answers).
