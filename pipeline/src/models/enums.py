"""Enum definitions for the fake news detection pipeline."""

from enum import Enum


class Verdict(str, Enum):
    """Final verdict for a claim."""
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    NOT_ENOUGH_EVIDENCE = "NOT_ENOUGH_EVIDENCE"
    CONFLICTING = "CONFLICTING"


class Stance(str, Enum):
    """Stance of evidence relative to a claim."""
    SUPPORTS = "SUPPORTS"
    REFUTES = "REFUTES"
    NEUTRAL = "NEUTRAL"


class SourceTier(str, Enum):
    """Source credibility tier."""
    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    TIER_3 = "TIER_3"
    UNKNOWN = "UNKNOWN"
    BLACKLISTED = "BLACKLISTED"


class InputType(str, Enum):
    """Type of input content."""
    ARTICLE = "article"
    HEADLINE = "headline"
    CLAIM = "claim"
    SOCIAL_MEDIA = "social_media"
    IMAGE_CAPTION = "image_caption"
    VIDEO_TRANSCRIPT = "video_transcript"
    AUDIO_TRANSCRIPT = "audio_transcript"
    URL = "url"


class ReviewStatus(str, Enum):
    """Human review status."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    DISMISSED = "DISMISSED"


class PipelineStep(str, Enum):
    """Pipeline processing steps."""
    CLAIM_EXTRACTION = "claim_extraction"
    CLAIM_NORMALIZATION = "claim_normalization"
    CLAIM_MATCHING = "claim_matching"
    EVIDENCE_RETRIEVAL = "evidence_retrieval"
    EVIDENCE_RERANKING = "evidence_reranking"
    CLAIM_VERIFICATION = "claim_verification"
    CONFIDENCE_ESTIMATION = "confidence_estimation"
    HUMAN_ESCALATION = "human_escalation"
    CONTINUOUS_LEARNING = "continuous_learning"
