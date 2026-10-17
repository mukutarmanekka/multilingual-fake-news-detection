"""Internal API routes for the ML pipeline."""

from __future__ import annotations

import traceback
import structlog
from fastapi import APIRouter, HTTPException

from ..models.schemas import VerifyRequest, VerificationJobResponse
from ..pipeline.orchestrator import PipelineOrchestrator

logger = structlog.get_logger()
router = APIRouter()

# Singleton orchestrator
_orchestrator: PipelineOrchestrator | None = None


def get_orchestrator() -> PipelineOrchestrator:
    """Get or create the pipeline orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = PipelineOrchestrator()
    return _orchestrator


@router.post("/verify", response_model=VerificationJobResponse)
async def verify_content(request: VerifyRequest):
    """
    Run the full verification pipeline on input text.

    Extracts claims, normalizes, checks for matches, retrieves evidence,
    re-ranks, verifies, estimates confidence, and optionally escalates.
    """
    logger.info("api.verify", input_type=request.input_type, text_len=len(request.text))

    try:
        orchestrator = get_orchestrator()
        result = await orchestrator.run(
            input_text=request.text,
            input_type=request.input_type,
            job_id=request.job_id,
        )
        return result
    except Exception as e:
        logger.error("api.verify.error", error=str(e), trace=traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@router.get("/claims/recent")
async def get_recent_claims(limit: int = 50):
    """Get recently verified claims."""
    from ..db.postgres import ClaimDB
    try:
        claims = await ClaimDB.get_recent_claims(limit=limit)
        return {"claims": claims, "total": len(claims)}
    except Exception as e:
        logger.error("api.claims.error", error=str(e))
        return {"claims": [], "total": 0}


@router.get("/reviews/pending")
async def get_pending_reviews(limit: int = 20):
    """Get claims pending human review."""
    from ..db.postgres import ClaimDB
    try:
        reviews = await ClaimDB.get_pending_reviews(limit=limit)
        return {"reviews": reviews, "total": len(reviews)}
    except Exception as e:
        logger.error("api.reviews.error", error=str(e))
        return {"reviews": [], "total": 0}


@router.get("/claims/{job_id}")
async def get_claim_result(job_id: str):
    """Get verification results for a specific job ID."""
    from ..db.postgres import ClaimDB
    try:
        results = await ClaimDB.get_job_results(job_id)
        if not results:
            # Check if job exists at all
            job = await ClaimDB.get_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            return {"job_id": job_id, "status": job.get("status", "unknown"), "claims": []}
        
        return {"job_id": job_id, "status": "completed", "claims": results}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("api.claim_result.error", job_id=job_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
