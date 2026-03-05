import base64
from fpdf import FPDF


class PDF(FPDF):
    def header(self):
        self.set_fill_color(0, 80, 160)
        self.rect(0, 0, self.w, 22, style="F")
        self.set_y(6)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "ProFuturo - Informe Directivo", align="C")
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_text_color(153, 153, 153)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 8, f"Página {self.page_no()}", align="C")


def generate_report_pdf(text: str, title: str) -> str:
    clean_title = (title or "Reporte de Auditoria IA - ProFuturo").replace("_", " ").strip()
    if not clean_title:
        clean_title = "Reporte de Auditoria IA - ProFuturo"

    pdf = PDF()
    pdf.set_margins(20, 25, 20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 80, 160)
    pdf.multi_cell(0, 10, clean_title, align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", size=11)
    pdf.set_text_color(50, 50, 50)

    lines = (text or "").split("\n")
    in_table = False
    table_rows = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if in_table:
                _render_table(pdf, table_rows)
                table_rows = []
                in_table = False
            pdf.ln(4)
            continue

        if "|" in stripped:
            if stripped.replace("-", "").replace("|", "").replace(":", "").strip() == "":
                continue
            in_table = True
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            table_rows.append(cells)
            continue

        if in_table:
            _render_table(pdf, table_rows)
            table_rows = []
            in_table = False

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            heading_text = stripped.lstrip("#").strip()
            if level == 1:
                pdf.set_font("Helvetica", "B", 14)
            elif level == 2:
                pdf.set_font("Helvetica", "B", 12)
            else:
                pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(0, 80, 160)
            pdf.multi_cell(0, 8, heading_text)
            pdf.ln(2)
            pdf.set_font("Helvetica", size=11)
            pdf.set_text_color(50, 50, 50)
        else:
            clean_line = stripped.replace("**", "")
            if "**" in stripped:
                pdf.set_font("Helvetica", "B", 11)
                pdf.multi_cell(0, 6, clean_line)
                pdf.set_font("Helvetica", size=11)
            else:
                pdf.multi_cell(0, 6, stripped)
            pdf.ln(0)

    if in_table:
        _render_table(pdf, table_rows)

    pdf_bytes = pdf.output(dest="S")
    if isinstance(pdf_bytes, str):
        pdf_bytes = pdf_bytes.encode("latin-1", errors="ignore")
    return base64.b64encode(pdf_bytes).decode("utf-8")


def _render_table(pdf: PDF, rows: list[list[str]]):
    if not rows or len(rows) < 2:
        return

    headers = rows[0]
    data_rows = rows[1:]

    num_cols = len(headers)
    if num_cols == 0:
        return

    usable_width = pdf.w - pdf.l_margin - pdf.r_margin
    col_width = usable_width / num_cols

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(0, 80, 160)
    pdf.set_text_color(255, 255, 255)
    for header in headers:
        pdf.cell(col_width, 8, header[:30], border=1, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", size=10)
    pdf.set_text_color(50, 50, 50)
    for row in data_rows:
        for i, cell in enumerate(row):
            if i >= num_cols:
                break
            pdf.cell(col_width, 7, cell[:30], border=1)
        pdf.ln()

    pdf.ln(3)
    pdf.set_font("Helvetica", size=11)
