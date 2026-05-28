"""
Generate an answer key + concise solution set for a Google Classroom assignment.

For each unprocessed coursework whose assignment_type is WA/QA/AA:
  1. Pull the question paper PDF from Classroom 'materials' attachments
  2. Send to Claude with a structured prompt
  3. Render two-section LaTeX (Concise + Detailed) → PDF via tectonic
  4. Upload PDF as {TYPE}_{CODE}_KEY.pdf to Drive answer_keys/
  5. Send review email to TEACHER_EMAIL with PDF attachment + OTP
  6. Save state to answer_key_state.json on Drive

Usage:
    python tools/generate_answer_key.py                 # process all pending
    python tools/generate_answer_key.py <coursework_id> # single coursework
    python tools/generate_answer_key.py --regen <coursework_id>  # rerun with rework flags
"""

import base64
import io
import json
import os
import re
import secrets
import string
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic
import jinja2
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "answer_key_template.tex")
KEYS_TMP = os.path.join(os.path.dirname(__file__), "..", ".tmp", "keys")

GENERATION_PROMPT = """You are an expert mathematics teacher with deep JEE Advanced experience. You are creating a definitive answer key and solution set for a student assignment.

You have been given the question paper (PDF). For EVERY question in the paper:

1. Identify the question text precisely.
2. State the conceptual approach.
3. Provide a complete, rigorous step-by-step solution using LaTeX inline math (e.g. $\\frac{a+b}{c}$, $\\int_0^1 x^2 dx$).
4. Give the final answer clearly.
5. Note common mistakes students typically make.
6. Write a CONCISE version (one or two sentences capturing key steps + final answer) for teacher quick-reference.

RULES:
- Be mathematically rigorous. Show every algebraic and arithmetic step.
- Use LaTeX inline math for ALL formulas: $...$ for inline, $$...$$ for display.
- Do NOT use markdown bold/italic; the consumer is LaTeX.
- For multi-part questions, treat each part as a separate "question" entry.
- Difficulty must be one of: "Easy", "Medium", "Hard", "JEE Advanced".
- For paragraph/step breaks inside string fields use a real newline character in the JSON (i.e. \n with a SINGLE backslash, which json.loads to a 0x0A newline). Do NOT write `\\n` (double-backslash + n) — that produces a literal `\n` which LaTeX treats as an undefined control sequence.

Return ONLY a valid JSON object (no markdown fences, no explanation) with this exact shape:
{
  "questions": [
    {
      "number": 1,
      "question_text": "Find the domain of f(x) = ...",
      "difficulty": "Medium",
      "approach": "Identify constraints from each component...",
      "solution": "We need both $\\\\sqrt{x-1}$ defined and $\\\\frac{1}{x-3} \\\\neq 0$. Step 1: ... Step 2: ...",
      "final_answer": "$x \\\\in [1, 3) \\\\cup (3, \\\\infty)$",
      "concise": "Combine domain constraints; exclude points where denominator is zero. Answer: $x \\\\in [1,3) \\\\cup (3,\\\\infty)$.",
      "common_mistakes": "Forgetting to exclude $x=3$ from the domain."
    }
  ]
}"""

REGEN_PROMPT_PREFIX = """You previously generated answer-key entries for this question paper. The teacher reviewed and asked you to RE-DO the following question numbers because they had issues:

QUESTIONS TO REDO: {qnums}

Please re-solve ONLY those questions. For all others, return the existing entry unchanged. Apply extra rigor on the questions being redone.

PREVIOUS OUTPUT:
{prev_json}

"""


# ── Jinja2 + LaTeX ──────────────────────────────────────────────────────────────
_LATEX_ESCAPE_MAP = {
    "&": r"\&", "%": r"\%", "#": r"\#",
    "_": r"\_",
}
_LATEX_ESCAPE_RE = re.compile(
    "|".join(re.escape(k) for k in _LATEX_ESCAPE_MAP)
)


