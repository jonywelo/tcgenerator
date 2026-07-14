"""
T&C Generator - Flask Application v2
Procesador de Términos y Condiciones para contratos de operadores de aviación
"""

import os
import io
import base64
from flask import Flask, request, send_file, jsonify
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
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# Logo Welojets embebido como base64
LOGO_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAARAAAABhCAYAAAAeA/7FAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAAEnQAABJ0Ad5mH3gAABckSURBVHhe7d15VFTn+Qfw7zAwIPu+jrIMIouKC7KYxKNgkxSpbdpGSdxQ1CxNpTVibINKXFpNVZqQNPWkPdU0CiektvFU2tIj1miIAaMIguwGMGwi2wiyzvv7o3AP9x2QmQvK0N/zOec9h/u+z70XBnjmfd/7zr0yxhgDIYRIYMRXEEKIriiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIkowRCCJGMEgghRDJKIIQQySiBEEIowX+kq9E0wFZiZAAAAABJRU5ErkJggg=="

def load_logo():
    """Intenta cargar logo desde archivo como fallback"""
    global LOGO_BASE64
    logo_path = os.path.join(os.path.dirname(__file__), 'logo_welojets.png')
    if os.path.exists(logo_path) and not LOGO_BASE64:
        try:
            with open(logo_path, 'rb') as f:
                LOGO_BASE64 = base64.b64encode(f.read()).decode('utf-8')
        except:
            pass

