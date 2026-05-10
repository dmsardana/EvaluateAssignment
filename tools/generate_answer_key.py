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


def latex_escape(text: str) -> str:
    """Conservative escape — DO NOT escape $, {, }, \\ since solutions contain LaTeX math."""
    return _LATEX_ESCAPE_RE.sub(lambda m: _LATEX_ESCAPE_MAP[m.group()], str(text or ""))


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
            raise RuntimeError(
                f"LaTeX compile failed:\n{result.stderr}\n--LOG--\n{log}"
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


def generate_solutions(question_pdf_bytes: bytes, asgn_type: str,
                       redo_q_nums: list[int] | None = None,
                       prev_questions: list[dict] | None = None) -> dict:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    model = pick_model(asgn_type)

    pdf_b64 = base64.standard_b64encode(question_pdf_bytes).decode("utf-8")

    prompt = GENERATION_PROMPT
    if redo_q_nums and prev_questions:
        prev_json = json.dumps({"questions": prev_questions}, indent=2)
        prompt = REGEN_PROMPT_PREFIX.format(
            qnums=", ".join(str(n) for n in redo_q_nums),
            prev_json=prev_json,
        ) + GENERATION_PROMPT

    msg = client.messages.create(
        model=model,
        max_tokens=8192,
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
    )

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    return json.loads(raw)


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
def process_coursework(course_id: str, coursework_id: str, asgn_type: str,
                       asgn_code: str, asgn_title: str,
                       drive, classroom, keys_folder_id: str,
                       state: dict,
                       redo_q_nums: list[int] | None = None) -> dict:
    """Run AK generation for one coursework. Returns updated state entry."""
    from tools.email_helper import send_review_email

    print(f"  [AK] Pulling question paper for {asgn_type} {asgn_code}…")
    question_pdf = get_question_paper_pdf(drive, classroom, course_id, coursework_id)

    prev_entry = state.get(coursework_id, {})
    prev_questions = prev_entry.get("questions", []) if redo_q_nums else None

    print(f"  [AK] Generating solutions with {pick_model(asgn_type)}…")
    solutions = generate_solutions(
        question_pdf, asgn_type,
        redo_q_nums=redo_q_nums, prev_questions=prev_questions,
    )

    otp = generate_otp()

    # Render LaTeX
    env = build_jinja_env()
    template = env.get_template("answer_key_template.tex")
    tex = template.render(
        assignment={"type": asgn_type, "code": asgn_code, "title": asgn_title},
        questions=solutions["questions"],
        generated_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        model=pick_model(asgn_type),
        otp=otp,
    )
    base = f"{asgn_type}_{asgn_code}_KEY"
    pdf_path = compile_latex(tex, KEYS_TMP, base)
    print(f"  [AK] PDF: {pdf_path}")

    # Upload to Drive
    drive_id = upload_pdf_to_drive(drive, keys_folder_id, pdf_path, f"{base}.pdf")
    print(f"  [AK] Uploaded to Drive: {drive_id}")

    # Send email
    teacher_email = os.getenv("TEACHER_EMAIL", "").strip()
    subject, body_text, body_html = build_review_email(
        asgn_type, asgn_code, asgn_title,
        len(solutions["questions"]), otp, pick_model(asgn_type),
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
        "assignment_type": asgn_type,
        "assignment_code": asgn_code,
        "assignment_title": asgn_title,
        "status": "PENDING_REVIEW",
        "current_otp": otp,
        "thread_id": sent["threadId"],
        "regen_count": prev_entry.get("regen_count", 0) + (1 if redo_q_nums else 0),
        "questions": solutions["questions"],
        "questions_status": questions_status,
        "drive_pdf_id": drive_id,
        "model": pick_model(asgn_type),
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
