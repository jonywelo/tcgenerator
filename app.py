import os
import io
from flask import Flask, request, send_file, jsonify
import pdfplumber
import re
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from langdetect import detect
from datetime import datetime

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
PORT = int(os.environ.get('PORT', 5000))

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

    def extract_tc_from_pdf(self, pdf_bytes):
        """Extrae SOLO TERMS & CONDITIONS sin basura"""
        try:
            pdf_file = io.BytesIO(pdf_bytes)
            full_text = ""
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    full_text += (page.extract_text() or "") + "\n"
            
            # Busca "TERMS & CONDITIONS"
            if "TERMS & CONDITIONS" in full_text:
                start = full_text.find("TERMS & CONDITIONS")
                extracted = full_text[start:]
            else:
                extracted = full_text
            
            # Corta en "By signing"
            if "By signing this contract" in extracted:
                end = extracted.find("By signing this contract")
                extracted = extracted[:end]
            
            return extracted.strip()
        except Exception as e:
            raise Exception(f"Error: {str(e)}")

    def transform_text(self, text, entity):
        self.detect_language(text)
        
        # PASO 1: Eliminar líneas completas con datos operador
        lines = text.split('\n')
        cleaned = []
        skip_terms = ['VAT:', 'DE 365 809 939', 'DYFKEL', 'Ref. ID:', 
                      'Prepared for:', 'Aircraft:', 'Dear ', 'Thank you',
                      'Charter Agreement', 'Company:', '@', 'https://', 'www.']
        
        for line in lines:
            if not any(term in line for term in skip_terms):
                cleaned.append(line)
        
        text = '\n'.join(cleaned)
        
        # PASO 2: FSH → The Operator
        text = re.sub(r'\bFSH\b', 'The Operator', text, flags=re.IGNORECASE)
        
        # PASO 3: Eliminar emails (excepto Welojets)
        text = re.sub(r'[a-zA-Z0-9._%+-]+@(?!welojets)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', text)
        
        # PASO 4: Eliminar teléfonos
        text = re.sub(r'(?:Phone|Fax|Tel):\s*[\+\d\s\(\)\-]+', '', text, flags=re.IGNORECASE)
        
        # PASO 5: Cancelaciones - duplicar %
        def fix_pct(m):
            pct = int(m.group(1))
            if pct == 0: return "15%"
            if pct == 100: return "100%"
            return f"{pct * 2}%"
        
        text = re.sub(r'(\d+)%\s+(?:after|if|less|for)', fix_pct, text, flags=re.IGNORECASE)
        
        # PASO 6: Credit card fee
        text = re.sub(r'credit\s+card\s+fee[:\s]+\d+%', 'credit card fee: 5%', text, flags=re.IGNORECASE)
        
        # PASO 7: Governing Law
        repl = 'Madrid, Spain' if entity == 'SL' else 'Florida, USA'
        text = re.sub(r'(?:governing|applicable)\s+law[:\s]+[^\n.]+',
                      f'Governing Law: {repl}', text, flags=re.IGNORECASE)
        
        # Limpia espacios
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        
        return text.strip()

    def generate_pdf(self, text, entity):
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1.2*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        
        notice_style = ParagraphStyle('Notice', parent=styles['Normal'], fontName='Helvetica-Bold',
                                     textColor=colors.red, fontSize=10, leading=13,
                                     alignment=TA_JUSTIFY, spaceAfter=16)
        normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontName='Helvetica',
                                     fontSize=9, leading=11, alignment=TA_JUSTIFY, spaceAfter=10)
        gdpr_style = ParagraphStyle('GDPR', parent=styles['Normal'], fontName='Helvetica-Oblique',
                                   fontSize=8, leading=10, alignment=TA_JUSTIFY, spaceAfter=8)
        
        story = []
        
        # NOTICE (rojo y negrita)
        notice_txt = "NOTICE: Unless otherwise agreed in writing by Welojets and the Customer, the flight will be 100% confirmed only upon simultaneous receipt of payment (must be credited to our bank account to be considered paid) and a signed contract. A signed contract alone does not guarantee the flight or the availability of the aircraft." if self.lang == 'en' else "AVISO: A menos que se acuerde lo contrario por escrito entre Welojets y el Cliente, el vuelo se confirmará al 100% únicamente previa la recepción simultánea del pago (debe estar acreditado en nuestra cuenta bancaria para considerarse pagado) y un contrato firmado."
        
        story.append(Paragraph(notice_txt, notice_style))
        story.append(Spacer(1, 0.25*inch))
        
        # TÉRMINOS
        for line in text.split('\n'):
            line = line.strip()
            if line and len(line) > 2:
                story.append(Paragraph(line, normal_style))
        
        story.append(PageBreak())
        
        # WHEREAS
        whereas_en = "WHEREAS: Client desires that Welojets act as Client's agent in arranging air transportation to be furnished to Client by one or more licensed air carriers (hereinafter referred to as \"Carrier\") under applicable regulations of the United States Federal Aviation Administration (FAA) and Department of Transportation (DOT) and/or EASA and/or equivalent foreign aeronautical authorities. For scheduled service, once a Client has agreed to the terms herein and paid for a flight, Welojets shall be authorized to purchase the flight from Carrier on Client's behalf (inclusive of all members of Client's party) and this agreement shall be binding as to each flight arranged by Welojets. For charter flights, Welojets will present a quote and a photograph of the type of aircraft to be used for the Client's flights. Once Client has confirmed his/her/its acceptance of a charter itinerary and price quote provided by Welojets, Welojets shall be authorized, as Client's agent, to enter into a charter contract with Carrier in the name and on the behalf of Client. Carriers are obligated to operate Flights in accordance with applicable EASA or U.S. or foreign laws, rules and regulations, and Carrier will have exclusive operational control of the aircraft at all times. CLIENT ACKNOWLEDGES AND AGREES THAT WELOJETS ACTS ONLY AS AN AGENT OF CLIENT FOR THE ARRANGEMENT OF AIR TRANSPORTATION AS DESCRIBED HEREIN, AND THAT WELOJETS DOES NOT OWN OR OPERATE ANY AIRCRAFT. This Agreement shall remain in full force for each flight arranged by Welojets until the Agreement is cancelled in writing by either party (term expires 10 days after the service/flight(s) are completed). This Agreement will be supplemented for each specific charter flight (or series of flights) by a separate \"Charter Quote\", which will include the flight details, pricing, and other applicable information and payment confirmation."
        
        whereas_es = "CONSIDERANDO: El Cliente desea que Welojets actúe como agente del Cliente en la organización de servicios de transporte aéreo proporcionados por uno o más transportistas aéreos autorizados conforme a las regulaciones aplicables de la Administración Federal de Aviación (FAA) y del Departamento de Transporte (DOT) y/o EASA y/o autoridades aeronáuticas extranjeras equivalentes."
        
        whereas = whereas_es if self.lang == 'es' else whereas_en
        story.append(Paragraph(whereas, normal_style))
        story.append(Spacer(1, 0.2*inch))
        
        # GDPR
        gdpr_en = "We inform you, as provided in the GDPR and the LOPDGDD, that WELOJETS AIR MOBILITY, S.L. collects and processes your personal data, applying the technical and organizational measures that guarantee their confidentiality, for the purpose of managing the hiring and services provided in accordance with the relationship that links us. For these purposes, you give your consent and authorization for this processing. We will retain your personal data collected for the time necessary to manage the relationship that links us. You may exercise your rights of access, rectification, deletion, limitation, portability, and opposition by contacting the Controller at Conde de Aranda nº10 piso 1 derecha, Madrid, 28001, Madrid, or by sending an email to fly@welojets.com."
        
        gdpr_es = "Le informamos, conforme a lo dispuesto en el RGPD y la LOPDGDD, que WELOJETS AIR MOBILITY, S.L. recaba y trata sus datos personales, aplicando las medidas técnicas y organizativas que garantizan su confidencialidad, con la finalidad de gestionar la contratación y prestación de servicios de conformidad con la relación que nos vincula."
        
        gdpr = gdpr_es if self.lang == 'es' else gdpr_en
        story.append(Paragraph(gdpr, gdpr_style))
        
        doc.build(story, onFirstPage=self._add_header, onLaterPages=self._add_header)
        buffer.seek(0)
        return buffer

    def _add_header(self, canvas, doc):
        logo_paths = [
            os.path.join(os.path.dirname(__file__), 'static', 'logo_welojets.png'),
            '/opt/render/project/src/static/logo_welojets.png',
            '/app/static/logo_welojets.png',
        ]
        for logo_path in logo_paths:
            try:
                if os.path.exists(logo_path):
                    img = Image(logo_path, width=1.3*inch, height=1.3*inch)
                    x = (letter[0] - 1.3*inch) / 2
                    y = letter[1] - 1.0*inch
                    img.drawOn(canvas, x, y)
                    break
            except:
                pass

HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>T&C Generator</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}.container{background:white;border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,0.3);padding:40px;max-width:500px;width:100%}h1{color:#333;font-size:28px;text-align:center}label{display:block;color:#333;font-weight:600;margin:20px 0 10px;font-size:14px}.upload-area{border:2px dashed #667eea;border-radius:8px;padding:30px;text-align:center;cursor:pointer;background:#f8f9ff}.upload-area:hover{border-color:#764ba2}.upload-icon{font-size:32px}#pdf-input{display:none}.file-name{color:#10b981;margin-top:8px;font-size:13px}.entity-group{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:20px 0}.radio-option input{display:none}.radio-label{display:block;padding:12px;border:2px solid #e0e0e0;border-radius:6px;cursor:pointer;font-weight:500}.radio-option input:checked+.radio-label{border-color:#667eea;background:#f0f2ff;color:#667eea}button{width:100%;padding:14px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;border-radius:6px;font-size:16px;font-weight:600;cursor:pointer;margin-top:20px}.error{background:#fee;border-left:4px solid #f00;color:#c33;padding:12px;margin-top:12px;font-size:13px;display:none}.error.show{display:block}</style></head><body><div class="container"><h1>T&C Generator</h1><form id="tc-form" enctype="multipart/form-data"><label>Carga PDF</label><div class="upload-area" id="upload-area"><div class="upload-icon">📄</div><div>Arrastra aquí</div></div><input type="file" id="pdf-input" accept=".pdf" required><div class="file-name" id="file-name"></div><label>Entidad</label><div class="entity-group"><div class="radio-option"><input type="radio" id="entity-sl" name="entity" value="SL" checked><label for="entity-sl" class="radio-label">SL - Madrid</label></div><div class="radio-option"><input type="radio" id="entity-llc" name="entity" value="LLC"><label for="entity-llc" class="radio-label">LLC - Florida</label></div></div><div class="error" id="error-message"></div><button type="submit">Descargar</button></form></div><script>const form=document.getElementById('tc-form');const uploadArea=document.getElementById('upload-area');const pdfInput=document.getElementById('pdf-input');const errorDiv=document.getElementById('error-message');uploadArea.addEventListener('click',()=>pdfInput.click());uploadArea.addEventListener('drop',(e)=>{e.preventDefault();pdfInput.files=e.dataTransfer.files;});pdfInput.addEventListener('change',()=>{if(pdfInput.files[0])document.getElementById('file-name').textContent='✓ '+pdfInput.files[0].name;});form.addEventListener('submit',async(e)=>{e.preventDefault();const formData=new FormData();formData.append('pdf',pdfInput.files[0]);formData.append('entity',document.querySelector('input[name="entity"]:checked').value);try{const r=await fetch('/api/process-pdf-download',{method:'POST',body:formData});if(!r.ok)throw new Error('Error');const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`TC_${new Date().toISOString().slice(0,10)}.pdf`;a.click();}catch(e){errorDiv.textContent='❌ '+e.message;errorDiv.classList.add('show');}});</script></body></html>"""

@app.route('/')
def index():
    return HTML

@app.route('/api/process-pdf-download', methods=['POST'])
def process_pdf():
    try:
        if 'pdf' not in request.files:
            return jsonify({'error': 'No PDF'}), 400
        pdf_file = request.files['pdf']
        entity = request.form.get('entity', 'SL')
        pdf_bytes = pdf_file.read()
        processor = TCProcessor()
        tc_text = processor.extract_tc_from_pdf(pdf_bytes)
        transformed_text = processor.transform_text(tc_text, entity)
        pdf_buffer = processor.generate_pdf(transformed_text, entity)
        return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True,
                        download_name=f'TC_Modified_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False)