_UNICODE_MATH_MAP = {
    "²": r"$^{2}$", "³": r"$^{3}$", "⁴": r"$^{4}$", "⁵": r"$^{5}$",
    "⁶": r"$^{6}$", "⁷": r"$^{7}$", "⁸": r"$^{8}$", "⁹": r"$^{9}$",
    "⁰": r"$^{0}$", "¹": r"$^{1}$",
    "₀": r"$_{0}$", "₁": r"$_{1}$", "₂": r"$_{2}$", "₃": r"$_{3}$",
    "₄": r"$_{4}$", "₅": r"$_{5}$", "₆": r"$_{6}$", "₇": r"$_{7}$",
    "₈": r"$_{8}$", "₉": r"$_{9}$",
    "≤": r"$\leq$", "≥": r"$\geq$", "≠": r"$\neq$", "≈": r"$\approx$",
    "→": r"$\rightarrow$", "←": r"$\leftarrow$", "⇒": r"$\Rightarrow$",
    "⇐": r"$\Leftarrow$", "↔": r"$\leftrightarrow$",
    "×": r"$\times$", "÷": r"$\div$", "·": r"$\cdot$",
    "∞": r"$\infty$", "∑": r"$\sum$", "∫": r"$\int$",
    "∂": r"$\partial$", "∇": r"$\nabla$",
    "π": r"$\pi$", "α": r"$\alpha$", "β": r"$\beta$", "γ": r"$\gamma$",
    "δ": r"$\delta$", "θ": r"$\theta$", "λ": r"$\lambda$", "μ": r"$\mu$",
    "σ": r"$\sigma$", "φ": r"$\phi$", "ω": r"$\omega$", "Δ": r"$\Delta$",
    "Σ": r"$\Sigma$", "Ω": r"$\Omega$", "°": r"$^{\circ}$",
    "±": r"$\pm$", "∓": r"$\mp$", "∈": r"$\in$", "∉": r"$\notin$",
    "⊂": r"$\subset$", "⊃": r"$\supset$", "∪": r"$\cup$", "∩": r"$\cap$",
}
_UNICODE_MATH_RE = re.compile("|".join(re.escape(k) for k in _UNICODE_MATH_MAP))


_LITERAL_ESC_RE = re.compile(r"\\([ntr])(?![a-zA-Z])")


def latex_escape(text: str) -> str:
    """Conservative escape — DO NOT escape $, {, }, \\ since solutions contain LaTeX math.
    Also converts common unicode math symbols to LaTeX equivalents so the
    model can't accidentally emit a bare ² or → outside $...$.
    Also normalizes literal \\n / \\t / \\r escape sequences (model emits these
    via double-escaped JSON like "\\\\n") to real whitespace — otherwise LaTeX
    sees \\n as an undefined control sequence."""
    s = str(text or "")
    s = _LITERAL_ESC_RE.sub(lambda m: {"n": "\n\n", "t": "  ", "r": ""}[m.group(1)], s)
    s = _UNICODE_MATH_RE.sub(lambda m: _UNICODE_MATH_MAP[m.group()], s)
    return _LATEX_ESCAPE_RE.sub(lambda m: _LATEX_ESCAPE_MAP[m.group()], s)


def latex_sanitize(text: str) -> str:
    """Gentle pass for math-bearing fields (solution, concise, final_answer,
    approach, question_text). Does NOT escape $/{/}/_/\\ because these fields
    legitimately contain raw LaTeX. Only:
      - normalizes literal \\n, \\t, \\r to real whitespace,
      - converts common unicode math symbols to LaTeX equivalents,
      - balances $ count by appending a closing $ if odd."""
    s = str(text or "")
    s = _LITERAL_ESC_RE.sub(lambda m: {"n": "\n\n", "t": "  ", "r": ""}[m.group(1)], s)
    s = _UNICODE_MATH_RE.sub(lambda m: _UNICODE_MATH_MAP[m.group()], s)
    unescaped = re.findall(r"(?<!\\)\$", s)
    if len(unescaped) % 2 == 1:
        s = s + " $"
    return s


