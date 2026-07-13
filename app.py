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
        """Extrae T&C manteniendo orden lineal izquierda-derecha, arriba-abajo"""
        try:
            pdf_file = io.BytesIO(pdf_bytes)
            text_content = ""
            
            with pdfplumber.open(pdf_file) as pdf:
                # Buscar página con Terms & Conditions
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    
                    # Si encontramos T&C, usar extracción por palabras ordenadas
                    if 'terms' in page_text.lower() or 'conditions' in page_text.lower():
                        words = page.extract_words()
                        if words:
                            # Ordenar palabras por: posición vertical (top), luego horizontal (x0)
                            sorted_words = sorted(words, key=lambda w: (round(w['top'] / 10) * 10, w['x0']))
                            
                            current_line_y = None
                            for word in sorted_words:
                                word_y = round(word['top'] / 10) * 10
                                
                                # Nueva línea si cambió la posición vertical
                                if current_line_y is not None and word_y != current_line_y:
                                    text_content += "\n"
                                
                                text_content += word['text'] + " "
                                current_line_y = word_y
                        else:
                            text_content += page_text
                    else:
                        text_content += page_text + "\n"
            
            return text_content
        except Exception as e:
            raise Exception(f"Error: {str(e)}")

    def transform_text(self, text, entity):
        self.detect_language(text)
        
        # 1. Reemplazar operador
        patterns = [r'\b[Vv]istajet\b', r'\b[Nn]etjets\b', r'\b[Ff]sh\b', r'\b[Aa]viation\b']
        repl = 'El Operador' if self.lang == 'es' else 'The Operator'
        for p in patterns:
            text = re.sub(p, repl, text, flags=re.IGNORECASE)
        
        # 2. Cancelaciones
        def fix_pct(m):
            pct = int(m.group(1))
            if pct == 0: return "15%"
            if pct == 100: return m.group(0)
            return f"{pct * 2}%"
        text = re.sub(r'(\d+)%\s+(?:of\s+)?cancellation', fix_pct, text, flags=re.IGNORECASE)
        
        # 3. Credit card fee
        text = re.sub(r'credit\s+card\s+fee:?\s+\d+%', 'credit card fee: 5%', text, flags=re.IGNORECASE)
        
        # 4. Governing law
        repl = 'Madrid, Spain' if entity == 'SL' else 'Florida, USA'
        text = re.sub(r'(?:governing\s+law|applicable\s+law):?\s+[^.\n]+', f'Governing Law: {repl}', text, flags=re.IGNORECASE)
        
        # 5. Eliminar contactos operador
        text = re.sub(r'[A-Za-z0-9._%+-]+@(?!welojets)[A-Za-z0-9.-]+\.[a-z]{2,}', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\+\d{1,3}[\d\s\-()]{7,}', '', text)
        text = re.sub(r'FSH\s*Aviation.*?www\.fsh\.de', '', text, flags=re.IGNORECASE | re.DOTALL)
        
        return text

    def generate_pdf(self, text, entity):
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        
        notice_style = ParagraphStyle('Notice', parent=styles['Normal'], fontName='Helvetica-Bold', 
                                     textColor=colors.red, fontSize=9, leading=12, alignment=TA_JUSTIFY, spaceAfter=14)
        normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontName='Helvetica', 
                                     fontSize=9, leading=12, alignment=TA_JUSTIFY, spaceAfter=8)
        gdpr_style = ParagraphStyle('GDPR', parent=styles['Normal'], fontName='Helvetica-Oblique',
                                   fontSize=8, leading=11, alignment=TA_JUSTIFY, spaceAfter=8)
        
        story = []
        
        # Notice
        notice_txt = "Aviso: A menos que se acuerde lo contrario por escrito entre Welojets y el Cliente, el vuelo se confirmará al 100% únicamente previa la recepción simultánea del pago (debe estar acreditado en nuestra cuenta bancaria para considerarse pagado) y un contrato firmado. Un contrato firmado solo no garantiza el vuelo ni la disponibilidad de la aeronave." if self.lang == 'es' else "Notice: Unless otherwise agreed in writing by Welojets and the Customer, the flight will be 100% confirmed only upon simultaneous receipt of payment (Must be credited to our bank account to be considered paid) and a signed contract. A signed contract alone does not guarantee the flight or the availability of the aircraft."
        story.append(Paragraph(notice_txt, notice_style))
        story.append(Spacer(1, 0.2*inch))
        
        # Content
        for line in text.split('\n'):
            if line.strip():
                story.append(Paragraph(line.strip(), normal_style))
            else:
                story.append(Spacer(1, 0.05*inch))
        
        story.append(Spacer(1, 0.3*inch))
        
        # WHEREAS
        whereas = "CONSIDERANDO: El Cliente desea que Welojets actúe como su agente en la contratación de servicios de transporte aéreo proporcionados por uno o más transportistas aéreos autorizados conforme a las regulaciones de la FAA, DOT y EASA. Para vuelos charter, una vez que el Cliente ha confirmado su aceptación de la cotización presentada por Welojets, Welojets estará autorizado como agente del Cliente para celebrar un contrato charter con el transportista en nombre del Cliente. EL CLIENTE RECONOCE Y ACEPTA QUE WELOJETS ACTÚA ÚNICAMENTE COMO AGENTE DEL CLIENTE Y QUE WELOJETS NO POSEE NI OPERA AERONAVE ALGUNA." if self.lang == 'es' else "WHEREAS: Client desires that Welojets act as Client's agent in arranging air transportation furnished by licensed air carriers under FAA, DOT and EASA regulations. For charter flights, once Client has confirmed acceptance of Welojets' quote, Welojets shall be authorized to enter into a charter contract with Carrier on Client's behalf. CLIENT ACKNOWLEDGES THAT WELOJETS ACTS ONLY AS AN AGENT AND DOES NOT OWN OR OPERATE ANY AIRCRAFT."
        story.append(Paragraph(whereas, normal_style))
        story.append(Spacer(1, 0.2*inch))
        
        # GDPR
        gdpr = "De conformidad con la RGPD y LOPDGDD, WELOJETS AIR MOBILITY, S.L. recopila sus datos personales con medidas de confidencialidad para gestionar servicios. Puede ejercer sus derechos contactando Conde de Aranda nº10, Madrid, 28001, o fly@welojets.com." if self.lang == 'es' else "Per GDPR regulations, WELOJETS AIR MOBILITY, S.L. processes your data with confidentiality measures. You may exercise your rights by contacting Conde de Aranda nº10, Madrid, 28001, or fly@welojets.com."
        story.append(Paragraph(gdpr, gdpr_style))
        
        doc.build(story, onFirstPage=self._add_header, onLaterPages=self._add_header)
        buffer.seek(0)
        return buffer

    def _add_header(self, canvas, doc):
        logo_paths = [
            os.path.join(os.path.dirname(__file__), 'static', 'logo_welojets.png'),
            '/opt/render/project/src/static/logo_welojets.png',
            'static/logo_welojets.png',
        ]
        for logo_path in logo_paths:
            if os.path.exists(logo_path):
                try:
                    img = Image(logo_path, width=1.25*inch, height=1.25*inch)
                    x = (letter[0] - 1.25*inch) / 2
                    y = letter[1] - 1.0*inch
                    img.drawOn(canvas, x, y)
                except:
                    pass
                break

HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>T&C Generator</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}.container{background:white;border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,0.3);padding:40px;max-width:500px;width:100%}h1{color:#333;font-size:28px;text-align:center}label{display:block;color:#333;font-weight:600;margin:20px 0 10px;font-size:14px}.upload-area{border:2px dashed #667eea;border-radius:8px;padding:30px;text-align:center;cursor:pointer;background:#f8f9ff}#pdf-input{display:none}.file-name{color:#10b981;margin-top:8px;font-size:13px}.entity-group{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:20px 0}.radio-option input{display:none}.radio-label{display:block;padding:12px;border:2px solid #e0e0e0;border-radius:6px;text-align:center;cursor:pointer;font-weight:500;font-size:13px}.radio-option input:checked+.radio-label{border-color:#667eea;background:#f0f2ff;color:#667eea}button{width:100%;padding:14px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;border-radius:6px;font-size:16px;font-weight:600;cursor:pointer;margin-top:20px}.error{background:#fee;border-left:4px solid #f00;color:#c33;padding:12px;margin-top:12px;font-size:13px;display:none}.error.show{display:block}</style></head><body><div class="container"><h1>T&C Generator</h1><form id="tc-form" enctype="multipart/form-data"><label>Carga tu PDF</label><div class="upload-area" id="upload-area"><div style="font-size:32px">📄</div><div>Arrastra aquí</div></div><input type="file" id="pdf-input" accept=".pdf" required><div class="file-name" id="file-name"></div><label>Entidad</label><div class="entity-group"><div class="radio-option"><input type="radio" id="entity-sl" name="entity" value="SL" checked><label for="entity-sl" class="radio-label">SL - Madrid</label></div><div class="radio-option"><input type="radio" id="entity-llc" name="entity" value="LLC"><label for="entity-llc" class="radio-label">LLC - Florida</label></div></div><div class="error" id="error-message"></div><button type="submit">Descargar PDF</button></form></div><script>const form=document.getElementById('tc-form');const uploadArea=document.getElementById('upload-area');const pdfInput=document.getElementById('pdf-input');const errorDiv=document.getElementById('error-message');uploadArea.addEventListener('click',()=>pdfInput.click());uploadArea.addEventListener('drop',(e)=>{e.preventDefault();pdfInput.files=e.dataTransfer.files;});pdfInput.addEventListener('change',()=>{if(pdfInput.files[0])document.getElementById('file-name').textContent='✓ '+pdfInput.files[0].name;});form.addEventListener('submit',async(e)=>{e.preventDefault();const formData=new FormData();formData.append('pdf',pdfInput.files[0]);formData.append('entity',document.querySelector('input[name="entity"]:checked').value);try{const r=await fetch('/api/process-pdf-download',{method:'POST',body:formData});if(!r.ok)throw new Error('Error');const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`TC_${new Date().toISOString().slice(0,10)}.pdf`;a.click();}catch(error){errorDiv.textContent='❌ '+error.message;errorDiv.classList.add('show');}});</script></body></html>"""

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
