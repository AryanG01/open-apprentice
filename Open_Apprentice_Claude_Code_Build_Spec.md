# Open Apprentice — end-to-end build specification for Claude Code

**Version:** 1.3 — real-SVG applicability and an external evaluation gate  
**Prepared:** 8 October 2026; updated 9 October 2026, Asia/Singapore  
**Owner:** Aryan Ganju; solo builder  
**Event:** Nebius x NVIDIA Global AI Hackathon  
**Submission deadline:** 31 October 2026, 01:00 SGT / 30 October 2026, 17:00 UTC  
**Recommended track:** Coding and Agentic Engineering; confirm the final category against the shipped project  
**Document status:** An implementation specification. No application, benchmark results, API account access, or measured performance is implied.

## 0. How to use this file

Place this file at the root of the project directory on the implementation device. Open that directory in Claude Code. Paste the kickoff prompt in section 30.

Read this entire document before making architectural decisions. It is self-contained; access to the original brainstorming conversation is unnecessary.

Build Open Apprentice only. Counterfactual Lab and Kernel Researcher were alternatives considered during ideation and are outside this project.

Treat this as a specification of the desired outcome and proposed engineering decisions. Respect existing repository instructions, user changes, permissions, and tool restrictions. Resolve routine implementation details independently. Record material departures in docs/decisions.md, including the reason and effect on the research claim.

Continue from implementation into verification and documentation. Do not stop after generating a scaffold, a UI mockup, or an architecture plan. Missing credentials should block live inference only: finish deterministic tests, the mock provider, the interface, deployment files, and instructions first. Label every mock and replay explicitly.

The finished product must make it possible to answer:

> Can an open-model agent expose where its learned visual rule might be wrong, obtain the missing evidence, and transfer or repair that rule without silently changing what the user taught it?

### 0.1 Hackathon context

The Nebius x NVIDIA Global AI Hackathon asks builders to create working AI systems using NVIDIA open models on Nebius infrastructure. Its advertised prize pool is USD 50,000. For this project, the essential platform integration is actual Nemotron inference through Token Factory [S10a].

The four tracks are Coding and Agentic Engineering, Best Apps and Agents, Personal AI, and Physical AI. We selected Coding and Agentic Engineering because the deliverable learns, executes, checks, and revises reusable tool procedures. Best Apps and Agents remains a reasonable category if the final product emphasizes the teaching interface more strongly; choose one based on what actually ships.

Judging equally weights technical implementation, product design, potential impact, and idea quality. Build evidence for all four. The public demo, repository, license, video, submission deadline, and judging-access requirements are specified in sections 25–27 [S10a, S10b].

### 0.2 Builder context and selection criteria

Aryan is building solo and can devote substantial time to the project. The deadline still limits the scope, and available API credits/hardware have not been established.

The explicit brief is to think like an NVIDIA judge or AI researcher: prioritize an interesting capability, meaningful model use, a memorable demonstration, and rigorous evidence. Do not anchor the idea in the builder's prior operations work.

The user also requested strict grading, research-backed improvements, and a self-contained handoff to Claude Code on another device. More components, a longer document, or higher claimed scores do not establish a better project.

### 0.3 Why Open Apprentice was selected

| Direction considered | Attraction | Reason for the decision |
| --- | --- | --- |
| Open Apprentice | Learning, reusable skills, visible generalization, CPU-hosted tool environments | Best balance of an interesting agent capability, measurable outcomes, and solo delivery |
| Counterfactual Lab | Visually strong robotics failure discovery and repair | More simulation/integration work and strong existing falsification methods to beat |
| Kernel Researcher | Deep GPU engineering and direct NVIDIA relevance | Crowded research area, demanding correctness/performance work, and a weaker distinctive contribution so far |

The choice is Open Apprentice. The original design emphasized selective repair of stored procedures; that remains the execution foundation. Version 1.1 makes learning portable intent the central product capability.

### 0.4 What changed to justify a stronger concept

The upgrade is a specific chain of capabilities:

1. Infer multiple plausible reusable rules from a demonstration.
2. When the intended rule is ambiguous, select a discriminating example and ask the user.
3. Preserve the inferred rule separately from the native tool procedure.
4. Generate and check a new implementation of the same rule in a second tool.
5. Combine two independently learned rules on a task never demonstrated as a whole.
6. If tool behavior changes, repair the affected implementation while preserving the rule and earlier validated behavior.

This is the selected v1.1 target, not a list of optional future features. Control its size by reducing task breadth: two small concepts, two graphics backends, one composition family, and one drift family first.

Historical v1.1 assessment: the previous concept rating was 7.5/10, and that revision had approximately 8.5/10 hackathon concept potential because it targeted a more useful and demonstrable generalization capability. These are subjective design assessments, not measured project scores. Section 0.5 gives the current assessment and scope.

A 9+ assessment would require convincing unseen-task/second-tool results against strong baselines and a complete product. No 10/10 claim is justified at planning time. If only the original repair loop ships, do not present the upgrade's rating or capability claims as achieved.

### 0.5 Selected v1.2 direction and precedence

The owner asked for further research toward a defensible 9.5/10. The new literature check found closer precedents: Socrates already synthesizes clarifying multiple-choice queries [S16]; ContractSkill already supports checked, local skill repair [S17]; VASO uses formal counterexamples to improve reusable skills [S18]. Those ingredients alone do not earn a novelty claim.

The selected improvement is **a counterexample loop grounded in actual tool execution**, presented through a usable visual teaching experience:

1. Nemotron proposes candidate rules from a demonstration.
2. A bounded search finds an input on which the rules disagree, or a rule violates an explicitly stated constraint.
3. A human resolves preference ambiguity; real tool execution resolves implementation uncertainty.
4. The system changes the affected artifact, retaining an immutable record of earlier teaching evidence.
5. A judge can challenge the result with fresh supported inputs, transfer it to the other engine, and export both the editable output and reproducible evidence.

This is an engineering and evaluation contribution to test, not a claim of a new general learning algorithm. The most important technical question is whether abstract checks remain useful when actual tool behavior differs from the model used by the checker.

**Strict assessment:** roughly 9/10 concept potential for this narrower, demonstrable target. A 9.5 is a target for an exceptional implemented submission, contingent on section 27.5. No working software or experimental evidence has been reviewed for this assessment. Do not describe this revision as having already achieved 9.5.

**Precedence:** v1.2 sections override earlier scope where explicitly stated. Sections 7.5, 8.9, 12.5, 21.11, and 27.5 are authoritative additions. The two-backend intent/binding architecture remains. Defer the adaptive-audit policy comparison, generic composition planner, extra drift families, and GEPA integration. Use failure-triggered checked repair first; support only one fixed two-concept composition. This trades breadth for stronger evidence rather than adding another full project.

The first product task is a user-specific visual rule across a batch of layouts, such as a badge margin that scales with a card but has a minimum and maximum. Ordinary equal-gap alignment is the tutorial, not the headline application. Figma already supports Auto Layout and suggested layout structure [S20]. We must demonstrate a useful teaching/correction workflow and exportable results, and compare with an ordinary template or layout tool where applicable.

### 0.6 Further research: the remaining gap to a 9.5 submission

The 9 October research pass identified a stronger application/evaluation direction: **learn a user's recurring SVG edit, apply it to fresh assets, and preserve unrequested content**. A useful output is an editable design file with an inspectable edit history. The existing badge example remains a teaching tutorial.

Vector-Bench provides an external repair/preservation/validity test [S22]. VectorGym supplies expert-authored editing examples relevant to more complex design work [S24]. The programming-by-example study [S25] motivates holding out rule structures and asset families rather than only dimensions. These sources strengthen the testing plan; they do not validate our product or establish that its algorithm is novel.

**Selected next action:** after the core teaching path works, timebox a real-SVG compatibility and baseline spike to two development days. Sections 6.8 and 21.12 define it. Preserve any implementation already built on the other device. This revision does not order a wholesale backend replacement or a third general graphics engine. If the spike succeeds, prioritize one real-asset teaching/batch/export workflow over optional query ablations or broader backend support. If it fails, retain v1.2 and state that real-asset applicability is unproven.

The rating remains roughly 9/10 concept potential, with a conditional 9.5 implemented-submission target. Another literature pass has not earned another half-point. A stronger assessment would require the core effect, useful real artifacts, and fair comparisons in both the controlled study and external trial.

Do not transfer the 90% controlled-task target in section 27.5 to an unrelated public benchmark. Different task definitions, supported operations, budgets, and input modalities require separate results. The public trial is an additional credibility test for the 9.5 ambition, not a substitute for proving learning from demonstrations.

### Reading map

- Sections 1–5: product, research claim, scope, architecture, repository.
- Sections 6–13: tool environment, skill language, learning, controller, diagnostics, repair, verifier.
- Sections 14–20: inference, persistence, API, interface, isolation, budgets.
- Sections 21–24: experiments, tests, milestones, implementation commands.
- Sections 25–30: deployment, submission, grading, risk decisions, sources, kickoff prompt.

Read sections 0.5, 1.7, 2.6, 7.4–7.5, 8.6–8.9, 12.5, 21.10–21.11, and 27.5 before implementing the orchestration. Section 23 gives the revised delivery gates. Section 30 remains the pasteable kickoff prompt.

For v1.3, also read 0.6, 6.8, and 21.12. These add a bounded applicability trial; all earlier evidence and safety boundaries remain.

## 1. Product and audience

### 1.1 One-sentence pitch

Teach Open Apprentice a visual rule; it finds revealing test cases, learns from your corrections, and reuses the rule through checked procedures in two supported graphics engines.

### 1.2 Specific user

The first product audience is people repeatedly preparing related visual layouts who can demonstrate their preferred rule more easily than write a program. Agent developers are the secondary audience for the inspectable skill package and evaluation framework. Whether either group benefits enough to adopt the tool is an empirical question, not established demand.

The visual demonstration is a design workspace: an agent learns procedures for arranging and modifying graphic objects. This provides immediately visible outcomes and deterministic geometric checks.

The product is a research-oriented developer tool with a usable creative workspace. It is not an operations dashboard. Keep infrastructure details in an optional evidence panel.

The concrete product benefit is that users can teach a reusable design rule without scripting a separate macro for every tool. Developers can inspect which rule was inferred, how its implementation was validated, and where transfer remains unsupported.

### 1.3 User journey

1. Open a sample design task and inspect the starting canvas and requested outcome.
2. Ask the agent to solve it, or record an explicit demonstration using the same supported tools.
3. Review the extracted reusable procedure and its validation evidence.
4. Apply that procedure to a new design.
5. Introduce an environment change through a separate evaluator control.
6. Watch the agent notice contradictory evidence, choose an experiment, and propose a repair.
7. Compare the result with a baseline agent and inspect retained abilities.
8. Export a versioned skill package and an evidence report.

The v1.1 path also includes a targeted clarification when needed, transfer to the second backend, and composition of two learned rules. Keep the ordinary explicitly specified task path for baseline comparisons and debugging.

### 1.4 The central demonstration

Teach a procedure that arranges differently sized objects in a row with a fixed edge-to-edge gap. Then ask for a fresh arrangement with different sizes and nesting.

Change a tool's coordinate interpretation without announcing it to the agent. The existing procedure may now move objects to the wrong positions. The agent must use ordinary observations and controlled experiments to discover what went wrong.

Show:

- the original procedure and its earlier successful output;
- the failure after a change;
- the diagnostic comparison and evidence;
- the proposed procedure or applicability update;
- independent checks and regression replay;
- another task solved after recovery.

Do not hardcode which skill should fail, what the repair is, or when the agent should declare recovery. The evaluator may control the change; the agent must not receive the evaluator's private labels.

### 1.5 Product boundaries

The agent initially observes structured scene/tool data. The canvas is the human-facing visualization. Do not claim visual perception, computer use from pixels, general intelligence, autonomous scientific discovery, or model-weight learning.

Keep model weights fixed in the principal experiments. The changing artifacts are executable procedures, their applicability conditions, and accumulated evidence.

### 1.6 The upgraded demonstration

Start with equal-sized cards arranged evenly. That example is compatible with both equal center spacing and equal edge gaps. Neither the model nor a simulator can infer the user's preference uniquely from that example alone.

The agent proposes a new layout with unequal widths and displays the different predicted outcomes. The user chooses the intended result or says neither. The choice narrows the candidate rules.

Then:

1. Apply the inferred rule to fresh dimensions and nesting in Konva.
2. Switch to Fabric, with its actual native operations and public documentation.
3. Have Nemotron generate/check a backend-specific implementation of the same rule.
4. Teach a second small rule, such as badge placement with a relative margin.
5. Ask for a new layout combining both rules.
6. Change one tool behavior and show whether only the relevant binding needs repair.

All stages need not run live within three minutes. A video may show an honestly labeled recorded execution; the deployed app must still support the claimed functions.

The initial rules are deliberately small. Generalization beyond two graphics libraries, arbitrary applications, or arbitrary user demonstrations is outside the claim.

### 1.7 The v1.2 demonstration and its actual limits

Use a custom badge-placement rule as the main visual story. An illustrative target is a margin equal to 8% of card width, clamped between 8 and 24 pixels. At width 150, its 12-pixel margin also fits a constant-margin rule and an unclamped proportional rule. The formula and constants are evaluator/user knowledge; never seed them as the learner's answer.

The system generates competing explanations and finds a simple supported layout where they predict visibly different outputs. Show the alternatives on the canvas. The user picks an output or chooses Neither and supplies a corrected example. The resulting concept must survive new sizes, including inputs near a branch boundary.

This example illustrates ambiguity; it does not imply that every parameter of a clamped rule is identifiable from one answer. If the allowed examples do not resolve competing explanations, retain uncertainty or stop at the teaching budget. Demonstrate the successful measured case honestly and report unresolved cases in evaluation.

Then transfer the concept from Konva to Fabric. In a labeled controlled challenge, alter a native coordinate convention. The inferred rule can still produce correct desired targets while the native procedure places the badge incorrectly. Compare intended targets with actual observed geometry, expose a concrete witness, repair the binding, and replay earlier examples. The concept hash must stay unchanged for a binding-only repair.

For a composition example, arrange the cards and then apply the independently learned badge rule. Keep this two-stage pipeline explicit; a general-purpose planner is unnecessary.

Important distinctions:

- A disagreement is not automatically an error. Only new user evidence can settle an unstated preference.
- A successful solver check does not prove real tool behavior or recover an omitted user intention.
- If no candidate expresses the intended behavior, selecting Neither must permit a new candidate or an honest unresolved result.
- A corrected example is an additional teaching interaction, with its time and cost counted.
- The judge chooses fresh dimensions or supplies a supported scene after the learned artifacts are frozen. This challenges memorization, but is not a statistically sufficient evaluation by itself.
- Edited video and replay may explain a slow run, but must be labeled. The hosted challenge must execute real code.

The visible sequence should be teach, inspect a revealing case, correct or confirm, challenge, transfer, and export. Infrastructure and model details belong in the evidence drawer.

## 2. Research foundations and honest contribution

### 2.1 What is reused

| Source | Relevant mechanism | Implementation decision |
| --- | --- | --- |
| SkillApt, September 2026 preprint [S01] | Matched executions with and without a retrieved skill; activation based on evidence | Reimplement a transparent applicability baseline and use paired diagnostics |
| GEPA, accepted to ICLR 2026 [S02, S03] | Reflection on execution evidence to propose and evaluate textual improvements | Start with a bounded reflective repair search; add a real GEPA adapter only if it improves the experiment |
| SkillCommit, August 2026 preprint [S04] | Cross-instance replay before accepting broader skill changes | Validate candidate updates against earlier supported cases before promotion |
| LILO, ICLR 2024 [S13] | Learning interpretable program libraries through synthesis, compression, and documentation | Motivation for separating reusable concepts from individual task traces |
| Active Task Disambiguation with LLMs [S14] | Selecting clarifying questions by reasoning about competing solutions | Generate a small candidate set and choose examples where predictions differ |
| Break It Down, Pass It On, August 2026 preprint [S15] | Controlled study of skill granularity and representation; text/subtask skills transferred better in its experiments | Learn small concepts and include a text-memory baseline rather than assuming executable memory always wins |

SkillApt explicitly distinguishes its main frozen study from real temporal drift. That motivates an experiment here; it does not prove our proposed contribution is unprecedented. SkillCommit and GEPA also do not establish the performance of our implementation.

The GEPA repository is publicly available. SkillApt's checked paper states that code/artifacts will be released. A public SkillCommit implementation was not verified. Do not make either unreleased implementation a critical dependency.

Respect third-party licenses and preserve attribution. A paper's availability is not permission to copy unrelated implementation code without checking its license.

### 2.2 Proposed contribution

Implement and evaluate **demonstration-based learning of portable rules, with budgeted clarification, tool experimentation, transfer, composition, and selective repair**.

The v1.1 hypothesis, retained as background to the selected v1.2 question in section 2.6:

> Under matched demonstration, clarification, and computation budgets, separating learned intent from native execution can improve held-out transfer and composition while retaining earlier behavior.

The original selective-repair hypothesis remains a secondary question. A controller that simply checks everything may be useful, but it does not establish selective resource-allocation benefits. Neither hypothesis is a result until measured.

### 2.3 Claims we may make only after evidence

- Better post-change task success: requires paired comparisons on locked episodes.
- Lower recovery cost: must include diagnosis, repair, replay, and failed calls.
- Retention: requires earlier tasks to be replayed under their original environment snapshots.
- Cross-tool generalization: requires the independently developed second backend and a declared supported task subset.
- Learning useful skills: requires unseen parameter combinations and meaningful advantages over a competent fresh agent.

Never describe a heuristic score as a calibrated probability or a paired stochastic run as conclusive causal proof. Never call this a faithful reproduction of a paper unless its protocol actually matches.

### 2.4 Strict prior assessment

Historical concept assessments were approximately 7.5/10 for v1.0 and 8.5/10 for v1.1. The selected v1.2 direction has approximately 9/10 concept potential, with a conditional 9.5 submission target. These subjective judgments must not be confused with a measured grade or prize probability.

Do not put a fabricated 10/10 rating, invented speedup, or expected experimental result into the README or demo.

### 2.5 What the upgrade does and does not establish

Library induction and active disambiguation already have substantial prior research [S13, S14]. Combining them does not establish scientific priority.

Our proposed system-level contribution is an inspectable, open-model pipeline that preserves inferred intent across real tool implementations, chooses useful clarifications/probes, and isolates implementation repair. The focused evaluation must determine whether this combination actually helps.

