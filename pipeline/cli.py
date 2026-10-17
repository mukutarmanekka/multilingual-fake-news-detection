#!/usr/bin/env python3
"""
Real-Time Fake News Detection - CLI
Terminal-only interface for the verification pipeline.

Usage:
    python cli.py                        # Interactive mode
    python cli.py "Some claim to verify"  # Single-shot mode
    python cli.py --history               # Show recent verifications
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

# Ensure the pipeline src is importable
sys.path.insert(0, os.path.dirname(__file__))

# Load environment variables from the project root .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Suppress noisy pipeline logs — redirect to a log file
import logging
logging.disable(logging.CRITICAL)

# Suppress transformers progress bars and HuggingFace warnings
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
import warnings
warnings.filterwarnings("ignore")

import structlog
_log_file = os.path.join(os.path.dirname(__file__), "pipeline.log")
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    logger_factory=structlog.WriteLoggerFactory(
        file=open(_log_file, "a", encoding="utf-8")
    ),
)

# ── ANSI Color Codes ─────────────────────────────────────────────────
class C:
    """Terminal colors."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    BG_RED  = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"

# ── Verdict Styling ──────────────────────────────────────────────────
VERDICT_STYLE = {
    "SUPPORTED":           (C.BG_GREEN + C.WHITE + C.BOLD, "[SUPPORTED]"),
    "REFUTED":             (C.BG_RED + C.WHITE + C.BOLD,   "[REFUTED]"),
    "NOT_ENOUGH_EVIDENCE": (C.BG_YELLOW + C.WHITE + C.BOLD, "[NOT ENOUGH EVIDENCE]"),
    "CONFLICTING":         (C.BG_MAGENTA + C.WHITE + C.BOLD, "[CONFLICTING]"),
}

STANCE_ICON = {
    "SUPPORTS": C.GREEN + "[+]" + C.RESET,
    "REFUTES":  C.RED + "[-]" + C.RESET,
    "NEUTRAL":  C.DIM + "[~]" + C.RESET,
}

# ── Pretty Printers ─────────────────────────────────────────────────

def print_banner():
    """Print the startup banner."""
    print(f"""
{C.CYAN}{C.BOLD}+==============================================================+
|         Real-Time Fake News Detection Pipeline               |
|                    Terminal Interface                         |
+==============================================================+{C.RESET}
""")


def print_separator():
    print(f"{C.DIM}{'-' * 62}{C.RESET}")


