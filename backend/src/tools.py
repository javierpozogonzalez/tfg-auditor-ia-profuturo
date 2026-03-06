import base64
import markdown
import os
from fpdf import FPDF


def generate_report_pdf(text: str, title: str) -> str:
    title_clean = title.replace("_", " ")
    html_content = markdown.markdown(text, extensions=["tables"])
    
    pdf = FPDF()
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    
    logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "logo.png")
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=8, w=30)
    
    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(0, 8, txt=title_clean, align="C")
    pdf.ln(10)
    
    pdf.set_font("Helvetica", size=10)
    pdf.write_html(html_content)
    
    pdf_bytes = pdf.output(dest="S")
    if isinstance(pdf_bytes, str):
        pdf_bytes = pdf_bytes.encode("latin-1", errors="ignore")
    return base64.b64encode(pdf_bytes).decode("utf-8")