LILO's full compression/search system is not a required dependency. The first implementation uses a small generated hypothesis set, a declared disagreement heuristic, a restricted rule language, and the existing procedure validator. Do not claim to reproduce LILO or Bayesian optimal experiment design.

The cross-task transfer paper's findings are domain/model dependent [S15]. They motivate a text-memory baseline and smaller learned units; they do not prove that our representations will outperform others.

### 2.6 Further research and the sharper experiment

| Primary source | Finding relevant to this decision | Consequence for Open Apprentice |
| --- | --- | --- |
| Socrates, PLDI 2026 [S16] | Uses semantic program clusters and informative multiple-choice questions; its convergence result assumes a finite hypothesis space containing the target and correct answers | Credit interactive disambiguation; explicitly test omitted hypotheses and Neither instead of assuming the target was proposed |
| ContractSkill, March/April 2026 preprint [S17] | Makes procedural artifacts explicit enough for verification, fault localization, and local repair; evaluates portability within related benchmark settings | Include a strong structured-procedure repair baseline; local repair alone is not the differentiator |
| VASO, June 2026 preprint [S18] | Connects formal counterexamples to reusable skill revision; states that an unverified state-to-proposition mapping can invalidate its guarantees | Check witnesses against actual tool behavior and state precisely which semantics were modeled |
| SynGuar, 2021 [S21] | Studies generalization guarantees from examples under explicit assumptions and additional sampling | Do not turn a few examples or candidate agreement into a statistical guarantee |

The proposed research question is now:

> At fixed teaching and computation budgets, does separating user-taught intent from native execution, together with grounded counterexamples, improve unseen rule application and reduce harmful repairs compared with a competent structured-procedure learner?

This is a proposed system experiment. It does not establish a first-ever method, reproduce these papers, or inherit their guarantees. The geometry domain makes a small symbolic search feasible, but also creates a demanding alternative explanation: an ordinary symbolic synthesizer may solve the task just as well. Test that possibility early.

There are two different contributions to evaluate: user effort needed to acquire a useful rule, and correct native execution under changed inputs/tools. Report both. Success at one cannot compensate for failure at the other.

The public Socrates artifact was located, but a reusable code license was not verified during this review. Do not copy it into the project without resolving its license. Reimplement the small declared mechanism independently, with attribution. ContractSkill's public code is also useful for inspecting baseline design; porting an entire web benchmark is outside scope.

## 3. Scope and decision hierarchy

### 3.1 Required first vertical slice

- One real graphics backend: Konva in a controlled browser runtime.
- Rectangle-based scenes, primitive tools, and the gap-row family first.
- A typed JSON procedure language.
- One Nemotron model served through Nebius Token Factory.
- A fresh agent, skill extraction, reuse, a transparent controller, and a bounded repair loop.
- Independent result checks, immutable snapshots, versioned skills, and cost records.
- One semantic drift condition and a no-change control.
- A real UI that renders live events and artifacts.

### 3.2 Required before the final submission

- Two learned concepts, initially spacing and badge placement, with bounded hypothesis generation and user clarification.
- Konva and Fabric implementations for a declared narrow common subset.
- One held-out composition family and one semantic drift family plus no-change controls.
- The focused v1.1 comparison in section 21.10 and locked evaluation manifests.
- Regression replay and rollback.
- Exportable skills, execution traces, and machine-readable results.
- A hosted live demo, public licensed repository, setup documentation, feedback, and a short demonstration video.

For v1.2, the counterexample loop and focused tests in 21.11 take priority over broadening this list. If transfer or composition fails its gate, ship a clearly scoped fallback and remove the corresponding capability claim. Do not claim an upgrade merely because its interface exists.

The additional fit-group family, three-family drift matrix, and full original six-policy repair study are expansion work after the focused experiment. This reallocation is how the stronger capability remains plausible for a solo build.

The v1.2 mandatory additions are a bounded witness finder, concrete witness replay, honest evidence states, one useful editable-output workflow, the stronger procedure baseline, and a target-omission stress test. Implement failure-triggered repair first. Selective proactive auditing remains specified below as optional research machinery, not a release gate.

### 3.3 Defer

Fine-tuning, reinforcement learning, a vector database, arbitrary Python/JavaScript generated by the agent, general browser automation, multi-user collaboration, a marketplace, mobile apps, paid billing, screenshot understanding, physical robots, and kernel optimization.

A collection of additional models is not a substitute for demonstrating the core effect.

### 3.4 Default engineering stack

These are chosen implementation defaults, not assertions that they are the latest releases.

| Component | Choice |
| --- | --- |
| Python | 3.12; uv; committed uv.lock |
| API and orchestration | FastAPI, Pydantic 2, HTTPX, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 16 |
| Durable jobs | PostgreSQL jobs table; one worker initially |
| Node runtime | Node 22.12 or newer within the supported Node 22 line; use a supported newer LTS if a chosen dependency requires it |
| Frontend | React, TypeScript, Vite, a small maintained component set |
| Graphics runtime | Konva first; Fabric.js second |
| Browser execution and E2E checks | Playwright, version matched to its browser installation |
| Local orchestration | Docker Compose |
| Deployment | The same containers on one Linux host; Token Factory hosts inference |
| Artifacts | Local persistent volume first; an object-storage adapter only when needed |

At initialization, resolve compatible package versions, run a smoke test, and commit exact lockfiles. Do not put unverified latest version numbers into this specification or silently update dependencies during the final experiment.

## 4. Architecture and trust boundaries

~~~mermaid
flowchart TD
    UI["React workspace"] --> API["FastAPI"]
    API --> DB["PostgreSQL and job queue"]
    WORKER["Agent worker"] --> DB
    WORKER --> TF["Nemotron on Token Factory"]
    WORKER --> ENGINE["Graphics tool runtime"]
    ENGINE --> ART["Snapshots and rendered artifacts"]
    EVAL["Evaluator and experiment harness"] --> ENGINE
    EVAL --> DB
~~~

### 4.1 Responsibilities

**Frontend:** task entry, scene display, teaching controls, progress, side-by-side output, skill inspection, and report export.

**API:** authentication, authorization, request validation, run creation, cancellation, artifact access, and event streaming. It does not execute model-generated code.

**Worker:** agent steps, deterministic policy decisions, budgets, inference requests, skill extraction/repair, and orchestration of allowed tool actions.

For v1.1, also orchestrate intent hypotheses, human clarification, backend binding generation, and bounded composition. A human answer resumes a durable teaching job; do not keep a database transaction or paid provider call open while waiting.

**Graphics runtime:** a small internal Node service controlling Playwright browser contexts. It imports only our shipped Konva/Fabric code, accepts allowlisted operations, and returns observations/artifacts.

**Evaluator:** deterministic goal checking and experiment control. It owns hidden drift schedules and locked evaluation details. Agent requests cannot read or mutate that state.

**Database:** durable run state, leases, skills, evidence, artifacts, budgets, and event ordering.

### 4.2 Agent-visible versus evaluator-private information

| Agent-visible | Evaluator-private |
| --- | --- |
| User request and declared task requirements | Drift label, intervention seed, activation time |
| Tool names, public schemas, public documentation | Hidden implementation switches and private backend snapshots |
| Scene observations obtained through tools | Hidden final-test variants and expected-result files |
| Past visible tool outcomes and authorized feedback | Final benchmark score before the episode is sealed |
| Skill text/program and its accessible evidence | Verifier source, database credentials, infrastructure secrets |

Public API documentation is available equally to all policies. A documented change is not an unannounced semantic-change result. Controlled undocumented changes are benchmark interventions and must be described as such.

The evaluator may return coarse development feedback such as an observable constraint failing. It must not disclose an answer program, corrected coordinates, hidden drift ID, or private test cases.

Demonstration-only teaching is a separate mode. Its latent intended rule is available to the human/benchmark teacher, not directly to the learner. The learner receives demonstrations and bounded answers to its questions. This is not the explicitly specified task mode; keep their inputs and evaluation semantics separate.

### 4.3 Concurrency and reproducibility

- Serialize tasks within each experimental episode.
- Use isolated browser contexts for separate runs and for both arms of a paired diagnosis.
- Snapshot before running an experiment; never compare different starting states.
- Give each policy its own skill/evidence history.
- Keep separate namespaces for development, validation, final evaluation, and public demo sessions.
- Record backend version, adapter version, tool schema hash, verifier version, prompts, model identity, and controller configuration.
- A public schema hash may signal a documented change. An internal drift hash must never be passed to the controller.

## 5. Repository contract

Create this structure, adjusting only where an existing repository already imposes a sensible equivalent:

~~~text
Open_Apprentice_Claude_Code_Build_Spec.md
README.md
LICENSE
THIRD_PARTY_NOTICES.md
CLAUDE.md
.env.example
compose.yaml
pyproject.toml
uv.lock
package.json
package-lock.json
apps/web/
services/engine/
src/open_apprentice/
  api/
  agent/
    runner.py
    controller.py
    acquisition.py
    diagnosis.py
    repair.py
    promotion.py
  concepts/
    schemas.py
    hypotheses.py
    query_selection.py
    bindings.py
    composition.py
  skills/
    schemas.py
    interpreter.py
    retrieval.py
    evidence.py
  providers/
    nebius.py
    mock.py
    capabilities.py
  environments/
    client.py
    observations.py
  evaluation/
    verifier.py
    episodes.py
    baselines.py
    metrics.py
    report.py
  storage/
  jobs/
  cli.py
schemas/
prompts/
configs/
  dev.yaml
  pilot.yaml
  portable.yaml
  final.yaml
benchmarks/
  development/
  validation/
  final/
tests/
  unit/
  integration/
  contracts/
  evaluation/
  e2e/
scripts/
docs/
  architecture.md
  decisions.md
  status.md
  experiment_protocol.md
  capabilities.json
  deployment.md
  demo_script.md
  hackathon_submission.md
  provider_feedback.md
  limitations.md
~~~

The application implementation must not import private benchmark manifests or verifier answer data. Enforce this separation with dependency boundaries and tests.

CLAUDE.md should summarize project commands and invariants, and point back to this specification. Do not copy credentials or device-specific absolute paths into it.

Use structured logs and versioned JSON schemas. Generate frontend API types from the backend contract instead of maintaining incompatible hand-written copies.

## 6. Graphics environments and task definitions

### 6.1 Why use real graphics libraries

Implement the first environment on Konva, rather than building a complete graphics engine. Its node and transform APIs provide a concrete external integration [S11].

The second environment uses Fabric.js [S12]. It must execute through Fabric's actual object/transform behavior, not be a second label for the Konva implementation.

Both may render inside a fixed, locally bundled browser page. The agent does not need direct browser control.

### 6.2 Canonical task representation

Use an evaluator-owned canonical representation for task generation, comparison, and initial scene creation:

~~~json
{
  "task_id": "dev-gap-row-0001",
  "family": "gap_row",
  "canvas": {"width": 800, "height": 500},
  "instruction": "Arrange the three selected cards left to right with a 24 px edge gap, preserving their order and sizes.",
  "selected_ids": ["card_a", "card_b", "card_c"],
  "parameters": {"gap_px": 24, "left_px": 80, "top_px": 120},
  "initial_scene_ref": "scene-0001",
  "public_constraints": ["preserve_order", "preserve_sizes", "stay_on_canvas"],
  "schema_version": 1
}
~~~

The task goal describes desired world-space outcomes. Tool-native coordinates may differ. Do not silently normalize every action into a universal semantic API, because that would remove the adaptation problem being studied.

Publish all default task invariants, including preservation of unrelated objects and styles, in the task/tool documentation supplied to every policy. The final verifier must not penalize a policy for a requirement that was never disclosed.

Never expose the backend's private drift variant through task IDs, scene labels, error messages, artifact filenames, or model prompts.

Add goal_source with values explicit_task and demonstration. The existing example is explicit_task. In demonstration mode, the learner-facing payload contains example before/after scenes, selected objects, neutral instruction, and public preservation constraints. Omit the private rule/family name, formula, and answer parameters. Do not leak equal_edge_gap through an ID or a supposedly descriptive field.

### 6.3 Initial task families

1. **gap_row:** arrange 3–8 rectangles with specified edge gaps, order, and vertical alignment.
2. **fit_group:** scale/translate a group into a target frame while preserving aspect ratio, child order, and relative layout.
3. **badge_attach:** clone and position a small badge at the requested corner of a card or nested group, preserving unrelated objects.

Add rotation, masking, and export-format changes only after these work. Rectangle geometry deliberately makes independent verification tractable. Include varied sizes and nested groups; fixed-size examples alone are too easy to memorize.

For the v1.1 focused build, prioritize gap_row and badge_attach. fit_group and broader drift coverage follow the main transfer/composition gate.

### 6.4 Primitive tool surface

All functions need non-empty descriptions and strict argument validation.

| Tool | Input | Returned observation |
| --- | --- | --- |
| inspect_scene | No arguments | Object IDs, types, parent relationships, public native properties |
| inspect_node | node_id | Native properties and supported capabilities |
| observe_geometry | ordered node_ids | Public world-space bounds from the actual rendered objects |
| measure_node | node_id | Bounds according to the current tool contract |
| move_node | node_id, x, y | Updated public properties or typed failure |
| resize_node | node_id, width, height | Updated public properties or typed failure |
| set_style | node_id, allowlisted style fields | Updated allowed style values |
| clone_node | node_id | New node_id |
| group_nodes | ordered node_ids | Group node_id |
| ungroup_node | node_id | Ordered child IDs |
| export_scene | format in png/svg where supported | Artifact ID, dimensions, MIME type |
| finish | result summary | Ends the current attempt |

Do not expose a high-level arrange_row or solve_task tool. That would hide the procedure we want the agent to learn.

observe_geometry is a measurement surface, not an action normalizer: it reports visible geometry but does not implement native moves, resize conversions, or task solutions. Give every policy the same access and charge its calls. Keep the final verifier's implementation independent. Do not claim screenshot perception.

Use explicit capability errors for genuinely unsupported operations. Do not pretend both backends support the same operations.

### 6.5 Tool service implementation

- Start one Playwright browser process per engine service and use bounded context pooling.
- Load the local bundled application and assets only.
- Browser evaluation executes our static allowlisted dispatcher, not arbitrary model-provided JavaScript.
- One session holds one scene and backend instance.
- Enforce session ownership, action counts, node counts, numeric bounds, and per-action deadlines.
- Close contexts on cancellation, lease loss, timeout, or terminal completion.
- Recreate snapshots from immutable scene data plus the private environment configuration.
- Attach monotonically increasing scene revision numbers to responses.
- Mutations require the expected revision; stale writes return a conflict instead of silently overwriting changes.
- Tool action IDs support idempotent delivery. A retried clone must not create another object.

### 6.6 Controlled drift families

These are artificial benchmark interventions, not claims about actual Konva/Fabric releases.

| Family | Intervention | Expected diagnostic challenge |
| --- | --- | --- |
| Coordinate semantics | A move operation switches from parent-local positions to world positions while preserving its argument schema | Discover the correct frame for the affected procedure |
| Size semantics | A resize operation switches between intrinsic object dimensions and rendered dimensions affected by scale | Determine whether scale must be accounted for |
| Group semantics | Grouping preserves world placement under one mode and changes the interpretation of child positions under another | Identify the interaction between grouping and subsequent moves |

Constrain variants to deterministic, well-defined behavior and implement reference solutions. Reject impossible tasks during dataset generation.

Maintain no-change episodes and irrelevant-change episodes. A controller should not repair everything merely because unrelated tools changed.

The evaluator changes semantics between tasks, not halfway through one tool transaction. Keep the environment fixed during both diagnostic arms and candidate validation. Additional within-task drift is out of scope.

### 6.7 Independent second integration

After the Konva pipeline passes its gates:

1. Implement Fabric-native primitive operations and scene serialization.
2. Restrict to a declared common subset, initially gap_row and badge_attach.
3. Expose legitimate backend identity and public docs equally to all policies.
4. Evaluate held-out object layouts and adapter-specific semantics.
5. Report transfer separately from artificial drift results.

Do not claim generalization because two adapters share our wrapper code. Report their shared surface and the independent underlying library behavior.

### 6.8 Real-SVG trial: a narrow integration, not a new editor

First support owner-authored or provenance-verified SVG assets containing editable rectangles/groups plus inert vector detail. Keep the original document as the authoritative source. Do not reconstruct the entire asset through Konva or Fabric and assume that the round trip preserves it. This lane is distinct from the existing two-engine transfer experiment.

Expose a public read-only element inventory, geometry, and original SVG source within explicit size limits. The user can select objects in teaching/product mode. In an external scored task, object selection must come from the public instruction and source; never supply private target IDs or preservation annotations.

Nemotron emits a bounded typed patch through the existing restricted interpreter. Start with set_attribute on existing elements for numeric geometry, fill/stroke, stroke width, and local translation; add no arbitrary JavaScript, CSS, path synthesis, deletion, or insertion in the first spike. Declare the exact attribute/element whitelist. Each patch names the source document hash, element identifier, attribute, expected old value, and new value. Reject stale revisions, duplicate/conflicting writes, invalid values, and unsupported edits. Materialize a complete SVG by applying the patch to an isolated copy of the original document.

The narrow operation set deliberately limits benchmark coverage. Unsupported tasks remain visible in coverage reports. Do not broaden the interpreter hastily to obtain a better score or call a selected subset the full benchmark.

Apply patches transactionally. Validate XML, unique IDs where required, local references, and supported attribute syntax. Reject active content, external resource references, and unsupported embedded documents before opening an upload. Render in the existing isolated browser with external network disabled. Reject incompatible assets rather than silently sanitizing away content and claiming it was preserved.

Use trusted native SVG geometry calls and explicit coordinate transforms; local bounding boxes are not automatically world coordinates [S27]. Verify behavior in the locked browser. Save original and modified documents, normalized structural differences, rendered previews, and measured geometry. Pure-rule solver claims still apply only to the earlier restricted domain; they do not extend to arbitrary SVG paths or document rendering.

Preservation needs more than checking which attribute strings changed. A changed parent transform, shared style, or definition can affect descendants or other referenced objects. Initially disallow edits to shared definitions/style rules and compute the affected descendant set for group changes. Compare both structure and relevant rendered geometry. Report the checked scope; this is not a universal guarantee of visual equivalence.

A model-proposed edit scope is an operational hypothesis, not ground truth. In product mode the user may explicitly confirm that scope. In evaluation, final requested edits and protected content remain private. A checker that merely confirms the model stayed inside its own chosen scope cannot establish task correctness.

