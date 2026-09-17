"""Plain-language explanations for each test result.

Every card answers three questions: what was measured, what your number
means, and what to check when it looks off. Values are estimates from an
uncalibrated playground, not clinical measurements.
"""

WOW_EXPERIMENTAL = "Experimental playground estimate, not a clinical measure."

TEST_INFO = {
    "static_contrast": {
        "title": "Static contrast detection",
        "what": (
            "One Gabor patch of stripes flashed on screen half the time. "
            "You answered stripes-or-nothing. Threshold = faintest stripes "
            "seen ~79% of the time."
        ),
        "unit": "lower % = sees fainter stripes",
        "good": "Low contrast threshold with high hit rate and low false alarms.",
        "checks": (
            "High false-alarm rate means guessing yes too often; truncated "
            "means the staircase ran out of trials before converging."
        ),
    },
    "static_color": {
        "title": "Static colour bullseye",
        "what": (
            "Center vs surround discs differ along red-blue. You judged the "
            "center redder or bluer. Threshold = smallest colour step told "
            "apart ~79% of the time."
        ),
        "unit": "smaller step = finer colour discrimination",
        "good": "Small delta with symmetric red/blue answers.",
        "checks": "A strong red or blue bias shows in hit vs false-alarm rates.",
    },
    "static_rt": {
        "title": "Simple reaction time",
        "what": "Blank wait, then a disc pops up and you press SPACE as fast as possible.",
        "unit": "lower ms = faster",
        "good": "Median ~200-300 ms with few false starts for most adults.",
        "checks": "Many false starts means anticipating instead of reacting.",
    },
    "collinear": {
        "title": "Collinearity judgment",
        "what": (
            "Two bar segments; you judged aligned vs offset. Threshold = "
            "smallest offset reliably spotted."
        ),
        "unit": "smaller arcmin = finer alignment sense",
        "good": "Low threshold with aligned trials correctly called aligned.",
        "checks": "Calling everything aligned inflates the threshold silently.",
    },
    "brightness": {
        "title": "Brightness match (simultaneous contrast)",
        "what": (
            "Identical grey patches sit on dark vs light rings and look "
            "different. Threshold = real luminance step needed to tell "
            "patches apart despite the illusion."
        ),
        "unit": "smaller step = less fooled by the surround",
        "good": "Small delta; the illusion still fools almost everyone somewhat.",
        "checks": "Calling everything same means the illusion is winning.",
    },
    "vernier": {
        "title": "Vernier acuity",
        "what": (
            "Upper bar fixed, lower bar shifted. You judged left vs "
            "right. Hyperacuity: thresholds finer than photoreceptor "
            "spacing are normal."
        ),
        "unit": "smaller arcmin = finer position sense",
        "good": "Tens of arcseconds is typical for healthy vision.",
        "checks": "Clipped levels mean offsets hit the 1-pixel display floor.",
    },
    "subitize": {
        "title": "Subitizing (how many dots)",
        "what": "Brief dot clouds of 1-9 dots; you pressed the count.",
        "unit": "higher % = better rapid enumeration",
        "good": "Near-perfect up to 4 dots; errors climb past the subitizing range.",
        "checks": "Low accuracy past 5 dots is normal, not a failure.",
    },
    "hueorder": {
        "title": "Hue ordering",
        "what": "Six colour chips clicked lightest to darkest.",
        "unit": "0 = perfect order; larger = more misordered",
        "good": "Mean displacement near 0.",
        "checks": "Repeated swaps of the same pair hint at a genuine confusion.",
    },
    "sizematch": {
        "title": "Size match bias",
        "what": "Left disc fixed, you resized the right disc until equal.",
        "unit": "0% = veridical; signed % shows over/undershoot",
        "good": "Bias near 0%.",
        "checks": "Consistent overshoot suggests a context or strategy effect.",
    },
    "masked": {
        "title": "Masked Gabor detection",
        "what": (
            "A brief ~50 ms Gabor followed by a noise mask. You answered "
            "stripes-or-nothing; the mask limits processing time."
        ),
        "unit": "lower % = sees briefer/fainter stripes",
        "good": "Low threshold with low false alarms.",
        "checks": "High false alarms mean guessing through the mask.",
    },
    "contrast": {
        "title": "Contrast detection (2IFC)",
        "what": (
            "Striped patch in interval 1 or 2. You picked the interval. "
            "Threshold = faintest stripes picked correctly ~79% of the time."
        ),
        "unit": "lower % = sees fainter stripes",
        "good": "Threshold near 1% contrast is typical on a calibrated display.",
        "checks": "Check display calibration; gamma shifts move this number.",
    },
    "acuity": {
        "title": "Acuity (Landolt C)",
        "what": "A C with a gap in one of 4 directions; you reported the gap.",
        "unit": "20/20 = normal; smaller denominator = sharper",
        "good": "logMAR near 0.0 (20/20). Negative is better than average.",
        "checks": "Uncorrected refraction or a dim display hurts this first.",
    },
    "color": {
        "title": "Colour discrimination (2IFC)",
        "what": (
            "Two intervals of colour pairs; you picked the interval with the different colours."
        ),
        "unit": "smaller step = finer colour discrimination",
        "good": "Small delta at fixed luminance.",
        "checks": "Night-mode / blue-light filters invalidate this test.",
    },
}

