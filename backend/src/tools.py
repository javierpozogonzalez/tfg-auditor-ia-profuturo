import base64
import html
import re
from fpdf import FPDF
import markdown2


class PDF(FPDF):
    def __init__(self, report_title: str):
        super().__init__()
        self.report_title = report_title

    def header(self):
        self.set_fill_color(0, 80, 160)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 12)
        self.set_xy(0, 0)
        self.cell(0, 14, self.report_title, align="C", fill=True)
        self.ln(10)

    def footer(self):
        self.set_y(-12)
        self.set_text_color(120, 120, 120)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 8, f"Pagina {self.page_no()}", align="C")


def _clean_line(text: str) -> str:
    clean = re.sub(r"\*\*|__|`", "", text)
    clean = re.sub(r"^\s*#{1,6}\s*", "", clean)
    clean = re.sub(r"^\s*[-*]\s+", "- ", clean)
    clean = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", clean)
    clean = re.sub(r"\[GENERATE_PDF:[^\]]*\]", "", clean)
    clean = re.sub(r"(\S{45})(?=\S)", r"\1 ", clean)
    return clean.strip()


def _looks_like_table_separator(line: str) -> bool:
    return bool(re.match(r"^\s*\|?\s*[:\-]+\s*(\|\s*[:\-]+\s*)+\|?\s*$", line))


def _calculate_col_widths(col_count: int) -> tuple:
    if col_count <= 0:
        return (70,)
    if col_count == 1:
        return (70,)
    if col_count == 2:
        return (35, 35)
    if col_count == 3:
        return (15, 55, 15)
    if col_count == 4:
        return (12, 35, 12, 12)
    
    base_width = 70 / col_count
    return tuple(base_width for _ in range(col_count))



def _fit_text(pdf: PDF, text: str, width: float) -> str:
    value = _clean_line(text)
    if not value:
        return ""
    max_width = max(width - 3, 8)
    if pdf.get_string_width(value) <= max_width:
        return value
    ellipsis = "..."
    while value and pdf.get_string_width(value + ellipsis) > max_width:
        value = value[:-1]
    return f"{value}{ellipsis}" if value else ellipsis


def _render_table(pdf: PDF, rows: list[list[str]]):
    if not rows:
        return
    normalized_rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not normalized_rows:
        return

    column_count = max(len(row) for row in normalized_rows)
    headers = normalized_rows[0] + [""] * (column_count - len(normalized_rows[0]))
    data_rows = [row + [""] * (column_count - len(row)) for row in normalized_rows[1:]]

    col_widths = _calculate_col_widths(column_count)
    
    with pdf.table(borders=1, cell_fill_color=(0, 80, 160), text_align="CENTER", line_height=5) as table:
        for header_cell in headers:
            cell = table.row()
            cell.style = pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(255, 255, 255)
            cell(text=_clean_line(header_cell))
        
        for idx, row_data in enumerate(data_rows):
            pdf.set_text_color(35, 35, 35)
            row = table.row()
            for cell_text in row_data:
                row(text=_clean_line(cell_text))
    
    pdf.ln(4)


def generate_report_pdf(text: str, title: str) -> str:
    try:
        markdown_text = text or ""

        pdf = PDF("Reporte de Auditoria IA - ProFuturo")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_margins(15, 20, 15)
        pdf.add_page()

        pdf.set_text_color(0, 80, 160)
        pdf.set_font("Helvetica", "B", 15)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 9, _clean_line(title), align="C")
        pdf.ln(2)

        pdf.set_draw_color(0, 80, 160)
        pdf.set_line_width(0.4)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(4)

        lines = markdown_text.splitlines()
        index = 0

        while index < len(lines):
            raw_line = lines[index].rstrip()

            if not raw_line.strip():
                pdf.ln(2)
                index += 1
                continue

            is_table_header = (raw_line.count("|") >= 2 and 
                             index + 1 < len(lines) and 
                             _looks_like_table_separator(lines[index + 1]))

            if is_table_header:
                table_lines = [raw_line]
                index += 2
                while index < len(lines) and lines[index].count("|") >= 2:
                    if _looks_like_table_separator(lines[index]):
                        index += 1
                        continue
                    table_lines.append(lines[index])
                    index += 1

                parsed_rows = []
                for table_line in table_lines:
                    cells = [c.strip() for c in table_line.strip().strip("|").split("|")]
                    parsed_rows.append(cells)
                
                _render_table(pdf, parsed_rows)
                continue

            cleaned = _clean_line(raw_line)
            if not cleaned:
                index += 1
                continue

            if cleaned == "---":
                pdf.set_draw_color(190, 190, 190)
                pdf.set_line_width(0.2)
                pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
                pdf.ln(3)
                index += 1
                continue

            if raw_line.lstrip().startswith("#"):
                pdf.set_text_color(0, 80, 160)
                pdf.set_font("Helvetica", "B", 12)
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 8, cleaned)
                pdf.ln(1)
                pdf.set_text_color(35, 35, 35)
                pdf.set_font("Helvetica", "", 10)
            else:
                pdf.set_text_color(35, 35, 35)
                pdf.set_font("Helvetica", "", 10)
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 6, html.unescape(cleaned))

            index += 1

        pdf_bytes = pdf.output(dest="S")
        if isinstance(pdf_bytes, str):
            pdf_bytes = pdf_bytes.encode("latin-1", errors="ignore")
        return base64.b64encode(pdf_bytes).decode("utf-8")
    except Exception:
        return ""