Make the same patch tools, parser, runtime checks, rollback behavior, and public observations available to every baseline. If the only gain comes from avoiding full-document generation, credit the patch representation rather than claiming that learned memory caused it.

Spike exit criteria: import and export at least three distinct supported assets without unrelated changes, execute one learned edit on a fresh asset, reject a deliberately harmful patch, and complete the matched pilot in 21.12. If these do not work within the timebox, keep this lane experimental. Successful SVG execution is not evidence of arbitrary-app transfer.

## 7. Executable skill representation

### 7.1 Skill package

A skill is a versioned, typed procedure plus provenance and applicability evidence. It is not just a paragraph in a vector store.

Required fields:

~~~json
{
  "schema_version": 1,
  "skill_id": "gap_row",
  "version": 1,
  "parent_version": null,
  "title": "Arrange objects with equal edge gaps",
  "description": "Preserve object order and dimensions while placing selected objects in a row.",
  "input_schema": {
    "type": "object",
    "properties": {
      "node_ids": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 8},
      "gap": {"type": "number", "minimum": 0, "maximum": 200},
      "left": {"type": "number"},
      "top": {"type": "number"}
    },
    "required": ["node_ids", "gap", "left", "top"],
    "additionalProperties": false
  },
  "required_tools": ["measure_node", "move_node"],
  "assumptions": [
    {"key": "move_frame", "expected": "parent_local", "evidence_refs": []}
  ],
  "program": [],
  "provenance": {
    "origin": "agent_extracted",
    "source_run_ids": [],
    "model_id": "configured-at-runtime",
    "prompt_hash": "computed-at-runtime"
  },
  "status": "candidate"
}
~~~

This example defines a package shape; its empty program is a placeholder and must not pass executable-skill validation. Model-produced packages must contain a valid program before they can run.

Maintain evidence records in the database, referenced by ID. Avoid rewriting the entire skill file whenever another observation arrives.

Assumptions are hypotheses. Their labels are not hidden environment truth. A skill may require a cheap observable probe to establish applicability.

### 7.2 Restricted procedure language

Use JSON AST interpretation. No eval, exec, generated shell, imports, arbitrary expressions, remote URLs, file paths, or dynamic code loading.

Allowed statement forms:

- let: assign a named local from an expression.
- call: invoke an allowlisted primitive tool and bind its response.
- for_each: bounded iteration over an input list.
- if: branch on a typed boolean expression.
- assert: reject the current procedure attempt if an observable invariant fails.
- return: provide the result payload.

Allowed expression forms:

- literal JSON values;
- input/local references;
- allowlisted object-field and array-index access;
- finite arithmetic: add, subtract, multiply, divide with zero checks;
- length, min, max, and comparisons;
- boolean and/or/not.

Set hard limits: 64 static statements, nesting depth 4, loop collections of at most 16 elements, 500 evaluated expressions, and 100 primitive actions per invocation. Count expanded loop operations. Reject NaN, infinity, and oversized strings or arrays.

Example AST fragment:

~~~json
{
  "op": "call",
  "tool": "move_node",
  "args": {
    "node_id": {"ref": "locals.node"},
    "x": {"ref": "locals.cursor"},
    "y": {"ref": "inputs.top"}
  },
  "bind": "move_result"
}
~~~

Validate references statically where possible and at runtime otherwise. Never let attribute lookup reach language objects, prototypes, constructors, database clients, or filesystem handles.

### 7.3 Applicability versus lifecycle

Maintain separate fields:

- Lifecycle: candidate, active, superseded, retired.
- Validity for an observed context: unknown, provisionally_valid, suspect, quarantined.
- Utility evidence: helpful, harmful, tied, or inconclusive.

A skill may remain useful for an earlier context while being quarantined in a new one. Do not globally delete it after one failure.

New versions are immutable. Promotion updates an active-version pointer or a routing rule atomically. Keep previous versions and their evidence available.

### 7.4 Portable concept and native binding

Retain the section 7.1 skill package as the executable native procedure. Add a separate concept object; do not merely rename a cached program a concept.

~~~json
{
  "schema_version": 1,
  "concept_id": "generated-id",
  "version": 1,
  "summary": "Model-generated explanation of the inferred relationship",
  "input_schema_ref": "validated-schema-id",
  "rule_ast_ref": "immutable-pure-program-id",
  "preservation_constraints": ["preserve_unrelated_objects"],
  "demonstration_refs": ["example-id"],
  "clarification_refs": ["answered-query-id"],
  "intent_state": "resolved_within_candidate_set",
  "binding_refs": [
    {
      "backend": "konva",
      "skill_id": "generated-native-skill-id",
      "version": 1,
      "validation_report_ref": "report-id"
    }
  ]
}
~~~

The rule AST maps public geometry and parameters to desired geometry relationships/targets. It uses the same bounded expression/control grammar, but has no environment tools, filesystem, or network. Its only call-like operation is emit_target, a pure collector for a typed desired-object update. This does not mutate the scene.

Allowed emitted properties initially cover desired world position, dimensions, and badge relationship. Validate finite numbers, IDs, object counts, and supported properties. Native binding programs translate those targets into the actual backend's primitive operations.

Use a typed target union: move_existing, resize_existing, or clone_place. clone_place references an existing permitted prototype and assigns a run-local symbolic target ID. The native binding records the actual new object ID for that symbol; the verifier checks the actual created object. Symbols cannot reference filesystem paths, foreign sessions, or arbitrary constructors. Composition propagates the validated symbol map.

Nemotron proposes rule ASTs and native binding programs. The host supplies the language, primitive APIs, and validation, not a handwritten implementation of each benchmark rule. Handwritten reference rules belong only to the evaluator or explicitly labeled fixture baselines.

Keep distinct evidence for:

- intent fit to demonstrations and user answers;
- native execution correctness against proposed targets;
- correctness against independent held-out intended outcomes.

The model's inferred rule is never its own final correctness oracle. A binding that executes the wrong inferred rule perfectly is still a learning failure.

A tool repair creates a new binding version while retaining the concept version when intent is unchanged. A user correction changes the concept and invalidates/revalidates affected bindings explicitly.

### 7.5 Evidence-bearing rule package

Extend a concept package with domain_ref, evidence_ledger_ref, public_constraints_ref, binding_semantics_refs, and witness_refs. Each reference identifies an immutable, hashed artifact. Record compiler, interpreter, backend, and solver versions. Preserve unsupported fields as unsupported; do not silently coerce them into the symbolic subset.

The evidence ledger records each demonstration, question, answer, corrected example, and its provenance. Existing answers cannot be silently deleted to make a new candidate fit. If a user intentionally changes the rule, create a new concept version and explicitly mark which earlier preference is superseded. Ordinary native repair cannot supersede any teaching evidence.

Expose separate evidence dimensions:

| Dimension | Allowed states and meaning |
| --- | --- |
| Intent | unresolved; consistent_with_examples; resolved_within_candidate_set; user_corrected. None means universal knowledge of the user's wishes |
| Symbolic search | witness_found; no_witness_in_model; incomplete; timeout; unsupported. Include domain, formulas, and assumptions |
| Native execution | reproduced_mismatch; checked_on_listed_cases; untested; failed. Include actual scene hashes and traces |
| Held-out evaluation | hidden during execution; scored only after commitment by the independent evaluator |

Do not collapse these into a green confidence percentage. A report is evidence, not a general proof certificate. An UNSAT result refers only to the encoded property and domain; it does not certify the learned intent, native API, renderer, or unrelated future inputs.

Keep a sealed concept hash during binding repair. Promotion verifies that this hash, teaching ledger, domain, and public constraints remain unchanged. A repair cannot narrow the supported domain solely to hide a failing case. Domain restriction is a separate visible product decision and reduces measured coverage.

## 8. Skill acquisition and retrieval

### 8.1 Acquisition from agent experience

1. Run the fresh agent on a development task.
2. Check the result independently.
3. If successful, provide the trace, task variation schema, and supported primitive tools to the extractor.
4. Ask Nemotron for a parameterized skill package.
5. Reject fixed task IDs, copied answer coordinates where parameters should be used, illegal operations, and unverifiable assumptions.
6. Run at least three development variations, including changed sizes and nested objects where relevant.
7. Promote only if validation passes; record extraction and validation costs.

Successful extraction is not established by replaying the exact demonstration alone.

### 8.2 Acquisition from a user demonstration

Record actions through the same validated tool interface. In explicit-task mode, use the existing extractor/checks. In demonstration mode, use sections 8.6–8.8 to infer and disambiguate a concept before compiling a binding. UI dragging may generate many pointer events; collapse them into a deterministic final primitive action before recording.

Do not silently treat handcrafted example skills as learned. Fixture skills used for testing must have origin=fixture and must be excluded from learning claims.

### 8.3 Retrieval

Start with deterministic lexical retrieval over title, description, required tools, and declared task tags. Use the top three candidates at most.

Do not introduce an embedding model or vector database until retrieval failure is demonstrated on the development set. Keep retrieval identical across methods when comparing controller quality.

A family label may be used if it is genuinely present in the public task interface; do not pass evaluator-only categories to the agent. Record whichever public features retrieval uses.

### 8.4 Skill input binding

Use deterministic binding for explicit public task parameters. Use a validated model-generated binding only for free-form user requests, counting its cost.

Reject nonexistent node IDs and incompatible parameter types. Skills must not reach objects outside the current session.

### 8.5 Prompt assets

Store versioned prompts for fresh execution, extraction, diagnostic proposals, repair, and concise user explanations in prompts/.

Add v1.1 prompts for concept hypotheses, clarification input generation, native binding generation, and composition planning. Intent correction belongs to the teaching path with new user evidence, not the ordinary tool-repair prompt.

Each prompt must specify the exact output schema, permitted tools, resource limits, and observed evidence. The repair prompt must list forbidden changes, including verifier code, goal definitions, hidden manifests, and claimed test results.

Explanations should cite observed actions and checks. Do not display private model reasoning or imply a natural-language rationale is itself proof.

### 8.6 Hypotheses and intent clarification

Use one demonstration initially. Allow up to four model-generated candidate rule programs, all validated and replayed on the demonstration. Keep only candidates that fit it within the declared tolerance.

Avoid hardcoding the true candidate or its index. Known simple rules may exist in test fixtures, but the live learner must generate its own candidates.

If multiple candidates disagree on unseen inputs:

1. Propose up to eight valid small input scenes by varying widths, positions, nesting, or reference-object size.
2. Execute the candidate rule programs on each input without touching the user's scene.
3. Partition their predicted outputs using the frozen geometric-equivalence tolerance.
4. Select a scene with high disagreement and reasonable user effort.
5. Render neutral options A/B/etc. and a Neither / show another example option.
6. Ask the user which result expresses the intended rule.
7. Filter/refine candidates, retaining the question and answer as evidence.

Use a uniform candidate-weight disagreement heuristic initially:

~~~text
partition_weight = candidates_in_partition / total_candidates
disagreement = -sum(partition_weight * log2(partition_weight))
query_score = disagreement / max(1, estimated_query_cost_units)
~~~

This measures disagreement within a sampled hypothesis set. It does not establish that the true rule was considered or that the question is globally optimal.

Permit at most two user queries and two candidate-generation rounds for the initial teaching session. If all candidates fail or the user selects Neither, expand the set within budget or return unresolved. Do not force a preferred answer or quietly choose a rule.

Use a common query envelope for every method: query_id, input_scene_ref, up to four predicted_output_refs, and a Neither option. The teacher returns an accepted option ID or neither; it must not return the hidden rule, its formula, or a reference implementation. A requested extra demonstration counts as another teacher interaction. Bind each answer to the query's candidate-set hash.

One observed example can be genuinely insufficient. Asking a well-chosen question is a capability, not a failure to conceal.

### 8.7 Tool experiments and binding generation

Tool behavior and user intent are different unknowns:

- Ask a human/teacher about the intended result.
- Use isolated tool experiments to investigate observable API behavior.

A simulator cannot determine a user's unstated preference. A human should not need to answer questions whose answers are available from a safe tool probe.

Given a resolved/provisional concept and target backend:

1. Read the public tool schema/docs and current observations.
2. Generate up to three plausible native binding candidates.
3. Validate each restricted program.
4. Test candidates on isolated calibration scenes with declared target geometry.
5. When candidates make different predictions about a tool action, choose a bounded discriminating probe.
6. Execute through the real backend and compare actual observable geometry with predictions.
7. Retain a binding only after independent execution checks and replay.

For v1.2, a transfer or repair session permits at most 24 additional native primitive actions for experiments and witness reproduction, inside the episode's existing total action cap. This replaces v1.1's six-action probe default. Give comparison methods the same allowance and count all validation/replay work. Do not require probes when documentation already resolves the uncertainty.

A generated binding must handle unseen dimensions within its claimed scope. A backend adapter may expose native primitives but must not contain handwritten task-specific semantic translations that solve the transfer test for the learner.

### 8.8 Small, bounded skill composition

After learning spacing and badge-placement separately, accept a task that combines them on a held-out scene. No complete trace for that composition may be in the learning set.

Nemotron proposes a composition plan containing at most four nodes. Each node references an immutable concept/binding version, input bindings, and dependencies. Use a directed acyclic graph; reject cycles, recursion, unresolved references, and unbounded fan-out.

The host executes nodes in topological order through the existing restricted interpreter. Share one action/expression/token budget across the entire composition; child invocations must not reset it.

Check both each node's local result and the final task's independent global requirements. Correct parts can still interfere, for example if a later arrangement moves badges away from their intended cards.

Record expected and actual affected-object sets. If a node changes objects outside its declared scope, reject or quarantine that composition. Retain the component versions and the full lineage.

The initial goal is one novel two-concept combination, not arbitrary hierarchical planning.

### 8.9 Counterexample loop: implementation contract

Implement a pure witness-search service beside the interpreter. Nemotron proposes rules and revisions. The host compiles validated rules, searches for witnesses, executes checks, and records evidence. An extra LLM critic is not required.

**First symbolic subset.** Use Z3 through a locked z3-solver dependency [S19]. Support axis-aligned rectangle geometry, fixed explicit selection/order, rational constants, addition/subtraction, multiplication or division by constants, comparisons, bounded branches, and min/max. Unroll two to eight selected objects; run each object count as a separate bounded case. Reject variable-by-variable multiplication, variable division, arbitrary strings, sorting with symbolic order, rotation, and unsupported tool calls. Native scenes may still use nesting; only the normalized, public world-geometry input enters this first symbolic subset. This does not prove the native transform implementation.

The initial public domain uses positive card widths/heights between 24 and 512 pixels, canvas widths between 64 and 1600 pixels, canvas heights between 64 and 1200 pixels, and finite in-canvas input coordinates. Declare the exact supported object counts, selected roles, preservation requirements, and feasibility conditions in a versioned manifest. Additional constraints must describe the user task, not the hidden answer. Tune these ranges only on development/validation data, then freeze them. Requests outside them are unsupported for symbolic claims, even if concrete execution is possible.

Implement these interfaces as typed Python services, not raw model-supplied SMT text:

~~~text
find_disagreement(candidate_rules, public_domain, budget) -> WitnessSearchResult
find_public_constraint_violation(rule, public_constraints, public_domain, budget)
reproduce_native_witness(rule, binding, input_scene, public_context, budget)
~~~

For candidate pair P_i, P_j, search for a valid x where both are defined and their output targets differ by more than the frozen visible-difference threshold. Start with 1 pixel for question selection, separate from the final verifier tolerance. Partition all candidates' concrete predictions on each returned witness and use the section 8.6 disagreement/effort heuristic to choose the displayed question. This is not Socrates' full algorithm or an optimal query guarantee.

For constraint search, look for an x where a candidate violates an explicit public requirement, such as preserving unselected objects. The learner may not query the private final teacher rule through this service.

Use a trusted AST-to-Z3 compiler. Both compiler input and result have strict size limits. Start with at most 12 solver calls of 500 ms each per session and a six-second aggregate solver wall-time allowance. A timeout is unknown. Counts and time remain inside the overall run budget. Do not retry indefinitely with a more powerful solver.

Each solver query names one explicit shape/object-count case. A combined no_witness_in_model result requires conclusive UNSAT for every relevant pair and case in its stated search domain. If the budget allows only part of that set, return incomplete with the checked subset. Searching two-object scenes cannot establish agreement for eight-object scenes. Run solver work in a cancellable process with a memory ceiling; never block the application server's event loop.

Convert a SAT assignment to an ordinary scene, rerun every relevant candidate through the concrete pure interpreter, and verify the claimed difference. Rounding can erase a witness; reject or refine it rather than displaying an invalid question. Prefer readable integer or short-decimal dimensions when they retain the witness. A bounded shrink pass may simplify it, but call it a simple witness, not a globally minimal one.

Use the witness according to its type:

| Witness type | Source of truth | Allowed next step |
| --- | --- | --- |
| Candidate intent disagreement | User or benchmark teacher | Ask a neutral question; filter or regenerate with the answer |
| Violation of an explicit public constraint | Independent constraint implementation | Reject/revise the candidate; retain the violated constraint |
| Native output differs from inferred target | Actual tools plus independent observed geometry | Diagnose the binding or semantic assumptions; preserve concept and teaching ledger |
| Composition breaks an earlier relationship | Declared component contracts plus concrete replay | Change the allowed order/binding or report conflict; do not silently drop a component |

For native mismatches, concretely try valid witness scenes and boundary variations in isolated snapshots. Any symbolic tool model is a hypothesis. Do not invent a native failure because an abstract model predicts one. Only a reproduced mismatch can support a native repair claim. Record model-versus-runtime disagreements explicitly; this is the grounding issue highlighted by the new research.

When the target is absent from the candidate set, Neither does not reveal its formula. Accept a corrected output scene as the next counted teacher interaction, then ask Nemotron to generate a new rule consistent with the complete ledger. Permit the existing maximum two queries and two generation rounds per concept. If these are exhausted, abstain honestly. A rule change that fits only the new example fails promotion.

Fallback: if symbolic compilation is unsupported or the solver times out, use the existing concrete candidate-scene search and label its finite coverage. If every candidate agrees, say no disagreement was found; never say the intended rule has been proven. There is no inference of an unknown user's preferences from tool experiments alone.

## 9. Agent runner and controller

For v1.2, start with explicit applicability guards, reuse, failure-triggered diagnosis/repair, replay-gated promotion, and truthful stopping. Sections 9.4–9.6 retain the optional selective-audit design. Do not implement or evaluate its adaptive scheduling before the focused v1.2 gate, and do not claim a selective-auditing improvement from the main experiment.

### 9.1 Fresh agent contract

