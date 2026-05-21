"""
Evaluate a student's handwritten PDF submission against an answer key
using Claude's vision API. Returns a rich evaluation JSON suitable for
the ThinkingSouls report template (ts_evalreport.sty).

Usage:
    python tools/evaluate_pdf.py '<download_result_json>'
"""

import base64
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")

# ── Performance bands (locked) ─────────────────────────────────────────────────
def band_for(percentage: float) -> tuple[str, str, str]:
    """Returns (band_name, band_color_token, verdict_text)."""
    if percentage >= 75:
        return "Trailblazer", "tsGreen", ""  # verdict filled by qualifies_for
    if percentage >= 60:
        return "Qualifier",   "tsBlue",  ""
    if percentage >= 45:
        return "Developing",  "tsAmber", "Approaching the Qualifier threshold"
    return "Foundational Gaps", "tsRed", "Foundational rebuild required"


SYSTEM_PROMPT = """You are a senior mathematics teacher evaluator at ThinkingSouls Education.
You produce JEE Advanced–quality evaluation reports for handwritten student submissions.

You are given two PDFs:
- Document 1: Answer Key (with questions, expected solutions, and final answers)
- Document 2: Student's handwritten submission

Apply the **Standard Subjective Rubric** to every question:
| Dimension                | Weight | Code |
|--------------------------|--------|------|
| Conceptual Understanding | 40%    | CU   |
| Approach & Method        | 20%    | AM   |
| Step-by-Step Execution   | 20%    | SS   |
| Numerical Accuracy       | 10%    | NA   |
| Presentation & Clarity   | 10%    | PR   |

**Per-dimension score is strictly one of: 0, 0.5, 1**  (0 = absent, 0.5 = partial, 1 = full).
**Per-question weighted score = 0.40·CU + 0.20·AM + 0.20·SS + 0.10·NA + 0.10·PR  ∈ [0,1].**

You must return a single JSON object (no markdown fences, no commentary outside JSON) with the schema:

{
  "topic": "Domain of Functions",
  "topic_breadcrumb": "Mathematics · Differential Calculus · Functions · Domain",

  "questions": [
    {
      "number": 1,
      "topic": "Square root + Log on x²",
      "function_latex": "$f(x) = \\\\sqrt{\\\\log_{16}(x^2)}$",
      "your_answer": "$x \\\\in (-\\\\infty, -1] \\\\cup [1, \\\\infty)$",
      "expected_answer": "$x \\\\in (-\\\\infty, -1] \\\\cup [1, \\\\infty)$",
      "dimensions": {
        "concept_understanding": {"score": 1.0, "comment": "..."},
        "approach_method":       {"score": 1.0, "comment": "..."},
        "step_by_step":          {"score": 1.0, "comment": "..."},
        "numerical_accuracy":    {"score": 1.0, "comment": "..."},
        "presentation":          {"score": 1.0, "comment": "..."}
      },
      "feedback": "Specific, error-naming, growth-oriented paragraph (2-4 sentences) tied to this student's actual working — not generic.",
      "scan_quality": "Good",
      "scan_note": ""
    }
    // ... one entry per question in the answer key
  ],

  "concept_map": {
    "concepts": ["Constraint extraction", "Square root non-negativity", "Log argument positivity", "Denominator non-zero", "Inverse trig domain"],
    "matrix": [
      ["G","G","G","G","G"],
      ["G","N","G","G","N"],
      ["G","G","N","N","G"],
      ["N","N","G","N","N"],
      ["N","G","N","G","N"]
    ]
  },

  "swot": {
    "strengths":     [{"title": "Disciplined constraint extraction.", "evidence": "$R_1, R_2, R_3$ structure used consistently from Q1 to Q25..."}],
    "weaknesses":    [{"title": "Method-selection efficiency.",       "evidence": "Q21 was solved by case analysis - correct but..."}],
    "opportunities": [{"title": "Ready for graphical reasoning.",     "evidence": "..."}],
    "threats":       [{"title": "JEE Advanced has different stakes.", "evidence": "..."}]
  },

  "misconceptions": [
    {"title": "Confusing domain with codomain.", "evidence": "Q4, Q11", "wrong_model": "...", "correct_model": "..."}
  ],

  "improvements": [
    {"priority": 1, "label": "Critical",     "color": "tsRed",   "title": "Method-selection drill", "action": "...", "measure": "...", "by_when": "Within 1 week."},
    {"priority": 2, "label": "Important",    "color": "tsAmber", "title": "...",                    "action": "...", "measure": "...", "by_when": "..."},
    {"priority": 3, "label": "Nice to have", "color": "tsBlue",  "title": "...",                    "action": "...", "measure": "...", "by_when": "..."}
  ],

  "summary_box": "3-4 sentence plain-language summary aimed at a non-technical reader (parent/admin). Mention the score, the band, the headline strength, and the focus area for next sitting. No rubric jargon.",

  "closing_note": {
    "intro": "Direct, named address (use the student's first name once). 2-4 sentences acknowledging effort and what the score signals.",
    "what_signals": "1-2 sentences explaining what habits the score reflects (e.g., 'You've internalised the four habits that matter at JEE Advanced level: ...').",
    "next_steps": [
      {"label": "Next assignment", "text": "Concrete pointer — code + topic + suggested timing."},
      {"label": "Adjacent topic",  "text": "What to start studying alongside."},
      {"label": "Speed target",    "text": "Per-question pace target for the next tier."}
    ]
  }
}

GUIDELINES
- Use LaTeX inline math `$...$` everywhere a formula appears (function_latex, your_answer, expected_answer, comments, feedback, swot evidence). Use `\\\\mathbb{R}`, `\\\\cup`, `\\\\cap`, `\\\\geq`, `\\\\leq`, `\\\\in`, `\\\\sqrt{}`, `\\\\frac{}{}` etc.
- Concept-map matrix cells must be one of: "G" (green = full), "A" (amber = partial), "R" (red = failed), "N" (neutral grey = untested by that question).
- Concept-map matrix must be a list of rows where each row has exactly len(questions) cells. List 5–8 concepts that are genuinely tested across the paper.
- SWOT: each quadrant has 2–4 bullets. Every bullet anchored to specific Q-numbers when possible.
- Misconceptions: ONLY include if 2 or more questions exhibit the same conceptual error. If none, return an empty list `[]`.
- Improvements: ALWAYS exactly 3 priorities, ranked by impact. Each must have a concrete, measurable, time-bound action.
- Scan quality must be one of: "Excellent", "Good", "Acceptable", "Poor". Set "scan_note" only when scan_quality is "Acceptable" or "Poor".
- Feedback tone: specific, error-naming, growth-oriented. Address the student's actual working, not a generic template.
- Closing-note tone matches band: motivational for Trailblazer, constructive for Qualifier, honest-but-supportive for Developing, compassionate but direct for Foundational Gaps.
- DO NOT use em-dashes (—); use hyphens (-).
- Standard sets always rendered as `\\\\mathbb{R}`, `\\\\mathbb{Z}`, `\\\\mathbb{N}` in LaTeX.

If the student has not attempted a question, all five dimensions = 0, comments = "Not attempted", feedback = "Not attempted. <one-line note on what was expected and where to study>". Scan quality = "Good" (the page is fine; the question just wasn't answered).

If a question is illegible, set scan_quality = "Poor", scan_note describing the issue, and grade as best-effort (often 0 if you genuinely can't read it).

Be rigorous. Verify each step. Cross-check numerical answers."""


