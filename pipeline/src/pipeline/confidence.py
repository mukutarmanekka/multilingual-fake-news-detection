

from __future__ import annotations

import structlog

from ..models.schemas import (
    VerificationResult,
    ConfidenceBreakdown,
    RerankedEvidenceResult,
)
from ..models.enums import Verdict, Stance

logger = structlog.get_logger()


async def estimate_confidence(
    verification: VerificationResult,
    evidence: RerankedEvidenceResult,
) -> tuple[float, ConfidenceBreakdown]:
    logger.info("confidence.start", claim_id=verification.claim_id)

    ranked = evidence.ranked_evidence
    stances = verification.supporting_evidence

    if not ranked:
        breakdown = ConfidenceBreakdown(final_confidence=0.15)
        return 0.15, breakdown
    supports = sum(1 for s in stances if s.stance == Stance.SUPPORTS)
    refutes = sum(1 for s in stances if s.stance == Stance.REFUTES)
    neutrals = sum(1 for s in stances if s.stance == Stance.NEUTRAL)
    total = len(stances) or 1

    if verification.verdict == Verdict.SUPPORTED:
        agreement = supports / total
    elif verification.verdict == Verdict.REFUTED:
        agreement = refutes / total
    elif verification.verdict == Verdict.CONFLICTING:
        agreement = 0.3
    else:
        agreement = 0.2

    source_agreement_score = min(agreement, 1.0)
    if ranked:
        avg_credibility = sum(r.credibility_score for r in ranked) / len(ranked)
        max_credibility = max(r.credibility_score for r in ranked)
        has_primary = any(r.is_primary_source for r in ranked)

        quality = avg_credibility * 0.5 + max_credibility * 0.3
        if has_primary:
            quality += 0.2
        evidence_quality_score = min(quality, 1.0)
    else:
        evidence_quality_score = 0.1

    if ranked:
        avg_freshness = sum(r.freshness_score for r in ranked) / len(ranked)
        freshness = avg_freshness
    else:
        freshness = 0.0

    if total > 1:
        dominant_count = max(supports, refutes, neutrals)
        consistency = dominant_count / total
    else:
        consistency = 0.5

    contradiction_penalty = 0.0
    if supports > 0 and refutes > 0:
        minority = min(supports, refutes)
        contradiction_penalty = (minority / total) * 0.3

    retrieval_certainty = min(len(ranked) / settings_top_evidence(), 1.0)
    if ranked:
        avg_relevance = sum(r.relevance_score for r in ranked) / len(ranked)
        retrieval_certainty = (retrieval_certainty + avg_relevance) / 2

    raw_confidence = (
        0.30 * source_agreement_score
        + 0.20 * evidence_quality_score
        + 0.10 * freshness
        + 0.20 * consistency
        + 0.20 * retrieval_certainty
        - contradiction_penalty
    )

    raw_confidence = max(0.05, min(0.99, raw_confidence))

    if verification.verdict == Verdict.NOT_ENOUGH_EVIDENCE:
        raw_confidence = min(raw_confidence, 0.50)
    elif verification.verdict == Verdict.CONFLICTING:
        raw_confidence = min(raw_confidence, 0.70)

    has_strong_primary = any(
        r.is_primary_source and r.credibility_score >= 0.70
        for r in ranked
    )
    if has_strong_primary and source_agreement_score >= 0.6:
        raw_confidence = max(raw_confidence, 0.82)

    if source_agreement_score >= 0.8 and consistency >= 0.7 and len(ranked) >= 3:
        raw_confidence = max(raw_confidence, 0.75)

    final_confidence = round(raw_confidence, 2)

    breakdown = ConfidenceBreakdown(
        source_agreement_score=round(source_agreement_score, 3),
        evidence_quality_score=round(evidence_quality_score, 3),
        freshness_score=round(freshness, 3),
        consistency_score=round(consistency, 3),
        retrieval_certainty=round(retrieval_certainty, 3),
        contradiction_penalty=round(contradiction_penalty, 3),
        final_confidence=final_confidence,
    )

    logger.info(
        "confidence.done",
        claim_id=verification.claim_id,
        confidence=final_confidence,
    )

    return final_confidence, breakdown


def settings_top_evidence() -> int:
    try:
        from ..config import settings
        return settings.top_evidence_count
    except Exception:
        return 5
