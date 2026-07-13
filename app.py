"""
T&C Generator - Flask Application
Procesador de Términos y Condiciones para contratos de operadores de aviación
"""

import os
import io
from flask import Flask, render_template, request, send_file, jsonify
import pdfplumber
import re
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from langdetect import detect
from datetime import datetime

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

# Paths
LOGO_PATH = os.path.join(os.path.dirname(__file__), 'static', 'logo_welojets.png')

class TCProcessor:
    """Procesador de Términos y Condiciones"""

    def __init__(self):
        self.lang = 'en'

    def detect_language(self, text):
        """Detecta idioma del texto"""
        try:
            self.lang = detect(text[:500])
            if self.lang not in ['en', 'es']:
                self.lang = 'en'
        except:
            self.lang = 'en'
        return self.lang

    def extract_tc_from_pdf(self, pdf_bytes):
        """Extrae Terms and Conditions del PDF"""
        try:
            pdf_file = io.BytesIO(pdf_bytes)
            text_content = ""

            with pdfplumber.open(pdf_file) as pdf:
                # Buscar página donde empiezan los T&C
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text() or ""
                    text_content += page_text + "\n"

                # Identificar inicio de T&C (generalmente "Terms", "Conditions", etc)
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
        """Aplica todas las transformaciones según reglas de Welojets"""

        # 1. Detectar idioma
        self.detect_language(text)

        # 2. Reemplazar nombre del operador
        operator_patterns = [
            r'\b[Vv]istajet\b', r'\b[Nn]etjets\b', r'\b[Ae]xecutive\b',
            r'\b[Cc]arrier\b(?!\s+\()', r'\b[Oo]perator\b'
        ]

        for pattern in operator_patterns:
            if self.lang == 'es':
                text = re.sub(pattern, 'El Operador', text, flags=re.IGNORECASE)
            else:
                text = re.sub(pattern, 'The Operator', text, flags=re.IGNORECASE)

        # 3. Duplicar políticas de cancelación
        text = self._transform_cancellations(text)

        # 4. Modificar sección de Payments
        text = self._transform_payments(text, entity)

        # 5. Reemplazar Governing Law
        text = self._transform_governing_law(text, entity)

        # 6. Eliminar contactos del operador
        text = self._remove_operator_contacts(text)

        return text

    def _transform_cancellations(self, text):
        """Transforma políticas de cancelación"""
        # Buscar porcentajes y aplicar reglas
        def replace_percentage(match):
            percentage = int(match.group(1))

            if percentage == 0:
                return f"{15}%"
            elif percentage == 100:
                return match.group(0)  # No cambiar
            else:
                return f"{percentage * 2}%"

        # Patrones comunes para cancelaciones
        patterns = [
            r'(\d+)%\s+(?:of\s+)?(?:cancellation|refund)',
            r'cancellation\s+fee:?\s+(\d+)%',
            r'(?:cancelación|reembolso):?\s+(\d+)%'
        ]

        for pattern in patterns:
            text = re.sub(pattern, replace_percentage, text, flags=re.IGNORECASE)

        return text

    def _transform_payments(self, text, entity):
        """Transforma sección de Payments"""
        if self.lang == 'es':
            payment_clause = (
                "El pago debe realizarse de forma simultánea con la firma del contrato. "
                "El pago se considerará acreditado únicamente una vez que el dinero se encuentre "
                "acreditado en la cuenta bancaria de Welojets."
            )
            cc_fee_text = "La comisión de tarjeta de crédito será siempre del 5%."
        else:
            payment_clause = (
                "Payment must be made simultaneously with contract signature. "
                "Payment is considered credited only once the funds have been credited to Welojets' bank account."
            )
            cc_fee_text = "Credit card fee shall always be 5%."

        # Reemplazar credit card fee por 5%
        text = re.sub(r'credit\s+card\s+fee:?\s+\d+%', 'credit card fee: 5%', text, flags=re.IGNORECASE)
        text = re.sub(r'comisión\s+(?:de\s+)?tarjeta:?\s+\d+%', 'comisión de tarjeta: 5%', text, flags=re.IGNORECASE)

        return text

    def _transform_governing_law(self, text, entity):
        """Reemplaza Governing Law según entidad"""
        if entity == 'SL':
            replacement = 'Madrid, Spain'
        elif entity == 'LLC':
            replacement = 'Florida, USA'
        else:
            return text

        text = re.sub(
            r'(?:governing\s+law|applicable\s+law|jurisdiction):?\s+[^.\n]+',
            f'Governing Law: {replacement}',
            text,
            flags=re.IGNORECASE
        )

        return text

    def _remove_operator_contacts(self, text):
        """Elimina emails y teléfonos del operador"""
        # Eliminar emails que no sean @welojets.com
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@(?!welojets\.com)[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', text)

        # Eliminar teléfonos (patrones comunes)
        text = re.sub(r'\+\d{1,3}\s?[\d\s\-\(\)]{7,}', '', text)
        text = re.sub(r'\(\d{3}\)\s?\d{3}-\d{4}', '', text)

        return text

    def generate_pdf(self, text, entity):
        """Genera PDF final con formato Welojets"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1.35*inch)

        # Estilos
        styles = getSampleStyleSheet()

        notice_style = ParagraphStyle(
            'Notice',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            textColor=colors.red,
            fontSize=9,
            leading=12.5,
            alignment=TA_JUSTIFY,
            spaceAfter=14
        )

        normal_style = ParagraphStyle(
            'Normal',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=12.5,
            alignment=TA_JUSTIFY,
            spaceAfter=8
        )

        gdpr_style = ParagraphStyle(
            'GDPR',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=8,
            leading=11,
            alignment=TA_JUSTIFY,
            spaceAfter=8
        )

        story = []

        # Notice (inicio)
        if self.lang == 'es':
            notice_text = (
                "Aviso: A menos que se acuerde lo contrario por escrito entre Welojets y el Cliente, "
                "el vuelo se confirmará al 100% únicamente previa la recepción simultánea del pago "
                "(debe estar acreditado en nuestra cuenta bancaria para considerarse pagado) y un contrato firmado. "
                "Un contrato firmado solo no garantiza el vuelo ni la disponibilidad de la aeronave."
            )
        else:
            notice_text = (
                "Notice: Unless otherwise agreed in writing by Welojets and the Customer, "
                "the flight will be 100% confirmed only upon simultaneous receipt of payment "
                "(Must be credited to our bank account to be considered paid) and a signed contract. "
                "A signed contract alone does not guarantee the flight or the availability of the aircraft."
            )

        story.append(Paragraph(notice_text, notice_style))
        story.append(Spacer(1, 0.2*inch))

        # Contenido principal (T&C)
        for line in text.split('\n'):
            if line.strip():
                story.append(Paragraph(line.strip(), normal_style))
            else:
                story.append(Spacer(1, 0.1*inch))

        story.append(Spacer(1, 0.3*inch))

        # WHEREAS (al final)
        if self.lang == 'es':
            whereas_text = (
                "<b>CONSIDERANDO:</b> El Cliente desea que Welojets actúe como su agente en la "
                "contratación de servicios de transporte aéreo proporcionados por uno o más transportistas "
                "aéreos autorizados conforme a las regulaciones aplicables de la FAA, DOT, EASA y/u otras "
                "autoridades aeronáuticas equivalentes. Para vuelos charter, una vez que el Cliente ha "
                "confirmado su aceptación de la cotización presentada por Welojets, Welojets estará autorizado, "
                "como agente del Cliente, para celebrar un contrato charter con el transportista en nombre del Cliente. "
                "Los transportistas operarán los vuelos de conformidad con las leyes y regulaciones aplicables. "
                "EL CLIENTE RECONOCE Y ACEPTA QUE WELOJETS ACTÚA ÚNICAMENTE COMO AGENTE DEL CLIENTE PARA LA CONTRATACIÓN "
                "DE SERVICIOS DE TRANSPORTE AÉREO, Y QUE WELOJETS NO POSEE NI OPERA AERONAVE ALGUNA."
            )
        else:
            whereas_text = (
                "<b>WHEREAS:</b> Client desires that Welojets act as Client's agent in arranging air transportation "
                "to be furnished by one or more licensed air carriers under applicable FAA, DOT, EASA and equivalent regulations. "
                "For charter flights, once Client has confirmed acceptance of Welojets' quote, Welojets shall be authorized "
                "to enter into a charter contract with Carrier on Client's behalf. Carriers shall operate flights in accordance "
                "with applicable laws and regulations. CLIENT ACKNOWLEDGES AND AGREES THAT WELOJETS ACTS ONLY AS AN AGENT "
                "OF CLIENT FOR AIR TRANSPORTATION ARRANGEMENT, AND THAT WELOJETS DOES NOT OWN OR OPERATE ANY AIRCRAFT."
            )

        story.append(Paragraph(whereas_text, normal_style))
        story.append(Spacer(1, 0.2*inch))

        # GDPR
        if self.lang == 'es':
            gdpr_text = (
                "De conformidad con la RGPD y LOPDGDD, informamos que WELOJETS AIR MOBILITY, S.L. recopila y trata sus datos personales, "
                "aplicando las medidas técnicas y organizativas que garanticen su confidencialidad, con la finalidad de gestionar "
                "la contratación de servicios. Puede ejercer sus derechos de acceso, rectificación, supresión, limitación, portabilidad "
                "y oposición contactando con el responsable en Conde de Aranda nº10 piso 1, Madrid, 28001, o enviando un correo a fly@welojets.com."
            )
        else:
            gdpr_text = (
                "We inform you, as provided in the GDPR, that WELOJETS AIR MOBILITY, S.L. collects and processes your personal data "
                "with technical and organizational measures ensuring confidentiality for service management purposes. You may exercise "
                "your rights by contacting Conde de Aranda nº10 piso 1, Madrid, 28001, or emailing fly@welojets.com."
            )

        story.append(Paragraph(gdpr_text, gdpr_style))

        # Construir PDF
        doc.build(story, onFirstPage=self._add_header, onLaterPages=self._add_header)
        buffer.seek(0)
        return buffer

    def _add_header(self, canvas, doc):
        """Agrega logo como encabezado"""
        if os.path.exists(LOGO_PATH):
            img = Image(LOGO_PATH, width=1.25*inch, height=1.25*inch)
            img.hAlign = 'CENTER'
            # Posicionar en el top center
            x = (letter[0] - 1.25*inch) / 2
            y = letter[1] - 0.85*inch
            img.drawOn(canvas, x, y)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/process-pdf-download', methods=['POST'])
def process_pdf():
    """Procesa PDF y retorna descarga"""
    try:
        # Validar inputs
        if 'pdf' not in request.files:
            return jsonify({'error': 'No PDF provided'}), 400

        pdf_file = request.files['pdf']
        entity = request.form.get('entity', 'SL')

        if not pdf_file or pdf_file.filename == '':
            return jsonify({'error': 'Invalid file'}), 400

        # Leer PDF
        pdf_bytes = pdf_file.read()

        # Procesar
        processor = TCProcessor()
        tc_text = processor.extract_tc_from_pdf(pdf_bytes)
        transformed_text = processor.transform_text(tc_text, entity)
        pdf_buffer = processor.generate_pdf(transformed_text, entity)

        # Retornar descarga
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'TC_Modified_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
