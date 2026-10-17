"""Step 8 — Human Review Escalation.

Determines whether a verified claim should be escalated to human reviewers
based on confidence level, evidence conflicts, claim impact, and novelty.
"""

from __future__ import annotations

import re

import structlog

from ..models.schemas import VerificationResult, EscalationDecision, RerankedEvidenceResult
from ..models.enums import Verdict, Stance
from ..config import settings

logger = structlog.get_logger()

# High-impact domains that always warrant extra scrutiny
HIGH_IMPACT_DOMAINS = {
    "health": ["vaccine", "covid", "cancer", "disease", "drug", "treatment", "virus",
               "pandemic", "epidemic", "medication", "surgery", "death toll",
               "mortality", "cure", "therapy", "WHO", "CDC", "FDA"],
    "war_conflict": ["war", "military", "attack", "bomb", "missile", "invasion",
                     "troops", "casualties", "ceasefire", "conflict", "soldier",
                     "nuclear", "weapon", "drone strike", "airstrike"],
    "finance": ["stock market", "crash", "recession", "inflation", "GDP",
                "bankruptcy", "federal reserve", "interest rate", "bank",
                "cryptocurrency", "bitcoin", "SEC", "fraud"],
    "elections": ["election", "vote", "ballot", "candidate", "poll", "primary",
                  "president", "senator", "governor", "electoral",
                  "campaign", "debate", "rigged"],
    "disasters": ["earthquake", "hurricane", "flood", "wildfire", "tsunami",
                  "tornado", "eruption", "explosion", "collapse", "disaster",
                  "emergency", "evacuation"],
    "public_safety": ["shooting", "terrorism", "arrest", "kidnap", "missing",
                      "alert", "warning", "recall", "contamination", "poison",
                      "radiation", "chemical"],
}


async def check_escalation(
    claim_text: str,
    verification: VerificationResult,
    evidence: RerankedEvidenceResult,
) -> EscalationDecision:
    """
    Determine whether a claim requires human review escalation.

    Escalation triggers:
    1. Confidence < threshold (default 0.65)
    2. Strong evidence conflicts
    3. High-impact domain + any uncertainty
    4. Novel claim with no prior evidence
    5. All evidence is NEUTRAL (no clear stance)
    """
    logger.info("escalation.check", claim_id=verification.claim_id)

    reasons = []
    matched_domains = []
    priority = 5  # Default priority

    # ── 1. Low confidence ────────────────────────────────────
    if verification.confidence < settings.confidence_escalation_threshold:
        reasons.append(
            f"Low confidence ({verification.confidence:.2f} < {settings.confidence_escalation_threshold})"
        )
        priority = max(priority, 7)

    # ── 2. Evidence conflicts ────────────────────────────────
    if verification.verdict == Verdict.CONFLICTING:
        supports = sum(1 for s in verification.supporting_evidence if s.stance == Stance.SUPPORTS)
        refutes = sum(1 for s in verification.supporting_evidence if s.stance == Stance.REFUTES)
        if supports > 0 and refutes > 0:
            reasons.append(
                f"Conflicting evidence: {supports} sources support, {refutes} sources refute"
            )
            priority = max(priority, 8)

    # ── 3. High-impact domain ────────────────────────────────
    claim_lower = claim_text.lower()
    for domain, keywords in HIGH_IMPACT_DOMAINS.items():
        if any(kw in claim_lower for kw in keywords):
            matched_domains.append(domain)

    if matched_domains:
        # High-impact claims need higher confidence to avoid escalation
        if verification.confidence < 0.80:
            reasons.append(
                f"High-impact domain ({', '.join(matched_domains)}) with confidence < 0.80"
            )
            priority = max(priority, 9)

    # ── 4. Novel claim / no evidence ─────────────────────────
    if not evidence.ranked_evidence:
        reasons.append("No evidence found — novel or unverifiable claim")
        priority = max(priority, 7)

    # ── 5. All neutral stances ───────────────────────────────
    if verification.supporting_evidence:
        all_neutral = all(
            s.stance == Stance.NEUTRAL for s in verification.supporting_evidence
        )
        if all_neutral:
            reasons.append("All evidence stances are NEUTRAL — no clear support or refutation")
            priority = max(priority, 6)

    # ── Decision ─────────────────────────────────────────────
    requires_review = len(reasons) > 0

    if requires_review:
        reason_text = "; ".join(reasons)
        logger.info(
            "escalation.escalated",
            claim_id=verification.claim_id,
            reason=reason_text,
            priority=priority,
        )
    else:
        reason_text = None
        logger.info("escalation.not_needed", claim_id=verification.claim_id)

    return EscalationDecision(
        requires_human_review=requires_review,
        reason=reason_text,
        priority=priority,
        high_impact_domains=matched_domains,
    )
