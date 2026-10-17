A person corrected the result of a saved label-placement rule on one diagram: they moved some labels by hand. Decide how
to revise the rule, ask the person what you need, and save the revision once they have approved it, or stop. You decide
which questions to ask and when to stop.

Each turn, reply with ONE JSON object and nothing else, choosing one of the `options` the message lists:
  {"choose": "<option id>"}
For the `abstain` option also give a reason: {"choose": "abstain", "reason": "<why>"}.

{{SHARED_GRAMMAR}}

A SCOPE is one condition over a label `o` and its node `object(o.attached)` naming which labels the revision changes,
for example `o.role == "warning"`. Each candidate revision (S1, S2, ...) is a revised rule plus its scope.

THE OPTIONS (only the legal ones are listed each turn; every turn is one model call, and turns are limited):
  propose_scope        get up to 3 candidate revisions with their scopes, drafted from the correction (one more call).
  ask_scope:S1[,S2]    ask the person which of these scopes they meant (they may also say it was a one-off override
                       or an accident, or that none fits). Offered while no scope is authorized.
  ask_choose:DOC:S1,S2 after a scope is authorized: show the person those revisions' outputs on DOC to pick one.
  affected:S1          ask the person to approve the earlier examples that S1 would change.
  revision_preview:S1  ask the person to approve S1's output on up to three documents.
  commit:S1            save S1. Offered only when its scope is authorized, every earlier example it changes was
                       approved, its revision preview was approved, and it changes nothing outside its scope.
  abstain              stop; the saved rule stays as it is.

HOW A CORRECTION ENDS. A revision is saved only by commit, which needs the scope authorized and the revision preview
approved. If the person says the edit was an override or an accident, that is recorded for you and the rule stays.

THE MESSAGE gives: the corrected document and the labels the person moved, the saved rule, the candidate revisions
(id, scope, summary, how many earlier examples they change), what is authorized and approved so far, the budget, the
`options`, and the `history` of your earlier choices and their results.
