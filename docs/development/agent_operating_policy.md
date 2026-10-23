# Persistent Agent Operating Policy

**Status: operational workflow policy.** This document governs how authorized
agent work is carried across sessions. It does not create or amend business,
scientific, data-use, model, compute, or release authority. Approved
requirements, implementation briefs, this repository's `AGENTS.md` files,
and the four living MMM governance records take precedence. On conflict, stop
and report it.

## Persistent task record

Every non-trivial multi-session task must have a durable, repository-controlled
task record in an approved task/work package location. Do not put confidential
source contents, raw data, secrets, posterior artifacts, or confidential run
details into the record unless the owner has explicitly authorized that
specific material and location. The record contains only what is needed to
resume safely:

- task identifier, objective, scope, authority sources, and current owner;
- exact status, current stage, and last completed checkpoint;
- concise changed-file list and validation evidence, without confidential
  payloads;
- outstanding work, blockers, risks, and the next concrete action;
- approvals and their exact bindings (or the explicit fact that approval is
  absent).

Use only these terminal/task states: `NOT_STARTED`, `ACTIVE`,
`WAITING_FOR_APPROVAL`, `BLOCKED`, `COMPLETE`, and `CANCELLED`. A session
ending is not task completion. Before ending or handing off, save the current
state and next action. Resume from the record and current worktree state;
never infer completion from a prior session summary. Preserve user-provided
instructions and approval scope across sessions, but never broaden them.
These workflow states track task execution only; they do not replace or alter
MMM governance, stage, run, evidence, or approval statuses.

## Context and confidentiality

Use minimum necessary context. A separate session, agent, worktree, or tool is
not a confidentiality boundary. Do not copy, quote, summarize, or transmit
confidential MMM source files, data, reports, secrets, or posterior artifacts
to another agent or external service without explicit owner authorization for
that material and recipient. If a handoff requires such content, stop at the
boundary and request the owner to provide or authorize the necessary context.
Use a non-confidential task record to hand off scope, status, and safe next
steps.

## Roles and review authority

The named workflow roles are exactly:

- **Sol (GPT-6.1 Sol):** independent lead architect and reviewer.
- **Luna (GPT-6 Luna):** primary developer.
- **Codex:** orchestrator, final validation, and evidence recorder.

Verify each participant's actual tool/session identity where available; do not
infer a model or person identity from a display label, an asserted role, or a
handoff message. Record what was actually verified and identify any
unverified identity as a limitation.

If orchestration or an independent reviewer is unavailable, record that
limitation; do not claim the missing review occurred or silently assign its
authority to another role. A reviewer has technical review authority only.
Review does not grant business, scientific, data, compute, or release
approval.

### Default authorized work loop

Within the active user authorization, Codex identifies scope and acceptance
criteria; Luna implements; Luna runs focused tests; Sol independently reviews
the changes; Luna corrects any findings and repeats focused tests and review
until the review is clear; Codex records evidence and automatically continues
to the next already-authorized checkpoint. Record each handoff and outcome.
Do not claim a stage occurred if it did not. Codex's continuation authority
does not broaden the authorized scope. Keep proposal, approval,
implementation, and validation as distinct recorded states.

The owner's standing routine authority covers scoped fixes and refactors,
investigations, local and synthetic tests, non-consuming preflight,
independent technical review, evidence recording, authorized transfer and
checkpoint checks, and local commits/worktrees that exclude unrelated dirty
files. It also persistently authorizes pushing validated development branches,
creating pull requests, and merging them automatically only under the GitHub
safety conditions below. Within these boundaries, do not request repeated
confirmation for each routine action. This standing authority does not cover
the approval-gated actions listed below or expand any task's specific scope.

### Standing GitHub sync workflow

Before any remote write, verify the owner-authorized repository and base
branch, then inspect the exact outgoing tree and commit history for confidential
data, credentials, posterior artifacts, or other prohibited material. The owner
has explicitly authorized `papayasamosa/Media-Mix-Lab` as a public destination
for reviewed-safe application code, tests, and documentation. This does not
authorize publishing Ancestry datasets, commercial information, confidential
reports, credentials, or posterior artifacts. Recheck the live repository and
the exact outgoing content for each synchronization; `.gitignore` does not
protect files already tracked by Git.

The publication review must include tracked and untracked files, staged and
unstaged diffs, and every commit that will become reachable from the PR head.
Use synthetic fixtures in tests. Do not add `.local-data` contents, local input
workbooks, raw business rows, private posterior results, checkpoints, run
manifests, credentials, local caches, logs, or generated reports. Do not add
personal absolute paths or source-root names such as a user's home or private
input directory to code, examples, tests, or docs; use a required environment
setting, a repository-relative fixture, or a clearly synthetic placeholder.
Review `.gitignore` and add protections for common private inputs/artifacts,
but treat it only as a forward-looking guard, never as evidence that tracked
files are safe. Run an available local credential scanner; when none is
available, perform and record a bounded pattern scan and state that limitation.

When a local branch is substantially divergent, contains unsafe historical
blobs, or mixes unrelated experiments, do not push that history wholesale.
Create a clean integration branch from the latest authorized base and add only
the reviewed, validated final-tree changes. This preserves the original local
branch and does not rewrite or force-push shared history. Exclude abandoned or
superseded experiments; retain diagnostic-only scientific code only when its
status and use restrictions remain explicit.

Known confidential content already present in public history is a separate
remediation item. Record its location and safe remediation options in a
non-public project record; do not repeat or expand the exposure in a public
issue, PR, or commit. Do not rewrite shared history or change repository
visibility without separate owner authorization. Existing exposure does not
by itself block publication of an unrelated, verified-safe code change.