def build_jinja_env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(os.path.dirname(TEMPLATE_PATH)),
        block_start_string="((*",
        block_end_string="*))",
        variable_start_string="((((",
        variable_end_string="))))",
        comment_start_string="((#",
        comment_end_string="#))",
        undefined=jinja2.StrictUndefined,
    )
    env.filters["latex_escape"] = latex_escape
    env.filters["latex_sanitize"] = latex_sanitize
    return env


def compile_latex(tex_source: str, output_dir: str, base_name: str) -> str:
    import subprocess
    import tempfile
    import shutil

    engine = os.getenv("PDFLATEX_PATH", "tectonic")
    is_tectonic = "tectonic" in os.path.basename(engine).lower()
    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, f"{base_name}.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_source)

        if is_tectonic:
            cmd = [engine, "--keep-logs", "--outdir", tmpdir, tex_path]
        else:
            cmd = [engine, "-interaction=nonstopmode", "-output-directory", tmpdir, tex_path]

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=tmpdir)
        if result.returncode != 0:
            log_path = os.path.join(tmpdir, f"{base_name}.log")
            log = open(log_path).read()[-3000:] if os.path.exists(log_path) else ""
            # Persist the failing .tex + .log so the actual broken macro
            # can be inspected (the tmpdir vanishes when this function
            # returns). Lives next to the keys output dir.
            dbg_dir = os.path.join(os.path.dirname(output_dir), "_failed_ak")
            try:
                os.makedirs(dbg_dir, exist_ok=True)
                from datetime import datetime as _dt
                ts = _dt.now().strftime("%Y%m%dT%H%M%S")
                shutil.copy2(tex_path, os.path.join(dbg_dir, f"{ts}_{base_name}.tex"))
                if os.path.exists(log_path):
                    shutil.copy2(log_path, os.path.join(dbg_dir, f"{ts}_{base_name}.log"))
                dbg_hint = f" (saved to {dbg_dir}/{ts}_{base_name}.{{tex,log}})"
            except Exception:
                dbg_hint = ""
            raise RuntimeError(
                f"LaTeX compile failed{dbg_hint}:\n{result.stderr}\n--LOG--\n{log}"
            )

        compiled = os.path.join(tmpdir, f"{base_name}.pdf")
        dest = os.path.join(output_dir, f"{base_name}.pdf")
        shutil.copy2(compiled, dest)
    return dest


