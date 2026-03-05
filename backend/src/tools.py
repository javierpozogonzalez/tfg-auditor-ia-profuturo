import base64
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

    html_content = markdown.markdown(text or "", extensions=['tables'])

    pdf = PDF()
    pdf.set_margins(20, 25, 20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(0, 10, clean_title, align="C")
    pdf.ln(8)

    pdf.set_font("Helvetica", size=10)
    pdf.write_html(html_content)

    pdf_bytes = pdf.output(dest="S")
    if isinstance(pdf_bytes, str):
        pdf_bytes = pdf_bytes.encode("latin-1", errors="ignore")
    return base64.b64encode(pdf_bytes).decode("utf-8")