The fresh agent receives the public task, current observation, tool schemas, and its own within-task trace. It proposes a typed program or a short sequence of primitive operations. Execute, return visible observations and operational-check feedback, and permit bounded correction.

Default: at most three propose/execute cycles within the task envelope. This is a development default; tune once on development/validation data and then freeze it.

A fresh baseline must be capable of checking and correcting its work. Comparing against a deliberately weak one-shot prompt would undermine the experiment.

### 9.2 Controller action space

| Action | Meaning |
| --- | --- |
| REUSE | Execute a compatible validated skill |
| FRESH | Solve using the fresh agent without retrieved procedural memory |
| AUDIT | Run a matched diagnostic comparison from a snapshot |
| REPAIR | Propose and evaluate a bounded set of candidate changes |
| QUARANTINE | Disable the suspect version for this observed context |
| STOP | Return a truthful terminal state when no valid action fits the remaining budget |

The controller is ordinary application code initially. Nemotron handles procedure creation, execution planning, and repair proposals. Do not use an LLM to fabricate confidence values or decide whether its own patch passed.

### 9.3 Observable context

Construct a context key from public backend identity, tool schema signatures, task features actually exposed to the agent, and observed probe results.

Do not include private drift IDs, change-point times, evaluator seeds, hidden canonical state, or future task frequencies.

When a probe exposes a semantic distinction, record the observation and an evidence ID. A routing predicate may depend on that measured distinction. It must not depend on the benchmark label.

### 9.4 Evidence score: implementable initial heuristic

Maintain the last 20 complete paired observations per skill version and observable context. For pair i:

- s_with and s_without are operational-check pass indicators.
- c_with and c_without are the actual resource costs of the two arms.
- w_i = 0.9 raised to the number of later observations for that skill/context.
- d_i = (s_with - s_without) - 0.05 * (c_with - c_without) / C_ref.
- G = sum(w_i * d_i) / (1 + sum(w_i)).
- n_eff = sum(w_i).
- U = 1 / sqrt(1 + n_eff).

Use one declared cost unit for this score, initially consumed model tokens plus a development-calibrated equivalent for primitive actions. Freeze the conversion and C_ref before final evaluation. Report raw tokens, calls, actions, time, and dollars separately so the conclusion does not depend on a hidden weighting.

For the first implementation, set the action equivalent to 10 token-units per primitive action and C_ref to the episode token cap divided by the number of scheduled tasks, initially 8,000. These are arbitrary declared starting coefficients, not measured hardware costs. Inspect sensitivity on validation data before freezing them.

G is a heuristic utility score; U is an evidence-scarcity score. Neither is a calibrated uncertainty interval or causal-effect estimator.

Correctness dominates this ranking: a known current-context correctness failure cannot be offset by token savings. Keep the explicit guard below even if G remains positive from older evidence.

Track recent independently checked supporting executions separately from paired observations. Acquisition validation may establish initial execution support, but must not be counted as WITH/WITHOUT evidence. With no complete pairs, G starts at zero and U at one.

### 9.5 Initial decision rules

Evaluate in this order:

1. If the overall budget or deadline is exhausted, STOP.
2. If there is no relevant active-lifecycle skill, FRESH. Keep suspect/quarantined versions available for diagnosis and repair selection, while excluding them from REUSE.
3. If a required tool is absent or an observable precondition demonstrably fails, QUARANTINE for that context and then FRESH if budget remains.
4. If a complete pair shows correctness harm plus a reproducible observable skill failure, or the two most recent complete pairs show correctness harm, select REPAIR if its reserved envelope fits and no repair search has already run for this skill/context/task. Otherwise FRESH; do not continue REUSE.
5. If the last invocation produces an unresolved observable contradiction, mark it suspect. Prefer AUDIT if a complete pair and useful continuation fit and this task has not already been audited; otherwise FRESH.
6. Otherwise, compute audit priority from recent demand, evidence scarcity, and anomaly evidence.
7. AUDIT when priority crosses the frozen threshold, audit budget remains, and this skill/context/task has not already been audited.
8. REUSE when the skill has at least three recent independently checked supporting executions under its observable routing context, G is nonnegative, and no current contradiction is unresolved.
9. Otherwise FRESH.

An initial audit-priority heuristic:

~~~text
demand = number of times this skill was a candidate in the last 10 tasks / 10
anomaly = 1 if there is an unresolved observable contradiction, else 0
staleness = min(tasks_since_last_complete_pair / 5, 1)
priority = demand * U + anomaly + 0.5 * staleness
audit if priority >= 0.7 and the complete action fits its envelope
~~~

These constants are engineering starting points. Record them in configuration, tune only on development/validation data, and state honestly that this is a heuristic controller.

Clear an anomaly only through an explicit evidence-backed transition, such as a passing validated repair or a diagnosis that establishes the original failure was infrastructure-related. A failed repair must not create a retry loop. If FRESH is selected again after its task attempt allowance is exhausted, STOP with the corresponding truthful terminal state.

If the main effect comes from the repair loop rather than selective auditing, report that finding and narrow the claim.

### 9.6 Repair trigger and budget allocation

Permit at most one repair search per skill/context per task and three candidates per search. Reserve a continuation budget before diagnosis or repair begins.

Suggested initial envelope allocation: at most 20% of episode tokens for paired auditing and 30% for repair/proposal/replay. These are ceilings, not mandatory spending targets. Ordinary execution can use the unused remainder.

Acquisition has its own recorded cost and is included in total system comparisons.

Anomaly-triggered auditing may use remaining repair allocation only if that policy is specified in the frozen configuration. Do not quietly change allocation rules after seeing final results.

### 9.7 Event-driven state machine

~~~text
QUEUED -> RUNNING
RUNNING -> EXECUTING | DIAGNOSING | REPAIRING | CHECKING
DIAGNOSING -> EXECUTING | REPAIRING | FAILED | BUDGET_EXHAUSTED
REPAIRING -> CHECKING
CHECKING -> EXECUTING | SUCCEEDED | FAILED | BUDGET_EXHAUSTED
Any nonterminal state -> CANCELLED | INFRA_ERROR
~~~

Skill quarantine is a skill/context event, not automatically a run failure. A run can still succeed through a fresh solution.

Persist decisions before launching expensive work. Emit reason codes such as insufficient_evidence, observed_precondition_failure, recent_correctness_harm, or audit_budget_unavailable.

### 9.8 v1.1 orchestration above the execution controller

The section 9 controller manages execution utility and repair. Add a small outer state machine:

~~~text
TEACHING -> HYPOTHESES_READY
HYPOTHESES_READY -> AWAITING_USER | INTENT_READY | UNRESOLVED
AWAITING_USER -> HYPOTHESES_READY | CANCELLED
INTENT_READY -> BINDING | READY_TO_REUSE
BINDING -> PROBING | VALIDATING | UNSUPPORTED
VALIDATING -> READY_TO_REUSE | BINDING | FAILED
READY_TO_REUSE -> EXECUTING | COMPOSING
~~~

Before ordinary execution: resolve required intent, locate a compatible validated binding, and synthesize one if needed and budgeted. Then hand control to the existing REUSE/FRESH/AUDIT/REPAIR policy.

User-wait time is measured separately from machine latency. Release browser contexts and worker leases while a teaching session awaits an answer, then resume from the stored snapshot. Expire abandoned sessions without silently consuming further credits.

Native supporting executions do not establish certainty about user intent. Keep those confidence/evidence domains separate.

## 10. Matched diagnostics

### 10.1 What a pair means

Create two isolated executions from the same scene snapshot, task, public documentation, tool semantics, model configuration, and attempt limits:

- WITH: make the selected skill available and invoke it through the normal reuse path, followed by the same bounded correction allowance.
- WITHOUT: omit that skill and run the normal fresh path with the same correction allowance.

The skill's saved procedure can avoid a model call. That is part of the treatment being evaluated. This is an implementation-inspired diagnostic, not an exact reproduction of SkillApt.

Record whether the skill was actually invoked. If the WITH path never uses it, label the pair noncompliant/inconclusive rather than attributing a difference to skill execution.

Both arms count toward the parent budget, including a discarded arm. Run them sequentially initially; randomize their order in experiments. Freeze all adaptive state until both finish.

### 10.2 Model randomness

Fix model and decoding settings. If the endpoint supports a seed, record it; do not assume that temperature zero or a seed guarantees deterministic inference.

For important comparisons, use repeated trials. Store environment seeds separately from any supported model seed.

### 10.3 Feedback and final evaluation separation

Use two checking layers:

1. **Operational checker:** validates the public task requirements and returns a coarse, consistent feedback schema. Every baseline may use it under the same attempt/budget rules.
2. **Final verifier:** independently computes the reported outcome and hidden evaluation variants. Its scores and implementation details are unavailable for online candidate selection.

Use operational-check outcomes for online evidence and repair selection. Seal the committed task output before obtaining its final score. Do not feed that final score back into the running episode.

The final verifier must not introduce undisclosed goals; hidden tests exercise the published requirements on unseen cases.

For demonstration-only teaching, the task is to infer the teacher's latent rule from provided examples and allowed answers. Operational checks can verify fit to known examples and execution of a proposed target; they cannot certify the inferred rule on unanswered cases. Final held-out scoring uses the teacher's independent rule, and the same example/query budget applies to every method.

### 10.4 Classification

| WITH | WITHOUT | Evidence |
| --- | --- | --- |
| Pass | Fail | Skill helpful on this observation |
| Fail | Pass | Skill harmful on this observation |
| Pass | Pass | Compare actual costs; retain correctness tie |
| Fail | Fail | Base limitation, shared tool issue, or unresolved failure; no proof that the skill caused it |
| Infra failure in either arm | Any | Incomplete pair; no usefulness update |

Budget exhaustion is a real outcome for the resource-bounded policy. Report it explicitly and do not discard it as infrastructure failure.

### 10.5 Committing an output

After an audit, select the passing arm with lower measured cost if both pass, or the only passing arm. If neither passes, proceed only if a repair/fresh continuation fits the remaining task envelope.

One task receives one final outcome. The two diagnostic arms are internal attempts, not two benchmark successes.

Keep artifact references for both arms and identify which output was committed.

## 11. Repair search and promotion

### 11.1 Candidate generation

For v1.1, first classify the proposed change as a native binding repair, an intent correction supported by new user evidence, or a composition-order/scope correction. A tool failure alone does not authorize rewriting the user's intended rule.

Provide Nemotron with:

- the immutable current skill and declared assumptions;
- task requirements and actual visible traces;
- operational-check feedback;
- the paired diagnostic summary when available;
- permitted primitive tools and the exact skill schema;
- examples of earlier behavior that must be retained;
- the candidate and cost limits.

Request:

- a concise diagnosis tied to evidence IDs;
- a candidate program or a narrower applicability predicate;
- the expected observable change;
- which existing behaviors might regress.

The diagnosis is a hypothesis. Only execution determines candidate acceptance.

### 11.2 Search method

Start with a bounded reflective search:

1. Generate up to three candidates, sequentially if feedback is useful.
2. Validate structure and capabilities.
3. Run the triggering task and a small development variation set.
4. Replay affected previously successful cases.
5. Reject any candidate that violates required behavior or exceeds the allowed resource envelope.
6. Among surviving candidates, prefer greater verified coverage; break ties by lower measured cost and then smaller patch size.

This is GEPA-inspired, not GEPA itself. If using the actual GEPA package later, implement its evaluator adapter, pin the package version, preserve lineage, and measure its overhead. Do not call undocumented APIs guessed from the paper.

### 11.3 Regression set selection

Choose a deterministic bounded set:

- the original demonstration;
- at least two distinct earlier successful parameter variations;
- one nested/grouped variation if the skill claims that capability;
- one unrelated procedure as a system-level guard where shared behavior could be affected.

Replay earlier cases under their stored original environment configuration. Test new-context cases under the current configuration. A tool change that invalidates the old environment must not make the historical test impossible by construction.

These replay cases come from accessible historical/development evidence, never the locked final test set.

### 11.4 Conditional versions

A repair may be correct in the new context and incorrect in the old one. In that case:

- keep both immutable versions;
- add an observable routing condition backed by a probe or public capability;
- count the routing probe's runtime cost;
- abstain when the condition is ambiguous.

Do not route using a private version label supplied by the benchmark.

### 11.5 Promotion transaction

Require a recorded validation report containing candidate hash, parent version, verifier/checker versions, case outcomes, costs, and supported context.

In one database transaction:

1. Confirm the parent/active routing state has not changed since search began.
2. Insert the immutable accepted version.
3. Store its validation report and evidence references.
4. Update the active version/routing pointer.
5. Emit a promotion event.

If another update wins the race, retain this candidate as unpromoted. Revalidate against the new parent before promotion.

Rollback changes a pointer and records why. Never erase the failed update or overwrite history.

### 11.6 Repair failure

If no candidate passes, keep the affected version quarantined for the observed context. Continue with a fresh attempt if possible. Report the failed repair honestly.

Do not relax verification tolerances, remove constraints, or label a candidate successful merely to complete the demo.

## 12. Independent checking and geometry

### 12.1 Implementation independence

The final verifier must not call the agent-facing measure_node implementation. A bug in that tool should not make the same wrong coordinates appear correct to the evaluator.

Use private native scene inspection and independently implemented world-coordinate calculations. Read actual object transforms and geometry, compose matrices in the verifier, and compare world-space results with task requirements.

Keep this code outside the agent's tool surface and writable outputs. Separate service credentials or process boundaries should prevent the worker from reading private final manifests during evaluation.

A shared schema for scene types is acceptable; shared semantic conversion code between a deliberately perturbed tool and the verifier is not.

### 12.2 Checks by task family

**gap_row**

- Required objects still exist exactly once.
- World-space order is correct.
- Adjacent edge gaps match the requested gap.
- Alignment matches the specified edge or center.
- Sizes and styles remain unchanged where required.
- No unauthorized object was moved.
- Objects remain within declared canvas bounds.

**fit_group**

- Group fits the target frame.
- Aspect ratio is preserved within tolerance.
- Relative child positions and ordering remain consistent.
- No child disappears, duplicates, or changes style unexpectedly.

**badge_attach**

- Exactly one required badge exists.
- Its designated corner relationship and margin are correct.
- The source object and unrelated objects remain unchanged.

Use world-space polygon corners for rotated objects if rotation is supported. Otherwise reject rotation in the task schema and state the limitation.

### 12.3 Tolerances

Start with a 0.5 px absolute geometric tolerance and a small relative tolerance for dimensions. Treat these as declared development defaults; verify they are appropriate for both engines and freeze them before final evaluation.

Do not optimize the tolerances after seeing failures. Use the same requirements for every baseline.

Rendering differences should not determine geometric success. Save screenshots for human inspection; add visual checks only for explicitly supported appearance requirements.

### 12.4 Verifier validation

Seed meaningful faults:

- move the wrong object;
- shift every object by a constant offset;
- preserve centers but change widths;
- duplicate or delete a required object;
- change parent transforms while preserving misleading local coordinates;
- return a success message without mutating the scene.

The verifier must reject these examples. Keep independently constructed golden scenes for each task family. Include tests that prove changing an agent-facing measurement tool cannot change final truth.

### 12.5 Symbolic checks and concrete grounding

The pure symbolic compiler and concrete interpreter need agreement tests over the supported grammar. For generated valid ASTs and concrete inputs, substitute the same input into the symbolic translation and compare its targets with concrete interpretation. Include min/max boundaries, branches, negative intermediate values, preservation of unrelated fields, and rejected unsupported operators.

Use exact rationals in symbolic expressions. The native engines use floating-point arithmetic; the final geometry verifier retains its independently frozen tolerance. Display both semantics in exported evidence. A rational arithmetic result is not a proof about all floating-point executions.

Add an explicit abstraction-gap case: the rule and an outdated abstract action model agree, while the actual engine operation yields different geometry. The system must preserve this counterexample, mark the semantic model untrusted in that observed context, and decline to report verified native execution. A passing abstract check must never override observed failure.

Validate public operational properties and private final intent independently. Runtime witness search gets only the former. After output commitment, the private evaluator checks the intended rule on the held-out input, even if the learner's own targets and implementation agree perfectly.

For every no_witness_in_model result, export the SMT-LIB query, solver/version, domain hash, candidate hashes, encoded property, status, and elapsed time. This is a reproducible solver result under stated assumptions, not an independently proof-checked certificate. Never report timeout or unsupported as passed.

## 13. Skill export and reuse

Export a ZIP package or a JSON package plus human-readable explanation containing:

- schema version, skill ID, version, content hash;
- program and input schema;
- required tools and capabilities;
- applicability assumptions and how they were checked;
- source/validation evidence summaries;
- supported context and known limitations;
- license/attribution information.

Strip credentials, internal hostnames, private task manifests, and user-specific data. Imported skills always enter candidate state and require local validation; a claimed success count in imported metadata must not establish trust.

Support JSON import first. If ZIP import is added, reject path traversal, symlinks, nested archives, duplicate filenames, excessive expanded size, and unexpected file types before extraction.

A skill generated for one backend is not automatically portable. Portability claims require the transfer experiment.

In v1.1 exports, include the concept, its hypothesis/clarification history, each validated backend binding, and any composition graph. Label the exact evidence supporting each layer.

For v1.2 add the evidence ledger, witnessed disagreements/mismatches, scope manifest, solver queries/results, native replay traces, and a one-command offline replay entry point. A replay verifies saved artifacts/actions; it does not rerun model learning. Keep the two reproduction modes distinct.

Also export a genuinely editable SVG of the current supported scene and an SVG batch with a manifest. Do not provide only a screenshot. Preserve supported IDs, hierarchy, and editable geometric objects; include enough metadata to associate output objects with the recorded rule application. Re-import an exported example in an independent vector editor during product validation and document any fidelity limitations.

Start with scene JSON import and editable SVG export. An SVG importer is optional until the core research gate passes. If added, declare a whitelist of supported elements/transforms, disable scripts/external references, and report unsupported content before processing. Never claim arbitrary design-file compatibility or a Figma integration merely because an SVG can be opened there.

## 14. Nebius Token Factory integration

### 14.1 Verified platform facts and uncertainties

The checked official quickstart uses:

~~~text
https://api.tokenfactory.nebius.com/v1/
~~~

The official Nemotron Super cookbook shows this model identifier:

~~~text
nvidia/nemotron-3-super-120b-a12b
~~~

Its example uses a regional base URL. Account/model availability and routing must be verified on the implementation device; do not silently mix endpoints or assume every account has access [S05, S06].