# ── Classroom + Drive helpers ───────────────────────────────────────────────────
def get_creds():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    token_path = os.path.join(os.path.dirname(__file__), "..", "token.json")
    from tools.setup_drive import SCOPES
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def get_question_paper_pdf(drive, classroom, course_id: str, coursework_id: str) -> bytes:
    """Pull the first PDF attachment from a coursework's materials."""
    cw = classroom.courses().courseWork().get(
        courseId=course_id, id=coursework_id
    ).execute()
    materials = cw.get("materials", [])
    pdf_id = None
    for m in materials:
        if "driveFile" in m:
            df = m["driveFile"]["driveFile"]
            if df.get("title", "").lower().endswith(".pdf"):
                pdf_id = df["id"]
                break
    if not pdf_id:
        raise ValueError(f"No PDF attached to coursework {coursework_id}")

    request = drive.files().get_media(fileId=pdf_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def upload_pdf_to_drive(drive, folder_id: str, local_path: str, dest_name: str) -> str:
    # Remove any existing file with the same name
    query = f"name='{dest_name}' and '{folder_id}' in parents and trashed=false"
    existing = drive.files().list(q=query, fields="files(id)").execute().get("files", [])
    for f in existing:
        drive.files().delete(fileId=f["id"]).execute()

    metadata = {"name": dest_name, "parents": [folder_id]}
    media = MediaFileUpload(local_path, mimetype="application/pdf", resumable=True)
    uploaded = drive.files().create(
        body=metadata, media_body=media, fields="id"
    ).execute()
    return uploaded["id"]


# ── Claude generation ──────────────────────────────────────────────────────────
def pick_model(asgn_type: str) -> str:
    return os.getenv(f"EVALUATOR_MODEL_{asgn_type}", "claude-sonnet-4-6")


def _drop_truncated_questions(solutions: dict) -> dict:
    """Drop questions missing required fields — protects the LaTeX template
    from accessing q.final_answer / q.solution on stubs left behind when
    the LLM hit max_tokens mid-question. Emits a warning to stderr so the
    operator knows the AK is incomplete."""
    required = ("question_text", "solution", "final_answer")
    qs = solutions.get("questions") or []
    kept, dropped = [], []
    for q in qs:
        if all(q.get(k) for k in required):
            kept.append(q)
        else:
            dropped.append(q.get("number"))
    if dropped:
        import sys as _sys
        _sys.stderr.write(
            f"  [AK] WARNING: dropping {len(dropped)} truncated question(s) "
            f"(no final_answer/solution): {dropped}\n"
        )
    solutions["questions"] = kept
    return solutions


def generate_solutions(question_pdf_bytes: bytes, asgn_type: str,
                       redo_q_nums: list[int] | None = None,
                       prev_questions: list[dict] | None = None) -> dict:
    # Stream the response. A 15-question answer key easily fills 15K+
    # output tokens; the old non-streaming call with max_tokens=8192
    # was truncating mid-JSON and crashing with "Unterminated string".
    # Anthropic recommends streaming for any call that may run >60s
    # (see https://docs.anthropic.com/en/api/errors#long-requests).
    client = anthropic.Anthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_retries=1,
        timeout=600.0,
    )
    model = pick_model(asgn_type)

    pdf_b64 = base64.standard_b64encode(question_pdf_bytes).decode("utf-8")

    prompt = GENERATION_PROMPT
    if redo_q_nums and prev_questions:
        prev_json = json.dumps({"questions": prev_questions}, indent=2)
        prompt = REGEN_PROMPT_PREFIX.format(
            qnums=", ".join(str(n) for n in redo_q_nums),
            prev_json=prev_json,
        ) + GENERATION_PROMPT

    with client.messages.stream(
        model=model,
        max_tokens=60000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                    "title": "Question Paper",
                },
                {"type": "text", "text": prompt},
            ],
        }],
    ) as stream:
        final = stream.get_final_message()

    from tools.usage_log import log_llm_call
    log_llm_call(
        provider="anthropic",
        model=model,
        input_tokens=getattr(final.usage, "input_tokens", 0) or 0,
        output_tokens=getattr(final.usage, "output_tokens", 0) or 0,
        purpose="ak_generation",
        assignment_type=asgn_type,
        question_pdf_bytes=len(question_pdf_bytes),
        is_regen=bool(redo_q_nums),
    )

    raw = final.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    # Try plain parse first; if the model emitted bad escapes (a LaTeX
    # backslash that wasn't doubled), repair and retry. On a final
    # failure, persist the raw payload to .tmp/_raw_ak/ for postmortem
    # — the surfaced error message includes the path so an operator
    # can inspect what the model actually produced.
    try:
        return _drop_truncated_questions(json.loads(raw))
    except json.JSONDecodeError:
        pass

    # LaTeX-command detector — same heuristic as tools/evaluate_pdf.py.
    import re as _re
    _LATEX_CMD_RE = _re.compile(r'(?<!\\)\\([a-zA-Z])(?=[a-zA-Z])')
    _INVALID_ESC_RE = _re.compile(r'(?<!\\)\\(?!["\\/bfnrtu]|u[0-9a-fA-F]{4})')
    repaired = _LATEX_CMD_RE.sub(lambda m: '\\\\' + m.group(1), raw)
    repaired = _INVALID_ESC_RE.sub(r'\\\\', repaired)
    try:
        return _drop_truncated_questions(json.loads(repaired))
    except json.JSONDecodeError as exc:
        # Last-ditch: json-repair handles the long tail (unescaped quotes
        # mid-string, trailing commas, unquoted keys, truncated tails)
        # that our regex pass misses on 32K-token outputs.
        try:
            import json_repair  # type: ignore
            return _drop_truncated_questions(json_repair.loads(repaired))
        except Exception:
            try:
                return _drop_truncated_questions(json_repair.loads(raw))
            except Exception:
                pass
        from datetime import datetime as _dt
        dbg_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".tmp", "_raw_ak",
        )
        os.makedirs(dbg_dir, exist_ok=True)
        ts = _dt.now().strftime("%Y%m%dT%H%M%S")
        path = os.path.join(dbg_dir, f"{ts}_{asgn_type}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# JSON parse failure: {exc}\n")
                f.write(f"# asgn_type={asgn_type}\n\n")
                f.write(raw)
        except OSError:
            path = "(could not write debug file)"
        raise json.JSONDecodeError(
            f"{exc.msg} (raw payload saved to {path})",
            exc.doc,
            exc.pos,
        ) from exc