def encode_pdf(path: str) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def compute_weighted_score(dimensions: dict) -> float:
    weights = {
        "concept_understanding": 0.40,
        "approach_method":       0.20,
        "step_by_step":          0.20,
        "numerical_accuracy":    0.10,
        "presentation":          0.10,
    }
    return round(
        sum(dimensions[dim]["score"] * w for dim, w in weights.items()), 4
    )


def aggregate_dim_pct(questions: list, dim_key: str) -> int:
    if not questions:
        return 0
    avg = sum(q["dimensions"][dim_key]["score"] for q in questions) / len(questions)
    return int(round(avg * 100))


def pick_model(asgn_type: str) -> str:
    """Anthropic per-tier default (legacy; preserved for back-compat callers)."""
    return os.getenv(f"EVALUATOR_MODEL_{asgn_type}", "claude-sonnet-4-6")


def _default_model_for(provider: str, asgn_type: str) -> str:
    """Per-provider, per-tier default when the caller doesn't pass a model.

    Operators can override each via env vars:
        EVALUATOR_MODEL_<TYPE>           (anthropic)
        EVALUATOR_GEMINI_MODEL_<TYPE>    (gemini)
        EVALUATOR_OPENAI_MODEL_<TYPE>    (openai)
    """
    if provider == "anthropic":
        return os.getenv(f"EVALUATOR_MODEL_{asgn_type}", "claude-sonnet-4-6")
    if provider == "gemini":
        return os.getenv(f"EVALUATOR_GEMINI_MODEL_{asgn_type}", "gemini-2.5-pro")
    if provider == "openai":
        return os.getenv(f"EVALUATOR_OPENAI_MODEL_{asgn_type}", "gpt-4o")
    # Unknown provider — let the caller surface the issue.
    return "claude-sonnet-4-6"


