# Workflow: Generate Answer Key (with Email Approval Loop)

**Purpose:** Auto-generate a definitive answer key + concise solution set for any new Google Classroom assignment, then route it through teacher email approval before grading is unlocked.

## How It Works (state machine)

```
DETECTED → GENERATING → PENDING_REVIEW ──→ APPROVED ✓ (grading unlocks)
                              ↓
                         NEEDS_REGEN → GENERATING → PENDING_REVIEW (new OTP)
```

State for every coursework is stored in `answer_key_state.json` inside the Drive `answer_keys/` folder.

## Triggering

The orchestrator (`run_pipeline.py`) **automatically** triggers AK generation for any coursework it detects without an APPROVED state. You can also run it manually:

```bash
# Generate keys for all unprocessed courseworks
python3 tools/generate_answer_key.py

# Single coursework by ID
python3 tools/generate_answer_key.py 863763941032

# Re-generate ONLY questions flagged as needs_rework in state
python3 tools/generate_answer_key.py --regen 863763941032
```

## What Gets Generated

For each new coursework:

1. **Question paper PDF** is pulled from the coursework's `materials` attachments in Classroom.
2. **Claude** (Opus 4.7 for QA/AA, Sonnet 4.6 for WA) is given the question paper and prompted to produce JSON with per-question detailed solutions + concise versions + difficulty + common-mistake notes.
3. **LaTeX** is rendered using `tools/templates/answer_key_template.tex` and compiled to PDF via tectonic.
4. **PDF** is uploaded to Drive `answer_keys/` as `{TYPE}_{CODE}_KEY.pdf`.
5. **Email** is sent to `TEACHER_EMAIL` with the PDF attached and a 6-character OTP printed in both the email and the PDF cover.

## Reviewing the Email

You receive a subject like: `[ACTION] Approve Answer Key: QA DOM3 — OTP: AB12CD`

The PDF has two sections:
- **§ 1 Concise Solution Set** — final answers + key steps (teacher quick-ref)
- **§ 2 Detailed Solutions** — full step-by-step working with LaTeX math, plus common student errors

### Reply formats

| To… | Reply with |
|---|---|
| Approve all | `OK <OTP>` |
| Reprocess specific questions | `Q3, Q5-7 reprocess <OTP>` |
| Redo entire key | `Wrong, redo all <OTP>` |

The reply parser:
- **Strips quoted original-message content** (so example text in the original email isn't misread)
- **Authenticates by Gmail-verified From address** matching `TEACHER_EMAIL` (OTP is supplementary trust)
- **Treats generic "wrong / redo / regenerate" without question numbers as ALL questions need rework**

## Polling Replies

The orchestrator runs this on every tick:

```bash
python3 tools/check_review_replies.py
```

It walks every PENDING_REVIEW state entry, fetches replies from the original Gmail thread, parses the latest reply, and updates state to APPROVED or NEEDS_REGEN. NEEDS_REGEN entries are auto-passed back to `generate_answer_key.py --regen` so a new email goes out without manual intervention.

## State File Schema

Stored at `answer_keys/answer_key_state.json` on Drive:

```json
{
  "<coursework_id>": {
    "course_id": "...",
    "coursework_id": "...",
    "assignment_type": "QA",
    "assignment_code": "DOM3",
    "assignment_title": "07 Domain | Code: DOM3 | Type: QA",
    "status": "APPROVED",
    "current_otp": "AB12CD",
    "thread_id": "<gmail thread>",
    "regen_count": 0,
    "questions": [...],
    "questions_status": ["approved", "approved", ...],
    "drive_pdf_id": "...",
    "model": "claude-opus-4-7",
    "generated_at": "2026-05-10T10:00:00+00:00",
    "approved_at": "2026-05-10T11:30:00+00:00"
  }
}
```

Grading (in `run_pipeline.py`) is gated on `status == "APPROVED"` for the coursework_id.

## Tuning the Generation Prompt

Edit `GENERATION_PROMPT` in [tools/generate_answer_key.py](../tools/generate_answer_key.py:30). For a recurring quality gap, add explicit instructions (e.g. "Verify each step. Re-derive at the end. Use $\\mathbb{R}$ for reals.") to bake guardrails in.

## Cost Notes

- Opus 4.7 (QA/AA): expensive — full 25-question key can be ~$0.50–$1
- Sonnet 4.6 (WA): cheaper — ~$0.10–$0.20 per key
- Each regeneration cycle re-charges, so good first-pass prompts pay back fast