def _fix_solutions_for_latex(
    question_pdf_bytes: bytes,
    solutions: dict,
    latex_error: str,
    model: str,
) -> dict:
    """Self-healing retry: when compile_latex fails, send the bad solutions
    JSON + the LaTeX error back to the model and ask it to return a fixed
    JSON. The sanitize filters catch the common patterns; this catches the
    long tail (missing braces, undefined commands, stray ^ in text, etc.)."""
    client = anthropic.Anthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_retries=1,
        timeout=600.0,
    )
    pdf_b64 = base64.standard_b64encode(question_pdf_bytes).decode("utf-8")
    prev_json = json.dumps(solutions, indent=2)
    err_tail = latex_error[-2000:]
    prompt = f"""The previous JSON solution set produced LaTeX that fails to compile with this error:

{err_tail}

Common causes (fix all of them across EVERY question):
- Unbalanced $...$ delimiters — count of $ must be even within each string field.
- Bare ^ or _ outside math mode (wrap in $...$).
- Literal \\n inside a string — in JSON use a single backslash + n which json.loads collapses to a real newline.
- Undefined commands like \\cancel — remove or replace with a defined alternative.
- Missing closing brace in \\frac{{a}}{{b}}, \\sqrt{{x}}, etc.
- Spurious trailing $ at the end of a field.

Return the corrected JSON in the EXACT same shape (same keys, same number of questions). Do NOT add explanation. Return ONLY the JSON object.

PREVIOUS JSON:
{prev_json}
"""
    with client.messages.stream(
        model=model,
        max_tokens=60000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
                    "title": "Question Paper",
                },
                {"type": "text", "text": prompt},
            ],
        }],
    ) as stream:
        final = stream.get_final_message()
    from tools.usage_log import log_llm_call
    log_llm_call(
        provider="anthropic",
        model=model,
        input_tokens=getattr(final.usage, "input_tokens", 0) or 0,
        output_tokens=getattr(final.usage, "output_tokens", 0) or 0,
        purpose="ak_self_heal",
        question_pdf_bytes=len(question_pdf_bytes),
    )
    raw = final.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    try:
        return _drop_truncated_questions(json.loads(raw))
    except json.JSONDecodeError:
        import re as _re
        _LATEX_CMD_RE = _re.compile(r'(?<!\\)\\([a-zA-Z])(?=[a-zA-Z])')
        _INVALID_ESC_RE = _re.compile(r'(?<!\\)\\(?!["\\/bfnrtu]|u[0-9a-fA-F]{4})')
        repaired = _LATEX_CMD_RE.sub(lambda m: '\\\\' + m.group(1), raw)
        repaired = _INVALID_ESC_RE.sub(r'\\\\', repaired)
        try:
            return _drop_truncated_questions(json.loads(repaired))
        except json.JSONDecodeError:
            import json_repair  # type: ignore
            try:
                return _drop_truncated_questions(json_repair.loads(repaired))
            except Exception:
                return _drop_truncated_questions(json_repair.loads(raw))