def _user_instruction(meta: dict) -> str:
    return (
        f"Evaluate this submission rigorously and return the full JSON.\n"
        f"Student: {meta['student_name']}\n"
        f"Assignment: {meta['assignment_type']} {meta['assignment_code']}\n"
        f"Today: {date.today().isoformat()}\n"
    )


def _strip_json_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def make_tracking_id(asgn_type: str, asgn_code: str, student_name: str, eval_date: str) -> str:
    """e.g. TS-WA-DOM2-20260509-KVN-001"""
    initials = "".join(p[0] for p in student_name.split() if p)[:3].upper() or "STU"
    yyyymmdd = eval_date.replace("-", "")
    return f"TS-{asgn_type}-{asgn_code}-{yyyymmdd}-{initials}-001"


# ─────────────────────────────────────────────────────────────────────
# Provider dispatch — each call function returns raw JSON text. The
# top-level evaluate() then parses + enriches identically across
# providers so the report renderer sees a uniform shape.
# ─────────────────────────────────────────────────────────────────────


def _call_anthropic_vision(key_b64: str, sub_b64: str, meta: dict, model: str) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf", "data": key_b64},
                 "title": "Document 1: Answer Key"},
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf", "data": sub_b64},
                 "title": "Document 2: Student Submission"},
                {"type": "text", "text": _user_instruction(meta)},
            ],
        }],
    )
    return message.content[0].text


def _call_gemini_vision(
    key_bytes: bytes, sub_bytes: bytes, meta: dict, model: str
) -> str:
    # Lazy import — Phase-2 SDK; not required for Anthropic-only installs.
    try:
        from google import genai
        from google.genai import types as gtypes
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "google-genai not installed. Run "
            "`pip install -r requirements.txt` (or `pip install google-genai`) "
            "to enable Gemini routing."
        ) from exc

    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it via Settings · Credentials "
            "or set it directly in .env."
        )

    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=model,
        contents=[
            gtypes.Part.from_bytes(data=key_bytes, mime_type="application/pdf"),
            gtypes.Part.from_bytes(data=sub_bytes, mime_type="application/pdf"),
            _user_instruction(meta),
        ],
        config=gtypes.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            max_output_tokens=16000,
        ),
    )
    return response.text or ""


def _call_openai_vision(
    key_b64: str, sub_b64: str, meta: dict, model: str
) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "openai not installed. Run `pip install -r requirements.txt` "
            "(or `pip install openai`) to enable OpenAI routing."
        ) from exc

    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it via Settings · Credentials "
            "or set it directly in .env."
        )

    client = OpenAI(api_key=key)
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": "answer_key.pdf",
                        "file_data": f"data:application/pdf;base64,{key_b64}",
                    },
                    {
                        "type": "input_file",
                        "filename": "submission.pdf",
                        "file_data": f"data:application/pdf;base64,{sub_b64}",
                    },
                    {"type": "input_text", "text": _user_instruction(meta)},
                ],
            },
        ],
        max_output_tokens=16000,
        text={"format": {"type": "json_object"}},
    )
    # Newer SDKs expose .output_text as a convenience; fall back to
    # walking .output[*].content[*].text for older versions.
    raw = getattr(response, "output_text", None)
    if raw:
        return raw
    out: list[str] = []
    for item in getattr(response, "output", []) or []:
        for part in getattr(item, "content", []) or []:
            text = getattr(part, "text", None)
            if text:
                out.append(text)
    return "".join(out)


