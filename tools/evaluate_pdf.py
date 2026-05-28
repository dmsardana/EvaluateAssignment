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
import re
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic
from dotenv import load_dotenv

from tools.tier_config import (
    get_pass_pct,
    is_terminal,
    promotes_to,
    tier_label,
)

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

**Per-dimension scoring rules (READ CAREFULLY — these are non-negotiable):**

- **CU, AM, SS, PR** — score is a **continuous real value in [0, 1] rounded to 2 decimals**.
  The full range is in play: 0.13, 0.27, 0.48, 0.62, 0.78, 0.91 are all valid.
  - DO NOT quantize to 0, 0.5, 1 buckets.
  - DO NOT quantize to 0.05 / 5-point steps (no 0.55, 0.60, 0.65, 0.70 pattern).
  - DO NOT default to "round" numbers — if your honest assessment is 0.62, write 0.62 not 0.60.
  - Calibrate against the JEE-Advanced subjective grading scale: every 0.01 difference
    should be defensible from the student's actual working.

- **NA — Numerical Accuracy — is binary per atomic numerical claim**, NOT continuous:
  - **Single-claim question** (one final answer / one number / one set):
    NA = **1.0 if exactly right, 0.0 if wrong**. No "small error" partial credit.
  - **Multi-part question** (e.g. domain + range; α + β; multiple bounds):
    NA = correct_parts / total_parts. So 1 of 2 = 0.5, 2 of 3 ≈ 0.67.
    The NA comment MUST declare which parts were treated as atomic and which were right.
  - Sign flips, transcription slips, wrong stated sets, branch errors → NA = 0.0.
  - Right process + wrong number costs NA (binary), not SS.

**Per-question weighted score = 0.40·CU + 0.20·AM + 0.20·SS + 0.10·NA + 0.10·PR  ∈ [0,1].**

You must return a single JSON object (no markdown fences, no commentary outside JSON) with the schema:

