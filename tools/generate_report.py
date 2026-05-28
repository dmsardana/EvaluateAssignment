"""
Render the LaTeX report template from an evaluation JSON, compile to PDF.
Uses the ThinkingSouls evaluation report style (ts_evalreport.sty).

Usage:
    python tools/generate_report.py '<evaluation_json>'
"""

import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jinja2
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
TEMPLATE_NAME = "report_template.tex"
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", ".tmp", "reports")

# Tier long-form names shown on the report cover. Sourced from
# tier_config.TIER_CONFIG so any new tier appears automatically; the
# override map preserves legacy possessives ("Qualifier's") that
# tier_config doesn't track.
from tools.tier_config import KNOWN_TIERS, tier_label

_TIER_FULL_NAME_OVERRIDES = {
    "WA": "Warm-Up",
    "QA": "Qualifier's",
    "AA": "Achiever's",
    "ZA": "Quiz",
}
TIER_FULL_NAME = {
    t: _TIER_FULL_NAME_OVERRIDES.get(t, tier_label(t)) for t in KNOWN_TIERS
}

# ── LaTeX escape (conservative — DO NOT escape $, {, }, \\ since solutions contain math) ──
_LATEX_ESCAPE_MAP = {
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "^": r"\textasciicircum{}",
    "~": r"\textasciitilde{}",
}
_LATEX_ESCAPE_RE = re.compile("|".join(re.escape(k) for k in _LATEX_ESCAPE_MAP))


def latex_escape(text) -> str:
    """For metadata strings (names, titles, breadcrumbs) — keeps math intact."""
    return _LATEX_ESCAPE_RE.sub(lambda m: _LATEX_ESCAPE_MAP[m.group()], str(text or ""))


# Math-aware escape: only escape specials OUTSIDE $...$ regions. LLM prose
# fields (summary_box, feedback, swot evidence, closing note) routinely
# contain `%` for percentages, `&` for "Q1 & Q2", `#` for hashes, `_` for
# variable names — every one of which silently breaks LaTeX. A blind escape
# would corrupt inline math `$f_n(x)$`; this preserves math regions verbatim.
def latex_escape_safe(text) -> str:
    """Escape LaTeX specials in prose while preserving $...$ math regions."""
    if not text:
        return ""
    s = str(text)
    # Split on $...$ — even-indexed parts are prose, odd-indexed are math.
    parts = re.split(r'(\$[^$]*\$)', s)
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:  # math region — leave alone
            out.append(p)
        else:
            out.append(_LATEX_ESCAPE_RE.sub(
                lambda m: _LATEX_ESCAPE_MAP[m.group()], p
            ))
    return "".join(out)


# ── Helper functions exposed to the template ─────────────────────────────────
def pct(score: float) -> int:
    """Convert a 0..1 dimension score to an integer percentage."""
    return int(round(float(score) * 100))


def status_color(percentage: int) -> str:
    """Color token for a percentage."""
    if percentage >= 100:
        return "tsGreen"
    if percentage >= 50:
        return "tsAmber"
    return "tsRed"


def status_label(percentage: int) -> str:
    if percentage >= 100:
        return "Mastery"
    if percentage >= 75:
        return "Strong"
    if percentage >= 50:
        return "Developing"
    if percentage >= 25:
        return "Emerging"
    return "Needs work"


def scan_color(quality: str) -> str:
    return {
        "Excellent": "tsGreen",
        "Good":      "tsBlue",
        "Acceptable": "tsAmber",
        "Poor":      "tsRed",
    }.get(quality, "tsBlue")


def make_concept_map_helpers(evaluation: dict, block_size: int = 25):
    """Builds block descriptors + parameterized header/row callables for the
    Concept Dependency Map.

    The map can have 50+ questions in an AA paper. Rendering all of them as
    a single horizontal tabular spills off the page. We chunk the columns
    into blocks of ``block_size`` (default 25) and the template renders one
    tsConceptMap environment per block.

    Returns ``(blocks, header_fn, row_fn)`` where:
      - blocks: list of dicts {start, end, count} (1-based, inclusive)
      - header_fn(start, end) → LaTeX header cells for that slice
      - row_fn(concept_index, start, end) → LaTeX row cells for that slice
    """
    cm = evaluation.get("concept_map", {}) or {}
    n = evaluation.get("summary", {}).get("total_questions", 0)
    matrix = cm.get("matrix", []) or []
    cell_macro = {"G": r"\tsCG", "A": r"\tsCA", "R": r"\tsCR", "N": r"\tsCN"}

    blocks: list[dict] = []
    start = 1
    while start <= n:
        end = min(start + block_size - 1, n)
        blocks.append({"start": start, "end": end, "count": end - start + 1})
        start = end + 1

    def header(start: int, end: int) -> str:
        return " &".join(rf"\tsCH{{{i}}}" for i in range(start, end + 1))

    def row(concept_index: int, start: int, end: int) -> str:
        slice_len = end - start + 1
        if concept_index >= len(matrix):
            return " &".join([r"\tsCN"] * slice_len)
        row_cells = matrix[concept_index]
        out = []
        for i in range(start - 1, end):
            c = row_cells[i] if i < len(row_cells) else "N"
            out.append(cell_macro.get((c or "N").upper(), r"\tsCN"))
        return " &".join(out)

    return blocks, header, row


