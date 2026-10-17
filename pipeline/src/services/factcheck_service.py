"""Fact-Check Service — Google Fact Check Tools API integration.

Looks up existing fact-checks via the ClaimReview standard.
"""

from __future__ import annotations

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings

logger = structlog.get_logger()


class FactCheckService:
    """Google Fact Check Tools API client."""

    BASE_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15)
        return self._client

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=10))
    async def search_claims(
        self,
        query: str,
        language_code: str = "en",
        max_results: int = 10,
    ) -> list[dict]:
        """
        Search for existing fact-checks related to a claim.

        Returns a list of matching fact-checks with:
        - claim_text: The original claim reviewed
        - claimant: Who made the claim
        - rating: The fact-checker's rating
        - url: Link to the fact-check article
        - publisher: The fact-checking organization
        - review_date: When the review was published
        """
        if not settings.google_factcheck_api_key:
            logger.debug("factcheck.no_key", msg="Skipping — no API key configured")
            return []

        try:
            response = await self.client.get(
                self.BASE_URL,
                params={
                    "key": settings.google_factcheck_api_key,
                    "query": query,
                    "languageCode": language_code,
                    "pageSize": max_results,
                },
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for claim in data.get("claims", []):
                claim_text = claim.get("text", "")
                claimant = claim.get("claimant", "Unknown")

                for review in claim.get("claimReview", []):
                    results.append({
                        "claim_text": claim_text,
                        "claimant": claimant,
                        "rating": review.get("textualRating", ""),
                        "url": review.get("url", ""),
                        "publisher": review.get("publisher", {}).get("name", ""),
                        "review_date": review.get("reviewDate", ""),
                        "title": review.get("title", ""),
                        "language": review.get("languageCode", "en"),
                    })

            logger.debug("factcheck.search", query=query[:80], results=len(results))
            return results

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("factcheck.rate_limited")
            else:
                logger.error("factcheck.error", status=e.response.status_code)
            return []
        except Exception as e:
            logger.error("factcheck.error", error=str(e))
            return []

    async def close(self):
        if self._client:
            await self._client.aclose()


# Singleton
factcheck_service = FactCheckService()