{
  "topic": "Domain of Functions",
  "topic_breadcrumb": "Mathematics · Differential Calculus · Functions · Domain",
  "paper_total_questions": 25,

  "questions": [
    {
      "number": 1,
      "topic": "Square root + Log on x²",
      "concept": "Square-root non-negativity",
      "difficulty": "D2",
      "learning_objective": "L2",
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
    // ... ONE ENTRY PER QUESTION IN THE ANSWER KEY — emit exactly paper_total_questions entries, in ascending order by `number`. If the student did not attempt a question, still emit the entry with all 5 dimensions.score=0, comments="Not attempted", your_answer="(blank)", feedback="Not attempted. <one-line study pointer>". NEVER omit unattempted questions — the percentage is computed against paper_total_questions, so missing entries silently inflate the score.
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

  "scan_quality_note": "1-2 sentences naming specific pages or questions whose scan quality hurt readability (thumb in frame, dim lighting, faded ink, page order). Leave empty string if scan was uniformly Excellent or Good.",

  "closing_note": {
    "intro": "Direct, named address (use the student's first name once). 2-4 sentences acknowledging effort and what the score signals.",
    "what_signals": "1-2 sentences explaining what habits the score reflects (e.g., 'You've internalised the four habits that matter at JEE Advanced level: ...').",
    "next_steps": [
      {"label": "Focus topic",    "text": "The single topic from THIS paper to drill next, with a concrete sub-skill to master."},
      {"label": "Adjacent topic", "text": "A related concept to start studying alongside, based on gaps in THIS paper."},
      {"label": "Speed target",   "text": "Per-question pace target to work towards in practice."}
    ]
  }
}

CLOSING-NOTE HARD RULES (violations cause the report to be regenerated):
- The "Where to go next" / next_steps section MUST NOT reference, name, hint at, or schedule any next assignment, upcoming assignment, previous assignment, prior assignment, assignment code, tier transition (e.g. WA->QA, QA->AA), or any sitting/timing of another assignment.
- No phrases like "next assignment", "upcoming", "previous", "last assignment", "before the next sitting", "by your next test", assignment codes (WA1, QA3, AA2, etc.), or due dates tied to assignments.
- Speak only about study focus derived from THIS paper. Frame guidance as habits, topics, and practice targets — never as cross-assignment instructions.
- The intro and what_signals fields are bound by the same rule.

GUIDELINES
- Classify `difficulty` and `learning_objective` from the QUESTION PAPER, not from the student's response. `concept` is the single specific idea the question primarily tests (a short noun phrase). Difficulty: D1=Easy / D2=Medium / D3=Difficult. Learning objective: L1=Recall, L2=Apply, L3=Relate/Analytical, L4=Create/Synthesise.
- Use LaTeX inline math `$...$` everywhere a formula appears (function_latex, your_answer, expected_answer, comments, feedback, swot evidence). Use `\\\\mathbb{R}`, `\\\\cup`, `\\\\cap`, `\\\\geq`, `\\\\leq`, `\\\\in`, `\\\\sqrt{}`, `\\\\frac{}{}` etc.
- JSON ESCAPE RULE — every backslash inside a JSON string MUST be doubled. Write `\\\\frac`, `\\\\sqrt`, `\\\\mathbb`, `\\\\circ`, `\\\\angle`, `\\\\int`, `\\\\sum` etc. A single `\\f`, `\\s`, `\\m`, `\\c`, `\\i` will fail strict JSON parsing and the whole evaluation is discarded.
- Concept-map matrix cells must be one of: "G" (green = full), "A" (amber = partial), "R" (red = failed), "N" (neutral grey = untested by that question).
- Concept-map matrix: list of rows. EACH ROW MUST CONTAIN EXACTLY total_questions CELLS — not 5, not 8, not 10. If the paper has 15 questions, every row must have 15 cells. If a concept is NOT exercised by a particular question, mark that cell "N" (neutral grey). Never truncate a row early. Before returning, verify that len(concept_map.matrix[i]) == total_questions for every row. The renderer drops trailing columns when rows are shorter, so users see only the first N columns and assume questions N+1…total were skipped. List 5–8 concepts that are genuinely tested across the paper.
- SWOT: each quadrant has 2–4 bullets. Every bullet anchored to specific Q-numbers when possible.
- Misconceptions: identify EVERY genuine conceptual gap — a wrong mental model, a confused definition, an invalid mechanical move (e.g., taking log of a negative, confusing domain vs codomain, applying a global property on a restricted domain, mistaking 0/0 for indeterminate when numerator is identically zero). Even a SINGLE question is enough if the error reveals a mental-model bug rather than an arithmetic slip. Each entry must include: title (one-line statement of the wrong model), evidence (Q-number + page anchor), wrong_model (what the student is thinking), correct_model (the right mental frame, 2–4 sentences with the corrective). Do NOT flag pure arithmetic / sign / transcription errors — those belong in question-level feedback, not here. If the student genuinely shows no conceptual gaps (rare; only when work is near-perfect and all errors are computational), return `[]`. Aim for 2–5 entries on a typical paper with mistakes.
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


from tools.usage_log import estimate_cost as _estimate_cost_usd, log_llm_call as _log_llm_call  # noqa: E402


def _normalize_concept_map(cm: dict, total_q: int) -> dict:
    """Pad every matrix row to total_q cells with 'N'. Defends the report
    renderer against models that emit short rows (observed: 5–8 cells when
    the paper has 15 questions, silently dropping the last 7 columns)."""
    concepts = list(cm.get("concepts") or [])
    matrix = list(cm.get("matrix") or [])
    normalized: list[list[str]] = []
    for row in matrix:
        row = list(row or [])
        if len(row) < total_q:
            row = row + ["N"] * (total_q - len(row))
        elif len(row) > total_q:
            row = row[:total_q]
        normalized.append(row)
    return {"concepts": concepts, "matrix": normalized}


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
    base = (
        f"Evaluate this submission rigorously and return the full JSON.\n"
        f"Student: {meta['student_name']}\n"
        f"Assignment: {meta['assignment_type']} {meta['assignment_code']}\n"
        f"Today: {date.today().isoformat()}\n"
    )
    corrective = meta.get("_corrective")
    if corrective:
        base += f"\nCORRECTION REQUIRED — {corrective}\n"
    return base


def _strip_json_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


# LaTeX-command detector: a backslash NOT preceded by another backslash and
# followed by two consecutive letters (\frac, \sqrt, \mathbb, \nabla, \beta).
# `\n` for a real newline is `\n` + whitespace/punct, never letter+letter, so
# we don't clobber legitimate JSON control escapes.
_LATEX_CMD_RE = re.compile(r'(?<!\\)\\([a-zA-Z])(?=[a-zA-Z])')

# Catches any remaining `\X` where X is not in the JSON escape set
# (e.g. \,  \!  \;  from LaTeX spacing commands).
_INVALID_ESC_RE = re.compile(r'(?<!\\)\\(?!["\\/bfnrtu]|u[0-9a-fA-F]{4})')


def _repair_json_escapes(raw: str) -> str:
    """Repair LaTeX-shaped JSON strings the LLM forgot to double-escape.

    Two passes:
      1. ``\\<letter><letter>`` → ``\\\\<letter><letter>`` (LaTeX commands).
         This catches ``\\frac`` / ``\\sqrt`` / ``\\mathbb`` which would
         otherwise parse silently as ``\\f`` (form feed) + ``rac`` etc.
      2. Any remaining ``\\X`` where X is not a valid JSON escape char is
         doubled (LaTeX spacing like ``\\,`` ``\\!`` ``\\;``).
    """
    raw = _LATEX_CMD_RE.sub(lambda m: '\\\\' + m.group(1), raw)
    raw = _INVALID_ESC_RE.sub(r'\\\\', raw)
    return raw


def _dump_raw_on_failure(raw: str, meta: dict, exc: Exception) -> str:
    """Persist the raw LLM payload for postmortem when JSON parse fails hard."""
    import datetime as _dt
    dbg_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "web", "api", "_eval_cache", "_raw",
    )
    os.makedirs(dbg_dir, exist_ok=True)
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    sid = (meta.get("student_id") or "unknown")[:24]
    code = (meta.get("assignment_code") or "X")
    path = os.path.join(dbg_dir, f"{ts}_{code}_{sid}.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# JSON parse failure: {exc}\n")
            f.write(f"# student={meta.get('student_name')} ({sid})\n")
            f.write(f"# assignment={meta.get('assignment_type')} {code}\n\n")
            f.write(raw)
    except OSError:
        pass
    return path


def _parse_llm_json(raw_text: str, meta: dict, *, retry_call=None) -> dict:
    """Robust JSON parse for LLM vision output.

    1. Try strict ``json.loads`` after stripping fences.
    2. On failure, repair invalid backslash escapes and retry.
    3. If a ``retry_call`` is supplied, ask the LLM to re-emit valid JSON once.
    4. If still failing, dump the raw payload and raise a clear error.
    """
    fenced = _strip_json_fences(raw_text)
    try:
        return json.loads(fenced)
    except json.JSONDecodeError as exc1:
        repaired = _repair_json_escapes(fenced)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as exc2:
            if retry_call is not None:
                try:
                    retry_raw = retry_call(
                        f"Your previous response could not be parsed as JSON: "
                        f"{exc2.msg} at line {exc2.lineno} col {exc2.colno}. "
                        f"Re-emit the SAME evaluation as strict JSON. Every "
                        f"backslash inside a string MUST be doubled (write "
                        f"\\\\frac, \\\\sqrt, \\\\mathbb — not \\frac)."
                    )
                    return json.loads(_repair_json_escapes(_strip_json_fences(retry_raw)))
                except (json.JSONDecodeError, Exception):
                    pass
            path = _dump_raw_on_failure(fenced, meta, exc2)
            raise json.JSONDecodeError(
                f"{exc2.msg} (raw payload saved to {path})",
                exc2.doc, exc2.pos,
            ) from exc2


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


_ANTHROPIC_FILES_BETA = "files-api-2025-04-14"


def _anthropic_upload(client, path: str):
    """Upload a PDF via the Anthropic Files API and return its file_id.

    Using Files API avoids the ~32 MB inline-request size cap that base64
    PDFs blow past on large scanned submissions (413 RequestTooLarge).
    """
    with open(path, "rb") as fh:
        uploaded = client.beta.files.upload(
            file=(os.path.basename(path), fh, "application/pdf"),
            extra_headers={"anthropic-beta": _ANTHROPIC_FILES_BETA},
        )
    return uploaded.id


def _call_anthropic_vision(
    answer_key_path: str, submission_path: str, meta: dict, model: str
) -> tuple[str, dict]:
    # Stream the response — long vision calls (>60s) exceed the SDK's default
    # read-timeout in non-stream mode. Anthropic recommends streaming for any
    # request that may run beyond ~60s; see
    # https://docs.anthropic.com/en/api/errors#long-requests
    client = anthropic.Anthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_retries=1,
        timeout=600.0,
    )

    key_file_id = _anthropic_upload(client, answer_key_path)
    sub_file_id = _anthropic_upload(client, submission_path)

    try:
        with client.messages.stream(
            model=model,
            max_tokens=32000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document",
                     "source": {"type": "file", "file_id": key_file_id},
                     "title": "Document 1: Answer Key"},
                    {"type": "document",
                     "source": {"type": "file", "file_id": sub_file_id},
                     "title": "Document 2: Student Submission"},
                    {"type": "text", "text": _user_instruction(meta)},
                ],
            }],
            extra_headers={"anthropic-beta": _ANTHROPIC_FILES_BETA},
        ) as stream:
            final = stream.get_final_message()
        usage = {
            "input_tokens":  getattr(final.usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(final.usage, "output_tokens", 0) or 0,
            "model":         model,
            "provider":      "anthropic",
        }
        return final.content[0].text, usage
    finally:
        # Best-effort cleanup; Anthropic auto-expires files but we don't
        # want orphans piling up under the org account.
        for fid in (key_file_id, sub_file_id):
            try:
                client.beta.files.delete(
                    fid,
                    extra_headers={"anthropic-beta": _ANTHROPIC_FILES_BETA},
                )
            except Exception:
                pass


def _call_gemini_vision(
    key_bytes: bytes, sub_bytes: bytes, meta: dict, model: str
) -> tuple[str, dict]:
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
    um = getattr(response, "usage_metadata", None)
    usage = {
        "input_tokens":  getattr(um, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(um, "candidates_token_count", 0) or 0,
        "model":         model,
        "provider":      "gemini",
    }
    return (response.text or ""), usage


def _call_openai_vision(
    key_b64: str, sub_b64: str, meta: dict, model: str
) -> tuple[str, dict]:
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
    ou = getattr(response, "usage", None)
    usage = {
        "input_tokens":  getattr(ou, "input_tokens", 0) or getattr(ou, "prompt_tokens", 0) or 0,
        "output_tokens": getattr(ou, "output_tokens", 0) or getattr(ou, "completion_tokens", 0) or 0,
        "model":         model,
        "provider":      "openai",
    }
    raw = getattr(response, "output_text", None)
    if raw:
        return raw, usage
    out: list[str] = []
    for item in getattr(response, "output", []) or []:
        for part in getattr(item, "content", []) or []:
            text = getattr(part, "text", None)
            if text:
                out.append(text)
    return "".join(out), usage


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

    # Wall-clock stopwatch — covers the LLM call(s) AND every CPU step
    # (parsing, repair, concept-map normalization, scoring) up to the
    # _log_llm_call below. That's what the operator means by "how long
    # did this submission take to evaluate".
    _eval_started_at = time.monotonic()

    retry_call = None
    usage_records: list[dict] = []
    if provider == "anthropic":
        raw_text, _usage = _call_anthropic_vision(
            answer_key_path, submission_path, meta, model
        )
        usage_records.append(_usage)
        def retry_call(corrective: str) -> str:
            text, u = _call_anthropic_vision(
                answer_key_path,
                submission_path,
                {**meta, "_corrective": corrective},
                model,
            )
            usage_records.append(u)
            return text
    elif provider == "gemini":
        with open(answer_key_path, "rb") as f:
            key_bytes = f.read()
        with open(submission_path, "rb") as f:
            sub_bytes = f.read()
        raw_text, _g_usage = _call_gemini_vision(key_bytes, sub_bytes, meta, model)
        usage_records.append(_g_usage)
    elif provider == "openai":
        key_b64 = encode_pdf(answer_key_path)
        sub_b64 = encode_pdf(submission_path)
        raw_text, _o_usage = _call_openai_vision(key_b64, sub_b64, meta, model)
        usage_records.append(_o_usage)
    else:
        raise ValueError(
            f"Unknown LLM provider {provider!r}; expected one of "
            "'anthropic', 'gemini', 'openai'."
        )

    parsed = _parse_llm_json(raw_text, meta, retry_call=retry_call)

    # ── Determine paper_total_questions (denominator for pct) ───────────────
    # Priority: explicit field from model → max question.number → len(questions).
    # The denominator must be the PAPER total (e.g. 40), not just attempted (29),
    # otherwise a student who skips half the paper still posts a 94% score.
    qlist = parsed.get("questions") or []
    paper_total = parsed.get("paper_total_questions")
    if not isinstance(paper_total, int) or paper_total <= 0:
        max_num = max((q.get("number") or 0 for q in qlist), default=0)
        paper_total = max(max_num, len(qlist))
    parsed["paper_total_questions"] = paper_total

    # Pad missing questions (model didn't emit unattempted entries) so the
    # template can render a complete per-question section.
    present_nums = {q.get("number") for q in qlist if q.get("number")}
    for n_missing in range(1, paper_total + 1):
        if n_missing not in present_nums:
            qlist.append({
                "number": n_missing,
                "topic": "",
                "function_latex": "",
                "your_answer": "(blank)",
                "expected_answer": "",
                "dimensions": {
                    "concept_understanding": {"score": 0.0, "comment": "Not attempted."},
                    "approach_method":       {"score": 0.0, "comment": "Not attempted."},
                    "step_by_step":          {"score": 0.0, "comment": "Not attempted."},
                    "numerical_accuracy":    {"score": 0.0, "comment": "Not attempted."},
                    "presentation":          {"score": 0.0, "comment": "Not attempted."},
                },
                "feedback": "Not attempted.",
                "scan_quality": "Good",
                "scan_note": "",
            })
    qlist.sort(key=lambda q: q.get("number") or 0)
    parsed["questions"] = qlist

    # Recompute weighted scores for consistency
    total_earned = 0.0
    attempted_count = 0
    for q in parsed["questions"]:
        q["weighted_score"] = compute_weighted_score(q["dimensions"])
        total_earned += q["weighted_score"]
        if q["weighted_score"] > 0 or "Not attempted" not in (q.get("feedback") or ""):
            attempted_count += 1
    n = paper_total
    max_score = float(n)
    pct = round((total_earned / max_score) * 100, 1) if max_score > 0 else 0.0

    band, band_color, fallback_verdict = band_for(pct)

    # Promotion logic — derived entirely from tier_config so new tiers
    # (e.g. GA terminal, ZA → AA) require zero changes here.
    atype = meta["assignment_type"]
    next_tier = promotes_to(atype)               # None for terminal tiers
    cutoff = get_pass_pct(atype)                  # None for AA (no cutoff)
    qualifies_for: str | None = None
    if next_tier and cutoff is not None and pct >= cutoff:
        qualifies_for = next_tier

    if qualifies_for:
        verdict = f"Qualifies for {qualifies_for}"
        promotion_text = f"Promoted to {qualifies_for}."
        promotion_note = (
            f"Threshold (≥{cutoff}%) cleared by "
            f"{pct - cutoff:.1f} percentage points."
        )
    elif is_terminal(atype):
        # Terminal tier (AA, GA, …): grade exists but there's nothing to
        # promote to. Don't mislead the student with "below threshold".
        label = tier_label(atype)
        verdict = fallback_verdict or f"{label} - feedback only"
        promotion_text = f"{label} assignment - no tier promotion."
        if cutoff is not None:
            mark = "Above" if pct >= cutoff else "Below"
            promotion_note = (
                f"Score {pct:.1f}% - {mark} the informational pass mark of {cutoff}%."
            )
        else:
            promotion_note = f"Score {pct:.1f}% - this is a terminal tier."
    else:
        # Non-terminal tier but below cutoff: stays at this tier.
        verdict = fallback_verdict or f"Below {atype} promotion threshold"
        promotion_text = f"Stays at {atype} tier."
        if cutoff is not None:
            promotion_note = (
                f"Score {pct:.1f}% - {cutoff}% required to advance to {next_tier}."
            )
        else:
            promotion_note = f"Score {pct:.1f}%."

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
            "total_questions":     n,
            "attempted_questions": attempted_count,
            "earned_score":        round(total_earned, 3),
            "max_score":           max_score,
            "percentage":          pct,
            "band":            band,
            "band_color":      band_color,
            "verdict":         verdict,
            "promotion_text":  promotion_text,
            "promotion_note":  promotion_note,
            "qualifies_for":   qualifies_for,
            "summary_box":     parsed.get("summary_box", ""),
            "scan_quality_breakdown": scan_buckets,
            "scan_quality_note": parsed.get("scan_quality_note", ""),
        },
        "rubric_aggregate": {
            "concept_understanding_pct": aggregate_dim_pct(parsed["questions"], "concept_understanding"),
            "approach_method_pct":       aggregate_dim_pct(parsed["questions"], "approach_method"),
            "step_by_step_pct":          aggregate_dim_pct(parsed["questions"], "step_by_step"),
            "numerical_accuracy_pct":    aggregate_dim_pct(parsed["questions"], "numerical_accuracy"),
            "presentation_pct":          aggregate_dim_pct(parsed["questions"], "presentation"),
        },
        "concept_map":    _normalize_concept_map(parsed.get("concept_map") or {"concepts": [], "matrix": []}, total_q=len(parsed["questions"])),
        "swot":           parsed.get("swot", {}),
        "misconceptions": parsed.get("misconceptions", []),
        "improvements":   parsed.get("improvements", []),
        "closing_note":   parsed.get("closing_note", {}),
        "questions":      parsed["questions"],
        "tracking_id":    tracking_id,
    }

    # ── Usage + cost tracking ─────────────────────────────────────────────
    sub_bytes = os.path.getsize(submission_path) if os.path.exists(submission_path) else 0
    ak_bytes = os.path.getsize(answer_key_path) if os.path.exists(answer_key_path) else 0
    total_in = sum(u.get("input_tokens", 0) for u in usage_records)
    total_out = sum(u.get("output_tokens", 0) for u in usage_records)
    cost_usd = _estimate_cost_usd(model, total_in, total_out)
    duration_seconds = round(time.monotonic() - _eval_started_at, 2)
    usage_summary = {
        "provider": provider,
        "model": model,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cost_usd_est": cost_usd,
        "duration_seconds": duration_seconds,
        "calls": usage_records,
        "submission_bytes": sub_bytes,
        "submission_kb": round(sub_bytes / 1024, 1),
        "answer_key_bytes": ak_bytes,
        "answer_key_kb": round(ak_bytes / 1024, 1),
    }
    result["usage"] = usage_summary

    # One JSONL line per fresh evaluation (skipped when cached). All other
    # LLM call sites also route through tools.usage_log.log_llm_call.
    _log_llm_call(
        provider=provider,
        model=model,
        input_tokens=total_in,
        output_tokens=total_out,
        purpose="evaluation",
        student_id=meta.get("student_id"),
        student_name=meta.get("student_name"),
        assignment_type=atype,
        assignment_code=meta.get("assignment_code"),
        coursework_id=meta.get("coursework_id"),
        submission_bytes=sub_bytes,
        submission_kb=usage_summary["submission_kb"],
        answer_key_bytes=ak_bytes,
        n_calls=len(usage_records),
        duration_seconds=duration_seconds,
    )
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
