import pytest
from src.utils.source_credibility import (
    extract_domain,
    get_credibility,
    is_blacklisted,
    is_satire_or_troll,
    is_primary_source,
    KNOWN_SOURCES,
)
from src.models.schemas import RetrievedDocument, EvidenceRetrievalResult
from src.pipeline.evidence_reranker import rerank_evidence


def test_extract_domain():
    assert extract_domain("https://www.theonion.com/article/123") == "theonion.com"
    assert extract_domain("http://thefauxy.com/news") == "thefauxy.com"
    assert extract_domain("thefauxy.com") == "thefauxy.com"
    assert extract_domain("news.theonion.com:8080/path") == "news.theonion.com"
    assert extract_domain("https://reuters.com") == "reuters.com"
    assert extract_domain("") == ""


def test_is_blacklisted_and_satire():
    # Indian satire / troll
    assert is_blacklisted("thefauxy.com") is True
    assert is_blacklisted("fauxy.com") is True
    assert is_blacklisted("https://hindi.thefauxy.com/story") is True
    assert is_blacklisted("fakingnews.com") is True
    assert is_blacklisted("theunrealtimes.com") is True

    # Global satire
    assert is_blacklisted("theonion.com") is True
    assert is_blacklisted("onion.com") is True
    assert is_blacklisted("https://sports.theonion.com/some-joke") is True
    assert is_blacklisted("babylonbee.com") is True
    assert is_blacklisted("clickhole.com") is True
    assert is_blacklisted("thebeaverton.com") is True
    assert is_blacklisted("worldnewsdailyreport.com") is True

    # Legitimate news should NOT be blacklisted
    assert is_blacklisted("bbc.com") is False
    assert is_blacklisted("reuters.com") is False
    assert is_blacklisted("who.int") is False
    assert is_blacklisted("thehindu.com") is False
    assert is_blacklisted("ptinews.com") is False


def test_is_satire_or_troll_alias():
    assert is_satire_or_troll("thefauxy.com") is True
    assert is_satire_or_troll("theonion.com") is True
    assert is_satire_or_troll("reuters.com") is False


@pytest.mark.asyncio
async def test_get_credibility_satire_sources():
    # The Fauxy
    cred_fauxy = await get_credibility("https://thefauxy.com/article-slug")
    assert cred_fauxy["tier"] == "BLACKLISTED"
    assert cred_fauxy["credibility"] == 0.0

    # Subdomain of Fauxy
    cred_fauxy_sub = await get_credibility("https://entertainment.thefauxy.com/story")
    assert cred_fauxy_sub["tier"] == "BLACKLISTED"
    assert cred_fauxy_sub["credibility"] == 0.0

    # The Onion
    cred_onion = await get_credibility("https://www.theonion.com/article")
    assert cred_onion["tier"] == "BLACKLISTED"
    assert cred_onion["credibility"] == 0.0

    # The Babylon Bee
    cred_bee = await get_credibility("babylonbee.com")
    assert cred_bee["tier"] == "BLACKLISTED"
    assert cred_bee["credibility"] == 0.0


@pytest.mark.asyncio
async def test_get_credibility_trusted_and_unknown():
    # Tier 1
    cred_who = await get_credibility("https://www.who.int/news")
    assert cred_who["tier"] == "TIER_1"
    assert cred_who["credibility"] >= 0.90

    # Tier 2
    cred_pti = await get_credibility("https://ptinews.com")
    assert cred_pti["tier"] == "TIER_2"
    assert cred_pti["credibility"] >= 0.75

    # Unknown domain gets UNKNOWN tier with baseline 0.40
    cred_unknown = await get_credibility("https://random-unknown-site-12345.org")
    assert cred_unknown["tier"] == "UNKNOWN"
    assert cred_unknown["credibility"] == 0.40


def test_is_primary_source_rejects_satire():
    # Even if claim entity is "The Fauxy" or "Onion", it should NEVER be a primary source
    assert is_primary_source("https://thefauxy.com/post", ["The Fauxy", "Fauxy"]) is False
    assert is_primary_source("https://theonion.com/story", ["Onion", "The Onion"]) is False
    assert is_primary_source("https://babylonbee.com/post", ["Babylon Bee"]) is False

    # Legitimate primary sources work as expected
    assert is_primary_source("https://who.int/statement", ["WHO"]) is True
    assert is_primary_source("https://www.rbi.org.in/press", ["Reserve Bank of India"]) is True
    assert is_primary_source("https://fda.gov/release", ["FDA"]) is True


@pytest.mark.asyncio
async def test_evidence_reranker_filters_out_troll_sources():
    raw_docs = [
        RetrievedDocument(
            doc_id="doc1",
            title="The Fauxy Satirical Piece",
            url="https://thefauxy.com/aliens-in-delhi",
            source_domain="thefauxy.com",
            credibility_score=0.0,
            passages=["Satirical story passage"],
        ),
        RetrievedDocument(
            doc_id="doc2",
            title="Legitimate News Report",
            url="https://ptinews.com/real-story",
            source_domain="ptinews.com",
            credibility_score=0.86,
            passages=["Real news factual passage"],
        ),
        RetrievedDocument(
            doc_id="doc3",
            title="The Onion Parody Story",
            url="https://theonion.com/mars-chocolate",
            source_domain="theonion.com",
            credibility_score=0.0,
            passages=["Parody story passage"],
        ),
    ]

    retrieval_result = EvidenceRetrievalResult(
        claim_id="claim-123",
        search_queries=["test query"],
        retrieved_documents=raw_docs,
    )

    reranked = await rerank_evidence("Alien sighting in Delhi", retrieval_result)

    # Only legitimate news should remain
    ranked_domains = [doc.source_domain for doc in reranked.ranked_evidence]
    assert "thefauxy.com" not in ranked_domains
    assert "theonion.com" not in ranked_domains
    assert "ptinews.com" in ranked_domains