Use Nemotron Super as the first candidate if available. Prefer one fixed model for every role in the principal experiment. A smaller model can be explored separately after the main comparison is established.

The structured-output guide documents json_schema, while the checked chat-completion reference describes a narrower response_format surface. Treat this discrepancy as a reason to probe the actual endpoint and model [S07, S08].

Do not assume vision input, tool calling, schema-constrained generation, reasoning controls, seed support, or usage subfields from the family name alone.

### 14.2 Environment variables

Create .env.example with placeholders only:

~~~dotenv
APP_ENV=development
APP_BASE_URL=http://localhost:8080
DATABASE_URL=postgresql+psycopg://apprentice:change_me@db:5432/apprentice
POSTGRES_USER=apprentice
POSTGRES_PASSWORD=change_me
POSTGRES_DB=apprentice
ARTIFACT_ROOT=/data/artifacts
ENGINE_URL=http://engine:8090
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
NEBIUS_API_KEY=
NEBIUS_MODEL=nvidia/nemotron-3-super-120b-a12b
PROVIDER_MODE=mock
LIVE_RUN_MAX_USD=
INPUT_USD_PER_MILLION=
OUTPUT_USD_PER_MILLION=
MAX_PROVIDER_CONCURRENCY=2
SESSION_SECRET=replace_with_a_generated_secret
~~~

The database password example is local-only and must be replaced before deployment. Generate SESSION_SECRET before authenticated use and create the owner through the interactive admin command. Production startup must reject placeholder secrets. Do not expose PostgreSQL or the engine service to the public Internet.

### 14.3 Capability probe

Implement oa doctor and oa provider probe:

1. Verify required configuration without printing secret values.
2. Check configured base URL and TLS.
3. List available models through the documented /models endpoint if accessible [S09].
4. Send one minimal completion to the chosen model.
5. Test JSON-object output and local schema validation.
6. Optionally probe schema-constrained output and native tool calls independently.
7. Check the supported completion limit field and response usage fields.
8. Record accepted options, returned model identity, request ID, timestamp, and latency.

Save the report in docs/capabilities.json without credentials. Failed capability probes must not be interpreted as model reasoning failures.

Live probes require an explicitly configured spending ceiling. The default doctor command is offline and must not consume credits.

### 14.4 Thin provider adapter

Use HTTPX or a compatible SDK behind a Provider interface. Application code must not depend directly on raw response dictionaries.

~~~python
class Provider:
    async def complete_json(
        self,
        *,
        messages,
        output_schema,
        call_context,
        budget_reservation,
    ) -> "ValidatedCompletion":
        ...
~~~

Return parsed content, model/request IDs, finish reason, token usage, latency, retry metadata, and raw-response hash. Persist redacted raw responses only where needed for debugging.

Use server-side credentials only. Never put the API key into a VITE-prefixed variable, client bundle, browser request, exported trace, or public repository.

### 14.5 Structured output behavior

Baseline compatibility path:

- request JSON-object output if the probe confirms it;
- include our schema in the prompt;
- parse the complete response;
- validate with Pydantic using extra fields forbidden;
- permit one charged schema-correction call;
- reject remaining invalid responses as model-format failures.

Use schema-constrained output only after a successful probe. If plain text is the only workable mode, accept only a clearly delimited complete JSON payload, validate it, and label that capability in the report.

Do not silently repair a program by inventing omitted actions. Do not execute partially parsed output.

Avoid native tool calling in the first implementation; a typed JSON action/program envelope reduces provider-specific protocol work.

### 14.6 Limits and failures

- Use connect and read timeouts.
- Retry bounded transient failures with exponential backoff and jitter.
- Honor Retry-After where available.
- Fail authentication/configuration errors without repeated retries.
- Count retries and schema-correction calls.
- A timed-out request may still have been processed: mark its cost unknown/reserved until reconciled.
- Stop instead of silently switching provider or model during an experiment.
- Treat truncation, refusal, malformed JSON, tool failure, budget exhaustion, and infrastructure failure as distinct outcomes.
- If reasoning consumes the output budget, adjust documented supported settings on development runs and record the change; do not scrape hidden reasoning as the answer.

### 14.7 Usage accounting

Record prompt and completion tokens from the provider response. If additional reasoning or cached-token fields are present, record them without double counting.

Price calculations require a dated rate configuration from the account/model catalog. If rates or usage are unavailable, display unknown or an explicitly labeled estimate; never display zero as a substitute.

Reserve a conservative cost before every call, then reconcile. The reservation is an application safeguard, not a guarantee about external billing.

## 15. Persistence and job execution

### 15.1 Minimum relational model

| Table | Essential fields |
| --- | --- |
| users/sessions | id, role, credential hash/session expiry |
| workspaces | id, owner_id, mode |
| runs | id, workspace_id, status, policy_id, task_ref, parent_run_id, config_hash, model_id, started_at, ended_at |
| jobs | id, run_id, status, lease_owner, lease_expires_at, attempt, payload, available_at |
| events | run_id, sequence, type, timestamp, public_payload, private_payload_ref |
| scene_snapshots | id, owner/run, backend, public_state_ref, private_state_ref, hash |
| skills | id, workspace_id, title, active_routing_revision |
| skill_versions | skill_id, version, parent_version, program_hash, package, lifecycle |
| evidence | id, skill_version, observable_context, pair_id, outcome, cost, origin |
| diagnostic_pairs | id, snapshot_id, with_run_id, without_run_id, completeness |
| promotions | id, parent, candidate, validation_ref, decision, reason |
| provider_calls | id, run_id, role, model, request_id, usage, cost_state, latency, response_hash |
| budget_ledger | owner/run/episode, reservation_id, reserved, consumed, released, category |
| artifacts | id, owner/run, relative_storage_key, MIME, bytes, sha256, visibility |
| experiments | id, manifest_hash, config_hash, git_commit, status, report_ref |

Add v1.1 tables:

| Table | Essential fields |
| --- | --- |
| concepts | id, version, input_schema, pure_rule_ast, summary, intent_state, evidence_refs |
| hypotheses | teaching_session_id, candidate_hash, concept_payload, example_fit, status |
| clarification_queries | id, session_id, candidate_set_hash, input_scene_ref, option_refs, answer, answer_source, status |
| native_bindings | concept/version, backend, skill/version, observed_context, validation_ref |
| compositions | id, version, bounded_DAG, component_versions, scope_claims, validation_ref |

Add domain_manifests, teaching_evidence, witness_searches, witnesses, and semantic_models for v1.2. Store immutable content hashes, provenance, parent run/session, search status, encoded-property reference, abstract/concrete result references, and resource counters. The table names are engineering defaults; shared artifact tables are acceptable if they preserve the same relationships and access boundaries.

Store human answers with their provenance. A deterministic benchmark teacher uses answer_source=benchmark_teacher, and must not be presented as a real user study.

Use UUIDs, UTC timestamps, foreign keys, uniqueness constraints, and indexes for ownership/run lookups.

Private evaluator data must not appear in general API serialization. Public_payload must be created from an explicit allowlist.

### 15.2 Worker leases

Claim jobs in a short transaction using row locking and SKIP LOCKED. Set a lease, commit, then execute. Do not hold database locks during inference.

Heartbeat leases. Stop committing mutations if the lease is lost. Recovered jobs resume from durable step checkpoints.

Use a unique logical action key for each external/tool action. Exactly-once external inference is not guaranteed; record uncertain attempts rather than claiming they never occurred.

### 15.3 Cancellation

Cancellation sets a durable flag checked before each model call and primitive action. Abort local waits and close engine sessions. Do not promote a candidate after cancellation.

Release unused reservations, but retain unresolved external-call reservations until reconciliation. A browser tab closing is not a cancellation request.

### 15.4 Artifact storage

Use content hashes and server-generated relative keys. Resolve paths beneath ARTIFACT_ROOT and reject traversal. Write to a temporary path and rename atomically.

Keep database metadata and binary artifacts consistent. A failed artifact write must not leave a success event pointing to a missing file.

Backup both the database and artifact volume. The initial implementation does not require Redis, a separate vector store, or an event bus.

## 16. HTTP API and event contracts

### 16.1 Public application routes

| Method and route | Purpose |
| --- | --- |
| GET /health/live | Process liveness; no secrets or paid inference |
| GET /health/ready | Database, storage, and engine readiness |
| POST /api/auth/login | Establish a secure session |
| POST /api/auth/logout | Invalidate session |
| GET /api/templates | Supported sample tasks and capabilities |
| POST /api/workspaces | Create an isolated workspace |
| POST /api/tasks | Validate a user task and initial scene |
| POST /api/runs | Queue a run; return 202 and run_id |
| GET /api/runs/{id} | Current state, counters, and result references |
| GET /api/runs/{id}/events | Server-sent event stream |
| POST /api/runs/{id}/cancel | Durable cancellation request |
| POST /api/teaching-sessions | Start a demonstration recorder |
| POST /api/teaching-sessions/{id}/actions | Record validated primitive actions |
| POST /api/teaching-sessions/{id}/finish | Queue extraction and validation |
| GET /api/teaching-sessions/{id}/question | Fetch the current discriminating question |
| POST /api/teaching-sessions/{id}/answers | Submit an answer tied to the current query/version |
| GET /api/concepts/{id} | Inspect the inferred rule and its evidence |
| POST /api/concepts/{id}/transfer | Queue a binding for the selected supported backend |
| POST /api/compositions | Validate and queue a bounded composition request |
| GET /api/skills | List versions and supported contexts |
| GET /api/skills/{id}/versions/{version} | Inspect an immutable package |
| POST /api/skills/{id}/validate | Queue validation under an allowed context |
| POST /api/skills/{id}/export | Create a sanitized portable package |
| GET /api/artifacts/{id} | Authorized artifact retrieval |
| GET /api/experiments/{id}/report | Completed report, with visibility checks |

For v1.2 add POST /api/concepts/{id}/challenge, GET /api/witnesses/{id}, and POST /api/workspaces/{id}/export-svg. Challenge accepts supported public input variations or queues bounded witness search. It cannot choose a hidden teacher rule, read final labels, or mutate a concept without a recorded teaching event. Reuse the existing run/job/event infrastructure for these routes.

Require workspace ownership on every object lookup. Guessing a UUID must not grant access.

An idempotency key on run creation must return the same run for the same request body and reject reuse with different content.

### 16.2 Private evaluator routes

Expose drift scheduling, final-manifest loading, and experiment administration only to the evaluator/admin role, preferably on an internal interface.

The evaluator UI may show the human what changed. Those controls and payloads must not enter the agent context, task input, or ordinary event stream until the applicable evaluation is sealed.

### 16.3 Event shape

~~~json
{
  "schema_version": 1,
  "run_id": "uuid",
  "sequence": 42,
  "timestamp": "2026-10-08T08:00:00Z",
  "type": "skill.validation_completed",
  "payload": {
    "skill_id": "gap_row",
    "candidate_version": 2,
    "passed": false,
    "report_artifact_id": "uuid"
  }
}
~~~

Use durable increasing sequence numbers. Support Last-Event-ID reconnects and deduplicate client events. Send heartbeat comments so a quiet stream does not look disconnected.

SSE uses the authenticated same-origin session. Do not put API keys or reusable access tokens in query strings.

Emit events for decisions, provider calls, tool actions, snapshots, pair completion, candidate creation, validation, promotion, quarantine, budget updates, cancellation, and terminal states.

Add hypothesis-set, clarification-requested/answered, intent-state, binding-created/validated, and composition-node events. Version answers so a stale browser cannot answer a superseded question.

### 16.4 Error shape

Return a stable error code, safe message, retryability, and correlation ID. Examples: INVALID_PROGRAM, UNSUPPORTED_CAPABILITY, SCENE_REVISION_CONFLICT, PROVIDER_AUTH_ERROR, PROVIDER_RATE_LIMIT, MODEL_FORMAT_ERROR, BUDGET_EXHAUSTED, and INFRA_TIMEOUT.

Redact provider bodies that may contain credentials or internal configuration. Preserve diagnostic details in authorized server logs.

## 17. Frontend product specification

### 17.1 Main workspace

At desktop width, use:

- a narrow task panel with the request, supported inputs, and Run/Teach controls;
- a large central canvas showing the committed artifact;
- a compact activity panel showing decisions and evidence.

The main canvas must dominate the interface. Use a restrained palette, clear typography, and smooth transitions tied to actual execution events.

Provide Learn, Reuse, Transfer, Challenge, and Compare modes. Composition is a supported task in Reuse. Their functions must share the same backend paths used in evaluation.

### 17.2 Required interaction details

- Start with a runnable sample and a short explanation.
- Distinguish queued, running, checking, repairing, and finished states.
- Keep Cancel visible during long work.
- Show an actual elapsed timer, budget remaining, and observed provider usage.
- Never animate fabricated progress percentages.
- Let users inspect the old/new procedure diff and the exact checks that accepted or rejected it.
- Make a failed repair understandable and recoverable.
- Offer a fresh-agent fallback when a skill is quarantined.
- Show artifacts from both comparison arms and identify the committed result.
- Provide keyboard-accessible controls and a textual equivalent of canvas results.
- Use labels as well as colors for pass, fail, unknown, and replay.
- Respect reduced-motion settings.

For v1.1, show the competing rendered interpretations when asking a question, retain a Neither option, and distinguish the learned rule from its Konva/Fabric implementations. The transfer view should show which rule stayed unchanged and what native procedure changed.

### 17.3 Evidence view

Display:

- provider and returned model identity;
- skill version and program hash;
- primitive actions and scene snapshots;
- operational-check outcomes;
- diagnosis pair outcomes and costs;
- candidate validation and retained-case results;
- known limitations and uncertainty;
- final evaluation results only after sealing.

Do not expose raw private reasoning. Provide concise, evidence-linked action summaries.

### 17.4 Comparison mode

Show the same initial scene and task on both sides. Label policies clearly. Keep their resource limits visible.

If one run uses recorded evidence, label it Recorded run with timestamp/configuration. Live means a new execution using the actual provider. Mock means deterministic simulated provider behavior.

Do not compare a freshly executed candidate to an unlabeled selected historical failure.

### 17.5 Skill inspector

Show title, purpose, parameters, required tools, observable assumptions, lifecycle, supported contexts, evidence counts, last validation, and version history.

Avoid presenting an evidence count or heuristic score as a reliability percentage.

### 17.6 Browser rendering

The human preview can render scene snapshots locally, but the authoritative artifact is the engine-produced state/image. After each committed revision, synchronize to that artifact.

Do not let a frontend animation hide a mismatch between the displayed state and the actual evaluated state.

### 17.7 Teaching and challenge experience

Use the canvas as the main explanation. Show the demonstration, two to four predicted outcomes for one informative input, and a plainly labeled Neither / correct this example action. Explain the difference in one short sentence backed by the candidate outputs. Avoid exposing SMT syntax or long agent traces in this flow.

Challenge mode lets the user vary supported card dimensions/counts or load a supported scene, then execute the frozen rule. It can also request a bounded automatic search. Show the actual result and whether the evidence concerns intent ambiguity, public constraints, or native execution. A single green Verified label is prohibited because these are different claims.

When a repair occurs, show what stayed fixed and what changed: for example, the margin rule and its examples remain; the native coordinate calculation changes. Offer the actual before/after witness and retained-case results in the evidence drawer. Keep natural-language explanations concise and grounded in stored facts.

The primary completion action is exporting the editable layout or batch. The evidence/skill package is a second action for developers and judges. Include an immediately usable sample but do not require users to understand the research vocabulary before trying it.

## 18. Isolation and security requirements

These protections address concrete risks of generated procedures, public demos, and paid API access.

### 18.1 Generated procedures

- Accept only the restricted AST and allowlisted primitive tools.
- Validate package size and depth before parsing/execution.
- Bound expression count, loops, tool calls, object count, and render dimensions.
- Reject unknown properties and prototype-related keys.
- Never pass model text to a shell, Python eval, JavaScript eval, a template engine with execution capabilities, or SQL concatenation.
- Treat imported skill descriptions and tool outputs as untrusted data, not privileged instructions.

### 18.2 Browser runtime

- Block external page navigation and network requests.
- Use locally bundled fonts and assets.
- Exclude arbitrary HTML, SVG uploads with scripts, and remote asset URLs from the first release.
- Do not mount the Docker socket.
- Run containers as non-root with restricted filesystem access.
- Use per-session isolation and resource limits.
- Keep browser and Playwright versions compatible.

### 18.3 Public application

- Use HTTPS in deployment and secure HttpOnly session cookies.
- Use CSRF protection for authenticated mutations and a narrow CORS policy.
- Store password hashes, not plaintext passwords.
- Keep public preview/read-only mode separate from authenticated execution.
- Apply request-size, session, concurrency, and spending limits.
- Authorize artifact downloads by ownership/visibility.
- Do not expose private experiment labels or unpublished final results through list endpoints.

### 18.4 Secrets and exported data

Store secrets in deployment configuration. Add .env, tokens, private evaluation credentials, and local raw logs to .gitignore.

Use synthetic task data for the public demo. No corporate files or credentials are required for this project.

Before publishing, scan tracked files and rendered frontend assets for secrets. Export sanitized evidence with stable hashes so results remain inspectable.

## 19. Resource budgets and performance

### 19.1 Budget dimensions

Track all of:

- prompt/completion tokens;
- provider requests, including retries and formatting repairs;
- primitive tool actions and operational-check calls;
- browser/runtime seconds;
- wall-clock time;
- estimated or confirmed inference cost;
- artifact/storage volume.

Also count provided demonstrations, user clarification turns, probe actions, hypothesis-generation calls, binding-compilation calls, and composition overhead. Report human wait time separately from machine time.

Do not collapse all measures into one number in the report. The controller may use a declared weighted score internally.

### 19.2 Initial development defaults

These are starting limits, not measured requirements:

| Scope | Initial limit |
| --- | --- |
| One fresh task attempt | 3 propose/execute cycles |
| One program invocation | 100 primitive actions |
| One repair search | 3 candidates |
| One live interactive task | 180 seconds; separate smaller demo profile after measurement |
| One experimental episode | 8 scored tasks for v1.2; 10 only for the optional original repair study |
| Episode total tokens | 80,000 |
| Episode provider calls | 64 |
| Episode primitive actions | 800 |
| Episode wall-clock | 900 seconds |
| Parallel provider requests | 2 |
| Parallel browser contexts | 4 |
| Rendered canvas dimensions | At most 1600 by 1200 |
| Scene object count | At most 100 |
| Initial concept candidates | At most 4 |
| Candidate clarification scenes | At most 8 |
| User questions per taught concept | At most 2 |
| Candidate generation rounds per concept | At most 2 |
| Native candidates per transfer search | At most 3 |
| Transfer/repair experiment actions | At most 24 additional native primitive actions per session, inside the 800-action total |
| Solver calls per session | At most 12, each at most 500 ms |
| Aggregate solver wall time per session | At most 6 seconds, inside the run deadline |
| Composition nodes | 2 for the shipped workflow; interpreter maximum 4, no recursion |

