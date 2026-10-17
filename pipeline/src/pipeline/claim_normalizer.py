"""Step 2 — Claim Normalization.

Resolves aliases, normalizes dates, resolves pronouns,
normalizes quantities, and canonicalizes entity names.
"""

from __future__ import annotations

import structlog

from ..services.llm_service import llm_service
from ..models.schemas import ExtractedClaim, NormalizedClaim
from ..utils.temporal import normalize_date

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a claim normalization system for a fact-checking pipeline.

Your task is to normalize a factual claim so it is unambiguous and self-contained.

Perform these transformations:
1. RESOLVE PRONOUNS: Replace "he", "she", "they", "it" with the actual entity names.
2. RESOLVE ALIASES: Replace nicknames, abbreviations, or informal names with canonical names.
   - "The US President" → "President of the United States [full name]"
   - "WHO" → "World Health Organization (WHO)"
   - "PM" → "Prime Minister [full name]"
3. NORMALIZE DATES: Convert relative dates to absolute ISO format (YYYY-MM-DD).
   - "yesterday" → actual date
   - "last week" → approximate date
   - "today" → current date
4. NORMALIZE QUANTITIES: Standardize numbers and units.
   - "billions" → specific number if known
   - "$2B" → "$2,000,000,000"
5. MAKE SELF-CONTAINED: The normalized claim should be understandable without any context.

If you cannot resolve a reference with certainty, keep the original and note it.

Respond with valid JSON:
{
  "normalized_claim": "The fully normalized, unambiguous claim text",
  "resolved_entities": [
    {"original": "the president", "resolved": "President Joe Biden", "type": "PERSON"}
  ],
  "resolved_dates": ["2025-03-15"]
}"""


async def normalize_claim(
    claim: ExtractedClaim,
    input_context: str = "",
    current_date: str = "",
) -> NormalizedClaim:
    """
    Normalize a claim for unambiguous verification.

    Resolves pronouns, aliases, dates, and quantities.
    """
    logger.info("claim_normalizer.start", claim_id=claim.claim_id)

    user_prompt = f"""Normalize the following factual claim.

CLAIM: "{claim.text}"

KNOWN ENTITIES FROM CONTEXT: {', '.join(claim.entities) if claim.entities else 'None'}
KNOWN DATES: {', '.join(claim.dates) if claim.dates else 'None'}
CURRENT DATE: {current_date or 'Unknown'}

ORIGINAL CONTEXT (for pronoun resolution):
\"\"\"
{input_context[:3000] if input_context else 'No additional context available.'}
\"\"\"

Return the normalized claim as JSON."""

    result = await llm_service.generate_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.05,
        max_tokens=2048,
    )

    # Normalize dates in the result
    resolved_dates = []
    for date_str in result.get("resolved_dates", []):
        normalized = normalize_date(date_str)
        resolved_dates.append(normalized or date_str)

    normalized = NormalizedClaim(
        claim_id=claim.claim_id,
        original_text=claim.text,
        normalized_claim=result.get("normalized_claim", claim.text),
        resolved_entities=result.get("resolved_entities", []),
        resolved_dates=resolved_dates,
        resolved_numbers=result.get("resolved_numbers", claim.numbers),
    )

    logger.info(
        "claim_normalizer.done",
        claim_id=claim.claim_id,
        entities_resolved=len(normalized.resolved_entities),
    )

    return normalized
