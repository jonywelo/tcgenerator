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
from datetime import datetime

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
PORT = int(os.environ.get('PORT', 5000))

class TCExtractor:
    def __init__(self, pdf_bytes):
        self.pdf_bytes = pdf_bytes
        self.text = ""

    def extract_and_order(self):
        """Extrae y ordena el texto correctamente usando coordenadas"""
        pdf_file = io.BytesIO(self.pdf_bytes)
        
        with pdfplumber.open(pdf_file) as pdf:
            # Extrae de todas las páginas
            chars_list = []
            
            for page_num, page in enumerate(pdf.pages):
                # Obtiene todos los caracteres con coordenadas
                for char in page.chars:
                    chars_list.append({
                        'text': char['text'],
                        'x0': char['x0'],
                        'top': char['top'],
                        'page': page_num
                    })
            
            # Ordena por: página, top (arriba-abajo), x0 (izquierda-derecha)
            chars_list.sort(key=lambda c: (c['page'], round(c['top'] / 10) * 10, c['x0']))
            
            # Reconstruye el texto
            current_line = ""
            current_top = None
            lines = []
            
            for char in chars_list:
                # Si cambió la línea (top cambió significativamente), guarda la línea
                if current_top is not None and abs(char['top'] - current_top) > 5:
                    if current_line.strip():
                        lines.append(current_line.strip())
                    current_line = char['text']
                    current_top = char['top']
                else:
                    current_line += char['text']
                    if current_top is None:
                        current_top = char['top']
            
            if current_line.strip():
                lines.append(current_line.strip())
            
            self.text = '\n'.join(lines)
        
        return self.text

    def extract_terms(self):
        """Extrae solo TERMS & CONDITIONS"""
        if "TERMS & CONDITIONS" not in self.text:
            raise Exception("No TERMS & CONDITIONS found")
        
        start = self.text.find("TERMS & CONDITIONS")
        extracted = self.text[start:]
        
        # Busca el final (antes de "By signing" o firma)
        end_markers = ["By signing this contract", "Both parties agree", "Date, Signature"]
        for marker in end_markers:
            if marker in extracted:
                end = extracted.find(marker)
                extracted = extracted[:end]
                break
        
        return extracted.strip()

    def transform_terms(self, entity):
        """Aplica transformaciones de Welojets"""
        text = self.extract_terms()
        
        # Limpia info del operador
        text = re.sub(r'(Industriestraße|Geschäftsführer|Deutsche Bank|IBAN|BIC|SWIFT|HRB|Amtsgericht).*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'VAT:?\s*DE\s*\d+\s*\d+\s*\d+', '', text)
        text = re.sub(r'sales@\S+\.\w+', '', text)
        text = re.sub(r'www\.\S+', '', text)
        
        # Duplica cancelaciones pero MÁXIMO 100%
        def fix_cancel(m):
            pct_str = m.group(1)
            try:
                pct = int(pct_str)
                new_pct = pct * 2
                # MÁXIMO 100%
                return f"{min(new_pct, 100)}%"
            except:
                return m.group(0)
        
        text = re.sub(r'(\d+)%\s+(?:of|after|if|for)', fix_cancel, text, flags=re.IGNORECASE)
        
        # Credit card fee
        text = re.sub(r'credit\s+card\s+fee[:\s]+\d+%', 'credit card fee: 5%', text, flags=re.IGNORECASE)
        
        # Governing Law
        repl = 'Madrid, Spain' if entity == 'SL' else 'Florida, USA'
        text = re.sub(r'(?:governing|applicable)\s+law[:\s]*[^\n.]*', f'Governing Law: {repl}', text, flags=re.IGNORECASE)
        
        # Limpia espacios
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        
        return text.strip()

class TCGenerator:
    def __init__(self, terms_text, entity):
        self.terms_text = terms_text
        self.entity = entity

    def generate_pdf(self):
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1.2*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()

        notice_style = ParagraphStyle('Notice', parent=styles['Normal'], fontName='Helvetica-Bold',
                                     textColor=colors.red, fontSize=10, leading=13,
                                     alignment=TA_JUSTIFY, spaceAfter=18)
        normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontName='Helvetica',
                                     fontSize=9, leading=11, alignment=TA_JUSTIFY, spaceAfter=9)
        heading_style = ParagraphStyle('Heading', parent=styles['Normal'], fontName='Helvetica-Bold',
                                      fontSize=9, leading=11, alignment=TA_JUSTIFY, spaceAfter=9)
        gdpr_style = ParagraphStyle('GDPR', parent=styles['Normal'], fontName='Helvetica-Oblique',
                                   fontSize=8, leading=10, alignment=TA_JUSTIFY)

        story = []

        notice_txt = "NOTICE: Unless otherwise agreed in writing by Welojets and the Customer, the flight will be 100% confirmed only upon simultaneous receipt of payment (must be credited to our bank account to be considered paid) and a signed contract. A signed contract alone does not guarantee the flight or the availability of the aircraft."
        story.append(Paragraph(notice_txt, notice_style))
        story.append(Spacer(1, 0.3*inch))

        # TÉRMINOS EXTRAÍDOS
        for line in self.terms_text.split('\n'):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 0.08*inch))
            elif line.isupper() and len(line) < 50:
                story.append(Paragraph(line, heading_style))
            else:
                story.append(Paragraph(line, normal_style))

        story.append(PageBreak())

        whereas = "WHEREAS: Client desires that Welojets act as Client's agent in arranging air transportation to be furnished to Client by one or more licensed air carriers (hereinafter referred to as \"Carrier\") under applicable regulations of the United States Federal Aviation Administration (FAA) and Department of Transportation (DOT) and/or EASA and/or equivalent foreign aeronautical authorities. For scheduled service, once a Client has agreed to the terms herein and paid for a flight, Welojets shall be authorized to purchase the flight from Carrier on Client's behalf (inclusive of all members of Client's party) and this agreement shall be binding as to each flight arranged by Welojets. For charter flights, Welojets will present a quote and a photograph of the type of aircraft to be used for the Client's flights. Once Client has confirmed his/her/its acceptance of a charter itinerary and price quote provided by Welojets, Welojets shall be authorized, as Client's agent, to enter into a charter contract with Carrier in the name and on the behalf of Client. Carriers are obligated to operate Flights in accordance with applicable EASA or U.S. or foreign laws, rules and regulations, and Carrier will have exclusive operational control of the aircraft at all times. CLIENT ACKNOWLEDGES AND AGREES THAT WELOJETS ACTS ONLY AS AN AGENT OF CLIENT FOR THE ARRANGEMENT OF AIR TRANSPORTATION AS DESCRIBED HEREIN, AND THAT WELOJETS DOES NOT OWN OR OPERATE ANY AIRCRAFT. This Agreement shall remain in full force for each flight arranged by Welojets until the Agreement is cancelled in writing by either party (term expires 10 days after the service/flight(s) are completed). This Agreement will be supplemented for each specific charter flight (or series of flights) by a separate \"Charter Quote\", which will include the flight details, pricing, and other applicable information and payment confirmation."
        story.append(Paragraph(whereas, normal_style))
        story.append(Spacer(1, 0.2*inch))

        gdpr = "We inform you, as provided in the GDPR and the LOPDGDD, that WELOJETS AIR MOBILITY, S.L. collects and processes your personal data, applying the technical and organizational measures that guarantee their confidentiality, for the purpose of managing the hiring and services provided in accordance with the relationship that links us. For these purposes, you give your consent and authorization for this processing. We will retain your personal data collected for the time necessary to manage the relationship that links us. You may exercise your rights of access, rectification, deletion, limitation, portability, and opposition by contacting the Controller at Conde de Aranda nº10 piso 1 derecha, Madrid, 28001, Madrid, or by sending an email to fly@welojets.com."
        story.append(Paragraph(gdpr, gdpr_style))

        doc.build(story, onFirstPage=self._add_header, onLaterPages=self._add_header)
        buffer.seek(0)
        return buffer

    def _add_header(self, canvas, doc):
        logo_paths = [
            'static/logo_welojets.png',
            os.path.join(os.path.dirname(__file__), 'static', 'logo_welojets.png'),
            '/app/static/logo_welojets.png',
            '/opt/render/project/src/static/logo_welojets.png',
        ]
        for logo_path in logo_paths:
            try:
                if os.path.exists(logo_path):
                    img = Image(logo_path, width=1.2*inch, height=1.2*inch)
                    x = (letter[0] - 1.2*inch) / 2
                    y = letter[1] - 0.95*inch
                    img.drawOn(canvas, x, y)
                    break
            except:
                pass

HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>T&C Generator</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}.container{background:white;border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,0.3);padding:40px;max-width:500px;width:100%}h1{color:#333;font-size:28px;text-align:center}label{display:block;color:#333;font-weight:600;margin:20px 0 10px}.upload-area{border:2px dashed #667eea;border-radius:8px;padding:30px;text-align:center;cursor:pointer;background:#f8f9ff}.upload-area:hover{border-color:#764ba2}#pdf-input{display:none}.file-name{color:#10b981;margin-top:8px;font-size:13px}.entity-group{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:20px 0}.radio-option input{display:none}.radio-label{display:block;padding:12px;border:2px solid #e0e0e0;border-radius:6px;cursor:pointer;font-weight:500}.radio-option input:checked+.radio-label{border-color:#667eea;background:#f0f2ff;color:#667eea}button{width:100%;padding:14px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;border-radius:6px;font-size:16px;font-weight:600;cursor:pointer;margin-top:20px}.error{background:#fee;border-left:4px solid #f00;color:#c33;padding:12px;margin-top:12px;display:none}.error.show{display:block}</style></head><body><div class="container"><h1>T&C Generator</h1><form id="f" enctype="multipart/form-data"><label>Carga PDF</label><div class="upload-area" id="ua"><div style="font-size:32px">📄</div><div>Arrastra aquí</div></div><input type="file" id="pi" accept=".pdf" required><div class="file-name" id="fn"></div><label>Entidad</label><div class="entity-group"><div class="radio-option"><input type="radio" id="es" name="e" value="SL" checked><label for="es" class="radio-label">SL - Madrid</label></div><div class="radio-option"><input type="radio" id="el" name="e" value="LLC"><label for="el" class="radio-label">LLC - Florida</label></div></div><div class="error" id="em"></div><button type="submit">Generar PDF</button></form></div><script>const f=document.getElementById('f');const ua=document.getElementById('ua');const pi=document.getElementById('pi');const em=document.getElementById('em');ua.addEventListener('click',()=>pi.click());ua.addEventListener('drop',(e)=>{e.preventDefault();pi.files=e.dataTransfer.files;});pi.addEventListener('change',()=>{if(pi.files[0])document.getElementById('fn').textContent='✓ '+pi.files[0].name;});f.addEventListener('submit',async(e)=>{e.preventDefault();if(!pi.files[0]){em.textContent='❌ Selecciona un PDF';em.classList.add('show');return;}const d=new FormData();d.append('pdf',pi.files[0]);d.append('entity',document.querySelector('input[name="e"]:checked').value);try{const r=await fetch('/api/generate',{method:'POST',body:d});if(!r.ok)throw new Error('Error');const b=await r.blob();const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download=`TC_${new Date().toISOString().slice(0,10)}.pdf`;a.click();}catch(e){em.textContent='❌ '+e.message;em.classList.add('show');}});</script></body></html>"""

@app.route('/')
def index():
    return HTML

@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        if 'pdf' not in request.files:
            return jsonify({'error': 'No PDF'}), 400
        pdf_file = request.files['pdf']
        entity = request.form.get('entity', 'SL')
        pdf_bytes = pdf_file.read()
        
        # Extrae y ordena
        extractor = TCExtractor(pdf_bytes)
        extractor.extract_and_order()
        terms = extractor.transform_terms(entity)
        
        # Genera PDF
        generator = TCGenerator(terms, entity)
        pdf_buffer = generator.generate_pdf()
        
        return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True,
                        download_name=f'TC_Modified_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False)
