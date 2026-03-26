import base64
import os
import re
import tempfile
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import KeepTogether

PROFUTURO_BLUE  = colors.HexColor("#003087")
PROFUTURO_CYAN  = colors.HexColor("#00AEEF")
ACCENT_RED      = colors.HexColor("#DC0000")
ACCENT_ORANGE   = colors.HexColor("#FF6400")
ACCENT_YELLOW   = colors.HexColor("#FFC800")
ACCENT_SOFT     = colors.HexColor("#5A96FF")
TEXT_DARK       = colors.HexColor("#1A1A2E")
TEXT_BODY       = colors.HexColor("#2D2D2D")
BG_LIGHT        = colors.HexColor("#F4F7FB")
RULE_COLOR      = colors.HexColor("#D0DFF0")

PAGE_W, PAGE_H  = A4
MARGIN          = 22 * mm


def _build_styles():
    base = getSampleStyleSheet()

    styles = {
        "doc_title": ParagraphStyle(
            "doc_title",
            fontName="Helvetica-Bold",
            fontSize=22,
            textColor=PROFUTURO_BLUE,
            spaceAfter=4,
            alignment=TA_CENTER,
            leading=28,
        ),
        "doc_subtitle": ParagraphStyle(
            "doc_subtitle",
            fontName="Helvetica",
            fontSize=10,
            textColor=PROFUTURO_CYAN,
            spaceAfter=2,
            alignment=TA_CENTER,
            leading=14,
        ),
        "h1": ParagraphStyle(
            "h1",
            fontName="Helvetica-Bold",
            fontSize=14,
            textColor=PROFUTURO_BLUE,
            spaceBefore=14,
            spaceAfter=4,
            leading=18,
            borderPad=0,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=PROFUTURO_CYAN,
            spaceBefore=10,
            spaceAfter=3,
            leading=16,
        ),
        "h3": ParagraphStyle(
            "h3",
            fontName="Helvetica-BoldOblique",
            fontSize=11,
            textColor=TEXT_DARK,
            spaceBefore=8,
            spaceAfter=2,
            leading=14,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=10,
            textColor=TEXT_BODY,
            spaceAfter=5,
            leading=15,
            alignment=TA_JUSTIFY,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            fontName="Helvetica",
            fontSize=10,
            textColor=TEXT_BODY,
            spaceAfter=3,
            leading=14,
            leftIndent=14,
            bulletIndent=4,
            bulletFontName="Helvetica-Bold",
            bulletFontSize=10,
            bulletColor=PROFUTURO_CYAN,
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=PROFUTURO_BLUE,
            alignment=TA_CENTER,
            leading=12,
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value",
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=PROFUTURO_CYAN,
            alignment=TA_CENTER,
            leading=22,
        ),
        "footer": ParagraphStyle(
            "footer",
            fontName="Helvetica",
            fontSize=8,
            textColor=colors.HexColor("#888888"),
            alignment=TA_CENTER,
        ),
        "alert_title": ParagraphStyle(
            "alert_title",
            fontName="Helvetica-Bold",
            fontSize=20,
            textColor=ACCENT_RED,
            alignment=TA_CENTER,
            spaceAfter=6,
            leading=26,
        ),
        "alert_body": ParagraphStyle(
            "alert_body",
            fontName="Helvetica",
            fontSize=10,
            textColor=TEXT_BODY,
            spaceAfter=5,
            leading=15,
        ),
        "alert_section": ParagraphStyle(
            "alert_section",
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=TEXT_DARK,
            spaceBefore=10,
            spaceAfter=4,
            leading=15,
        ),
    }
    return styles


def _header_footer(canvas, doc):
    canvas.saveState()
    w, h = A4

    canvas.setFillColor(PROFUTURO_BLUE)
    canvas.rect(0, h - 14 * mm, w, 14 * mm, fill=1, stroke=0)

    logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "logo.png")
    if os.path.exists(logo_path):
        canvas.drawImage(logo_path, 8 * mm, h - 12 * mm, width=22 * mm, height=10 * mm,
                         preserveAspectRatio=True, mask="auto")

    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(colors.white)
    canvas.drawRightString(w - 10 * mm, h - 8 * mm, "ProFuturo — Auditor IA")

    canvas.setFillColor(PROFUTURO_BLUE)
    canvas.rect(0, 0, w, 10 * mm, fill=1, stroke=0)

    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.white)
    canvas.drawString(10 * mm, 3.5 * mm,
                      f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}  |  Confidencial — Solo uso interno")
    canvas.drawRightString(w - 10 * mm, 3.5 * mm, f"Página {doc.page}")

    canvas.restoreState()


