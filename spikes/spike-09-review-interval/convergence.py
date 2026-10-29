"""Spike 09: does the L3 feedback loop actually converge? (a check, not a formality)

Setup: one dynamic item whose content truly goes stale after `h_true` days (ground truth).
The scheduler reviews it exactly when its decay reaches SURFACE_THRESHOLD (0.6), i.e. at
elapsed = 0.6 * I. Two feedback regimes are compared:

  decay-only  : the verdict comes from the decay number seen at review time.
  labeled     : the reviewer explicitly says "still fresh / changed / already stale".

The point of this experiment is to expose a property that is easy to miss when reading
the rule in isolation: under a scheduler that fires exactly at the surface threshold, the
decay number at review time is *always* 0.6, so decay-only feedback is a permanent no-op.
It never oscillates (safe) but it also never corrects a wrong baseline (useless). The
loop only carries information when the review is triggered by something other than the
decay clock — a human opening the item, a project milestone, or a late review caused by
an exhausted attention budget — or when the verdict is labelled explicitly.
"""
from interval_policy import (
    classify_review, clamp_days, SURFACE_THRESHOLD,
    FEEDBACK_EXPAND, FEEDBACK_SHRINK,
)

# a review is "on time" when it lands within this relative band of the true staleness
ON_TIME_BAND = 0.20


def simulate(h_true: float, i0: float, n_reviews: int = 40, labeled: bool = True,
             expand: float = FEEDBACK_EXPAND, shrink: float = FEEDBACK_SHRINK) -> list[float]:
    """Return the interval trajectory over `n_reviews` scheduled reviews."""
    interval = i0
    traj = []
    for _ in range(n_reviews):
        elapsed = SURFACE_THRESHOLD * interval      # scheduler fires at the surface point
        decay_at_review = elapsed / interval        # == SURFACE_THRESHOLD, by construction
        if labeled:
            if abs(elapsed - h_true) <= ON_TIME_BAND * h_true:
                verdict = "on_time"
            else:
                verdict = "too_early" if elapsed < h_true else "too_late"
        else:
            verdict = classify_review(decay_at_review)
        if verdict == "too_early":
            interval = clamp_days(interval * expand)
        elif verdict == "too_late":
            interval = clamp_days(interval * shrink)
        traj.append(interval)
    return traj


def convergence_summary(h_true: float, i0: float, **kw) -> dict:
    traj = simulate(h_true, i0, **kw)
    target = h_true / SURFACE_THRESHOLD      # I* such that 0.6 * I* == h_true
    return dict(
        h_true=h_true, i0=i0, target=round(target, 3),
        final=round(traj[-1], 3),
        changed=abs(traj[-1] - i0) > 1e-9,
        n_steps_to_band=next(
            (i + 1 for i, v in enumerate(traj)
             if abs(SURFACE_THRESHOLD * v - h_true) <= ON_TIME_BAND * h_true), None),
        trajectory=[round(v, 2) for v in traj[:12]],
    )