def print_result(result_data: dict):
    """Pretty-print a single verification result."""

    # ── Language Detection Banner ─────────────────────────────
    detected_lang = result_data.get("detected_language")
    lang_name = result_data.get("language_name")
    was_translated = result_data.get("was_translated", False)
    original_input = result_data.get("original_input_text")

    if detected_lang and detected_lang != "en":
        print()
        if was_translated:
            print(f"  {C.MAGENTA}{C.BOLD}[LANG]{C.RESET} Detected {C.BOLD}{lang_name}{C.RESET} ({detected_lang}) — auto-translated to English for verification")
            if original_input:
                preview = original_input[:120]
                print(f"  {C.DIM}Original: \"{preview}{'...' if len(original_input) > 120 else ''}\"{C.RESET}")
        else:
            print(f"  {C.YELLOW}{C.BOLD}[LANG]{C.RESET} Detected {C.BOLD}{lang_name}{C.RESET} ({detected_lang}) — translation failed, verifying as-is")

    for claim_result in result_data.get("results", []):
        verdict = claim_result.get("verdict", "UNKNOWN")
        confidence = claim_result.get("confidence", 0.0)
        claim_text = claim_result.get("claim", "")
        normalized = claim_result.get("normalized_claim", "")
        reasoning = claim_result.get("reasoning", [])
        evidence = claim_result.get("evidence", [])
        matched = claim_result.get("matched_existing_claim", False)
        review = claim_result.get("requires_human_review", False)
        escalation = claim_result.get("escalation_reason")
        duration = claim_result.get("pipeline_duration_ms", 0)
        claim_original = claim_result.get("original_text")

        style, label = VERDICT_STYLE.get(verdict, (C.DIM, f"? {verdict}"))

        print()
        print_separator()
        print(f"  {C.BOLD}Claim:{C.RESET}  {claim_text}")
        if normalized != claim_text:
            print(f"  {C.DIM}Normalized: {normalized}{C.RESET}")
        if claim_original and was_translated:
            print(f"  {C.DIM}Original ({lang_name}): {claim_original[:150]}{C.RESET}")
        print()

        # Verdict badge
        print(f"  {style}  {label}  {C.RESET}   Confidence: {_confidence_bar(confidence)}")
        print()

        # Reasoning
        if reasoning:
            print(f"  {C.BOLD}{C.CYAN}Reasoning:{C.RESET}")
            for step in reasoning:
                print(f"    {C.DIM}>{C.RESET} {step}")
            print()

        # Evidence
        if evidence:
            print(f"  {C.BOLD}{C.CYAN}Evidence ({len(evidence)} sources):{C.RESET}")
            for ev in evidence[:5]:
                stance = ev.get("stance", "NEUTRAL")
                icon = STANCE_ICON.get(stance, "─")
                source = ev.get("source", "Unknown")
                url = ev.get("url", "")
                snippet = ev.get("snippet", "")[:120]
                print(f"    {icon} {C.BOLD}{source}{C.RESET}")
                if snippet:
                    print(f"      {C.DIM}{snippet}...{C.RESET}")
                if url:
                    print(f"      {C.BLUE}{url}{C.RESET}")
            print()

        # Metadata
        meta_parts = []
        if was_translated:
            meta_parts.append(f"{C.MAGENTA}Translated from {lang_name}{C.RESET}")
        if matched:
            meta_parts.append(f"{C.YELLOW}Fast-path match{C.RESET}")
        if review:
            meta_parts.append(f"{C.RED}[!] Needs human review{C.RESET}")
        if escalation:
            meta_parts.append(f"{C.DIM}({escalation}){C.RESET}")
        if duration:
            meta_parts.append(f"{C.DIM}{duration/1000:.1f}s{C.RESET}")

        if meta_parts:
            print(f"  {' | '.join(meta_parts)}")

        print_separator()

    # Non-checkable statements
    non_checkable = result_data.get("non_checkable_statements", [])
    if non_checkable:
        print(f"\n  {C.DIM}Non-checkable statements:{C.RESET}")
        for stmt in non_checkable:
            print(f"    {C.DIM}* {stmt}{C.RESET}")

    total = result_data.get("total_duration_ms", 0)
    claims = result_data.get("total_claims", 0)
    print(f"\n  {C.DIM}Total: {claims} claim(s) verified in {total/1000:.1f}s{C.RESET}\n")


def _confidence_bar(conf: float) -> str:
    """Render a visual confidence bar."""
    pct = int(conf * 100)
    filled = int(conf * 20)
    if conf >= 0.75:
        color = C.GREEN
    elif conf >= 0.5:
        color = C.YELLOW
    else:
        color = C.RED
    bar = f"{color}{'#' * filled}{C.DIM}{'.' * (20 - filled)}{C.RESET}"
    return f"{bar} {color}{C.BOLD}{pct}%{C.RESET}"


def print_history(claims: list[dict]):
    """Pretty-print recent verification history."""
    if not claims:
        print(f"\n  {C.DIM}No recent verifications found.{C.RESET}\n")
        return

    print(f"\n  {C.BOLD}{C.CYAN}Recent Verifications ({len(claims)} claims):{C.RESET}\n")
    for i, claim in enumerate(claims[:20], 1):
        verdict = claim.get("verdict")
        text = claim.get("claim_text", "")[:70]
        conf = claim.get("confidence")
        raw_created = claim.get("created_at", "")
        created = raw_created.strftime("%Y-%m-%d %H:%M:%S") if hasattr(raw_created, "strftime") else str(raw_created)[:19]

        if verdict:
            style, label = VERDICT_STYLE.get(verdict, (C.DIM, verdict))
            verdict_str = f"{style} {verdict:^15s} {C.RESET}"
        else:
            verdict_str = f"{C.DIM}{'PENDING':^17s}{C.RESET}"

        conf_str = f"{conf*100:.0f}%" if conf else " - "
        print(f"  {C.DIM}{i:>3}.{C.RESET} {verdict_str} {C.DIM}{conf_str:>5s}{C.RESET}  {text}")
        if created:
            print(f"       {C.DIM}{created}{C.RESET}")
    print()


# ── Pipeline Runner ──────────────────────────────────────────────────