def _parse_markdown_to_story(text: str, styles: dict) -> list:
    story = []
    lines = text.splitlines()
    i = 0

    kpi_buffer = []

    def flush_kpis():
        if not kpi_buffer:
            return
        col_data = []
        for label, value in kpi_buffer:
            cell = [
                Paragraph(value, styles["kpi_value"]),
                Paragraph(label, styles["kpi_label"]),
            ]
            col_data.append(cell)

        num_cols = min(len(col_data), 4)
        rows = [col_data[j:j+num_cols] for j in range(0, len(col_data), num_cols)]

        for row in rows:
            while len(row) < num_cols:
                row.append([""])
            col_w = (PAGE_W - 2 * MARGIN) / num_cols
            tbl = Table([row], colWidths=[col_w] * num_cols, rowHeights=[22 * mm])
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), BG_LIGHT),
                ("ROUNDEDCORNERS", [6]),
                ("BOX", (0, 0), (-1, -1), 0.5, RULE_COLOR),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE_COLOR),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 4 * mm))
        kpi_buffer.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("### "):
            flush_kpis()
            story.append(Paragraph(stripped[4:], styles["h3"]))

        elif stripped.startswith("## "):
            flush_kpis()
            text_h = stripped[3:]
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(text_h, styles["h2"]))
            story.append(HRFlowable(width="100%", thickness=0.5,
                                    color=PROFUTURO_CYAN, spaceAfter=2))

        elif stripped.startswith("# "):
            flush_kpis()
            text_h = stripped[2:]
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph(text_h, styles["h1"]))
            story.append(HRFlowable(width="100%", thickness=1.5,
                                    color=PROFUTURO_BLUE, spaceAfter=3))

        elif stripped.startswith("- ") or stripped.startswith("* "):
            flush_kpis()
            content = stripped[2:]
            content = _inline_markdown(content)
            story.append(Paragraph(f"<bullet>\u2022</bullet> {content}", styles["bullet"]))

        elif re.match(r"^\d+\.\s", stripped):
            flush_kpis()
            content = re.sub(r"^\d+\.\s", "", stripped)
            content = _inline_markdown(content)
            num = re.match(r"^(\d+)\.", stripped).group(1)
            story.append(Paragraph(f"<bullet>{num}.</bullet> {content}", styles["bullet"]))

        elif stripped.startswith("---") or stripped.startswith("___"):
            flush_kpis()
            story.append(HRFlowable(width="100%", thickness=0.5,
                                    color=RULE_COLOR, spaceBefore=4, spaceAfter=4))

        elif re.match(r"^[A-Za-záéíóúÁÉÍÓÚñÑ ]+:\s+[\d\+\-\.,]+", stripped):
            parts = stripped.split(":", 1)
            if len(parts) == 2:
                kpi_buffer.append((parts[0].strip(), parts[1].strip()))

        elif stripped == "":
            flush_kpis()
            story.append(Spacer(1, 3 * mm))

        else:
            flush_kpis()
            content = _inline_markdown(stripped)
            story.append(Paragraph(content, styles["body"]))

        i += 1

    flush_kpis()
    return story


def _inline_markdown(text: str) -> str:
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", text)
    text = re.sub(r"\*\*(.+?)\*\*",     r"<b>\1</b>",         text)
    text = re.sub(r"\*(.+?)\*",         r"<i>\1</i>",         text)
    text = re.sub(r"`(.+?)`",           r"<font name='Courier'>\1</font>", text)
    text = text.replace("&", "&amp;").replace("<b>", "<b>").replace("</b>", "</b>")
    return text