load_logo()

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
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text() or ""
                    text_content += page_text + "\n"

            # Busca el inicio de T&C con patrones más flexibles
            patterns = [
                r'(?:terms?\s+and\s+conditions?|t\s*&\s*c)',
                r'(?:términos?\s+y\s+condiciones?)',
                r'(?:terms?|conditions?|términos?|condiciones?)',
            ]

            tc_start_idx = -1
            for pattern in patterns:
                match = re.search(pattern, text_content, re.IGNORECASE)
                if match:
                    tc_start_idx = match.start()
                    break

            if tc_start_idx > 0:
                text_content = text_content[tc_start_idx:]

            return text_content
        except Exception as e:
            raise Exception(f"Error extrayendo PDF: {str(e)}")

    def is_operator_data_line(self, line):
        """Detecta si una línea contiene datos del operador"""
        if not line.strip():
            return False

        line_lower = line.lower()

        # Patrones de datos del operador a eliminar
        operator_markers = [
            # Direcciones y ubicaciones geográficas
            r'\b\d+\s+(?:ammar|street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd|circle|cir)\b',
            r'\b(?:cairo|egypt|heliopolis|giza)\b',
            r'\b(?:p\.o\.\s+box|po box|postal code|zip code)\b',

            # Información bancaria
            r'\b(?:account|bank|iban|bic|swift|routing)\b',
            r'\b\d{10,20}\b',  # Números de cuenta (típicamente 10-20 dígitos)
            r'\b[a-z]{2}\d{2}[a-z0-9]{1,30}\b',  # IBAN format
            r'\b[a-z]{6}[a-z0-9]{2}[a-z0-9]{3}\b',  # BIC format
            r'usd|eur|currency',

            # Información de registro/licencia
            r'\blicense\s+number\b',
            r'\blimited\s+liability\b',
            r'\bregistered\b',

            # Nombres de operadores comunes
            r'\b(?:mayfair|netjets|vistajet|air\s+charter|charter\s+air|airways|aviation|executive)\b',

            # Emails y teléfonos
            r'\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b',
            r'\+\d{1,3}\s?[\d\s\-\(\)]{7,}',
            r'\(\d{3}\)\s?\d{3}-\d{4}',
            r'\boffice\s*:\s*\d+',
        ]

        for marker in operator_markers:
            if re.search(marker, line_lower):
                return True

        return False

    def transform_text(self, text, entity):
        """Aplica todas las transformaciones según reglas de Welojets"""
        self.detect_language(text)

        # Limpia líneas que contienen información del operador
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            if not self.is_operator_data_line(line):
                cleaned_lines.append(line)
        text = '\n'.join(cleaned_lines)

        # Reemplaza nombres de operadores genéricamente
        operator_patterns = [
            (r'\bthe\s+carrier\b', 'The Operator'),
            (r'\bthe\s+charterer\b', 'The Customer'),
            (r'\bmayfair\s+jets\s+egypt\b', 'The Operator'),
        ]

        for pattern, replacement in operator_patterns:
            if self.lang == 'es':
                if 'operator' in replacement.lower():
                    replacement = 'El Operador'
                elif 'customer' in replacement.lower():
                    replacement = 'El Cliente'
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        text = self._transform_cancellations(text)
        text = self._transform_payments(text, entity)
        text = self._transform_governing_law(text, entity)

        return text

    def _transform_cancellations(self, text):
        """Transforma políticas de cancelación - máximo 100%"""
        def replace_percentage(match):
            percentage_str = match.group(1)
            try:
                percentage = int(percentage_str)
            except:
                return match.group(0)

            # Regla: si es 0% -> 15%, si es >=50% -> 100%, si es <50% -> duplica pero máximo 100%
            if percentage == 0:
                return "15%"
            elif percentage >= 50:
                return "100%"
            else:
                new_pct = min(percentage * 2, 100)
                return f"{new_pct}%"

        patterns = [
            (r'(\d+)%\s+(?:non-refundable|of\s+)?(?:cancellation|refund)', r'\1% cancellation'),
            (r'cancellation\s+(?:fee|charge):\s*(\d+)%', r'cancellation fee: \1%'),
            (r'(?:cancelación|reembolso):\s*(\d+)%', r'\1%'),
        ]

        for pattern, _ in patterns:
            text = re.sub(pattern, replace_percentage, text, flags=re.IGNORECASE)

        return text

    def _transform_payments(self, text, entity):
        """Transforma sección de Payments - credit card fee siempre 5%"""
        # Credit card fee a 5%
        text = re.sub(r'credit\s+card\s+fee:?\s+\d+%', 'credit card fee: 5%', text, flags=re.IGNORECASE)
        text = re.sub(r'comisión\s+(?:de\s+)?tarjeta:?\s+\d+%', 'comisión de tarjeta: 5%', text, flags=re.IGNORECASE)

        return text

    def _transform_governing_law(self, text, entity):
        """Reemplaza Governing Law manteniendo estructura original"""
        if entity == 'SL':
            replacement = 'Madrid, Spain'
        elif entity == 'LLC':
            replacement = 'Florida, USA'
        else:
            return text

        # Patrones que capturan "governed by [COUNTRY/LAW]" y reemplazan solo la jurisdicción
        patterns = [
            (r'(governed\s+by\s+)[A-Za-z\s,]+(?:law|laws|jurisdiction)', r'\1' + replacement),
            (r'(shall\s+be\s+governed\s+by\s+)[A-Za-z\s,]+(?:law|laws)', r'\1' + replacement),
            (r'(applicable\s+law:\s*)[A-Za-z\s,]+', r'\1' + replacement),
            (r'(jurisdiction:\s*)[A-Za-z\s,]+(?:law)?', r'\1' + replacement),
        ]

        for pattern, repl in patterns:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

        return text

    def generate_pdf(self, text, entity):
        """Genera PDF final con formato Welojets"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1.35*inch)

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

        if self.lang == 'es':
            notice_text = (
                "<b><font color='red'>AVISO:</font></b> A menos que se acuerde lo contrario por escrito entre Welojets y el Cliente, "
                "el vuelo se confirmará al 100% únicamente previa la recepción simultánea del pago "
                "(debe estar acreditado en nuestra cuenta bancaria para considerarse pagado) y un contrato firmado. "
                "Un contrato firmado solo no garantiza el vuelo ni la disponibilidad de la aeronave."
            )
        else:
            notice_text = (
                "<b><font color='red'>NOTICE:</font></b> Unless otherwise agreed in writing by Welojets and the Customer, "
                "the flight will be 100% confirmed only upon simultaneous receipt of payment "
                "(must be credited to our bank account to be considered paid) and a signed contract. "
                "A signed contract alone does not guarantee the flight or the availability of the aircraft."
            )

        story.append(Paragraph(notice_text, normal_style))
        story.append(Spacer(1, 0.2*inch))

        for line in text.split('\n'):
            if line.strip():
                story.append(Paragraph(line.strip(), normal_style))
            else:
                story.append(Spacer(1, 0.1*inch))

        story.append(Spacer(1, 0.3*inch))

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

        doc.build(story, onFirstPage=self._add_header, onLaterPages=self._add_header)
        buffer.seek(0)
        return buffer

    def _add_header(self, canvas, doc):
        """Agrega logo como encabezado - intenta base64 primero, fallback a archivo"""
        try:
            if LOGO_BASE64:
                # Usa logo desde base64
                img_data = io.BytesIO(base64.b64decode(LOGO_BASE64))
                img = Image(img_data, width=1.25*inch, height=1.25*inch)
                img.hAlign = 'CENTER'
                x = (letter[0] - 1.25*inch) / 2
                y = letter[1] - 0.85*inch
                img.drawOn(canvas, x, y)
            else:
                # Intenta archivo local si existe
                logo_path = os.path.join(os.path.dirname(__file__), 'logo_welojets.png')
                if os.path.exists(logo_path):
                    img = Image(logo_path, width=1.25*inch, height=1.25*inch)
                    img.hAlign = 'CENTER'
                    x = (letter[0] - 1.25*inch) / 2
                    y = letter[1] - 0.85*inch
                    img.drawOn(canvas, x, y)
        except Exception as e:
            pass  # Si falla, continúa sin logo


@app.route('/')
def index():
    return '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>T&C Generator - Welojets</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            padding: 40px;
            max-width: 500px;
            width: 100%;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
            text-align: center;
        }
        .subtitle {
            color: #666;
            text-align: center;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .form-group {
            margin-bottom: 24px;
        }
        label {
            display: block;
            color: #333;
            font-weight: 600;
            margin-bottom: 10px;
            font-size: 14px;
        }
        .upload-area {
            border: 2px dashed #667eea;
            border-radius: 8px;
            padding: 30px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            background: #f8f9ff;
        }
        .upload-area:hover {
            border-color: #764ba2;
            background: #f0f2ff;
        }
        .upload-area.dragover {
            border-color: #764ba2;
            background: #e9ecff;
            transform: scale(1.02);
        }
        .upload-icon {
            font-size: 32px;
            margin-bottom: 8px;
        }
        .upload-text {
            color: #667eea;
            font-weight: 600;
            margin-bottom: 4px;
        }
        .upload-subtext {
            color: #999;
            font-size: 12px;
        }
        #pdfInput {
            display: none;
        }
        .file-name {
            color: #10b981;
            margin-top: 8px;
            font-size: 13px;
            font-weight: 500;
        }
        .entity-group {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }
        .radio-option {
            position: relative;
        }
        .radio-option input {
            display: none;
        }
        .radio-label {
            display: block;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 6px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            font-weight: 500;
            font-size: 13px;
        }
        .radio-option input:checked + .radio-label {
            border-color: #667eea;
            background: #f0f2ff;
            color: #667eea;
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
            font-size: 14px;
        }
        button:hover:not(:disabled) {
            transform: scale(1.02);
        }
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .error {
            color: #ef4444;
            margin-top: 10px;
            padding: 12px;
            background: #fee2e2;
            border-radius: 6px;
            font-size: 13px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>T&C Generator</h1>
        <p class="subtitle">Procesador de Términos y Condiciones</p>

        <div class="form-group">
            <label>Contrato PDF del Operador</label>
            <div class="upload-area" id="uploadArea">
                <div class="upload-icon">📄</div>
                <div class="upload-text">Arrastra tu PDF aquí o haz clic</div>
                <div class="upload-subtext">Máximo 50MB</div>
                <input type="file" id="pdfInput" accept=".pdf">
            </div>
            <div class="file-name" id="fileName"></div>
        </div>

        <div class="form-group">
            <label>Tipo de Entidad</label>
            <div class="entity-group">
                <div class="radio-option">
                    <input type="radio" id="sl" name="entity" value="SL" checked>
                    <label for="sl" class="radio-label">SL (Madrid)</label>
                </div>
                <div class="radio-option">
                    <input type="radio" id="llc" name="entity" value="LLC">
                    <label for="llc" class="radio-label">LLC (Florida)</label>
                </div>
            </div>
        </div>

        <button id="processBtn" disabled>Procesar PDF</button>
        <div id="errorMsg"></div>
    </div>

    <script>
        const uploadArea = document.getElementById('uploadArea');
        const pdfInput = document.getElementById('pdfInput');
        const fileName = document.getElementById('fileName');
        const processBtn = document.getElementById('processBtn');
        const errorMsg = document.getElementById('errorMsg');

        uploadArea.addEventListener('click', () => pdfInput.click());
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });
        uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            pdfInput.files = e.dataTransfer.files;
            handleFileSelect();
        });

        pdfInput.addEventListener('change', handleFileSelect);

        function handleFileSelect() {
            if (pdfInput.files.length > 0) {
                fileName.textContent = '✓ ' + pdfInput.files[0].name;
                processBtn.disabled = false;
            }
        }

        processBtn.addEventListener('click', async () => {
            if (!pdfInput.files.length) return;

            const formData = new FormData();
            formData.append('pdf', pdfInput.files[0]);
            formData.append('entity', document.querySelector('input[name="entity"]:checked').value);

            processBtn.disabled = true;
            processBtn.textContent = 'Procesando...';
            errorMsg.innerHTML = '';

            try {
                const response = await fetch('/api/process-pdf-download', {
                    method: 'POST',
                    body: formData
                });
                if (response.ok) {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'TC_Welojets_' + new Date().toISOString().split('T')[0] + '.pdf';
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    a.remove();
                } else {
                    const error = await response.json();
                    errorMsg.innerHTML = '<div class="error">Error: ' + (error.error || 'Error desconocido') + '</div>';
                }
            } catch (err) {
                errorMsg.innerHTML = '<div class="error">Error: ' + err.message + '</div>';
            }

            processBtn.disabled = false;
            processBtn.textContent = 'Procesar PDF';
        });
    </script>
</body>
</html>'''


@app.route('/api/process-pdf-download', methods=['POST'])
def process_pdf():
    """Procesa PDF y retorna descarga"""
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

        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'TC_Welojets_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 5000))
    DEBUG = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