# ── Jinja2 setup ───────────────────────────────────────────────────────────────
def build_jinja_env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATES_DIR),
        block_start_string="((*",
        block_end_string="*))",
        variable_start_string="((((",
        variable_end_string="))))",
        comment_start_string="((#",
        comment_end_string="#))",
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["latex_escape"] = latex_escape
    env.filters["tex"] = latex_escape_safe
    env.globals["pct"] = pct
    env.globals["status_color"] = status_color
    env.globals["status_label"] = status_label
    env.globals["scan_color"] = scan_color
    return env


# ── LaTeX compile ──────────────────────────────────────────────────────────────
def compile_latex(tex_source: str, output_dir: str, base_name: str) -> str:
    """Write tex_source to a temp file, copy required assets, compile, return PDF path."""
    load_dotenv(ENV_PATH)
    engine = os.getenv("PDFLATEX_PATH", "tectonic")
    is_tectonic = "tectonic" in os.path.basename(engine).lower()

    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy required assets into the compile dir (style + logo + bundled fonts)
        for asset in (
            "ts_evalreport.sty",
            "logo.png",
            "texgyreheros-regular.otf",
            "texgyreheros-bold.otf",
            "texgyreheros-italic.otf",
            "texgyreheros-bolditalic.otf",
            "latinmodern-math.otf",
        ):
            src = os.path.join(TEMPLATES_DIR, asset)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(tmpdir, asset))

        tex_path = os.path.join(tmpdir, f"{base_name}.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_source)

        if is_tectonic:
            cmd = [engine, "--keep-logs", "--outdir", tmpdir, tex_path]
            passes = 1
        else:
            # xelatex (required for fontspec + unicode-math)
            xelatex = engine if engine.endswith("xelatex") else "xelatex"
            cmd = [
                xelatex,
                "-interaction=nonstopmode",
                "-output-directory", tmpdir,
                tex_path,
            ]
            passes = 2

        for _pass in range(passes):
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=tmpdir)
            if result.returncode != 0:
                log_path = os.path.join(tmpdir, f"{base_name}.log")
                log = ""
                if os.path.exists(log_path):
                    with open(log_path) as lf:
                        log = lf.read()[-4000:]
                raise RuntimeError(
                    f"{os.path.basename(engine)} failed (pass {_pass+1}):\n"
                    f"STDERR:\n{result.stderr}\n---LOG (tail)---\n{log}"
                )

        compiled_pdf = os.path.join(tmpdir, f"{base_name}.pdf")
        dest_pdf = os.path.join(output_dir, f"{base_name}.pdf")
        shutil.copy2(compiled_pdf, dest_pdf)

    return dest_pdf


def _human_date(iso: str) -> str:
    """'2026-05-09' → '09 May 2026'"""
    try:
        d = _dt.date.fromisoformat(iso)
        return d.strftime("%d %b %Y")
    except Exception:
        return iso


