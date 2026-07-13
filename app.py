import os
import io
from flask import Flask, request, send_file, jsonify
import pdfplumber
import re
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from langdetect import detect
from datetime import datetime

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

PORT = int(os.environ.get('PORT', 5000))
LOGO_PATH = os.path.join(os.path.dirname(__file__), 'static', 'logo_welojets.png')

class TCProcessor:
    def __init__(self):
        self.lang = 'en'

    def detect_language(self, text):
        try:
            self.lang = detect(text[:500])
            if self.lang not in ['en', 'es']:
                self.lang = 'en'
        except:
            self.lang = 'en'
        return self.lang

    def extract_tc_from_pdf(self, pdf_bytes):
        try:
            pdf_file = io.BytesIO(pdf_bytes)
            text_content = ""
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    text_content += page_text + "\n"
                tc_start_idx = max(
                    text_content.lower().find('terms'),
                    text_content.lower().find('conditions'),
                    text_content.lower().find('términos'),
                    text_content.lower().find('condiciones')
                )
                if tc_start_idx > 0:
                    text_content = text_content[tc_start_idx:]
            return text_content
        except Exception as e:
            raise Exception(f"Error extrayendo PDF: {str(e)}")

    def transform_text(self, text, entity):
        self.detect_language(text)
        operator_patterns = [r'\b[Vv]istajet\b', r'\b[Nn]etjets\b', r'\b[Ae]xecutive\b', r'\b[Cc]arrier\b(?!\s+\()', r'\b[Oo]perator\b']
        for pattern in operator_patterns:
            if self.lang == 'es':
                text = re.sub(pattern, 'El Operador', text, flags=re.IGNORECASE)
            else:
                text = re.sub(pattern, 'The Operator', text, flags=re.IGNORECASE)
        text = self._transform_cancellations(text)
        text = self._transform_payments(text, entity)
        text = self._transform_governing_law(text, entity)
        text = self._remove_operator_contacts(text)
        return text

    def _transform_cancellations(self, text):
        def replace_percentage(match):
            percentage = int(match.group(1))
            if percentage == 0:
                return f"{15}%"
            elif percentage == 100:
                return match.group(0)
            else:
                return f"{percentage * 2}%"
        patterns = [r'(\d+)%\s+(?:of\s+)?(?:cancellation|refund)', r'cancellation\s+fee:?\s+(\d+)%', r'(?:cancelación|reembolso):?\s+(\d+)%']
        for pattern in patterns:
            text = re.sub(pattern, replace_percentage, text, flags=re.IGNORECASE)
        return text

    def _transform_payments(self, text, entity):
        text = re.sub(r'credit\s+card\s+fee:?\s+\d+%', 'credit card fee: 5%', text, flags=re.IGNORECASE)
        text = re.sub(r'comisión\s+(?:de\s+)?tarjeta:?\s+\d+%', 'comisión de tarjeta: 5%', text, flags=re.IGNORECASE)
        return text

    def _transform_governing_law(self, text, entity):
        if entity == 'SL':
            replacement = 'Madrid, Spain'
        elif entity == 'LLC':
            replacement = 'Florida, USA'
        else:
            return text
        text = re.sub(r'(?:governing\s+law|applicable\s+law|jurisdiction):?\s+[^.\n]+', f'Governing Law: {replacement}', text, flags=re.IGNORECASE)
        return text

    def _remove_operator_contacts(self, text):
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@(?!welojets\.com)[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', text)
        text = re.sub(r'\+\d{1,3}\s?[\d\s\-\(\)]{7,}', '', text)
        text = re.sub(r'\(\d{3}\)\s?\d{3}-\d{4}', '', text)
        return text

    def generate_pdf(self, text, entity):
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1.35*inch)
        styles = getSampleStyleSheet()
        notice_style = ParagraphStyle('Notice', parent=styles['Normal'], fontName='Helvetica-Bold', textColor=colors.red, fontSize=9, leading=12.5, alignment=TA_JUSTIFY, spaceAfter=14)
        normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=12.5, alignment=TA_JUSTIFY, spaceAfter=8)
        gdpr_style = ParagraphStyle('GDPR', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=8, leading=11, alignment=TA_JUSTIFY, spaceAfter=8)
        story = []
        if self.lang == 'es':
            notice_text = "Aviso: A menos que se acuerde lo contrario por escrito entre Welojets y el Cliente, el vuelo se confirmará al 100% únicamente previa la recepción simultánea del pago (debe estar acreditado en nuestra cuenta bancaria para considerarse pagado) y un contrato firmado. Un contrato firmado solo no garantiza el vuelo ni la disponibilidad de la aeronave."
        else:
            notice_text = "Notice: Unless otherwise agreed in writing by Welojets and the Customer, the flight will be 100% confirmed only upon simultaneous receipt of payment (Must be credited to our bank account to be considered paid) and a signed contract. A signed contract alone does not guarantee the flight or the availability of the aircraft."
        story.append(Paragraph(notice_text, notice_style))
        story.append(Spacer(1, 0.2*inch))
        for line in text.split('\n'):
            if line.strip():
                story.append(Paragraph(line.strip(), normal_style))
            else:
                story.append(Spacer(1, 0.1*inch))
        story.append(Spacer(1, 0.3*inch))
        if self.lang == 'es':
            whereas_text = "<b>CONSIDERANDO:</b> El Cliente desea que Welojets actúe como su agente en la contratación de servicios de transporte aéreo proporcionado por uno o más transportistas aéreos autorizados."
        else:
            whereas_text = "<b>WHEREAS:</b> Client desires that Welojets act as Client's agent in arranging air transportation to be furnished by licensed air carriers."
        story.append(Paragraph(whereas_text, normal_style))
        doc.build(story, onFirstPage=self._add_header, onLaterPages=self._add_header)
        buffer.seek(0)
        return buffer

    def _add_header(self, canvas, doc):
        if os.path.exists(LOGO_PATH):
            img = Image(LOGO_PATH, width=1.25*inch, height=1.25*inch)
            img.hAlign = 'CENTER'
            x = (letter[0] - 1.25*inch) / 2
            y = letter[1] - 0.85*inch
            img.drawOn(canvas, x, y)