def generate_report_pdf(text: str, title: str) -> str:
    title_clean = title.replace("_", " ")
    styles = _build_styles()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp_path = tmp.name

    doc = SimpleDocTemplate(
        tmp_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=20 * mm,
        bottomMargin=16 * mm,
        title=title_clean,
        author="ProFuturo Auditor IA",
    )

    story = []

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(title_clean, styles["doc_title"]))
    story.append(Paragraph("Informe generado automáticamente por el Auditor IA de ProFuturo", styles["doc_subtitle"]))
    story.append(Spacer(1, 2 * mm))
    story.append(HRFlowable(width="60%", thickness=2, color=PROFUTURO_CYAN,
                             hAlign="CENTER", spaceAfter=6))
    story.append(Spacer(1, 4 * mm))

    story += _parse_markdown_to_story(text, styles)

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)

    with open(tmp_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    os.unlink(tmp_path)
    return encoded


def generate_critical_alert_pdf(community: str, issue_summary: str, severity: str) -> str:
    styles = _build_styles()

    severity_upper = (severity or "MEDIA").upper()
    severity_lower = severity_upper.lower()

    severity_colors = {
        "critica": ACCENT_RED,
        "alta":    ACCENT_ORANGE,
        "media":   ACCENT_YELLOW,
        "baja":    ACCENT_SOFT,
    }
    sev_color = severity_colors.get(severity_lower, colors.grey)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp_path = tmp.name

    doc = SimpleDocTemplate(
        tmp_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=20 * mm,
        bottomMargin=16 * mm,
        title=f"Alerta {severity_upper} — {community}",
        author="ProFuturo Auditor IA",
    )

    story = []

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(f"⚠ ALERTA {severity_upper}", styles["alert_title"]))

    badge_data = [[Paragraph(severity_upper, ParagraphStyle(
        "badge", fontName="Helvetica-Bold", fontSize=13,
        textColor=colors.white, alignment=TA_CENTER, leading=18,
    ))]]
    badge = Table(badge_data, colWidths=[50 * mm], rowHeights=[10 * mm])
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), sev_color),
        ("ROUNDEDCORNERS", [6]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    from reportlab.platypus import KeepInFrame
    story.append(Table([[badge]], colWidths=[PAGE_W - 2 * MARGIN]))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=sev_color, spaceAfter=4))

    meta_data = [
        ["Comunidad",  community],
        ["Severidad",  severity_upper],
        ["Fecha",      datetime.now().strftime("%d/%m/%Y %H:%M:%S")],
        ["Sistema",    "ProFuturo Auditor IA — Monitor Proactivo"],
    ]
    meta_style = ParagraphStyle("meta", fontName="Helvetica", fontSize=10,
                                textColor=TEXT_BODY, leading=14)
    meta_label = ParagraphStyle("meta_label", fontName="Helvetica-Bold", fontSize=10,
                                textColor=PROFUTURO_BLUE, leading=14)
    meta_rows = [[Paragraph(k, meta_label), Paragraph(v, meta_style)] for k, v in meta_data]
    meta_tbl = Table(meta_rows, colWidths=[45 * mm, PAGE_W - 2 * MARGIN - 45 * mm])
    meta_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BG_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE_COLOR),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Detalle de incidencias detectadas", styles["alert_section"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_COLOR, spaceAfter=3))
    for line in issue_summary.strip().splitlines():
        if line.strip():
            story.append(Paragraph(f"<bullet>\u2022</bullet> {line.strip()}", styles["bullet"]))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Acciones recomendadas", styles["alert_section"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_COLOR, spaceAfter=3))
    actions = [
        "Revisar inmediatamente el contenido y los usuarios involucrados.",
        "Aplicar moderación o restricciones de acceso si es necesario.",
        "Contactar a los administradores de la comunidad afectada.",
        "Documentar el incidente en el sistema de tickets interno.",
        "Realizar seguimiento de resolución en un plazo máximo de 24 horas.",
    ]
    for idx, action in enumerate(actions, 1):
        story.append(Paragraph(f"<bullet>{idx}.</bullet> {action}", styles["bullet"]))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)

    with open(tmp_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    os.unlink(tmp_path)
    return encoded
