"""
Content Quality Scoring — Phase 3.1

Evaluates generated content quality on a 0–100 scale across multiple dimensions:
  - Script word count in ideal range (40–80 words)
  - Code line count in ideal range (3–15 lines)
  - Hashtag count (5–8)
  - Code has proper indentation (not all flat)
  - Content type diversity (bonus if different from recent)

If score < threshold → signal to regenerate.
"""
import logging
import re

logger = logging.getLogger(__name__)

# Quality thresholds
QUALITY_THRESHOLD = 50  # Minimum acceptable score (0–100)

# Ideal ranges (min, max) for scoring dimensions
_SCRIPT_WORD_RANGE = (40, 80)
_CODE_LINE_RANGE = (3, 15)
_HASHTAG_RANGE = (5, 8)
_CODE_CHAR_MAX_PER_LINE = 60  # Lines longer than this are penalized


def score_content(content: dict, recent_types: list[str] | None = None) -> dict:
    """
    Score content quality on a 0–100 scale.

    Args:
        content: The LLM-generated content dict.
        recent_types: List of recent content_type values (newest first)
                      for diversity scoring.

    Returns:
        Dict with keys:
          - total_score (int 0–100)
          - breakdown (dict of dimension → score)
          - passed (bool)
          - reasons (list of human-readable notes)
    """
    breakdown = {}
    reasons = []

    # ── 1. Script word count (0–25 points) ────────────────────
    script = content.get("script", "")
    word_count = len(script.split())
    breakdown["script_words"] = _range_score(
        word_count, _SCRIPT_WORD_RANGE[0], _SCRIPT_WORD_RANGE[1], 25
    )
    if word_count < _SCRIPT_WORD_RANGE[0]:
        reasons.append(f"Script too short ({word_count} words, ideal {_SCRIPT_WORD_RANGE[0]}-{_SCRIPT_WORD_RANGE[1]})")
    elif word_count > _SCRIPT_WORD_RANGE[1]:
        reasons.append(f"Script too long ({word_count} words, ideal {_SCRIPT_WORD_RANGE[0]}-{_SCRIPT_WORD_RANGE[1]})")

    # ── 2. Code line count (0–25 points) ──────────────────────
    code = content.get("code", "")
    code_lines = [l for l in code.splitlines() if l.strip()]
    line_count = len(code_lines)
    breakdown["code_lines"] = _range_score(
        line_count, _CODE_LINE_RANGE[0], _CODE_LINE_RANGE[1], 25
    )
    if line_count < _CODE_LINE_RANGE[0]:
        reasons.append(f"Code too short ({line_count} lines, ideal {_CODE_LINE_RANGE[0]}-{_CODE_LINE_RANGE[1]})")
    elif line_count > _CODE_LINE_RANGE[1]:
        reasons.append(f"Code too long ({line_count} lines, ideal {_CODE_LINE_RANGE[0]}-{_CODE_LINE_RANGE[1]})")

    # ── 3. Hashtag count (0–15 points) ────────────────────────
    hashtags = content.get("hashtags", [])
    tag_count = len(hashtags)
    breakdown["hashtags"] = _range_score(
        tag_count, _HASHTAG_RANGE[0], _HASHTAG_RANGE[1], 15
    )
    if tag_count < _HASHTAG_RANGE[0]:
        reasons.append(f"Too few hashtags ({tag_count}, ideal {_HASHTAG_RANGE[0]}-{_HASHTAG_RANGE[1]})")

    # ── 4. Code quality heuristics (0–20 points) ─────────────
    code_quality = 0

    # 4a. Has indentation (not all flat) → +5
    if any(l.startswith((" ", "\t")) for l in code_lines):
        code_quality += 5

    # 4b. Average line length reasonable (< 60 chars) → +5
    if code_lines:
        avg_len = sum(len(l) for l in code_lines) / len(code_lines)
        if avg_len <= _CODE_CHAR_MAX_PER_LINE:
            code_quality += 5
        else:
            reasons.append(f"Long avg line length ({avg_len:.0f} chars)")

    # 4c. No obvious placeholder/template code → +5
    code_lower = code.lower()
    has_placeholder = any(p in code_lower for p in [
        "todo", "fixme", "placeholder", "your code here", "...",
    ])
    if not has_placeholder:
        code_quality += 5
    else:
        reasons.append("Code contains placeholder text")

    # 4d. Code has comments or docstrings → +5 (educational value)
    has_comments = bool(re.search(r"(#|//|/\*|\"\"\"|''')", code))
    if has_comments:
        code_quality += 5

    breakdown["code_quality"] = code_quality

    # ── 5. Content type diversity (0–15 points) ──────────────
    diversity_score = 15  # Full marks by default
    ct = content.get("content_type", "tip")
    if recent_types:
        # Penalize if same type as most recent
        if recent_types and ct == recent_types[0]:
            diversity_score -= 5
            reasons.append(f"Same content type as last video ({ct})")
        # Penalize more if same type in last 3
        recent_3 = recent_types[:3]
        same_count = sum(1 for t in recent_3 if t == ct)
        if same_count >= 2:
            diversity_score -= 5
            reasons.append(f"Content type '{ct}' used {same_count}× in last 3")
        # Bonus back if truly unique in last 5
        recent_5 = recent_types[:5]
        if ct not in recent_5:
            diversity_score = 15  # Reset to full

    breakdown["diversity"] = max(0, diversity_score)

    # ── Total ─────────────────────────────────────────────────
    total = sum(breakdown.values())
    passed = total >= QUALITY_THRESHOLD

    result = {
        "total_score": total,
        "breakdown": breakdown,
        "passed": passed,
        "reasons": reasons,
    }

    logger.info(
        f"Quality score: {total}/100 ({'PASS' if passed else 'FAIL'}) "
        f"— {breakdown}"
    )

    return result


def _range_score(value: int, min_val: int, max_val: int, max_points: int) -> int:
    """
    Score a value based on how well it fits within an ideal range.
    Returns max_points if in range, scaled down outside.
    """
    if min_val <= value <= max_val:
        return max_points

    if value < min_val:
        # Scale: 0 → 0 points, min_val → max_points
        if min_val == 0:
            return 0
        ratio = max(0, value / min_val)
        return int(max_points * ratio)

    # value > max_val: penalize but not to zero
    overshoot = value - max_val
    penalty_per = max_val * 0.3  # Lose all points at 30% overshoot
    if penalty_per == 0:
        return 0
    ratio = max(0, 1 - overshoot / penalty_per)
    return int(max_points * ratio)