def flags_for(summary):
    """Short caveat strings: aborted, truncated, unreliable bias, clipped."""
    out = []
    s = summary or {}
    if s.get("aborted"):
        out.append(f"aborted ({s.get('abort_reason', 'no reason')})")
        return out
    if s.get("truncated"):
        out.append("ran out of trials before converging; treat as rough")
    if s.get("unreliable_bias"):
        out.append("response bias: too many yes answers; check d'")
    if s.get("clipped_levels"):
        out.append("hit the 1-pixel display floor on some trials")
    if s.get("n_catch") == 0 and "d_prime" in s:
        out.append("no catch trials recorded; bias unchecked")
    return out


def _norm_sentence(kind, display, percentile, band, n, z):
    if display is None:
        return "No score this run."
    if n < 1:
        return f"Your result: {display}. Take more sessions to build a comparison group."
    base = f"Your result: {display}."
    if percentile is None:
        return base + f" ({n} past session(s) on this machine; need a few more for ranking.)"
    beat = f"You beat {percentile:.0f}% of {n} past session(s) here."
    if z is not None:
        beat += f" (z {z:+.1f}; + means better)"
    return f"{base} {beat} {band}."


def interpret(card):
    """Attach plain-language text to a norms score card (mutates, returns it)."""
    info = TEST_INFO.get(card.get("kind") or "", {})
    card["title"] = info.get("title", card.get("name", "?"))
    card["what"] = info.get("what", "A visual judgment task.")
    card["unit"] = info.get("unit", "")
    card["good"] = info.get("good", "")
    card["checks"] = info.get("checks", "")
    card["caveats"] = flags_for(card.get("summary") or {})
    card["verdict"] = _norm_sentence(
        card.get("kind"),
        card.get("display"),
        card.get("percentile"),
        card.get("band"),
        card.get("n", 0),
        card.get("z"),
    )
    card["disclaimer"] = WOW_EXPERIMENTAL
    return card


def format_card_text(card):
    c = interpret(dict(card))
    lines = [f"== {c['title']} ==", c["what"]]
    if c.get("unit"):
        lines.append(f"Reading the number: {c['unit']}.")
    lines.append(c["verdict"])
    if c.get("good"):
        lines.append(f"Good looks like: {c['good']}")
    if c.get("checks"):
        lines.append(f"Sanity checks: {c['checks']}")
    for caveat in c.get("caveats", []):
        lines.append(f"! {caveat}")
    if "d_prime" in (c.get("summary") or {}):
        s = c["summary"]
        lines.append(
            f"Bias check: hit {s.get('hit_rate')} / false-alarm "
            f"{s.get('fa_rate')} / d' {s.get('d_prime')}"
        )
    lines.append(c["disclaimer"])
    return "\n".join(lines)


def summarize_session(cards):
    cards = [interpret(dict(c)) for c in (cards or [])]
    scored = [c for c in cards if c.get("display")]
    ranked = [c for c in scored if c.get("percentile") is not None]
    if not cards:
        return {"headline": "No tests completed.", "cards": cards}
    if not scored:
        return {"headline": "Session completed but no scores to report.", "cards": cards}
    if not ranked:
        n = scored[0].get("n", 0)
        return {
            "headline": (
                f"{len(scored)} test(s) done. No ranking yet "
                f"({n} past session(s); need a few more)."
            ),
            "cards": cards,
        }
    mean_pct = sum(c["percentile"] for c in ranked) / len(ranked)
    tops = [c["title"] for c in ranked if c["percentile"] >= 75]
    lows = [c["title"] for c in ranked if c["percentile"] <= 25]
    bits = [f"Average rank: beat {mean_pct:.0f}% of past sessions here."]
    if tops:
        bits.append("Strengths: " + ", ".join(tops) + ".")
    if lows:
        bits.append("To retest: " + ", ".join(lows) + ".")
    return {"headline": " ".join(bits), "cards": cards}
