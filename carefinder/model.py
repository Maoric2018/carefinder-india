"""Learned evidence model: how likely is it that a facility really offers a service, given its own record?

There are no ground-truth labels, so we cannot train a classifier. Instead we use the classic answer to
"several noisy witnesses, no answer key": a latent class model fitted by EM (Dawid & Skene 1979; the same
family as the label model in Snorkel / data programming, Ratner et al. 2016).

  Y ∈ {0, 1}            does the facility offer the service (unobserved)
  x_j                   what field j of its record says: nothing / mention inside a long list / dedicated mention
                        (procedures, equipment, capabilities, description, name, specialties), plus three binary
                        signals: related words only, text saying it is unavailable, concrete detail (counts, brands)
  z_k                   record-quality flags (clinic for a hospital-only service, merged record, no sources, ...)

  P(Y = 1 | z)          = σ(γ₀ + Σ γ_k z_k)                       latent class regression (Bandeen-Roche et al. 1997)
  P(x | Y = y)          = Π_j θ_{y,j}[x_j]                         fields are conditionally independent given Y
  P(Y = 1 | x, z)       ∝ σ(γ·z) Π_j θ_{1,j}[x_j]                  Bayes' rule

EM alternates between the posterior P(Y | x, z) for every record (E-step) and re-estimating θ and γ from those
soft labels (M-step). Field reliabilities are therefore learned from how often fields *agree with each other*:
a field whose mentions are usually corroborated by other fields gets a large likelihood ratio, a field whose
mentions usually stand alone gets a small one. Dirichlet(1) priors on θ and a ridge prior on γ keep rare
patterns stable, and flag effects are constrained to be ≤ 0 (a red flag can only lower the odds; projected Newton). Uncertainty comes from a non-parametric bootstrap over facilities (refit, recompute posteriors).

Limitations we report: conditional independence is an assumption (fields scraped from the same page can share
errors), and "offers the service" means "the record consistently says so", not an on-site verification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

FIELDS = ("procedure", "equipment", "capability", "description", "name", "specialties")
SIGNALS = ("support_only", "negated", "specific")
INDICATORS = FIELDS + SIGNALS
CATS = (3,) * len(FIELDS) + (2,) * len(SIGNALS)  # field: none / listed / dedicated; signals: no / yes
COVARIATES = ("clinic_for_hospital_service", "pharmacy_or_dental", "merged_record", "corrupted_row",
              "mentions_other_facilities", "no_source_urls", "no_own_website", "too_few_beds")
COVARIATE_TEXT = {
    "clinic_for_hospital_service": "it looks like a clinic, and this service usually needs a hospital",
    "pharmacy_or_dental": "it is listed as a pharmacy or dental practice",
    "merged_record": "the record may merge more than one facility",
    "corrupted_row": "the record's columns look shifted (corrupted row)",
    "mentions_other_facilities": "some of its mentions of this service are about other facilities (ignored)",
    "no_source_urls": "it has no source URL to check against",
    "no_own_website": "none of its sources is the facility's own website",
    "too_few_beds": "its listed bed count is below what this service usually needs",
}


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -40, 40)))


@dataclass
class LatentClassModel:
    theta1: list[np.ndarray]   # P(x_j = k | Y = 1)
    theta0: list[np.ndarray]   # P(x_j = k | Y = 0)
    gamma: np.ndarray          # [intercept, covariate effects] on the log-odds of Y = 1
    loglik: float = float("nan")
    iterations: int = 0
    n: int = 0
    lo: np.ndarray | None = None   # bootstrap 5th percentile of the posterior, per unique pattern
    hi: np.ndarray | None = None   # bootstrap 95th percentile
    patterns: np.ndarray | None = None
    index: dict = field(default_factory=dict)

    # ---- inference -------------------------------------------------------------------------------
    def log_lr(self, X: np.ndarray) -> np.ndarray:
        """log P(x | Y=1) - log P(x | Y=0) for each row of X."""
        out = np.zeros(len(X))
        for j, (t1, t0) in enumerate(zip(self.theta1, self.theta0)):
            out += np.log(t1[X[:, j]]) - np.log(t0[X[:, j]])
        return out

    def posterior(self, X: np.ndarray, Z: np.ndarray) -> np.ndarray:
        return _sigmoid(self.gamma[0] + Z @ self.gamma[1:] + self.log_lr(X))

    def evidence_only(self, X: np.ndarray) -> np.ndarray:
        """Posterior for a record with no quality flags: what its text alone supports."""
        return _sigmoid(self.gamma[0] + self.log_lr(X))

    def interval(self, X: np.ndarray, Z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        keys = [self.index.get(tuple(r)) for r in np.hstack([X, Z]).astype(int)]
        p = self.posterior(X, Z)
        lo = np.array([self.lo[k] if k is not None else v for k, v in zip(keys, p)])
        hi = np.array([self.hi[k] if k is not None else v for k, v in zip(keys, p)])
        return np.minimum(lo, p), np.maximum(hi, p)

    # ---- explanation ----------------------------------------------------------------------------
    def likelihood_ratios(self) -> dict[str, dict[str, float]]:
        """How much each kind of mention multiplies the odds that the facility offers the service."""
        out = {}
        for name, t1, t0, c in zip(INDICATORS, self.theta1, self.theta0, CATS):
            if c == 3:
                out[name] = {"dedicated": float(t1[2] / t0[2]), "listed": float(t1[1] / t0[1]),
                             "absent": float(t1[0] / t0[0])}
            else:
                out[name] = {"present": float(t1[1] / t0[1]), "absent": float(t1[0] / t0[0])}
        return out

    def odds_ratios(self) -> dict[str, float]:
        return {c: float(math.exp(g)) for c, g in zip(COVARIATES, self.gamma[1:])}

    def prior(self) -> float:
        return float(_sigmoid(self.gamma[0]))


def _unique(X: np.ndarray, Z: np.ndarray):
    rows = np.hstack([X, Z]).astype(np.int16)
    u, inv, counts = np.unique(rows, axis=0, return_inverse=True, return_counts=True)
    return u[:, :X.shape[1]].astype(int), u[:, X.shape[1]:].astype(float), counts.astype(float), inv.ravel(), u


def _em(Xu, Zu, w, cats, r, theta1=None, theta0=None, gamma=None, alpha=1.0, ridge=1.0, max_iter=500, tol=1e-9,
        nonpositive=True):
    n_cov = Zu.shape[1]
    D = np.hstack([np.ones((len(Zu), 1)), Zu])
    gamma = np.zeros(n_cov + 1) if gamma is None else gamma.copy()
    prev = -np.inf
    it = 0
    ll = prev
    for it in range(1, max_iter + 1):
        if it > 1 or theta1 is None:  # M-step from the current soft labels r
            theta1, theta0 = [], []
            for j, c in enumerate(cats):
                onehot = np.eye(c)[Xu[:, j]]
                n1 = (w * r) @ onehot + alpha
                n0 = (w * (1 - r)) @ onehot + alpha
                theta1.append(n1 / n1.sum())
                theta0.append(n0 / n0.sum())
            for _ in range(2):  # Newton steps for the weighted logistic regression of r on z (ridge on effects)
                p = _sigmoid(D @ gamma)
                pen = np.r_[0.0, np.full(n_cov, ridge)]
                g = D.T @ (w * (r - p)) - pen * gamma
                H = (D * (w * p * (1 - p))[:, None]).T @ D + np.diag(pen + 1e-9)
                gamma = gamma + np.linalg.solve(H, g)
                if nonpositive:  # red flags may only lower the odds; the data decides by how much
                    gamma[1:] = np.minimum(gamma[1:], 0.0)
        # E-step
        log_lr = np.zeros(len(Xu))
        for j in range(len(cats)):
            log_lr += np.log(theta1[j][Xu[:, j]]) - np.log(theta0[j][Xu[:, j]])
        eta = D @ gamma
        r = _sigmoid(eta + log_lr)
        log_p0 = np.zeros(len(Xu))
        for j in range(len(cats)):
            log_p0 += np.log(theta0[j][Xu[:, j]])
        # log P(x, z) = log[(1-π) P(x|0)] + log(1 + exp(eta + log_lr))
        ll = float(w @ (log_p0 - np.logaddexp(0, eta) + np.logaddexp(0, eta + log_lr)))
        if abs(ll - prev) < tol * max(1.0, abs(ll)):
            break
        prev = ll
    return theta1, theta0, gamma, r, ll, it


def fit(X: np.ndarray, Z: np.ndarray, cats=CATS, n_boot: int = 100, seed: int = 0, ridge: float = 1.0,
        nonpositive: bool = True) -> LatentClassModel:
    """X: (n, len(cats)) integer states; Z: (n, n_cov) 0/1 covariates."""
    Xu, Zu, w, _, rows = _unique(X, Z)
    # Start from "how many fields say it plainly": a sensible, monotone initial guess for P(Y=1 | x).
    dedicated = (Xu[:, :len(FIELDS)] == 2).sum(1)
    listed = (Xu[:, :len(FIELDS)] == 1).sum(1)
    r0 = np.clip(0.02 + 0.55 * (dedicated >= 1) + 0.38 * (dedicated >= 2) + 0.3 * ((dedicated == 0) & (listed >= 1)), 0, 0.98)
    theta1, theta0, gamma, r, ll, it = _em(Xu, Zu, w, cats, r0, ridge=ridge, nonpositive=nonpositive)
    # Keep class 1 = "offers the service": it must mention the service more often than class 0.
    mention1 = np.mean([1 - t[0] for t in theta1[:len(FIELDS)]])
    mention0 = np.mean([1 - t[0] for t in theta0[:len(FIELDS)]])
    if mention1 < mention0:
        theta1, theta0, gamma = theta0, theta1, -gamma
    model = LatentClassModel(theta1, theta0, gamma, ll, it, int(w.sum()))
    model.patterns = rows
    model.index = {tuple(r): i for i, r in enumerate(rows.tolist())}
    if n_boot:
        rng = np.random.default_rng(seed)
        draws = np.empty((n_boot, len(Xu)))
        N = int(w.sum())
        for b in range(n_boot):
            wb = rng.multinomial(N, w / N).astype(float)
            t1, t0, gb, _, _, _ = _em(Xu, Zu, wb, cats, r, theta1=[t.copy() for t in theta1],
                                      theta0=[t.copy() for t in theta0], gamma=gamma, ridge=ridge, max_iter=60, tol=1e-7,
                                      nonpositive=nonpositive)
            m = LatentClassModel(t1, t0, gb)
            draws[b] = m.posterior(Xu, Zu)
        model.lo = np.percentile(draws, 5, axis=0)
        model.hi = np.percentile(draws, 95, axis=0)
    return model


def simulate(n: int, theta1, theta0, gamma, Z: np.ndarray | None = None, seed: int = 0):
    """Draw records from a known model (used by the tests to check that EM recovers the parameters)."""
    rng = np.random.default_rng(seed)
    Z = np.zeros((n, len(gamma) - 1)) if Z is None else Z
    y = rng.random(n) < _sigmoid(gamma[0] + Z @ gamma[1:])
    X = np.zeros((n, len(theta1)), dtype=int)
    for j, (t1, t0) in enumerate(zip(theta1, theta0)):
        X[y, j] = rng.choice(len(t1), size=int(y.sum()), p=t1)
        X[~y, j] = rng.choice(len(t0), size=int((~y).sum()), p=t0)
    return X, Z, y