HTML = """<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>T&C Generator - Welojets</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}.container{background:white;border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,0.3);padding:40px;max-width:500px;width:100%}h1{color:#333;font-size:28px;text-align:center}.subtitle{color:#666;text-align:center;margin-bottom:30px;font-size:14px}.form-group{margin-bottom:24px}label{display:block;color:#333;font-weight:600;margin-bottom:10px;font-size:14px}.upload-area{border:2px dashed #667eea;border-radius:8px;padding:30px;text-align:center;cursor:pointer;transition:all 0.3s ease;background:#f8f9ff}.upload-area:hover{border-color:#764ba2;background:#f0f2ff}.upload-area.dragover{border-color:#764ba2;background:#e9ecff}.upload-icon{font-size:32px;margin-bottom:8px}.upload-text{color:#667eea;font-weight:600}.upload-subtext{color:#999;font-size:12px}#pdf-input{display:none}.file-name{color:#10b981;margin-top:8px;font-size:13px;font-weight:500}.entity-group{display:grid;grid-template-columns:1fr 1fr;gap:12px}.radio-option input{display:none}.radio-label{display:block;padding:12px;border:2px solid #e0e0e0;border-radius:6px;text-align:center;cursor:pointer;font-weight:500;font-size:13px}.radio-option input:checked+.radio-label{border-color:#667eea;background:#f0f2ff;color:#667eea}button{width:100%;padding:14px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;border-radius:6px;font-size:16px;font-weight:600;cursor:pointer}.error{background:#fee;border-left:4px solid #f00;color:#c33;padding:12px;margin-top:12px;font-size:13px;display:none}.error.show{display:block}</style></head><body><div class="container"><h1>T&C Generator</h1><p class="subtitle">Procesa contratos de operadores</p><form id="tc-form" enctype="multipart/form-data"><div class="form-group"><label>Carga tu PDF</label><div class="upload-area" id="upload-area"><div class="upload-icon">📄</div><div class="upload-text">Arrastra aquí</div></div><input type="file" id="pdf-input" accept=".pdf" required><div class="file-name" id="file-name"></div></div><div class="form-group"><label>Entidad</label><div class="entity-group"><div class="radio-option"><input type="radio" id="entity-sl" name="entity" value="SL" checked><label for="entity-sl" class="radio-label">SL - Madrid</label></div><div class="radio-option"><input type="radio" id="entity-llc" name="entity" value="LLC"><label for="entity-llc" class="radio-label">LLC - Florida</label></div></div></div><div class="error" id="error-message"></div><button type="submit">Procesar y descargar</button></form></div><script>const form=document.getElementById('tc-form');const uploadArea=document.getElementById('upload-area');const pdfInput=document.getElementById('pdf-input');const errorDiv=document.getElementById('error-message');uploadArea.addEventListener('click',()=>pdfInput.click());uploadArea.addEventListener('drop',(e)=>{e.preventDefault();pdfInput.files=e.dataTransfer.files;});pdfInput.addEventListener('change',()=>{if(pdfInput.files.length>0)document.getElementById('file-name').textContent='✓ '+pdfInput.files[0].name;});form.addEventListener('submit',async(e)=>{e.preventDefault();if(!pdfInput.files.length){errorDiv.textContent='❌ Selecciona un PDF';errorDiv.classList.add('show');return;}const formData=new FormData();formData.append('pdf',pdfInput.files[0]);formData.append('entity',document.querySelector('input[name="entity"]:checked').value);try{const response=await fetch('/api/process-pdf-download',{method:'POST',body:formData});if(!response.ok)throw new Error('Error');const blob=await response.blob();const url=window.URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`TC_Modified_${new Date().toISOString().slice(0,10)}.pdf`;a.click();window.URL.revokeObjectURL(url);}catch(error){errorDiv.textContent='❌ Error: '+error.message;errorDiv.classList.add('show');}});</script></body></html>"""

@app.route('/')
def index():
    return HTML

@app.route('/api/process-pdf-download', methods=['POST'])
def process_pdf():
    try:
        if 'pdf' not in request.files:
            return jsonify({'error': 'No PDF provided'}), 400
        pdf_file = request.files['pdf']
        entity = request.form.get('entity', 'SL')
        if not pdf_file or pdf_file.filename == '':
            return jsonify({'error': 'Invalid file'}), 400
        pdf_bytes = pdf_file.read()
        processor = TCProcessor()
        tc_text = processor.extract_tc_from_pdf(pdf_bytes)
        transformed_text = processor.transform_text(tc_text, entity)
        pdf_buffer = processor.generate_pdf(transformed_text, entity)
        return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, download_name=f'TC_Modified_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False)