Every activity consumes the shared episode budget. A three-candidate repair that does not fit must stop early and report that fact.

The per-task and episode deadlines operate together; the earlier limit wins.

Use the pilot to determine whether these envelopes permit meaningful recovery. Freeze final limits before final evaluation.

### 19.3 Dollar ceiling

Default to mock/offline mode. Live commands require a configured maximum dollar amount and dated rates, or a clearly documented conservative reservation strategy when exact rates cannot be obtained.

Maintain a global run/experiment ceiling in addition to per-call reservations. Stop launching new requests when the remaining allocation is insufficient.

No monetary estimate in this document is a quoted Nebius price. Read the account's current model rates.

### 19.4 Caching

Allow deterministic caching of immutable artifacts, parsed schemas, and replay fixtures.

Do not cache model answers across compared policies in a way that gives one policy free inference. If inference caching is studied, declare it as a separate experimental condition and account for cache population.

All branches of an audit, failed repairs, and historical replay are charged to the method that requests them.

### 19.5 Performance goals

Measure time to first visible event, time to first artifact, complete task latency, recovery latency, and browser-context cleanup.

Set UX targets after the live provider probe. Do not promise sub-second reasoning or a full adaptation loop under three minutes before measuring it.

Record solver time, witness construction/rounding checks, native replay, rejected proposals, and teacher interaction time separately. They are part of the cost of learning. A solved SMT query is not free merely because it consumes no model tokens. Apply the same CPU/wall-time and native-action ceilings to comparison methods.

## 20. Logging, observability, and reproducibility

Every run must record:

- Git commit and dirty-tree status;
- dependency lockfile hashes;
- environment and adapter versions;
- public tool schema hash and private environment hash in separate visibility domains;
- requested/returned model identifiers and supported decoding settings;
- prompt and skill hashes;
- initial snapshot hash;
- random seeds and their roles;
- event sequence and parent/child attempt relationships;
- budgets, reservations, actual usage, and unknown costs;
- check/verifier versions and terminal outcome.

Logs must distinguish task failure from system failure. Include request/run correlation IDs.

An evidence export contains configuration, sanitized events, skill packages, snapshot/artifact hashes, per-task rows, and a report-generation command.

The main report must be generated from stored raw results. Never type headline performance numbers into the UI or README manually.

Offer two reproducibility levels:

1. Replay saved actions and artifacts without paid inference.
2. Re-run the model-driven experiment, with clear acknowledgment that hosted inference may vary.

## 21. Experimental protocol

Sections 21.1–21.9 describe the original repair study and reusable experimental principles. Section 21.10 defines the compact episode structure. Section 21.11 overrides its primary comparison and adds the selected v1.2 tests. The full six-policy, three-family repair matrix is optional expansion, not an additional minimum workload.

### 21.1 Development, validation, and final separation

Create distinct manifests:

- Development: approximately 20 tasks used for implementation and prompt/controller debugging.
- Validation: separate templates/parameter combinations used to choose constants and budgets.
- Final: locked episodes with unseen combinations, nesting, and drift schedules.

Split by generating templates and semantic variations, not merely by random IDs. Exact snapshots must not appear across splits.

Final data may be released with the repository after evaluation. During the actual final run, the agent runtime must not have filesystem, API, or prompt access to its private manifest.

Record manifest hashes and a freeze commit before running final evaluation. If a substantive bug invalidates the protocol, describe the correction, freeze a new version, and rerun affected comparisons. Do not selectively replace unfavorable runs.

### 21.2 Baselines for the original repair study

| ID | Policy | Purpose |
| --- | --- | --- |
| B0 | Fresh agent with bounded checking/correction; no persistent procedural skills | Is reuse/adaptation useful at all? |
| B1 | Always use the highest-ranked compatible skill; ordinary bounded fallback | Does unconditional memory cause failures or overhead? |
| B2 | Static evidence-based activation; no online repair | Is activation alone enough? |
| B3 | Periodic audit and the same repair machinery every K skill opportunities | Does selective auditing improve allocation? |
| B4 | Repair on observable failure using the same repair machinery | Does proactive auditing add value beyond reactive repair? |
| FULL | Selective online audit, applicability, repair, and replay gates | Proposed system |

B2 is SkillApt-inspired. Label it as such unless implementing and matching the exact published method.

Tune K and other baseline parameters on validation data with the same tuning allowance as FULL. Report the selected values.

For a separate repair pilot, compare B0, B1, B3, and FULL. Add B2/B4 before making a strong claim about selective repair. The v1.1 primary baselines are specified in 21.10.

### 21.3 Equal starting conditions

Use a common initial learned skill library produced by an identical warm-up procedure for methods that use skills. Record and include warm-up cost in total-cost comparisons.

Fresh-only B0 has no skill-learning cost. Report both total cost including acquisition and adaptation-only cost after the shared warm-up; do not present only the more favorable view.

After initialization, each method evolves independently. No policy may use a skill, diagnosis, or discovered change from another policy's run.

All methods receive the same public task instructions, tool documentation, accessible observations, and operational feedback.

### 21.4 Episode design

Start with 10-task episodes, changes only at task boundaries:

- some episodes have no change;
- some have one change;
- some have a later reversal or second change;
- some contain irrelevant tool changes.

Generate task sequences and change schedules before policies run. Keep them identical across policies and repetitions.

Do not always change tools at the same task index. Include held-out change combinations and parameter ranges within the supported domain.

Commit and score each task outcome once. Internal diagnostic trials do not advance the external task sequence.

### 21.5 Suggested evaluation scale

Begin with a small pilot. If compute permits, freeze 12 final episodes of 10 tasks, spanning the three task families and no-change controls, and repeat each policy three times.

This is a suggested design, not a guarantee of statistical power. It creates 120 task opportunities per repetition and 360 per policy. Budget the full matrix before executing it.

If the cost is too high, reduce scope consistently across policies and report the limitation. Prefer fewer well-controlled conditions over many incomplete comparisons.

### 21.6 Metrics

Primary:

- fraction of committed tasks passing the independent final verifier under the declared resource limits;
- paired FULL minus B3 success difference, with uncertainty.

Secondary:

- post-change success by task distance from the change;
- tasks and cost until recovery;
- harmful skill reuse frequency;
- acquisition, diagnosis, repair, and ordinary-execution cost breakdown;
- retained historical task success;
- unnecessary audits/repairs on no-change episodes;
- cross-tool transfer success on the declared common subset;
- model-format, tool, budget, and infrastructure failure rates.

Define recovery before evaluation, for example two consecutive correct committed tasks in the affected family. Episodes that never recover are censored at the episode end and counted explicitly. Do not average only recovered cases.

### 21.7 Statistical reporting

Preserve pairing by episode, task schedule, and repetition. Use bootstrap resampling at the episode level, retaining within-episode task dependence; do not treat every action or task as an independent sample.

Report the actual sample size, confidence intervals, denominators, failures, and per-condition outcomes. With few independent episodes, describe uncertainty as substantial.

Predefine infrastructure-rerun policy. Retain interrupted attempts and their costs; rerun an affected paired comparison block consistently rather than only its losing method. Publish both scheduled-run completion and task-success denominators.

Use a two-stage resampling scheme only if justified and implemented correctly. A simple transparent episode-level analysis is sufficient for the first submission.

Do not interpret failure to find a difference as proof of equivalence.

### 21.8 Ablations

At minimum:

- FULL without paired audits;
- FULL without replay-gated promotion;
- FULL with periodic rather than selective audit timing.

Hold the remaining components and budgets fixed. Run unsafe promotion ablations only in isolated benchmark scenes.

If removing a supposedly central component changes nothing, reflect that in the write-up.

### 21.9 Early continuation gate

After the first roughly 72 hours of implementation, inspect:

- Can the fresh Nemotron agent solve enough baseline tasks to make comparisons meaningful?
- Does an extracted procedure transfer beyond its source example?
- Can a controlled semantic change produce a reproducible failure?
- Can a model-proposed repair fix new-context tasks while retaining old-context behavior?
- Does selective diagnosis plausibly save enough work to justify its overhead?

If the base agent fails nearly everything, simplify the task or improve the base prompt before evaluating memory.

If skills add no benefit, do not manufacture difficult conditions solely to force a win. Investigate whether the task family or contribution should be narrowed.

If selective auditing fails to beat periodic/reactive repair, ship the useful adaptation capability with an honest narrower claim.

### 21.10 Focused v1.1 experiment

**Question:** Does an explicit learned rule plus active disambiguation and checked native bindings improve transfer/composition over competent use of the same model and evidence?

Run four main methods:

| Method | Accessible memory and behavior |
| --- | --- |
| Fresh full-context agent | Same demonstrations, current tool docs, query opportunity, operational feedback, and compute envelope; no persistent compiled library |
| Flat procedure plus repair | The original v1.0 procedure memory and repair loop, with the same evidence and clarification access |
| Text-memory agent | Learned subtask summaries and the same evidence; regenerate execution for each tool/task |
| v1.1 FULL | Candidate rules, selected clarification, explicit concept/native bindings, bounded composition, and checked repair |

Give all methods the same maximum teacher-query allowance and prompt them competently to use it. Do not withhold tool docs or observation tools from baselines. Shared initial evidence is the same; later query answers may differ because question selection is part of the tested method.

Use a deterministic benchmark teacher that owns the latent rule and answers only submitted queries. Never let it write a solution for the learner. Human usability tests are separate.

Start with four pilot episodes. A suggested locked final design is 12 episodes, repeated three times per method, with two concepts in each episode. Each episode:

1. Teaches the two component rules separately, with one initial example each and at most two clarifications per concept.
2. Tests two new same-backend layouts.
3. Transfers to the other backend and tests two fresh layouts.
4. Tests two unseen compositions of the learned rules.
5. Applies one allowed semantic tool change and tests two recovery layouts.

This yields eight scored outputs per episode, 96 per repetition, and 288 per method across three repetitions. Clarifications, probes, and learning runs are additional charged work, not additional scored successes. Reverse the backend direction across episodes.

Primary metric: correct held-out transfer and composition outputs under the fixed total machine and teacher-query budgets. Prespecify the FULL versus text-memory comparison and report the other baselines. Also report same-backend learning, recovery, abstentions, failures, retention, and every cost component.

Use the independent teacher rule for final intent correctness. Executing the learner's own target correctly is insufficient. Do not give final scores back during the episode.

Add one focused ablation comparing selected clarification/probe inputs with valid randomly selected inputs at the same maximum query/probe counts. A second useful ablation collapses intent and binding back into one procedure.

Where a small enumerative symbolic learner can solve the restricted hypothesis space, include it as a reference on that subset. The usefulness of an LLM prior should not be presumed.

Validate simple spacing/padding ambiguity without hardcoding the true hypothesis in the learner. Hold out object-size ranges, nesting combinations, composition layouts, and tool-change placements within the declared supported domain. Successful transfer between two libraries does not establish arbitrary-app generalization.

All budgets in section 19 remain total ceilings. Expand them only during development if the larger episode requires it, publish the change, and freeze the same limits for all methods. Do not add free teaching/probe work on top of the original cap. Derive C_ref from the configured episode length: with eight scored tasks and an 80,000-token cap it is 10,000 token-units, rather than the original ten-task default of 8,000.

### 21.11 Selected v1.2 experiment and continuation gate

Use the eight-output episode design from 21.10. The current FULL policy is named full_v1_2 in manifests to distinguish it from the older selective-audit study. Use failure-triggered checked repair in the main comparison; proactive audits and audit-scheduling claims are deferred.

**Four main methods:** competent fresh full-context, text memory, structured procedure with checked local repair, and full_v1_2. Replace the weaker flat-procedure baseline with the structured variant: explicit preconditions, steps, public postconditions, fault localization, and replay-gated repair, inspired by ContractSkill but not called its reproduction. It retains a native procedure rather than a separately persistent portable concept plus bindings.

All methods may generate temporary candidate rules, ask questions, use public witness/checking services, inspect native geometry, and correct outputs. Their available information, tool interfaces, teaching allowances, overall budgets, and tuning effort are identical. Persistent representation and use of evidence differ. Do not secretly reserve the useful checker or a corrected example for FULL.

Primary endpoint: final intent-correct transfer/composition outputs under total resource caps. Prespecify FULL versus the structured-procedure method as the main comparison; report fresh and text-memory results alongside it. For the exceptional-result gate, compare against the strongest main baseline in the final results and acknowledge the additional comparison; do not switch the registered primary hypothesis after seeing scores.

Secondary endpoints: teacher interactions and human time, success on new same-engine inputs, native mismatch detection/repair, retention, abstention/coverage, latency, solver overhead, and total inference/action cost. Count unsupported/abstained outputs as failures in overall task completion, while also reporting conditional correctness. Record false success: a committed output reported as successful that the private evaluator rejects.

**Task content.** Keep two small concepts, but hold out compositions of allowed primitives and branch-boundary cases, not just random dimensions of two canned formulas. For example, constant, proportional, and clamped margins may coincide on a demonstration yet disagree elsewhere. Use the same declared grammar for all methods. A target program must be representable; its exact formula, constants, and template identifier stay private. Some episodes must remain unchanged at the nominal recovery stage, so a scheduled repair is not automatically rewarded. Allocate four of the twelve episodes to no-change controls and eight to the one supported drift family; balance backend direction within those counts.

Keep the suggested 12 episodes × 8 outputs × 3 repetitions: 288 outputs per method, including 144 transfer/composition outputs. There are only 12 independently constructed episodes; repetitions do not turn this into 288 independent samples. Preserve episode clusters when estimating uncertainty. Freeze manifests, prompts, budgets, and the primary metric before final runs.

**Target-omission stress test.** Add a small separate battery where a supplied, explicitly labeled fixture candidate set omits the true rule. The evaluator controls that artificial intervention. Compare recovery with the same teacher budget across methods; the only extra evidence is a counted corrected output example. This demonstrates the Neither path, not the rate of missing hypotheses in natural model generation. In ordinary runs separately report naturally occurring Neither responses, unresolved teaching, and candidate-generation failures.

**Grounding ablation.** On the controlled abstraction-gap subset, compare FULL with the native witness confirmation requirement removed, while preserving the final independent evaluator and all budgets. This ablation runs only in disposable benchmark scenes. It tests whether concrete checks help when the symbolic tool assumptions are wrong. It must not be represented as deployment behavior. If the ablation changes nothing, do not credit grounding with a measured benefit.

**Query ablation.** After the main pilot works, compare symbolic/disagreement-selected questions against valid sampled questions under the same machine and interaction ceilings. Charge solver CPU/wall time and all concrete checks. This is a secondary experiment, not another full mandatory policy matrix.

**Non-LLM reference.** Build a bounded enumerative learner for the declared small pure-rule subset, using the same examples, questions, constants policy, and checks. Publish its grammar, search limit, CPU time, and coverage. A smaller grammar must be labeled a subset reference. Do not make the model look necessary by supplying it a correct hypothesis that the symbolic baseline is forbidden to express. If the symbolic approach is sufficient, report that and reconsider whether the NVIDIA model contributes enough beyond natural-language interaction.

**First 72-hour decision.** Run four development episodes before polishing the full interface. Continue the 9.5-target design only if the live Nemotron path can generate useful candidates, some revealed disagreement improves held-out behavior, and at least one observed native mismatch is repaired without altering the learned rule. Also inspect the structured/text/symbolic references. No separation is itself useful information; improve the product or narrow the research claim instead of adding more agent roles.

Targets in section 27.5 are prospective quality goals, not forecast results. Do not invent easy test cases after a failed evaluation to meet them. If cost forces a smaller study, reduce all compared methods consistently, preserve the predeclared comparison, and report the resulting uncertainty.

### 21.12 External SVG trial and evidence of learning on real assets

Keep two evaluation lanes separate.

**External editing lane.** Freeze a commit of Vector-Bench's evaluator and independently verify the provenance of selected assets [S22, S23]. Start with eight tasks selected before running model outputs, using explicit licensing and supported-operation criteria. Record every inclusion/exclusion and coverage against the full corpus. If fewer qualify, report that instead of quietly simplifying tasks. Choose development and final assets separately; never tune against final scores. A small subset is a pilot, not a leaderboard result.

The author-issued notice excludes twenty scenic illustrations from the blanket code license because their provenance is unresolved [S23]. Do not bundle those illustrations or their derivatives in our public repository/demo. Use independently verified content or our own replacement assets. Replacements create an adapted study and must not be called an original benchmark score.

During scored runs give the solver only the released public input. Keep target_svg, expected_diff, and should_preserve in an evaluator-only process. No final-score feedback, target-derived hints, or retrieval from published solution traces. Raw SVG contains public IDs; that does not authorize exposing the private list of required edits.

Run the same available Nemotron model through Nebius for all local comparison methods. Compare: (A) competent fresh agent with patch tools and checking; (B) text-memory agent with the same tools; (C) Open Apprentice. The structured-procedure baseline from 21.11 should also run if claiming a representation advantage. Match tokens, calls, elapsed time, observations, and correction opportunities. Provide valid compiled public patches rather than forcing a baseline to regenerate a long file. Report complete task success, requested-edit completion, preservation, validity, coverage, and costs separately. The decomposition is also consistent with the evaluation concern raised by VeriEdit-Bench [S26], but is not a reproduction of that image-editing study.

Vector-Bench's published endpoint study used one scored response per task [S22]. Do not compare our multi-call agent directly with its headline rate and claim model superiority. Public-data contamination and a small task count also limit conclusions. Use the rerun matched baselines for the main local comparison.

**Learning lane.** External instruction editing alone does not establish learning from examples. Construct a separate, clearly labeled study on supported real assets: teach one recurring rule on one asset, allow the existing bounded clarification, freeze its concept, then apply it to assets from held-out structural families. Keep all methods' demonstrations and teacher budgets equivalent. Include one condition where the rule is irrelevant, so indiscriminate reuse can fail. Count teaching cost and any user-selected scope. Do not grant our method an extra hint unavailable to baselines.