async def init_services():
    """Initialize pipeline services (vector DB, models, etc.)."""
    from src.services.vector_service import vector_service
    try:
        await vector_service.ensure_collection()
    except Exception:
        pass  # Will retry on first use


async def verify_claim(text: str) -> dict:
    """Run the full pipeline on a text input and return the result dict."""
    from src.pipeline.orchestrator import PipelineOrchestrator

    orchestrator = PipelineOrchestrator()
    result = await orchestrator.run(input_text=text)

    # Convert to dict for display
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return result


async def get_history(limit: int = 20) -> list[dict]:
    """Fetch recent claims from the database."""
    from src.db.postgres import ClaimDB
    try:
        return await ClaimDB.get_recent_claims(limit=limit)
    except Exception as e:
        print(f"  {C.RED}Database error: {e}{C.RESET}")
        return []


# ── Main Entry Points ────────────────────────────────────────────────

async def interactive_mode():
    """Run the interactive REPL mode."""
    print_banner()
    print(f"  {C.DIM}Type a news claim to verify (any language), or use these commands:{C.RESET}")
    print(f"    {C.CYAN}/history{C.RESET}  - Show recent verifications")
    print(f"    {C.CYAN}/quit{C.RESET}     - Exit the program")
    print(f"  {C.DIM}Supports 50+ languages — non-English input is auto-translated.{C.RESET}")
    print()

    # Initialize services
    print(f"  {C.DIM}Initializing pipeline services...{C.RESET}", end="", flush=True)
    await init_services()
    print(f"\r  {C.GREEN}[OK] Pipeline ready.{C.RESET}                       \n")

    while True:
        try:
            user_input = input(f"  {C.CYAN}{C.BOLD}> {C.RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n\n  {C.DIM}Goodbye!{C.RESET}\n")
            break

        if not user_input:
            continue

        # Commands
        if user_input.lower() in ("/quit", "/exit", "/q", "quit", "exit"):
            print(f"\n  {C.DIM}Goodbye!{C.RESET}\n")
            break

        if user_input.lower() in ("/history", "/h", "history"):
            claims = await get_history()
            print_history(claims)
            continue

        if user_input.lower() in ("/help", "help", "/?"):
            print(f"\n  {C.DIM}Type any news claim or headline to verify it.{C.RESET}")
            print(f"  {C.DIM}Supports 50+ languages — non-English text is auto-translated.{C.RESET}")
            print(f"  {C.DIM}Commands: /history, /quit, /help{C.RESET}\n")
            continue

        # Verify the claim
        print(f"\n  {C.DIM}[...] Verifying claim...{C.RESET}", flush=True)
        start = time.time()

        try:
            result = await verify_claim(user_input)
            print_result(result)
        except Exception as e:
            elapsed = time.time() - start
            print(f"\n  {C.RED}[X] Pipeline error ({elapsed:.1f}s): {e}{C.RESET}\n")


async def single_shot(text: str):
    """Verify a single claim and exit."""
    print_banner()
    print(f"  {C.DIM}Initializing...{C.RESET}", end="", flush=True)
    await init_services()
    print(f"\r  {C.GREEN}[OK] Ready.{C.RESET}          ")
    print(f"\n  {C.DIM}[...] Verifying: \"{text[:80]}\"...{C.RESET}\n", flush=True)

    try:
        result = await verify_claim(text)
        print_result(result)
    except Exception as e:
        print(f"\n  {C.RED}[X] Pipeline error: {e}{C.RESET}\n")
        sys.exit(1)


async def show_history():
    """Show recent verification history and exit."""
    print_banner()
    claims = await get_history()
    print_history(claims)


def main():
    # Enable ANSI colors on Windows and force UTF-8
    if sys.platform == "win32":
        os.system("")  # Enables ANSI escape codes in Windows terminal
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Real-Time Fake News Detection — Terminal CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py                                          # Interactive mode
  python cli.py "BJP won the West Bengal elections"       # Single-shot verify
  python cli.py --history                                # Show recent results
        """,
    )
    parser.add_argument(
        "claim", nargs="?", default=None,
        help="A news claim to verify (omit for interactive mode)",
    )
    parser.add_argument(
        "--history", action="store_true",
        help="Show recent verification history",
    )

    args = parser.parse_args()

    if args.history:
        asyncio.run(show_history())
    elif args.claim:
        asyncio.run(single_shot(args.claim))
    else:
        asyncio.run(interactive_mode())


if __name__ == "__main__":
    main()