def evaluate(
    submission_path: str,
    answer_key_path: str,
    meta: dict,
    provider: str = "anthropic",
    model: str | None = None,
) -> dict:
    """Run the vision-based evaluation against the chosen provider.

    Backward compatible: legacy callers that don't pass provider/model
    keep getting the Anthropic per-tier default model. The frontend
    model-picker (Phase 2) is the new producer of (provider, model).
    """
    provider = (provider or "anthropic").lower()
    model = (model or "").strip() or _default_model_for(provider, meta["assignment_type"])

    if provider == "anthropic":
        key_b64 = encode_pdf(answer_key_path)
        sub_b64 = encode_pdf(submission_path)
        raw_text = _call_anthropic_vision(key_b64, sub_b64, meta, model)
    elif provider == "gemini":
        with open(answer_key_path, "rb") as f:
            key_bytes = f.read()
        with open(submission_path, "rb") as f:
            sub_bytes = f.read()
        raw_text = _call_gemini_vision(key_bytes, sub_bytes, meta, model)
    elif provider == "openai":
        key_b64 = encode_pdf(answer_key_path)
        sub_b64 = encode_pdf(submission_path)
        raw_text = _call_openai_vision(key_b64, sub_b64, meta, model)
    else:
        raise ValueError(
            f"Unknown LLM provider {provider!r}; expected one of "
            "'anthropic', 'gemini', 'openai'."
        )

    parsed = json.loads(_strip_json_fences(raw_text))

    # Recompute weighted scores for consistency
    total_earned = 0.0
    for q in parsed["questions"]:
        q["weighted_score"] = compute_weighted_score(q["dimensions"])
        total_earned += q["weighted_score"]
    n = len(parsed["questions"])
    max_score = float(n)
    pct = round((total_earned / max_score) * 100, 1) if max_score > 0 else 0.0

    band, band_color, fallback_verdict = band_for(pct)

    atype = meta["assignment_type"]
    qualifies_for = None
    if atype == "WA" and pct >= 60:
        qualifies_for = "QA"
    elif atype == "QA" and pct >= 75:
        qualifies_for = "AA"

    if qualifies_for:
        verdict = f"Qualifies for {qualifies_for}"
        promotion_text = f"Promoted to {qualifies_for}."
        threshold_label = "75%" if atype == "QA" else "60%"
        promotion_note = f"Threshold (≥{threshold_label}) cleared by {pct - (75 if atype=='QA' else 60):.1f} percentage points."
    else:
        verdict = fallback_verdict or f"Below {atype} promotion threshold"
        promotion_text = f"Stays at {atype} tier."
        target = "75%" if atype == "QA" else "60%"
        promotion_note = f"Score {pct:.1f}% — {target} required to advance."

    # Scan quality breakdown
    scan_buckets = {"Excellent": 0, "Good": 0, "Acceptable": 0, "Poor": 0}
    for q in parsed["questions"]:
        sq = q.get("scan_quality", "Good")
        if sq not in scan_buckets:
            sq = "Good"
        scan_buckets[sq] += 1

    eval_date = date.today().isoformat()
    tracking_id = make_tracking_id(atype, meta["assignment_code"], meta["student_name"], eval_date)

    result = {
        "student": {"name": meta["student_name"], "id": meta["student_id"]},
        "assignment": {
            "type": atype,
            "code": meta["assignment_code"],
            "title": meta.get("assignment_title", f"{atype} {meta['assignment_code']}"),
            "topic": parsed.get("topic", ""),
            "topic_breadcrumb": parsed.get("topic_breadcrumb", "Mathematics"),
        },
        "evaluation_date": eval_date,
        "summary": {
            "total_questions": n,
            "earned_score":    round(total_earned, 3),
            "max_score":       max_score,
            "percentage":      pct,
            "band":            band,
            "band_color":      band_color,
            "verdict":         verdict,
            "promotion_text":  promotion_text,
            "promotion_note":  promotion_note,
            "qualifies_for":   qualifies_for,
            "summary_box":     parsed.get("summary_box", ""),
            "scan_quality_breakdown": scan_buckets,
        },
        "rubric_aggregate": {
            "concept_understanding_pct": aggregate_dim_pct(parsed["questions"], "concept_understanding"),
            "approach_method_pct":       aggregate_dim_pct(parsed["questions"], "approach_method"),
            "step_by_step_pct":          aggregate_dim_pct(parsed["questions"], "step_by_step"),
            "numerical_accuracy_pct":    aggregate_dim_pct(parsed["questions"], "numerical_accuracy"),
            "presentation_pct":          aggregate_dim_pct(parsed["questions"], "presentation"),
        },
        "concept_map":    parsed.get("concept_map", {"concepts": [], "matrix": []}),
        "swot":           parsed.get("swot", {}),
        "misconceptions": parsed.get("misconceptions", []),
        "improvements":   parsed.get("improvements", []),
        "closing_note":   parsed.get("closing_note", {}),
        "questions":      parsed["questions"],
        "tracking_id":    tracking_id,
    }
    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/evaluate_pdf.py '<download_result_json>'", file=sys.stderr)
        sys.exit(1)

    load_dotenv(ENV_PATH)
    meta = json.loads(sys.argv[1])

    result = evaluate(
        submission_path=meta["submission_path"],
        answer_key_path=meta["answer_key_path"],
        meta=meta,
    )

    print(json.dumps(result, indent=2))

    base = os.path.splitext(meta["submission_path"])[0]
    eval_path = base + "_eval.json"
    with open(eval_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nEvaluation saved → {eval_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
