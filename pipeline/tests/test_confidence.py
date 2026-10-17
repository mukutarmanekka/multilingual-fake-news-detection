import pytest
from src.pipeline.confidence import estimate_confidence
from src.models.schemas import (
    VerificationResult,
    RerankedEvidenceResult,
    RankedEvidence,
    EvidenceStance,
)
from src.models.enums import Verdict, Stance


@pytest.mark.asyncio
async def test_confidence_supported_with_high_agreement():
    ranked_evidence = [
        RankedEvidence(
            doc_id=f"doc_{i}",
            title=f"Source {i}",
            url=f"https://source{i}.com",
            source_domain=f"source{i}.com",
            published_date="2026-01-01",
            credibility_score=0.9,
            relevance_score=0.9,
            freshness_score=0.8,
            final_rank_score=0.85,
            passages=["Supporting text"],
            is_primary_source=True,
        )
        for i in range(3)
    ]
    stances = [
        EvidenceStance(
            doc_id=f"doc_{i}",
            snippet="Supporting text",
            stance=Stance.SUPPORTS,
            confidence=0.9,
        )
        for i in range(3)
    ]
    verification = VerificationResult(
        claim_id="test_claim",
        verdict=Verdict.SUPPORTED,
        confidence=0.0,
        reasoning=["Supported by all sources"],
        subclaim_results=[],
        supporting_evidence=stances,
    )
    evidence = RerankedEvidenceResult(claim_id="test_claim", ranked_evidence=ranked_evidence)

    conf, breakdown = await estimate_confidence(verification, evidence)
    assert conf >= 0.75
    assert breakdown.source_agreement_score == 1.0
    assert breakdown.contradiction_penalty == 0.0


@pytest.mark.asyncio
async def test_confidence_conflicting_penalty():
    ranked_evidence = [
        RankedEvidence(
            doc_id="doc_1",
            title="Source 1",
            url="https://source1.com",
            source_domain="source1.com",
            published_date="2026-01-01",
            credibility_score=0.8,
            relevance_score=0.8,
            freshness_score=0.8,
            final_rank_score=0.8,
            passages=["Supports"],
        ),
        RankedEvidence(
            doc_id="doc_2",
            title="Source 2",
            url="https://source2.com",
            source_domain="source2.com",
            published_date="2026-01-01",
            credibility_score=0.8,
            relevance_score=0.8,
            freshness_score=0.8,
            final_rank_score=0.8,
            passages=["Refutes"],
        ),
    ]
    stances = [
        EvidenceStance(doc_id="doc_1", snippet="Supports", stance=Stance.SUPPORTS, confidence=0.8),
        EvidenceStance(doc_id="doc_2", snippet="Refutes", stance=Stance.REFUTES, confidence=0.8),
    ]
    verification = VerificationResult(
        claim_id="test_claim",
        verdict=Verdict.CONFLICTING,
        confidence=0.0,
        reasoning=["Conflicting evidence"],
        subclaim_results=[],
        supporting_evidence=stances,
    )
    evidence = RerankedEvidenceResult(claim_id="test_claim", ranked_evidence=ranked_evidence)

    conf, breakdown = await estimate_confidence(verification, evidence)
    assert breakdown.contradiction_penalty > 0.0
    assert conf <= 0.70


@pytest.mark.asyncio
async def test_confidence_not_enough_evidence_capped():
    verification = VerificationResult(
        claim_id="test_claim",
        verdict=Verdict.NOT_ENOUGH_EVIDENCE,
        confidence=0.0,
        reasoning=["Insufficient evidence"],
        subclaim_results=[],
        supporting_evidence=[],
    )
    evidence = RerankedEvidenceResult(claim_id="test_claim", ranked_evidence=[])

    conf, breakdown = await estimate_confidence(verification, evidence)
    assert conf <= 0.50
