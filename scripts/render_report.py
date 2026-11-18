"""Render docs/report/REPORT.md to docs/report/GigBid_Report.pdf (headings, paragraphs, bullets, tables).

uv run python -m scripts.render_report
"""

from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "report" / "REPORT.md"
OUT = ROOT / "docs" / "report" / "GigBid_Report.pdf"
SUBS = {"—": "-", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...",
        "→": "->", " ": " ", "≥": ">=", "≤": "<="}  # fmt: skip


def latin(text: str) -> str:
    for a, b in SUBS.items():
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


def inline(text: str) -> str:
    """Markdown inline -> fpdf2 markdown subset (**bold**, __italic__); code spans keep their text."""
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)([^*]+)\*(?!\*)", r"__\1__", text)
    return latin(text)


class Report(FPDF):
    label = "R&D report"

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.set_text_color(120)
        self.cell(0, 8, f"GigBid - {self.label} - page {self.page_no()}", align="C")
        self.set_text_color(0)


def render(src: Path = SRC, out: Path = OUT, label: str = "R&D report") -> None:
    pdf = Report(format="A4")
    pdf.label = label
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(True, 16)
    pdf.add_page()
    lines = src.read_text(encoding="utf-8").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            pdf.set_font("Helvetica", size=8)
            with pdf.table(headings_style=FontFace(emphasis="BOLD", fill_color=(235, 238, 245)), line_height=4.6,
                           text_align="LEFT", padding=1) as table:  # fmt: skip
                for r in rows:
                    row = table.row()
                    for c in r:
                        text = inline(c).replace("**", "")
                        if text.startswith("http"):
                            pdf.set_text_color(30, 80, 200)
                            row.cell(text, link=text)
                            pdf.set_text_color(0)
                        else:
                            row.cell(text)
            pdf.ln(3)
            continue
        if line.startswith("# "):
            pdf.set_font("Helvetica", "B", 18)
            pdf.multi_cell(0, 9, latin(line[2:]), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        elif line.startswith("## "):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 13)
            pdf.multi_cell(0, 7, latin(line[3:]), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        elif re.match(r"^\s*- ", line):
            indent = 10 if line.startswith("  ") else 4
            pdf.set_font("Helvetica", size=9.5)
            pdf.set_x(pdf.l_margin + indent)
            pdf.multi_cell(
                0, 5, "- " + inline(line.strip()[2:]), markdown=True, new_x="LMARGIN", new_y="NEXT"
            )
        elif line.strip():
            pdf.set_font("Helvetica", size=9.5)
            pdf.multi_cell(0, 5, inline(line), markdown=True, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1.5)
        i += 1
    pdf.output(str(out))
    print(f"wrote {out.relative_to(ROOT)} ({pdf.page_no()} pages)")


if __name__ == "__main__":
    import sys

    # default: the R&D report; or: render_report.py <src.md> <out.pdf> "<footer label>"
    if len(sys.argv) == 4:
        render(ROOT / sys.argv[1], ROOT / sys.argv[2], sys.argv[3])
    else:
        render()