Hold out meaningful structures such as nesting/layout organization and combinations of rule operators, not merely object names or colors. The PBE literature motivates this distinction [S25]; performance of its older evaluated models does not predict current Nemotron performance. Measure final correctness, unintended changes, teacher effort, and amortized cost across the batch. If reuse yields no advantage over a competent patch editor or text memory, narrow the claim accordingly.

Use VectorGym's human-authored edit examples as an optional source of task-design inspiration [S24]. Inspect its actual split, task schema, asset licenses, and supported primitives before adopting data. Do not assume its four-task benchmark matches our restricted SVG lane or introduce VLM fine-tuning merely because that paper studies it.

**Decision after the spike:** continue only if the SVG lane preserves useful artifacts and the pilot suggests a measurable benefit worth testing. Move one real-file teach–apply–export sequence into the video. Retain the controlled benchmark for mechanism analysis. Keep the 9.5 ambition conditional on both lanes and the formative user evidence; no public benchmark percentage alone earns that score.

## 22. Verification strategy

Write tests for the concrete correctness, isolation, and experimental risks. Avoid spending time on exhaustive snapshots of cosmetic UI details.

### 22.1 Unit checks

- AST validation and bounded execution.
- Illegal references, loops, divide-by-zero, non-finite values, unknown tools.
- Controller transitions from observed evidence.
- Correctness-harm override of cost utility.
- Evidence decay and context separation.
- Budget reservation/reconciliation and unknown-cost states.
- Skill-version immutability and routing.
- Geometric verifier golden/fault cases.

### 22.2 Integration checks

- Run a real Konva scene from snapshot through tool operations and final checking.
- Restore the same snapshot into two contexts and obtain equivalent starting state.
- Inject a tool semantic change without altering verifier truth.
- Persist a run, restart the worker, and resume without duplicating an action.
- Cancel during inference and prevent late promotion.
- Fail one paired arm and prevent incomplete evidence updates.
- Reject a candidate that fixes the new scene but breaks an old supported context.
- Import an untrusted package and keep it in candidate state.
- Enforce workspace ownership on runs, skills, and artifacts.

### 22.3 Provider checks

Use a fake HTTP server for malformed JSON, 429, timeout, missing usage, truncation, refusal, wrong model identity, and unsupported parameters.

Add one opt-in live smoke test against the configured Nemotron endpoint. A mocked pass is not evidence that the real API integration works.

### 22.4 E2E checks

Use Playwright to:

1. Open the starter task.
2. Start a run and observe actual events.
3. Inspect the committed artifact.
4. View a learned skill.
5. Trigger an authorized challenge.
6. Observe repair success or an honest failure state.
7. Export a report.
8. Reconnect the event stream and avoid duplicate actions.

Test the main flow at a normal desktop viewport and a narrow layout. Check that controls remain usable without relying on color alone.

### 22.5 Research-integrity checks

- Private drift IDs never appear in the model request payload.
- Final test fixtures are unavailable to the agent process.
- All policies receive equivalent visible information.
- Discarded audit arms and failed repairs remain charged.
- Shared warm-up cost is included in total comparisons.
- No cross-policy evidence reuse.
- Final score is obtained only after output commitment.
- Missing data is not silently dropped from denominators.
- A no-change episode does not trigger automatic staged repair by task index.

### 22.6 v1.1 capability checks

- An ambiguous equal-width demonstration retains distinct matching rule candidates.
- The selected unequal-width question separates those predictions when the candidate set permits it.
- Neither produces refinement or unresolved status, not a forced choice.
- The learner never receives a private rule label through example metadata.
- A correct native execution of an incorrect inferred rule fails final intent evaluation.
- A concept can have distinct validated Konva and Fabric bindings.
- Tool repair changes the binding while leaving unchanged intent/version intact.
- A user correction creates a new concept version and revalidates affected bindings.
- A held-out composition executes learned components without a stored complete demonstration.
- Composition cannot reset budgets, introduce cycles, or mutate out-of-scope objects.
- Teacher query counts and probe costs are charged consistently to every method.
- A stale or duplicated user answer cannot resume the wrong hypothesis set.
- Pausing for an answer releases the worker lease/context and resumes from durable state.

### 22.7 v1.2 checks that address concrete failure risks

- Symbolic translation agrees with concrete rule execution throughout a generated set of supported AST/input pairs.
- Unsupported nonlinear expressions and unknown solver outcomes never produce a success badge.
- A displayed question is backed by concretely different outputs after rounding and rendering.
- All proposed answers may be wrong; Neither does not fabricate a hidden correct option.
- A new candidate must satisfy the entire active teaching ledger, not just the latest correction.
- Native repair cannot edit concept/domain/teacher-evidence hashes or weaken the independent checker.
- The abstraction-gap fixture passes its abstract check, fails real execution, and is reported as a mismatch.
- Stale backend or semantic-model evidence is not silently inherited after a version change.
- Edited outputs and imported/exported supported scenes preserve object identity and unrelated content.
- Judge-entered dimensions drive actual execution, and invalid/out-of-scope inputs receive truthful status.
- Both solver and native witness/replay work appear in the total cost record.
- Offline evidence replay works on another checkout without a model API key.

## 23. Milestones and acceptance gates

Use gates rather than treating generated code volume as progress. Build a thin interface early, then expand it after the core effect is demonstrated.

| Milestone | Deliverable | Gate |
| --- | --- | --- |
| M0 | Repository, dependency locks, schemas, offline provider, configuration | Clean setup and offline tests work on a second checkout |
| M1 | Konva runtime, first family, independent verifier, fresh agent, minimal UI | One real model-driven task produces a checked artifact |
| M2 | Concept hypotheses, bounded witness search, clarification, native procedure | Live candidates yield a valid question and improve fresh-input behavior; Neither is honest |
| M3 | Second-backend binding, concrete mismatch, one drift and repair | Intent stays fixed during binding repair; abstract/concrete disagreement is visible |
| M4 | Fixed two-concept composition, strong baselines, omission/grounding pilot | The core research comparison works before product expansion |
| M5 | Teaching/challenge UI, editable SVG export, evidence replay, formative trials | People can complete the supported workflow; output survives an independent editor |
| M6 | Locked main study and grounding ablation; optional query ablation | Results and uncertainty are computed from immutable evidence |
| M7 | Deployment, final reports, video, README, submission materials | Another person can follow setup and reproduce the main demonstration |

Suggested calendar if implementation starts on 8 October 2026:

- 8–10 October: M0–M2 thin slice and four-episode continuation check. Timebox the first symbolic compiler spike to one day; use labeled sampled search if it is not sound/usable.
- 11–14 October: M3–M4, actual transfer and mismatch repair, baseline pilot, one fixed composition.
- 15–18 October: M5, owner-arranged formative trials, export/replay, product corrections. Freeze the final protocol after this development work.
- 19–23 October: M6, paired final runs and analysis within explicit credit limits.
- 24–27 October: deployment, reproducibility, measured demo, documentation. No optional model additions.
- 28–30 October: fix release blockers, record the short video, submit, and retain a deadline buffer.

If implementation begins later, preserve the research and usability gates and cut optional breadth. Do not compress a failed proof/compiler spike into an unverified success claim. Solver-backed questioning is useful only if it improves the actual workflow; adding Z3 to the stack does not itself raise the score.

Keep at least the final day as a submission buffer. Target a complete upload before 30 October evening SGT.

At each gate, update docs/status.md with completed work, actual commands/results, limitations, and the next concrete task. Never describe a blocked live check as passed.

## 24. Commands and another-device setup

The following commands are the interface the implementation must provide. They do not exist merely because this document lists them.

### 24.1 Prerequisites

Recommended simplest route: Docker Desktop/Engine with Compose. On Windows, prefer a WSL2 Linux checkout for the documented shell workflow. On macOS, use the same containers. No local NVIDIA GPU is required when inference runs through Token Factory.

If running services natively, install the chosen Python/uv and Node versions and the browser dependencies required by the locked Playwright version.

Never copy credentials from a corporate account or another unrelated project.

### 24.2 Local offline path

After the implementation exists:

~~~bash
cp .env.example .env
docker compose build
docker compose run --rm --no-deps -v "$PWD:/bootstrap" api oa config init --env-file /bootstrap/.env
docker compose up -d
docker compose exec api oa db upgrade
docker compose exec api oa admin create --username owner
docker compose exec api oa doctor
docker compose exec worker oa demo seed
docker compose exec worker oa run --task dev-gap-row-0001 --policy fresh --mode mock
~~~

The compose setup must expose the UI at http://localhost:8080 and provide clear logs/readiness checks. The application must visibly show MOCK until the real provider is configured.

The admin command prompts for a password without echoing or logging it. The offline config-init command generates the local session secret and development-only database credentials, replacing known placeholders while preserving user-supplied values. Keep POSTGRES_PASSWORD and DATABASE_URL consistent, write atomically, and do not print secrets. This bootstrap command must run without a database or valid application secrets. The temporary /bootstrap mount is only for initialization and must not appear on the running agent/engine services. Never use a published default admin password.

If the command names change, update this document's implementation companion README and CLI help together.

### 24.3 Live provider setup

Edit the local .env privately:

- configure the Nebius API key;
- confirm the model ID and account-compatible base URL;
- enter current pricing or the declared conservative cost policy;
- set PROVIDER_MODE=nebius;
- set a small explicit LIVE_RUN_MAX_USD.

Recreate affected services so configuration changes apply. Then:

~~~bash
docker compose exec worker oa provider probe --live --max-usd 1
docker compose exec worker oa run --task dev-gap-row-0001 --policy fresh --live --max-usd 1
~~~

The dollar values above are example spending ceilings, not expected costs. The CLI must refuse to exceed the configured global ceiling or bypass missing budget configuration.

Do not print API keys in terminal diagnostics or instruct the user to paste secrets into chat.

### 24.4 Learning and comparison commands

~~~bash
docker compose exec worker oa learn --task dev-gap-row-0001 --live --max-usd 2
docker compose exec worker oa compare --manifest benchmarks/development/pilot.json --config configs/pilot.yaml --live --max-usd 5
docker compose exec worker oa report --experiment latest --output /data/reports/pilot
~~~

Resolve latest to an explicit experiment ID and print it before generating output. Scripts used in published results should use explicit IDs.

### 24.5 Required CLI surface

Implement help and machine-readable exit states for:

~~~text
oa doctor
oa config init
oa admin create
oa db upgrade
oa provider probe
oa demo seed
oa run
oa learn
oa teach
oa transfer
oa compose
oa compare
oa benchmark freeze
oa benchmark run
oa report
oa replay
oa export-skill
oa challenge
oa export-svg
oa replay-evidence
~~~

Each expensive command accepts dry-run/offline inspection, a configuration path, and an explicit budget ceiling. A dry run must report the matrix size and planned maximum request envelope without spending credits.

The new teach command creates a durable teaching session and returns its UI URL; the user answers in the browser. transfer accepts a concept/version and supported backend. compose accepts a validated bounded-plan/task request. Implement the same backend services for CLI and UI, including query budgets.

Use configs/counterexample.yaml for the selected v1.2 protocol in sections 21.10–21.11. Reserve configs/portable.yaml for a separately labeled v1.1 comparison. Every pilot/final configuration must declare its protocol, primary comparison, model, budgets, and supported domain so studies cannot be silently mixed. challenge uses the current concept/version and public inputs; replay-evidence is offline and must not silently spend inference credits.

### 24.6 Reproduction commands

The README must provide exact locked commands to:

- install or build;
- run offline tests;
- run the live smoke test;
- generate development tasks;
- acquire the initial library;
- freeze an evaluation manifest;
- run the selected comparison;
- regenerate reports from saved results;
- replay the showcased run.

Capture a clean-checkout reproduction before calling the project complete.

## 25. Deployment and operating the judging demo

### 25.1 Deployment shape

Keep inference on Token Factory. Host the web/API/worker/graphics runtime/database on one Linux machine initially. A CPU machine is sufficient for this design because model inference is remote.

A starting sizing estimate is 4 vCPU and 8 GB RAM for light use, subject to measurement with the chosen number of browser contexts. This is our planning estimate, not a Nebius service requirement or price quote.

Use a Nebius AI Cloud host if practical and available in the owner's account. Avoid adding GPU rental, Kubernetes, or serverless integration solely for branding.

Token Factory runtime inference supplies the central Nebius/NVIDIA integration. Describe where each component actually runs.

### 25.2 Containers

Provide:

- web: built frontend plus a reverse proxy;
- api: HTTP API and migrations;
- worker: durable orchestration and provider access;
- engine: Node plus the locked Playwright browser runtime;
- db: PostgreSQL with a persistent volume.

A separate evaluator process/profile is appropriate for final experiments. Production public-demo containers must not mount final private manifests.

Only the web entry point should have public ports. Proxy API and event streams to the internal API. Disable buffering on the SSE route and test reconnects through the real proxy.

Use health checks, restart policies, fixed dependency/image versions, and explicit memory/process limits. Keep artifact and database volumes persistent across deployments.

### 25.3 Deployment steps

1. Build and test release images locally or in CI.
2. Pin the release Git commit and create a release manifest.
3. Configure the host, DNS, and HTTPS using existing authorized account access.
4. Install deployment secrets through a protected configuration mechanism.
5. Start the database and create a backup.
6. Run migrations once.
7. Start API, engine, worker, and web.
8. Check readiness and run one bounded live smoke task.
9. Verify the UI reports the actual provider/model.
10. Verify authentication, cancellation, artifact access, and SSE through the public URL.
11. Save the deployment/runbook details without secrets.

Prepare deployment scripts and configuration before any action that needs fresh account access or spending authorization. Follow the implementation environment's permissions. Do not create paid resources or publish under an account merely because this document includes deployment instructions.

### 25.4 Persistence and rollback

Back up the database and artifacts before migrations and releases. Test restoring into a temporary instance.

Deploy a new application release only after checking migration compatibility. Roll back the application image when possible; do not assume a destructive database migration can be safely reversed.

Retain the final submission release separately from ongoing development. Preserve original final experiment artifacts.

### 25.5 Demo access during judging

The checked rules place judging through 15 December 2026, 12:00 Pacific time, equivalent to 16 December 2026, 04:00 SGT. Keep the submitted project working through that period and recheck official updates [S10b].

Provide the judges with a working access path and any required test credentials through the submission instructions. Public visitor quotas must not block the judges' required evaluation access. Reserve enough provider credit and monitor availability.

Maintain a clearly labeled recorded-run viewer as a fallback aid. It does not replace the required functioning project.

### 25.6 Practical runbook

Document how to:

- rotate the inference key;
- update an expired model identifier after a deliberate compatibility check;
- restart a failed engine;
- find a run by correlation ID;
- cancel stuck jobs;
- reconcile unknown usage;
- restore a backup;
- inspect available credits without exposing account data;
- return to the submitted release.

Do not silently change the evaluated model after submission. If availability forces a change, preserve earlier results and clearly identify the live deployment's new configuration.

## 26. Hackathon submission and demonstration

### 26.1 Submission requirements to satisfy

The checked event requires an NVIDIA open model used through Nebius Token Factory or Nebius AI Cloud, a fitting track, a working demo for this software project, public source with an open-source license, setup guidance, a project description, feedback on the tools used, and a public YouTube demonstration of at most three minutes [S10a].

Choose a root MIT license for our original code unless a dependency decision requires another compatible choice. Preserve third-party notices.

Use the current official rules as authoritative. The final README should identify the exact NVIDIA model and actual runtime integration.

### 26.2 Three-minute story

Plan a video around measured runtime. Suggested allocation:

| Time | Content |
| --- | --- |
| 0:00–0:20 | Show a user's custom visual rule and two plausible interpretations of one demonstration |
| 0:20–0:50 | Generate a revealing case; let the user confirm or correct it |
| 0:50–1:15 | Execute fresh supported dimensions, then transfer the learned rule to the other engine |
| 1:15–1:55 | Show an abstract check disagreeing with actual native behavior in the labeled controlled challenge; repair the binding while retaining intent |
| 1:55–2:20 | Apply the fixed two-rule workflow to a fresh batch and export editable SVG |
| 2:20–2:55 | Show measured baselines, actual Nemotron/Nebius usage, scope limitations, and evidence replay |

Aim below three minutes to leave a margin. If a run is sped up or edited, label the timing honestly. Show actual execution, not a frontend that displays prewritten success messages.

### 26.3 Repository README contents

- Who the tool serves and what it does.
- One clear animation or screenshot of the core capability.
- Architecture and trust boundaries.
- Exact model/provider and where they are used.
- Setup via Compose, offline mode, and live mode.
- Required credentials and how to configure them privately.
- Supported tasks/tools and explicit limitations.
- Research lineage and the precise proposed contribution.
- Experiment commands and actual results with denominators/uncertainty.
- Costs, failures, and known deployment limits.
- License and third-party attribution.
- Link to the hosted app and video.

### 26.4 Tool feedback

Maintain docs/provider_feedback.md during development. Record concrete examples: documentation mismatches, structured-output behavior, rate-limit handling, observed latency, error ergonomics, and model capability limitations.

Separate measured observations from expectations. Include request IDs only if safe to publish; otherwise keep them in an authorized diagnostic record.

### 26.5 Demand and user validation

Technical papers establish relevant methods and unresolved problems, not demand for this particular product. Equal spacing alone is an inadequate value proposition beside existing layout tools [S20].

For the 9.5 target, have the owner arrange five formative trials with people who actually produce repeated layouts, or a clearly disclosed smaller pilot if recruitment fails. Ask them to bring a supported custom rule/task. Do not restrict them to praising a prewritten demo.

Compare completion of a small repeated-layout batch using Open Apprentice versus their competent ordinary workflow, including a reusable template/Auto Layout when appropriate. Include initial teaching/setup time, clarification time, corrections, and export cleanup. Counterbalance order where possible. Judge output quality independently with the participant's actual rule. Record whether they complete the workflow without developer intervention, not just whether they like the idea.

Five trials are formative evidence, not representative market research or strong statistical proof. Publish sample size, failures, limitations, and anonymized findings with participant permission. An owner-authored example must not be represented as an external user's task.

Do not contact people or send invitations automatically from Claude Code. The owner arranges participation. If user trials cannot happen, leave impact unvalidated and reduce the grading claim. Do not substitute survey statistics about general AI adoption for evidence that this workflow helps its intended audience.

## 27. Strict grading and completion criteria

The event's four judging dimensions are equally weighted: technical implementation, design, impact, and idea quality [S10b]. A sophisticated controller alone is insufficient.

### 27.1 Minimum credible submission

