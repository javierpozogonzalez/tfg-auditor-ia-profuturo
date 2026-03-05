import base64
import re
from fpdf import FPDF
import markdown


class PDF(FPDF):
    def header(self):
        self.set_fill_color(0, 80, 160)
        self.rect(0, 0, self.w, 22, style="F")
        self.set_y(6)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "ProFuturo - Informe de Auditoría Inteligente", align="C")
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_text_color(153, 153, 153)
        self.set_font("Helvetica", "I", 8)
        self.cell(
            0,
            8,
            f"Documento generado de forma autónoma por Auditor IA - Página {self.page_no()}",
            align="C",
        )


def generate_report_pdf(text: str, title: str) -> str:
    clean_title = (title or "Reporte de Auditoria IA - ProFuturo").replace("_", " ").strip()
    if not clean_title:
        clean_title = "Reporte de Auditoria IA - ProFuturo"

    markdown_text = text or ""
    markdown_text = markdown_text.replace("_", " ")
    markdown_text = re.sub(r'\*\*\s+', '**', markdown_text)
    markdown_text = re.sub(r'\s+\*\*', '**', markdown_text)

    html_raw = markdown.markdown(markdown_text, extensions=['tables'])

    html_raw = html_raw.replace('<h1>', '<h1 align="center"><font color="#0050A0">')
    html_raw = html_raw.replace('</h1>', '</font></h1>')
    html_raw = html_raw.replace('<h2>', '<h2><font color="#0050A0">')
    html_raw = html_raw.replace('</h2>', '</font></h2>')
    html_raw = html_raw.replace('<h3>', '<h3><font color="#0050A0">')
    html_raw = html_raw.replace('</h3>', '</font></h3>')

    html_final = f'<font face="Helvetica" color="#333333">{html_raw}</font>'

    pdf = PDF()
    pdf.set_margins(left=20, top=25, right=20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_text_color(0, 80, 160)
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 10, clean_title, align="C")
    pdf.ln(10)

    pdf.write_html(html_final)

    pdf_bytes = pdf.output(dest="S")
    if isinstance(pdf_bytes, str):
        pdf_bytes = pdf_bytes.encode("latin-1", errors="ignore")
    return base64.b64encode(pdf_bytes).decode("utf-8")