# ── Email ──────────────────────────────────────────────────────────────────────
def generate_otp(length: int = 6) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def build_review_email(asgn_type: str, asgn_code: str, asgn_title: str,
                       n_questions: int, otp: str, model: str) -> tuple[str, str, str]:
    subject = f"[ACTION] Approve Answer Key: {asgn_type} {asgn_code} — OTP: {otp}"

    body_text = f"""Hi,

A new answer key has been generated and needs your review.

Assignment: {asgn_title}
Type:       {asgn_type}
Code:       {asgn_code}
Questions:  {n_questions}
Generated by: {model}

Approval OTP: {otp}

REPLY OPTIONS (include OTP in your reply):

  All approved:
      OK {otp}

  Selectively reprocess:
      Q3, Q5-7 reprocess {otp}
      (questions not listed are auto-approved)

The PDF answer key + concise solution set is attached.

— Assignment Evaluation System
"""

    body_html = f"""<html><body style="font-family:-apple-system,Helvetica,Arial,sans-serif;color:#222;max-width:640px;">
<h2 style="color:#0F4C81;margin-bottom:6px;">Approve Answer Key</h2>
<p style="color:#666;margin-top:0;">A new answer key has been generated and needs your review.</p>
<table style="border-collapse:collapse;margin:16px 0;">
  <tr><td style="padding:4px 12px;color:#666;">Assignment</td><td style="padding:4px 12px;"><b>{asgn_title}</b></td></tr>
  <tr><td style="padding:4px 12px;color:#666;">Type</td><td style="padding:4px 12px;">{asgn_type}</td></tr>
  <tr><td style="padding:4px 12px;color:#666;">Code</td><td style="padding:4px 12px;"><code>{asgn_code}</code></td></tr>
  <tr><td style="padding:4px 12px;color:#666;">Questions</td><td style="padding:4px 12px;">{n_questions}</td></tr>
  <tr><td style="padding:4px 12px;color:#666;">Model</td><td style="padding:4px 12px;">{model}</td></tr>
</table>
<div style="background:#f5f9ff;border-left:4px solid #0F4C81;padding:12px 16px;margin:16px 0;">
  <div style="color:#666;font-size:13px;">Approval OTP</div>
  <div style="font-size:22px;font-weight:700;letter-spacing:3px;color:#0F4C81;font-family:monospace;">{otp}</div>
</div>
<h3 style="color:#0F4C81;">How to reply</h3>
<p><b>All approved:</b> reply with</p>
<pre style="background:#f8f8f8;padding:8px;border-radius:4px;">OK {otp}</pre>
<p><b>Reprocess specific questions:</b> reply with</p>
<pre style="background:#f8f8f8;padding:8px;border-radius:4px;">Q3, Q5-7 reprocess {otp}</pre>
<p style="color:#888;font-size:13px;">Questions you don't list are automatically approved.</p>
<hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
<p style="color:#aaa;font-size:12px;">Assignment Evaluation System • Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</body></html>"""
    return subject, body_text, body_html