Confirm that the target is a development branch and that the change has
passed its required validation.
Then the standing authority covers pushing that branch and creating a pull
request. Merge automatically only after required checks and repository
protections pass and the merge does not cross a scientific, business, or
release approval gate. Immediately before merging, verify that the repository
and base branch are authorized, the PR head still equals the exact reviewed
and validated commit, and required checks and protections pass on that head.
If the PR head, destination repository, or base branch changes, repeat the
affected content-safety review, validation, and independent review before
proceeding. Record the destination, authorized base, PR head, reviewed and
validated commit, checks, protection state, and resulting commit/merge
evidence.

If destination identity, content safety, validation, checks, or protections
cannot be verified, retain the work locally and report the specific blocker.
This authority never permits changing repository visibility, rewriting shared
history, force pushing, bypassing protections, or making another unapproved
external write. GitHub remote writes under this workflow remain bounded by the
task scope and all applicable approval gates.

### Synthetic Sol/Luna exercise acceptance

Before reporting this workflow as exercised, acceptance requires actual,
separate Sol and Luna sessions working on a sanitized synthetic case only;
an actual independent Sol review; any required Luna correction and focused
retest/review; and recorded evidence of the session identities, case scope,
review findings, corrections, and outcome. Do not use confidential source,
data, reports, secrets, business information, or posterior artifacts in this
exercise. If separate sessions or identity verification are unavailable,
report the exercise as not performed or partially evidenced; never simulate
the sessions or claim acceptance.

### Claude Code (third-party tool)

Claude Code is an optional separate third-party process, not one of the three
workflow roles and not a confidentiality boundary. Proactively use it when it
would materially improve complex or consequential work, or help resolve
repeated failures, subject to CLI availability and the confidentiality rules
below. Check `claude --version` and use `claude -p` for a bounded task; default
to read-only access. Record when the CLI is unavailable or confidentiality
rules block its use. Capture the actual reported version, exit status, and
relevant non-confidential evidence. Never simulate its output or report a
version, invocation, or result that was not observed. Do not send confidential
MMM source, data, reports, secrets, or business information to Anthropic
without specific owner authorization covering that content and destination.
Lack of source authorization must be respected even when the separate
process, session, or account appears isolated.

Stage C or equivalent high-impact sampling work requires an independent
full-path technical review covering the authorized identity and settings,
source and graph lineage, all relevant invocation paths, checkpoint/resume
behavior, resource controls, and the evidence/stop conditions. The review
must be recorded before launch; it does not replace the owner-bound fit
authorization required by the applicable governance records.

## Owner approvals remain mandatory

Obtain the approval required by the task prompt and applicable governance
before any of the following when not already explicitly authorized with the
same scope:

- material changes to scientific assumptions, data definitions, priors, or
  causal relationships;
- new paid compute or an increase/change to an approved resource envelope;
- an unauthorized historical launch or restart;
- destructive actions, external data sharing, or GitHub writes outside the
  standing sync workflow above;
- release, production use, or business sign-off.

For real-data sampling, approval must be bound to the exact compiled stage,
graph/prior, source hashes, masks, and settings, as required by the project
invariants. Approval for a proposal, source preparation, compile-only work, a
different identity, or an earlier attempt does not transfer. Never treat
reviewer sign-off as owner approval.

## Retry and recovery status

Any Stage C grant explicitly bound to **`NO_AUTOMATIC_RETRY`** remains
controlling for that run. Its authorization is bound to its stated attempt,
stage, identity, and scope; grants do not carry forward to another run or
stage. This policy authorizes no retry or restart. Any recovery design below
is a proposal only and is inactive until separately approved and implemented
under the normal authority process.

> **PROPOSED—INACTIVE—OWNER APPROVAL REQUIRED**
>
> Candidate recovery envelope for future review: allow at most one pre-sampling
> recovery retry after the initial launch, and only when positive, auditable
> evidence proves that no stochastic or predictive API was invoked in the
> failed attempt. A retry could be considered only for a verified
> non-model, non-resource orchestration, transport, or process-launch failure before that
> boundary; the eligible failure classes must be explicitly approved. Preserve
> identical scientific specification, source and graph identity, priors,
> masks, settings, and authorization binding. Use one cumulative wall-clock
> budget of 43,200 seconds across initial launch and retry; counters and all
> cumulative budgets must persist across process restarts and retries. A retry
> must not reset them. Proposed limits, subject to explicit approval, are at
> most 2 concurrent CPUs and aggregate RSS of 24,000,000,000 bytes across the
> launcher and all descendants. Before activation, specify explicit aggregate
> storage and cost limits and validate that the enforcement covers the full
> process tree and survives restart. Activation would require the owner to
> approve the eligible failure classes and limits, and evidence that the
> enforcement has been validated. Stop on ambiguous sampler state, or any
> model, data, authorization, resource, security, or statistical failure.
>
> This envelope is not operational permission. The existing
> `NO_AUTOMATIC_RETRY` rule remains controlling unless an owner-approved
> decision explicitly supersedes it and the implementation and governance
> records are updated.

Until such a separately approved change exists, follow `NO_AUTOMATIC_RETRY`
exactly. An ambiguous process state, checkpoint, or evidence of possible
stochastic/predictive invocation is a stop condition; do not resume or relaunch
automatically.

## Completion and evidence

At completion, record the exact terminal state, files changed, checks actually
run and their results, unresolved limits, and any required next action. For a
material MMM task, follow the root `AGENTS.md` bootstrap and update the
evidence ledger and next-actions register as required. Do not label a task
complete while required review, validation, approval, or evidence remains
outstanding. Do not run unrelated checks or inspect restricted materials to
fill a record; state the limitation plainly.
