"""
Phase 3 regression gate: runs eval.score's deterministic scoring against the
24 labeled denials, writes an eval_runs row (db/models.py) tying the result
to the exact commit that produced it, and compares against the most recent
prior eval_runs row to flag a regression.

Runnable as:
    python -m eval.run_eval
from backend/.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.models import EvalRun  # noqa: E402
from db.session import SessionLocal  # noqa: E402

from eval.score import run_scoring  # noqa: E402

# Regression threshold: a drop of more than 5 percentage points in
# overall_score versus the immediately preceding eval_runs row is flagged as
# a regression.
#
# Why 5pp: the harness scores 24 denials, so one denial's classification
# flipping wrong is already a ~1.4pp swing in that dimension alone (1/24 ~=
# 4.2%, weighted at 0.4 ~= 1.7pp of the overall score) -- a couple of
# genuinely-close judgment calls shifting between runs (e.g. a borderline
# CARC-97 duplicate-vs-coding-error case) can plausibly move the overall
# score a few points on its own without anything actually being broken.
# 5pp is chosen to sit above that single-flip noise floor while still being
# tight enough to catch a real regression (e.g. a prompt change that breaks
# a whole category, which would move accuracy by double digits). This is a
# starting point, not a statistically derived value -- with only 24 labeled
# examples there isn't enough data for a rigorous confidence interval, and
# the right move if this threshold proves too noisy in practice is to grow
# eval_labeled.json's sample size, not just retune the number.
REGRESSION_THRESHOLD_PP = 5.0


def get_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def main() -> int:
    print("Running eval scoring against DB (24 labeled denials)...")
    result = run_scoring()

    if result["data_issues"]:
        print(
            f"WARNING: {len(result['data_issues'])} labeled denial(s) have "
            f"missing/corrupted DB rows and were excluded from scoring where "
            f"applicable: {result['data_issues']}"
        )

    overall = result["overall_score"]
    print("\n=== Eval results ===")
    print(f"  Overall score:          {overall:.4f}" if overall is not None else "  Overall score:          N/A")
    print(f"  Classification accuracy: {result['classification_accuracy']:.4f} "
          f"({sum(1 for d in result['per_denial'] if d['classification_correct']) if result['classification_accuracy'] else 0}/24 correct)")
    print(f"  Extraction accuracy (CARC): {result['extraction_accuracy']:.4f}")
    print(f"  Extraction accuracy (RARC, informational): {result['extraction_rarc_accuracy']}")
    print(f"  Appeal completeness:    {result['appeal_completeness']:.4f} "
          f"(over {result['appeal_completeness_n_drafted']} drafted appeals)")
    print(f"  Denials routed to needs_review (no appeal): {result['n_needs_review_no_appeal']}/24")

    git_commit = get_git_commit()
    print(f"\nGit commit: {git_commit or '(unknown -- not a git repo or git unavailable)'}")

    db = SessionLocal()
    try:
        prior_run = (
            db.query(EvalRun)
            .filter(EvalRun.accuracy_score.isnot(None))
            .order_by(EvalRun.run_at.desc())
            .first()
        )

        new_run = EvalRun(
            accuracy_score=overall,
            details=result,
            git_commit=git_commit,
        )
        db.add(new_run)
        db.commit()
        db.refresh(new_run)
        print(f"\nWrote eval_runs row id={new_run.id} run_at={new_run.run_at.isoformat()}")

        if prior_run is None:
            print(
                "\nNo prior eval_runs row exists -- this is the first-ever eval "
                "run, so there is nothing to regress against. Establishing "
                "this run as the baseline."
            )
            return 0

        prior_score = prior_run.accuracy_score
        if prior_score is None or overall is None:
            print(
                f"\nPrior run (id={prior_run.id}) or current run has no "
                f"accuracy_score -- skipping regression comparison."
            )
            return 0

        delta_pp = (overall - prior_score) * 100
        print(
            f"\nComparing against prior run id={prior_run.id} "
            f"(commit={prior_run.git_commit or '?'}, score={prior_score:.4f}):"
        )
        print(f"  Delta: {delta_pp:+.2f} percentage points")

        if delta_pp < -REGRESSION_THRESHOLD_PP:
            print(
                f"\n*** REGRESSION DETECTED ***\n"
                f"Overall accuracy dropped by {abs(delta_pp):.2f}pp, exceeding "
                f"the {REGRESSION_THRESHOLD_PP}pp threshold "
                f"({prior_score:.4f} -> {overall:.4f}).\n"
                f"Prior commit: {prior_run.git_commit or '?'}\n"
                f"Current commit: {git_commit or '?'}"
            )
            return 1

        print("\nNo regression detected.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