# ── Pipeline integration ───────────────────────────────────────────────────────
def process_coursework(
    course_id: str,
    coursework_id: str,
    assignment_type: str,
    assignment_code: str,
    assignment_title: str,
    drive,
    classroom,
    keys_folder_id: str,
    state: dict | None = None,
    redo_q_nums: list[int] | None = None,
    on_progress=None,
) -> dict:
    """Run AK generation for one coursework. Returns updated state entry.

    Parameter naming aligns with the rest of the codebase — callers use
    `assignment_type`, `assignment_code`, `assignment_title` (matching
    the dict keys produced by parse_assignment_meta and the Pydantic
    Tier model). `state` is optional: if None we load it from Drive so
    CLI and web callers share one entry point. `on_progress(stage, label)`
    lets the queue UI surface pipeline milestones.
    """
    from tools.email_helper import send_review_email
    from tools.review_state import load_state

    def _notify(stage: str, label: str | None = None) -> None:
        if on_progress is None:
            return
        try:
            on_progress(stage, label)
        except Exception:  # never let UI plumbing break the pipeline
            pass

    if state is None:
        state = load_state(drive, keys_folder_id) or {}

    print(f"  [AK] Pulling question paper for {assignment_type} {assignment_code}…")
    _notify("fetching_pdf")
    question_pdf = get_question_paper_pdf(drive, classroom, course_id, coursework_id)

    prev_entry = state.get(coursework_id, {})
    prev_questions = prev_entry.get("questions", []) if redo_q_nums else None

    print(f"  [AK] Generating solutions with {pick_model(assignment_type)}…")
    _notify("calling_llm", pick_model(assignment_type))
    solutions = generate_solutions(
        question_pdf, assignment_type,
        redo_q_nums=redo_q_nums, prev_questions=prev_questions,
    )

    otp = generate_otp()

    # Render LaTeX with self-healing retry: if compile fails, send the
    # error back to the model and ask it to fix the JSON. Up to 2 fix
    # attempts (3 total compile attempts).
    _notify("rendering_pdf")
    env = build_jinja_env()
    template = env.get_template("answer_key_template.tex")
    base = f"{assignment_type}_{assignment_code}_KEY"
    model_used = pick_model(assignment_type)
    last_err: Exception | None = None
    pdf_path = None
    for attempt in range(3):
        tex = template.render(
            assignment={"type": assignment_type, "code": assignment_code, "title": assignment_title},
            questions=solutions["questions"],
            generated_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            model=model_used,
            otp=otp,
        )
        try:
            pdf_path = compile_latex(tex, KEYS_TMP, base)
            break
        except RuntimeError as err:
            last_err = err
            if attempt == 2:
                raise
            print(f"  [AK] compile attempt {attempt+1} failed; asking model to fix…", flush=True)
            _notify("calling_llm", f"{model_used} (fix-up {attempt+1})")
            try:
                solutions = _fix_solutions_for_latex(
                    question_pdf, solutions, str(err), model_used,
                )
            except Exception as fix_err:  # noqa: BLE001
                raise RuntimeError(
                    f"Self-heal failed on attempt {attempt+1}: {fix_err}. "
                    f"Original LaTeX error: {err}"
                ) from fix_err
    if pdf_path is None:
        raise RuntimeError(f"LaTeX compile failed after 3 attempts: {last_err}")
    print(f"  [AK] PDF: {pdf_path}")

    # Upload to Drive
    _notify("uploading")
    drive_id = upload_pdf_to_drive(drive, keys_folder_id, pdf_path, f"{base}.pdf")
    print(f"  [AK] Uploaded to Drive: {drive_id}")

    # Send email
    _notify("emailing_teacher")
    teacher_email = os.getenv("TEACHER_EMAIL", "").strip()
    subject, body_text, body_html = build_review_email(
        assignment_type, assignment_code, assignment_title,
        len(solutions["questions"]), otp, pick_model(assignment_type),
    )
    sent = send_review_email(
        to_addr=teacher_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        attachment_path=pdf_path,
        attachment_name=f"{base}.pdf",
    )
    print(f"  [AK] Review email sent to {teacher_email} (thread {sent['threadId']})")

    # Build state entry
    n_q = len(solutions["questions"])
    questions_status = prev_entry.get("questions_status", ["pending"] * n_q)
    if redo_q_nums:
        # The redone questions move back to "pending"; others remain as-is
        for n in redo_q_nums:
            if 0 <= n - 1 < len(questions_status):
                questions_status[n - 1] = "pending"
    else:
        questions_status = ["pending"] * n_q

    return {
        "course_id": course_id,
        "coursework_id": coursework_id,
        "assignment_type": assignment_type,
        "assignment_code": assignment_code,
        "assignment_title": assignment_title,
        "status": "PENDING_REVIEW",
        "current_otp": otp,
        "thread_id": sent["threadId"],
        "regen_count": prev_entry.get("regen_count", 0) + (1 if redo_q_nums else 0),
        "questions": solutions["questions"],
        "questions_status": questions_status,
        "drive_pdf_id": drive_id,
        "model": pick_model(assignment_type),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    load_dotenv(ENV_PATH)
    creds = get_creds()
    drive = build("drive", "v3", credentials=creds)
    classroom = build("classroom", "v1", credentials=creds)

    keys_folder = os.getenv("DRIVE_KEYS_ID", "").strip()
    if not keys_folder:
        print("DRIVE_KEYS_ID not set.", file=sys.stderr)
        sys.exit(1)

    from tools.review_state import load_state, save_state
    state = load_state(drive, keys_folder)

    args = sys.argv[1:]
    regen_id = None
    target_id = None
    if "--regen" in args:
        i = args.index("--regen")
        regen_id = args[i + 1] if i + 1 < len(args) else None
        if not regen_id:
            print("--regen requires a coursework_id", file=sys.stderr)
            sys.exit(1)
    elif args:
        target_id = args[0]

    # Determine what to process
    if regen_id:
        entry = state.get(regen_id)
        if not entry:
            print(f"No state for coursework {regen_id}", file=sys.stderr)
            sys.exit(1)
        redo = [i + 1 for i, s in enumerate(entry["questions_status"]) if s == "needs_rework"]
        if not redo:
            print(f"No questions flagged for rework in {regen_id}", file=sys.stderr)
            sys.exit(0)
        print(f"Regenerating Q{redo} for {entry['assignment_type']} {entry['assignment_code']}")
        new_entry = process_coursework(
            entry["course_id"], entry["coursework_id"],
            entry["assignment_type"], entry["assignment_code"], entry["assignment_title"],
            drive, classroom, keys_folder, state, redo_q_nums=redo,
        )
        state[regen_id] = new_entry
        save_state(drive, keys_folder, state)
        return

    # Discover candidate courseworks
    from tools.watch_classroom import parse_assignment_meta
    course_ids = [c.strip() for c in os.getenv("CLASSROOM_COURSE_IDS", "").split(",") if c.strip()]
    candidates = []
    for course_id in course_ids:
        try:
            cw_resp = classroom.courses().courseWork().list(courseId=course_id).execute()
        except Exception:
            continue
        for cw in cw_resp.get("courseWork", []):
            atype, acode = parse_assignment_meta(cw.get("title", ""))
            if atype in ("UNKNOWN", "ZA"):
                continue
            cwid = cw["id"]
            if target_id and cwid != target_id:
                continue
            existing = state.get(cwid)
            if existing and existing.get("status") == "APPROVED":
                continue
            candidates.append((course_id, cwid, atype, acode, cw.get("title", "")))

    if not candidates:
        print("No pending coursework needs an answer key.", file=sys.stderr)
        return

    print(f"Processing {len(candidates)} coursework(s)…")
    for course_id, cwid, atype, acode, title in candidates:
        print(f"\n→ {atype} {acode} — {title}")
        try:
            new_entry = process_coursework(
                course_id, cwid, atype, acode, title,
                drive, classroom, keys_folder, state,
            )
            state[cwid] = new_entry
            save_state(drive, keys_folder, state)
        except Exception as e:
            print(f"  FAILED: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