def _student_name_clean(name: str) -> str:
    """Strip diacritics, keep alphanumerics, CamelCase. Used for filenames."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", ascii_name) if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Student"


def _title_case_name(name: str) -> str:
    """'chaitanyaa pandey' → 'Chaitanyaa Pandey'. Preserves separators and existing capitalisation."""
    parts = re.split(r"(\s+|[-'])", str(name or ""))
    titled = []
    for p in parts:
        if not p or p.isspace() or p in {"-", "'"}:
            titled.append(p)
        else:
            titled.append(p[:1].upper() + p[1:].lower())
    return "".join(titled).strip() or "Student"


def make_dam_matrix(evaluation: dict) -> list[list[dict]]:
    """3x4 grid (rows=D1..D3, cols=L1..L4). Each cell: {count, avg_pct}.

    Aggregates per-question scores by difficulty x learning-objective.
    Cells with no questions return count=0, avg_pct=0.0 — the LaTeX
    macro renders them muted.
    """
    rows = ["D1", "D2", "D3"]
    cols = ["L1", "L2", "L3", "L4"]
    grid: list[list[dict]] = [
        [{"count": 0, "sum_pct": 0.0} for _ in cols] for _ in rows
    ]
    for q in evaluation.get("questions") or []:
        d = q.get("difficulty") or "D2"
        lo = q.get("learning_objective") or "L2"
        if d not in rows or lo not in cols:
            continue
        # Prefer the 0..1 `score` if present; else derive from dimensions.
        score = q.get("score")
        if score is None:
            dims = q.get("dimensions") or {}
            ds = [
                (dims.get(k) or {}).get("score", 0) or 0
                for k in (
                    "concept_understanding", "approach_method",
                    "step_by_step", "numerical_accuracy", "presentation",
                )
            ]
            score = (sum(ds) / 5.0) if ds else 0.0
        score = float(score)
        cell = grid[rows.index(d)][cols.index(lo)]
        cell["count"] += 1
        cell["sum_pct"] += 100.0 * score
    out: list[list[dict]] = []
    for r in grid:
        out.append([
            {
                "count": c["count"],
                "avg_pct": (c["sum_pct"] / c["count"]) if c["count"] else 0.0,
            }
            for c in r
        ])
    return out


def make_qrd_rows(evaluation: dict) -> list[dict]:
    """Flat per-question rows for the QRD (Question Response Data) table."""
    out: list[dict] = []
    for q in evaluation.get("questions") or []:
        attempted_raw = q.get("attempted")
        if attempted_raw is None:
            ya = q.get("your_answer")
            if ya is None:
                # Field absent (legacy data) — assume attempted.
                attempted = True
            else:
                ya_norm = ya.strip().lower()
                attempted = ya_norm not in ("", "(blank)", "blank")
        else:
            attempted = bool(attempted_raw)
        out.append({
            "number": q.get("number"),
            "topic": q.get("topic", ""),
            "concept": q.get("concept") or q.get("topic", ""),
            "attempted": attempted,
            "difficulty": q.get("difficulty") or "D2",
            "learning_objective": q.get("learning_objective") or "L2",
            "scan_quality": q.get("scan_quality", "Good"),
        })
    return out


def generate(evaluation: dict) -> str:
    env = build_jinja_env()
    template = env.get_template(TEMPLATE_NAME)

    raw_name = evaluation["student"]["name"]
    display_name = _title_case_name(raw_name)
    student_clean = _student_name_clean(raw_name)
    eval_date = evaluation.get("evaluation_date", _dt.date.today().isoformat())
    base_name = f"{student_clean}_{evaluation['assignment']['code']}_{eval_date}_Report"

    cm_blocks, cm_header, cm_row = make_concept_map_helpers(evaluation)

    # Override the student.name with the title-cased version for display only
    student_display = {**evaluation["student"], "name": display_name}

    # Annotate each question with a simple-average dimension percentage so the
    # Summary of Rubric Matrix can render with one number per row and sort by
    # it. Keeps the JSON shape unchanged for cached evaluations.
    questions_for_template = []
    _STRING_FIELD_DEFAULTS = {
        "topic": "",
        "function_latex": "",
        "your_answer": "(blank)",
        "expected_answer": "",
        "feedback": "",
        "scan_quality": "Good",
        "scan_note": "",
        # Per-tier-report-views fields. Legacy cached evaluations lack
        # these — defaults keep the renderer happy until the next re-eval
        # populates real classifications.
        "difficulty": "D2",
        "learning_objective": "L2",
        "concept": "",
    }
    for q in evaluation.get("questions") or []:
        dims = q.get("dimensions") or {}
        scores = [
            (dims.get(k) or {}).get("score", 0) or 0
            for k in (
                "concept_understanding",
                "approach_method",
                "step_by_step",
                "numerical_accuracy",
                "presentation",
            )
        ]
        avg_pct = int(round((sum(scores) / 5.0) * 100)) if scores else 0
        merged = {**_STRING_FIELD_DEFAULTS, **q, "avg_pct": avg_pct}
        for k, default in _STRING_FIELD_DEFAULTS.items():
            if merged.get(k) is None:
                merged[k] = default
        questions_for_template.append(merged)

    from tools.report_view_config import view_for
    components = view_for(evaluation["assignment"]["type"])

    context = {
        **evaluation,
        "student": student_display,
        "questions": questions_for_template,
        "tier_full_name": TIER_FULL_NAME.get(
            evaluation["assignment"]["type"], evaluation["assignment"]["type"]
        ),
        "evaluation_date_human": _human_date(eval_date),
        "concept_map_blocks": cm_blocks,
        "concept_map_header": cm_header,
        "concept_map_row": cm_row,
        "components": components,
        "dam_matrix": make_dam_matrix(evaluation),
        "qrd_rows": make_qrd_rows(evaluation),
    }

    tex_source = template.render(**context)
    return compile_latex(tex_source, REPORTS_DIR, base_name)


def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/generate_report.py '<evaluation_json>'", file=sys.stderr)
        sys.exit(1)

    load_dotenv(ENV_PATH)
    evaluation = json.loads(sys.argv[1])
    pdf_path = generate(evaluation)
    print(pdf_path)
    print(f"Report compiled → {pdf_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
