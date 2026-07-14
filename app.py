import os
import io
from flask import Flask, request, send_file, jsonify
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

class TCGenerator:
    def __init__(self, entity):
        self.entity = entity

    def get_terms_content(self):
        """Contenido exacto del operador, ya ordenado correctamente"""
        return """TERMS & CONDITIONS

Included Services and Fees:

CJ: selection of snacks as well as alcoholic and non-alcoholic beverages, including champagne

C680+: from a flight time of 1,5 h: VIP Catering (assorted sandwiches, fruit platter, cheese & meat platter)

Additional Fees:

Additional Pax: EUR 250,00 per Pax plus appl. taxes/fees

Additional Pet: EUR 150,00 per Pet per Leg

Pax Ground Transportation EUR 50,00 + actual Costs

Pax Airport Ground Transportation Fee: UK APD, ILT, French Solidarity Tax if applicable

Not included Services:

Aircraft De-Icing Costs

Passenger Ground Transportation

PPR-Costs

VIP Catering; can be arranged upon request and will be charged separately

Booking:

By signing this agreement, The Operator reserves the requested flight and invoices to the customer for the charter price. Upon receipt of the full amount by The Operator, the flight is booked for the customer. The amount is payable and due upon invoicing. If the invoice amount is not received within a period of 4 banking days, the reservation will be canceled.

Pets:

Animals are only carried with prior approval of The Operator.

Schedule:

We kindly inform that the flight schedule may be subject to weather and airport conditions and other unforeseen circumstances, which The Operator cannot be held responsible for. Please be advised that in order to maintain the planned flight departure time, passengers are required to arrive at the departure location minimum 30 minutes prior to the departure. In case of a possible delay please inform one of crew members or a The Operator representative. In the event of unforeseeable circumstances beyond The Operator's control that result in a change to the schedule, the additional costs will be passed on to the customer (for example: necessary repositioning due to cancelled airport parking or strike).

Cancellation Fees:

60% of charter price after confirming the booking / signing the contract

100% of charter price if less than 10 days before date of departure

150% of charter price if less than 7 days before date of flight

100% of charter price 48 hours before date of flight or no-show

No partial cancellation possible.

Documents:

Passengers are obliged to have the necessary travel documents, which include valid passport, all necessary visas as well as medical certificates (if required).

IMPORTANT:

It is a requirement of customs and immigration authorities within Europe that you provide full passport information for every passenger travelling not less than 24hrs prior to departure. This also allows for the correct calculation of Airport Passenger Duty where applicable. The number of passengers and their details cannot be altered without the prior consent of The Operator. Documents need to be sent to The Operator at least 3 days prior departure. For travels into UK, passenger will need to apply for UK APD in advance, which requires a valid passport. No travels possible with ID.

DGR:

Please note that the transport of dangerous goods (including lithium batteries, flammable liquids, compressed gases, guns and ammunition) is strictly prohibited. A comprehensive DGR list can be found here https://www.iata.org/en/publications/dgr/

Payment:

Credit card fee: 5%

Payment must be simultaneous with contract signature."""

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

        # RED BOLD NOTICE
        notice_txt = "NOTICE: Unless otherwise agreed in writing by Welojets and the Customer, the flight will be 100% confirmed only upon simultaneous receipt of payment (must be credited to our bank account to be considered paid) and a signed contract. A signed contract alone does not guarantee the flight or the availability of the aircraft."

        story.append(Paragraph(notice_txt, notice_style))
        story.append(Spacer(1, 0.3*inch))

        # TERMS CONTENT - EXACTO DEL OPERADOR
        terms = self.get_terms_content()

        for line in terms.split('\n'):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 0.08*inch))
            elif line.isupper() and len(line) < 50:
                story.append(Paragraph(line, heading_style))
            else:
                story.append(Paragraph(line, normal_style))

        story.append(PageBreak())

        # WHEREAS
        whereas = "WHEREAS: Client desires that Welojets act as Client's agent in arranging air transportation to be furnished to Client by one or more licensed air carriers (hereinafter referred to as \"Carrier\") under applicable regulations of the United States Federal Aviation Administration (FAA) and Department of Transportation (DOT) and/or EASA and/or equivalent foreign aeronautical authorities. For scheduled service, once a Client has agreed to the terms herein and paid for a flight, Welojets shall be authorized to purchase the flight from Carrier on Client's behalf (inclusive of all members of Client's party) and this agreement shall be binding as to each flight arranged by Welojets. For charter flights, Welojets will present a quote and a photograph of the type of aircraft to be used for the Client's flights. Once Client has confirmed his/her/its acceptance of a charter itinerary and price quote provided by Welojets, Welojets shall be authorized, as Client's agent, to enter into a charter contract with Carrier in the name and on the behalf of Client. Carriers are obligated to operate Flights in accordance with applicable EASA or U.S. or foreign laws, rules and regulations, and Carrier will have exclusive operational control of the aircraft at all times. CLIENT ACKNOWLEDGES AND AGREES THAT WELOJETS ACTS ONLY AS AN AGENT OF CLIENT FOR THE ARRANGEMENT OF AIR TRANSPORTATION AS DESCRIBED HEREIN, AND THAT WELOJETS DOES NOT OWN OR OPERATE ANY AIRCRAFT. This Agreement shall remain in full force for each flight arranged by Welojets until the Agreement is cancelled in writing by either party (term expires 10 days after the service/flight(s) are completed). This Agreement will be supplemented for each specific charter flight (or series of flights) by a separate \"Charter Quote\", which will include the flight details, pricing, and other applicable information and payment confirmation."

        story.append(Paragraph(whereas, normal_style))
        story.append(Spacer(1, 0.2*inch))

        # GDPR
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

HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>T&C Generator</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}.container{background:white;border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,0.3);padding:40px;max-width:500px;width:100%}h1{color:#333;font-size:28px;text-align:center;margin-bottom:5px}.subtitle{color:#666;text-align:center;margin-bottom:25px;font-size:13px}label{display:block;color:#333;font-weight:600;margin:18px 0 10px;font-size:14px}.upload-area{border:2px dashed #667eea;border-radius:8px;padding:30px;text-align:center;cursor:pointer;background:#f8f9ff;transition:all 0.3s}.upload-area:hover{border-color:#764ba2;background:#f0f2ff}.upload-icon{font-size:32px;margin-bottom:8px}#pdf-input{display:none}.file-name{color:#10b981;margin-top:8px;font-size:13px;font-weight:500}.entity-group{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:18px 0}.radio-option input{display:none}.radio-label{display:block;padding:12px;border:2px solid #e0e0e0;border-radius:6px;cursor:pointer;font-weight:500;font-size:13px;transition:all 0.3s}.radio-option input:checked+.radio-label{border-color:#667eea;background:#f0f2ff;color:#667eea}button{width:100%;padding:14px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;border-radius:6px;font-size:16px;font-weight:600;cursor:pointer;margin-top:20px;transition:all 0.3s}.error{background:#fee;border-left:4px solid #f00;color:#c33;padding:12px;margin-top:12px;font-size:13px;display:none}.error.show{display:block}</style></head><body><div class="container"><h1>T&C Generator</h1><p class="subtitle">Welojets Terms & Conditions</p><form id="f"><label>Entidad</label><div class="entity-group"><div class="radio-option"><input type="radio" id="es" name="e" value="SL" checked><label for="es" class="radio-label">SL - Madrid</label></div><div class="radio-option"><input type="radio" id="el" name="e" value="LLC"><label for="el" class="radio-label">LLC - Florida</label></div></div><div class="error" id="em"></div><button type="submit">Generar PDF</button></form></div><script>const f=document.getElementById('f');const em=document.getElementById('em');f.addEventListener('submit',async(e)=>{e.preventDefault();const d=new FormData();d.append('entity',document.querySelector('input[name="e"]:checked').value);try{const r=await fetch('/api/generate',{method:'POST',body:d});if(!r.ok)throw new Error('Error generando PDF');const b=await r.blob();const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download=`TC_${new Date().toISOString().slice(0,10)}.pdf`;a.click();}catch(e){em.textContent='❌ '+e.message;em.classList.add('show');}});</script></body></html>"""

@app.route('/')
def index():
    return HTML

@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        entity = request.form.get('entity', 'SL')
        generator = TCGenerator(entity)
        pdf_buffer = generator.generate_pdf()
        return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True,
                        download_name=f'TC_Modified_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False)
