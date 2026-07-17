from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


ORANGE = colors.HexColor("#D76B2D")
GRAPHITE = colors.HexColor("#202725")
MUTED = colors.HexColor("#68716E")
PAPER = colors.HexColor("#F7F6F2")
LINE = colors.HexColor("#D9DEDB")


def inline_markup(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r'<font name="STSong-Light" color="#AC4D19">\1</font>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    return escaped


def styles():
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleCN", parent=base["Title"], fontName="STSong-Light", fontSize=28,
            leading=36, textColor=GRAPHITE, alignment=TA_CENTER, spaceAfter=8 * mm,
        ),
        "subtitle": ParagraphStyle(
            "SubtitleCN", parent=base["Heading2"], fontName="STSong-Light", fontSize=16,
            leading=24, textColor=ORANGE, alignment=TA_CENTER, spaceAfter=5 * mm,
        ),
        "h2": ParagraphStyle(
            "Heading2CN", parent=base["Heading2"], fontName="STSong-Light", fontSize=18,
            leading=25, textColor=GRAPHITE, spaceBefore=7 * mm, spaceAfter=4 * mm,
            borderColor=ORANGE, borderWidth=0, borderPadding=(0, 0, 2 * mm, 0),
        ),
        "h3": ParagraphStyle(
            "Heading3CN", parent=base["Heading3"], fontName="STSong-Light", fontSize=13,
            leading=19, textColor=ORANGE, spaceBefore=4 * mm, spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "BodyCN", parent=base["BodyText"], fontName="STSong-Light", fontSize=10.5,
            leading=17, textColor=GRAPHITE, alignment=TA_LEFT, spaceAfter=2.5 * mm,
        ),
        "meta": ParagraphStyle(
            "MetaCN", parent=base["BodyText"], fontName="STSong-Light", fontSize=10,
            leading=17, textColor=MUTED, alignment=TA_CENTER, spaceAfter=2 * mm,
        ),
        "code": ParagraphStyle(
            "CodeCN", parent=base["Code"], fontName="STSong-Light", fontSize=9,
            leading=14, textColor=GRAPHITE, backColor=PAPER, borderColor=LINE,
            borderWidth=0.5, borderPadding=3 * mm, leftIndent=2 * mm, rightIndent=2 * mm,
            spaceBefore=2 * mm, spaceAfter=4 * mm,
        ),
        "bullet": ParagraphStyle(
            "BulletCN", parent=base["BodyText"], fontName="STSong-Light", fontSize=10.5,
            leading=17, textColor=GRAPHITE, leftIndent=2 * mm,
        ),
    }


def page_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(22 * mm, 16 * mm, 188 * mm, 16 * mm)
    canvas.setFont("STSong-Light", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(22 * mm, 10 * mm, "拾要 · 0.2.0-beta")
    canvas.drawRightString(188 * mm, 10 * mm, f"{doc.page}")
    canvas.restoreState()


def build(source: Path, output: Path) -> None:
    style = styles()
    lines = source.read_text(encoding="utf-8").splitlines()
    story = [Spacer(1, 23 * mm)]
    in_code = False
    code_lines: list[str] = []
    list_items: list[str] = []
    title_seen = False

    def flush_list() -> None:
        nonlocal list_items
        if not list_items:
            return
        story.append(ListFlowable(
            [ListItem(Paragraph(inline_markup(item), style["bullet"])) for item in list_items],
            bulletType="bullet", start="circle", leftIndent=7 * mm, bulletFontName="STSong-Light",
            bulletFontSize=6, spaceAfter=3 * mm,
        ))
        list_items = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                story.append(Paragraph("<br/>".join(html.escape(value) for value in code_lines), style["code"]))
                code_lines = []
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
            continue
        if stripped.startswith("- "):
            list_items.append(stripped[2:])
            continue
        flush_list()
        if not stripped:
            continue
        if stripped.startswith("# "):
            story.append(Paragraph(inline_markup(stripped[2:]), style["title"]))
            title_seen = True
        elif stripped.startswith("## "):
            heading = stripped[3:]
            if title_seen and heading == "Windows 测试版安装与使用说明":
                story.append(Paragraph(inline_markup(heading), style["subtitle"]))
            else:
                story.append(Paragraph(inline_markup(heading), style["h2"]))
        elif stripped.startswith("### "):
            story.append(Paragraph(inline_markup(stripped[4:]), style["h3"]))
        elif re.match(r"^\d+\. ", stripped):
            story.append(Paragraph(inline_markup(stripped), style["body"]))
        elif stripped.startswith("版本：") or stripped.startswith("系统：") or stripped.startswith("发布者："):
            story.append(Paragraph(inline_markup(stripped.rstrip("  ")), style["meta"]))
        else:
            story.append(Paragraph(inline_markup(stripped), style["body"]))
    flush_list()

    output.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output), pagesize=A4, rightMargin=22 * mm, leftMargin=22 * mm,
        topMargin=19 * mm, bottomMargin=22 * mm, title="拾要 Windows 测试版安装与使用说明",
        author="angle1592", subject="安装、配置、备份、更新与卸载说明",
    )
    document.build(story, onFirstPage=page_footer, onLaterPages=page_footer)


if __name__ == "__main__":
    repository = Path(__file__).resolve().parents[1]
    source_path = Path(sys.argv[1]) if len(sys.argv) > 1 else repository / "docs" / "user-guide.md"
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else repository / "release" / "Shiyao-Guide-zh-CN.pdf"
    build(source_path.resolve(), output_path.resolve())
    print(output_path.resolve())