- A real Nemotron-driven run creates and executes a procedure.
- A learned skill transfers to unseen development inputs.
- A controlled change produces a real failure and a model-generated repair attempt.
- The independent verifier rejects intentionally wrong outputs.
- The UI shows actual events and truthful failure states.
- At least one meaningful equal-budget comparison is complete.
- The demo is deployable and the repository reproducible.

### 27.2 Strong submission

In addition:

- The focused v1.2 baselines and grounding ablation run on a locked protocol.
- Ambiguity, second-tool transfer, and held-out composition are demonstrated with independent intent checks.
- Recovery and retention are demonstrated beyond one selected example.
- Costs include learning, audits, discarded branches, retries, repair, and replay.
- The second tool integration has independently measured results.
- A new user can teach, reuse, challenge, inspect, and export without developer help.

### 27.3 Exceptional result

A result approaching the original 10/10 ambition would need a distinctive demonstrated capability, a convincing advantage over competent baselines, generalization beyond the custom challenge, and a polished experience.

There is no guaranteed grade or prize. Do not write the conclusion before the experiment.

Design-rating history: v1.0 focused on repairing stored procedures (7.5/10 concept judgment); v1.1 added portable intent and composition (approximately 8.5/10); v1.2 focuses on grounded counterexamples, missing-hypothesis recovery, and practical teaching/export (approximately 9/10 concept potential). These are rough subjective assessments. The additional research also revealed strong overlap, so originality cannot honestly be upgraded just by listing more papers or components.

Raise an implemented-project assessment beyond that only when independent evidence and product quality warrant it. If strong baselines perform equally well, report that and reconsider the novelty/impact assessment.

### 27.4 Final definition of done

- [ ] Clean checkout boots using the documented commands.
- [ ] Exact dependencies and browser versions are locked.
- [ ] Offline mode is usable and visibly labeled.
- [ ] Actual Token Factory/Nemotron integration passes a live smoke test.
- [ ] Capability report records accepted provider options.
- [ ] Skill schemas, interpreter limits, and imports are validated.
- [ ] Learning and reuse work on unseen examples.
- [ ] Demonstration-only examples do not disclose the private intended rule.
- [ ] Clarification can distinguish candidate rules and accept Neither.
- [ ] Intent evidence is separate from native execution evidence.
- [ ] The same learned concept has checked bindings for both actual graphics backends.
- [ ] An unseen composition of two learned concepts passes independent checks.
- [ ] Drift scheduling is isolated from agent observations.
- [ ] Paired diagnostics restore identical initial states.
- [ ] Repair promotion requires independent checks and relevant replay.
- [ ] Old versions and routing evidence remain inspectable.
- [ ] Cost accounting includes every attempted branch.
- [ ] Queue recovery, cancellation, and idempotency work.
- [ ] No agent access to evaluator secrets or final answer data.
- [ ] Results are generated from immutable evidence.
- [ ] Baseline tuning and final-manifest freeze are documented.
- [ ] Failures and uncertain outcomes are included in reports.
- [ ] UI and artifacts agree on the committed state.
- [ ] Public demo and judge access are tested.
- [ ] No secrets or private data in the repo or browser bundle.
- [ ] README, license, attribution, limitations, and tool feedback are complete.
- [ ] Public video shows the working system and stays under the time limit.
- [ ] Submission is completed before the deadline.

Additional v1.2 completion checks:

- [ ] Symbolic status and native execution status are distinct; partial searches are labeled incomplete.
- [ ] Every displayed witness is concretely validated and linked to immutable evidence.
- [ ] Target-omission and abstract/native disagreement cases are tested without exposing the reference rule.
- [ ] Binding repair preserves the concept, domain, public constraints, and active teaching ledger.
- [ ] Editable SVG export and offline evidence replay work outside the main app.
- [ ] Formative user trials are reported honestly, including unavailable or unfavorable evidence.
- [ ] The final assessment uses actual outcomes against section 27.5 rather than a prewritten 9.5 claim.

### 27.5 What would make a 9.5 assessment defensible?

The following are proposed acceptance goals, not official judging cutoffs, literature results, or predicted outcomes. They make the ambition falsifiable. Passing them would support considering an exceptional score; it cannot guarantee a judge's grade or a prize.

| Dimension | Evidence needed for the 9.5 target | What fails the argument |
| --- | --- | --- |
| Technical implementation | At least 90% observed intent-correct transfer/composition completion within the declared domain, with all failure/abstention denominators reported; primary paired improvement is positive with uncertainty quantified | A successful staged example, a weak one-shot baseline, or a solver result with no real execution |
| Mechanism advantage | Aim for at least a 10 percentage-point improvement over the strongest main baseline under matched total budgets, and a positive episode-clustered 95% interval for the preregistered primary comparison | Extra uncounted teaching/compute, selective reruns, or no measurable benefit from the claimed mechanism |
| Retention and adaptation | At least 95% observed success on the declared retained-case replay set, plus recovery on fresh cases beyond the triggering witness; report no-change false repair rate and all failures | Fixing one scene by changing the inferred goal or forgetting earlier lessons |
| Design and usefulness | At least four of five formative participants complete the supported teach–challenge–export flow without developer intervention; aim for at least 30% median batch-completion time savings including setup at comparable output quality | A toy canvas that cannot produce a useful editable output, or comparisons that deny users an ordinary template |
| Idea quality and credibility | A clear contribution beyond the credited ingredients, evidence addressing omitted hypotheses and abstract/native disagreement, an unscripted supported challenge, and reproducible artifacts | Claims of inventing skill repair/disambiguation, arbitrary-app generalization, or unmeasured statistical guarantees |

The quality targets intentionally cover all four equally weighted event criteria. Do not compute a spurious 9.5 average from prospective numbers. Grade only delivered behavior and evidence; give an interval or rough score when uncertainty is material.

**Important stopping rule:** if the strong baselines or a simple symbolic system already solve the target just as well, the project can still be useful, but the research/wow-factor argument is weaker. Do not add a model role, synthetic failure, or extra integration merely to rescue the score. Use the remaining time to demonstrate real user value or explicitly lower the claimed ambition.

The current deliverable is a plan. Its approximate 9/10 concept potential and conditional 9.5 target are not a rating of an implemented system. The next meaningful improvement in confidence comes from the 72-hour pilot, not another round of numerical regrading.

## 28. Risk decisions and fallback rules

| Risk | Detection | Response |
| --- | --- | --- |
| Chosen Nemotron model unavailable | Capability probe fails | Select another available NVIDIA model explicitly, rerun the smoke test, and update configuration/claims |
| Structured output unreliable | High schema failure rate on development tasks | Simplify schema, use validated JSON-object mode, allow one counted correction; do not execute malformed output |
| Model cannot solve basic tasks | Fresh-agent pilot nearly always fails | Simplify the supported task family or improve the fresh prompt before comparing adaptation |
| No useful learned abstraction | Reuse fails new parameter combinations | Improve extraction/validation; do not relabel hardcoded examples as reusable skills |
| True intent absent from candidate set | User selects Neither or held-out intent check fails | Expand within the declared budget or abstain; do not treat hypothesis-set agreement as certainty |
| Transfer is solved by handwritten wrapper code | Backend adapter contains task-specific conversion/solution rules | Move learned semantics into generated, validated bindings and disclose any remaining shared abstractions |
| Composition only replays a known whole task | Full combined trace appears in the training set | Rebuild the split and test a genuinely held-out combination |
| Audit cost overwhelms benefit | FULL loses under total budgets | Reduce audit frequency on validation data or report the narrower repair capability |
| Repair memorizes one example | Triggering case passes, new variations fail | Reject promotion and require broader evidence |
| Historical capabilities regress | Replay fails | Keep conditional versions, tighten applicability, or reject the patch |
| Verifier shares a tool bug | Fault injection passes incorrectly | Separate implementations and repair the verifier before rerunning results |
| Fabric integration takes too long | Common-subset gate fails | Cut unsupported features and remove transfer claims if necessary |
| Live demo too slow | Measured runtime exceeds video budget | Use a small live task, show labeled time compression, and retain full trace |
| Provider costs unknown | Usage/rates missing | Use conservative reservations or block new paid runs; display unknown costs honestly |
| Deployment unstable | Restarts/timeouts during smoke tests | Reduce concurrency and features; prioritize a reliable complete core |
| New paper overlaps contribution | Updated literature review reveals overlap | Credit it, narrow the claim, and emphasize measured system behavior without claiming priority |
| Symbolic checks misrepresent real tools | A concrete witness contradicts an abstract check | Preserve the mismatch; invalidate that semantic-model evidence; repair only within the declared intent |
| Solver makes the demo slow or unsupported | Pilot timeouts or unsupported AST frequency | Use labeled sampled search, narrow the supported subset, and remove solver-specific benefit claims |
| Existing layout tools already solve the user's problem | Ordinary-workflow trials are as easy or faster | Reassess the audience/use case; do not hide that comparison |
| No observed learning advantage | Strong structured/text/symbolic references match FULL | Report the result and lower the research claim; prioritize demonstrated product value |

Never fix a research failure by weakening a baseline, leaking the hidden change, removing unsuccessful runs, or changing the evaluator after seeing results.

## 29. Sources and verification notes

Sources were checked during 7–8 October 2026. Hosted APIs, model availability, repositories, and event rules can change. Verify the operational details again at implementation and submission time.

Sources S22–S27 were checked on 9 October 2026 for the real-SVG applicability trial.

### Research

- **[S01] SkillApt: Learning When to Activate Agent Skills from Counterfactual Evidence.** September 2026 preprint. https://arxiv.org/html/2609.26863v1  
  Used for selective activation and matched evidence; its main study does not establish real temporal drift.
- **[S02] GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning.** Paper page identifies acceptance to ICLR 2026. https://arxiv.org/abs/2507.19457  
  Used as a foundation for reflective, evaluator-driven candidate improvement.
- **[S03] Official GEPA implementation.** https://github.com/gepa-ai/gepa  
  Public implementation; inspect the installed version's actual API and license.
- **[S04] SkillCommit: Evolving Agent Skills through Behaviorally Validated Scope Expansion.** August 2026 preprint. https://arxiv.org/abs/2608.15165  
  Used for the principle of replay before accepting broader skill changes.
- **[S13] LILO: Learning Interpretable Libraries by Compressing and Documenting Code.** ICLR 2024. https://arxiv.org/abs/2310.19791  
  Relevant prior work for learned program abstractions; our compact concept/binding system does not reproduce its full algorithm.
- **[S14] Active Task Disambiguation with LLMs.** February 2025. https://arxiv.org/abs/2502.04485  
  Relevant to selecting informative clarification questions; our candidate disagreement heuristic is a limited adaptation.
- **[S15] Break It Down, Pass It On: Cross-Task Skill Transfer in LLM Agents.** August 2026 preprint. https://arxiv.org/html/2608.20274v1  
  Motivates smaller learned units and an explicit text-memory comparison; its results do not establish performance on our tasks.
- **[S16] Choose, Don't Label: Multiple-Choice Query Synthesis for Program Disambiguation.** PLDI 2026 / PACMPL. https://arxiv.org/html/2604.08792v1  
  Closest prior work for informative program-disambiguation queries. Public artifact: https://github.com/celestebarnaby/socrates . Its licensing must be checked before code reuse; our plan does not inherit its convergence theorem.
- **[S17] ContractSkill: Repairable Contract-Based Skills for Multimodal Web Agents.** March 2026 preprint, revised April 2026. https://arxiv.org/html/2603.20340v3  
  Closest baseline inspiration for structured, checked local repair. Public code: https://github.com/underfitting-lu/contractskill . Our graphics-domain baseline is an adaptation, not a reproduction.
- **[S18] VASO: Formally Verifiable Self-Evolving Skills for Physical AI Agents.** June 2026 preprint. https://arxiv.org/html/2606.05395v1  
  Prior verification-guided skill refinement; its stated abstraction-mapping limitation motivates our concrete grounding experiment. We do not reproduce its robotics pipeline.
- **[S21] SynGuar: Guaranteeing Generalization in Programming by Example.** 2021. https://arxiv.org/abs/2106.11610  
  Relevant to the assumptions and evidence needed for generalization guarantees; no such statistical guarantee is claimed here.

The proposed controller, graphics benchmark, AST, service architecture, budgets, and evaluation matrix in this document are our engineering design. They are not results reported by those papers.

- **[S22] Vector-Bench: Can Models Surgically Edit SVG Code?** July 2026 preprint. https://arxiv.org/html/2607.19056v1
- **[S23] Vector-Bench official dataset card and licensing notice.** https://github.com/yug-space/vector-edit-gym/blob/main/DATASET_CARD.md and https://github.com/yug-space/vector-edit-gym/blob/main/NOTICE.md
- **[S24] VectorGym author project page.** https://haorandai.com/vectorgym/ . Human-authored SVG editing tasks; an optional source, not a required training pipeline.
- **[S25] Is Programming by Example Solved by LLMs?** NeurIPS 2024. https://papers.nips.cc/paper_files/paper/2024/hash/4eff61b79274124bc71efe2ee9772f95-Abstract-Conference.html
- **[S26] Beyond Plausibility: Verifiable Fine-Grained Image Editing on Structured Assets.** October 2026 preprint introducing VeriEdit-Bench. https://arxiv.org/abs/2610.04381

### Platform

- **[S05] Nebius Token Factory quickstart.** https://docs.tokenfactory.nebius.com/quickstart
- **[S06] Official Nebius Nemotron Super example.** https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-super-120B.md
- **[S07] Nebius structured-output guide.** https://docs.tokenfactory.nebius.com/ai-models-inference/json
- **[S08] Nebius chat-completion reference.** https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion
- **[S09] Nebius model-listing reference and example.** https://docs.tokenfactory.nebius.com/api-reference/models/list-models and https://docs.tokenfactory.nebius.com/api-reference/examples/list-of-models
- **[S19] Official Z3 arithmetic guide.** https://microsoft.github.io/z3guide/docs/theories/Arithmetic/  
  Supports the choice of a restricted linear-arithmetic symbolic subset. A solver backend does not establish correctness of our translator or native tool model.

The JSON-schema documentation discrepancy is unresolved by documentation alone. The required live capability probe resolves what works for the configured account/model.

### Event

- **[S10a] Hackathon overview and submission requirements.** https://nebiusglobalaihackathon.devpost.com/
- **[S10b] Official rules, deadline, judging period, and scoring.** https://nebiusglobalaihackathon.devpost.com/rules

### Graphics integrations

- **[S11] Konva Node API.** https://konvajs.org/api/Konva.Node.html  
  Provides native node, transform, and geometry operations; validate the behavior of the locked package version.
- **[S12] Fabric object API.** https://www.fabricjs.com/api/classes/fabricobject/  
  Provides the second graphics integration; do not assume older Fabric examples match the installed version.
- **[S20] Figma: Toggle on auto layout in designs.** https://help.figma.com/hc/en-us/articles/5731482952599-Toggle-on-auto-layout-in-designs  
  Existing product capability that must inform the ordinary-workflow comparison. This is not evidence of demand for Open Apprentice.
- **[S27] W3C SVG 2: basic data types and interfaces.** https://www.w3.org/TR/SVG2/types.html . Geometry and coordinate-transform interfaces; browser behavior still needs concrete validation.

## 30. Claude Code kickoff prompt

Paste this after placing the file in the project directory:

~~~text
Read Open_Apprentice_Claude_Code_Build_Spec.md completely and implement the project it specifies.

We are building Open Apprentice for the Nebius x NVIDIA Global AI Hackathon. I am the sole builder. The priority is a real, demonstrable learning-and-repair capability with honest evaluation and a coherent product.

First inspect the current repository and applicable instructions. Preserve existing work. Identify material assumptions or conflicts, create/update docs/status.md and docs/decisions.md, and then begin implementation. Do not stop after giving me a plan or generating a scaffold.

Follow v1.2 and its precedence rules in section 0.5. Build the thin Konva + independent verifier + live Nemotron path first, then candidate rules, bounded counterexample search, human clarification, and checked native bindings. Run the first 72-hour pilot before substantial UI expansion. Then add Fabric transfer, one actual mismatch and binding repair, one fixed two-concept composition, editable SVG export, and evidence replay. Prioritize sections 21.10–21.11. Defer adaptive audit research, a generic planner, extra drift families, and GEPA integration.

Apply the v1.3 addition in 0.6, 6.8, and 21.12 after the core teaching path works. Preserve any existing implementation. Timebox the real-SVG and matched-baseline spike to two development days; keep it experimental if it fails. If it succeeds, prioritize one useful real-asset workflow over optional query ablations or broader backend support. Do not replace every backend, build a general editor, or mistake external instruction editing for evidence of learning from demonstrations. Check asset provenance before including third-party designs in the public demo.

Use a trusted restricted symbolic compiler only on its declared subset. Reproduce proposed witnesses concretely. Keep timeout, incomplete, unsupported, no-witness-in-model, and native-checked states distinct. Do not present a solver result as a proof of human intent or arbitrary native tool behavior. Neither and omitted-hypothesis recovery must work without leaking the reference rule.

Build competent fresh, text-memory, and structured-procedure repair baselines, plus a bounded symbolic reference on the small supported subset. Include all teaching, checking, solver, failed-call, repair, and replay costs. Use section 27.5 as prospective quality gates, not promised results or a pre-earned 9.5 score.

Keep user intent separate from native execution. Ask the user when demonstrations leave intent ambiguous; use isolated experiments for tool behavior. Do not claim a simulator can recover an unstated preference. Never let a model's own inferred rule become its final correctness oracle.

Use the specified restricted procedure language. Do not execute arbitrary model-generated code. Keep evaluator-only information out of agent context. Use a real NVIDIA model through Nebius Token Factory for live runs, with credentials read from local configuration.

Implement the mock provider, deterministic tests, complete offline flow, and setup/deployment files even if credentials are initially missing. Label mocks and recorded replays clearly. Missing credentials do not mean live integration passed.

Check current API/model capabilities rather than assuming provider compatibility. Lock compatible dependency versions. Record every actual command and verification result needed to reproduce the build.

Keep baselines competent, budgets comparable, versions immutable, and results traceable. Never invent benchmark numbers, hardcode a successful repair, expose hidden drift labels, or weaken verification to make a demo succeed.

Continue autonomously through authorized local implementation and verification. Ask only when an unresolved product decision, required credential, access restriction, or new paid/public action truly needs my input; complete all useful preparation first. Respect the environment's permissions and existing repository instructions.

At each milestone, report what now works, what was tested, any remaining limitations, and the next concrete action. Keep this specification as the reference and document justified deviations.
~~~

The first expected output from Claude Code is a brief repository assessment followed by actual M0/M1 implementation.



