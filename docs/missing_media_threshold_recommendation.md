# Missing-media estimation threshold: recommendation, not an approval

Status: decision-support recommendation for the UK FH MMM implementation brief
(`UK_FH_MMM_Autonomous_Implementation_Brief_2026-09-10.md`, Workstream D / section
8), produced against `core.missing_media_evidence`'s estimation-evidence harness
(`ancestry_mmm/core/missing_media_evidence.py`, `evaluate_candidate_reconstruction_method`).
This document does not approve a threshold, does not select an official imputation
method, and does not change `docs/approved_requirements/REQ-COVERAGE-001.md`'s explicit
"Out of scope" position that no specific validation threshold, coverage-percentage
cutoff, or imputation formula is approved by that record. It is the synthetic-data
evidence base the brief asks for ("produce a short design note recommending a practical
threshold policy after synthetic tests") for a human reviewer (Product/Finance, per
REQ-COVERAGE-001's ownership split) to adopt, amend, or reject via a future,
separately-scoped decision record — mirroring `docs/frequency_conversion_method_options.md`'s
established pattern for exactly this kind of open statistical choice.

**No real Ancestry channel data appears anywhere in this document.** Every figure below
comes from a synthetic weekly series generated for this review only (trend + weekly
seasonality + Gaussian noise + six random promotional spikes over two years, seed 42;
see the reproduction script at the end of this document). It illustrates *the shape of
the tradeoff*, not what any specific real channel's imputation error would actually be.
Once real UK FH media data exists with genuine historical gaps (or synthetic gaps can be
carved out of real, otherwise-complete channels), the same harness should be re-run
against that data before any policy is actually adopted — this document explicitly does
not substitute for that empirical step.

## 1. Why this document exists

`REQ-COVERAGE-001`'s "Out of scope" section is explicit: "Any specific validation
threshold, coverage-percentage cutoff, or approval rule" and "Any specific imputation
formula, interpolation kernel, or default fill method not named in [S4]" are not approved
by that record, and remain for "a future, separately-approved requirement to resolve." The
UK FH MMM brief supplies exactly that dependent scope for missing media (distinct from
`REQ-COVERAGE-001` §4's frequency-conversion scope, which concerns changing a variable's
*frequency*, not filling a *gap* in an otherwise-correct frequency) — but is explicit that
"there is not yet an approved universal number of missing weeks that separates 'estimate'
from 'exclude'" and that this document's own threshold recommendation "must be clearly
labelled as a recommendation until approved."

## 2. Method

Three method-agnostic candidates were evaluated with
`evaluate_candidate_reconstruction_method` against a 104-week synthetic weekly spend
series: for each of five holdout-gap lengths (1, 2, 4, 8, 13 weeks) at three positions
(start, middle, end of the observed series), the harness removed those weeks' true
values, asked each candidate to reconstruct them from the remaining observed weeks only,
and scored MAPE against the real (synthetic) values. No candidate saw the true held-out
values at any point (this is exactly what `evaluate_candidate_reconstruction_method`'s
own docstring requires: already-observed data only, never a period that is itself
uncertain).

**Candidates evaluated** (none is proposed here as *the* approved method — see §5):

- **Flat-fill-last-observed** — every held-out week takes the value of the last observed
  week immediately before the gap.
- **Linear interpolation** — every held-out week is linearly interpolated between the last
  observed value before the gap and the first observed value after it (undefined, and not
  evaluated, for a gap touching the edge of history — an edge gap has no "after" anchor).
- **Seasonal-naive (52-week)** — every held-out week takes the value from 52 weeks earlier,
  when that week is itself observed; falls back to flat-fill otherwise.

## 3. Results (synthetic data only)

| Gap length | Flat-fill worst/mean MAPE | Linear-interp worst/mean MAPE | Seasonal-naive worst/mean MAPE |
|---|---|---|---|
| 1 week | 31.0% / 17.1% | 31.0% / 14.6% | 31.0% / 19.0% |
| 2 weeks | 35.0% / 19.3% | 35.0% / 14.5% | 35.0% / 18.4% |
| 4 weeks | 27.8% / 18.5% | 27.8% / 13.5% | 27.8% / 17.7% |
| 8 weeks | 26.9% / 18.8% | 26.9% / 13.8% | 26.9% / 19.3% |
| 13 weeks | 25.4% / 16.6% | **35.6% / 22.5%** | 25.4% / 19.1% |

Three observations, all specific to this synthetic scenario:

1. **Error does not shrink monotonically with gap length**, and worst-case error stayed in
   the 25-36% MAPE range across every gap length tested for every method — even a single
   held-out week was not reliably reconstructed to within a small error in this scenario's
   noise level. A permissive intuition ("short gaps are basically free to estimate") is not
   supported by this evidence.
2. **Linear interpolation's advantage inverted at the longest gap tested** (13 weeks):
   competitive-or-best at 1-8 weeks, but its worst-case error jumped to the highest of the
   three methods at 13 weeks — consistent with the mechanism (it assumes smooth change
   between two anchor points, which becomes a weaker assumption as the anchors get further
   apart and the true series exercises more of its trend/seasonal/noise structure in
   between).
3. **No candidate dominated at every gap length.** Choosing "the" method without gap-length-
   specific evidence risks silently picking the worse option for a given situation.

## 4. Recommendation (not approved)

Pending real UK FH data and Product/Finance review, this document recommends — as a
starting point for discussion, not an adopted policy — a **conservative, asymmetric**
posture rather than one single missing-week cutoff:

- Treat **1-4 week internal gaps with observed spend evidence during the gap** (see
  `GapDiagnostics.spend_observed_during_gap`) as the only default-eligible-for-estimation
  case, and only when `evaluate_candidate_reconstruction_method` evidence for the specific
  channel and gap length shows worst-case MAPE below an explicit ceiling the reviewer sets
  (this document does not set that number — see below).
- Treat **any edge gap** (touching the start or end of observed history — no anchor on one
  side) as excluded from default estimation regardless of length, matching
  `EstimationReadinessPolicy.allow_edge_gaps` defaulting to `False`. This synthetic
  evidence did not even test edge gaps (linear interpolation cannot reconstruct one), which
  is itself an argument for excluding them by default rather than assuming a same-length
  internal-gap result transfers.
- Treat **gaps longer than roughly 8-13 weeks** as presumptively excluded pending
  channel-specific evidence, since this synthetic scenario's longest-tested method actually
  got *worse*, not better-with-more-context, at 13 weeks.
- Never fall back to a fixed single number (e.g. "always allow up to N weeks") without
  first running this same harness against the actual channel's real observed history and
  checking the resulting worst-case MAPE against whatever ceiling the reviewer sets — the
  right length threshold in §3 clearly differs by method and did not decay smoothly, so a
  single memorised number for "how many weeks is safe" would not transfer across channels
  with different noise/seasonality characteristics.

**This document explicitly does not propose a MAPE ceiling number.** That is a business
risk-tolerance choice (how much reconstruction error is acceptable before an estimated
media value can influence a fitted coefficient, a CPA figure, or a plan), not a statistical
one this harness can answer by itself.

## 5. What this document does not do

- It does not select, approve, or register an official imputation method in any registry
  (`core.frequency_alignment`'s method registry remains empty, unaffected by this
  document, per `REQ-COVERAGE-001` §4).
- It does not set `EstimationReadinessPolicy.max_missing_week_count`,
  `max_consecutive_missing_run`, or `max_reconstruction_error_mape` to any value — every
  field remains the caller's/reviewer's explicit choice; `assess_estimation_readiness`
  fails closed (`blocked_no_policy`) until one is supplied.
- It does not claim the three candidates evaluated are the only reasonable ones, or that
  the synthetic series used is representative of any real Ancestry channel's actual
  noise/seasonality/promotional structure.

## 6. Reproduction

```python
from ancestry_mmm.core.missing_media_evidence import evaluate_candidate_reconstruction_method
# See the git history of this file's introducing commit for the exact synthetic-series
# generator and the three candidate `reconstruct` callables used to produce the table in
# §3 - reproduced in full in that commit's message for traceability.
```
