"""Sección 6 y 7 — Generación del .docx con reglas ATS estrictas.

Reglas aplicadas (no negociables, ver Sección 6 del spec):
  - Orden fijo de secciones: Encabezado → Perfil → Experiencia →
    Competencias y Herramientas → Educación → Certificaciones → Idiomas.
  - Una sola columna. Nunca tablas, columnas paralelas ni text boxes.
  - Sin imágenes, iconos, barras de progreso.
  - Sin headers/footers para ningún dato.
  - Fuente ATS-safe (Calibri), 10.5-12pt cuerpo, 14-16pt nombre.
  - Negritas solo en nombres de empresa/puesto y encabezados de sección.
  - Bullets estándar "•", nunca símbolos personalizados/emojis.
  - Fechas en formato MM/AAAA consistente.
  - Bullets inician con verbo de acción, sin pronombres personales
    (se asume que el motor de adaptación ya redacta así).

Generado con estilos programáticos (python-docx) — nunca copiando/pegando
formato de Word — para evitar metadatos corruptos.
"""

from __future__ import annotations

import os
import re
import unicodedata

from docx import Document
from docx.shared import Pt

ATS_FONT = "Calibri"
NAME_SIZE = Pt(16)
HEADLINE_SIZE = Pt(11)
SECTION_HEADER_SIZE = Pt(12)
BODY_SIZE = Pt(11)
CONTACT_SIZE = Pt(10.5)

SECTION_LABELS_ES = {
    "perfil": "Perfil Profesional",
    "experiencia": "Experiencia Profesional",
    "competencias": "Competencias y Herramientas",
    "educacion": "Educación",
    "certificaciones": "Certificaciones",
    "idiomas": "Idiomas",
}
SECTION_LABELS_EN = {
    "perfil": "Professional Summary",
    "experiencia": "Professional Experience",
    "competencias": "Skills & Tools",
    "educacion": "Education",
    "certificaciones": "Certifications",
    "idiomas": "Languages",
}


def _sanitize_filename_part(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text or "SinTitulo"


def build_filename(cv_maestro: dict, vacante_analizada: dict, extension: str) -> str:
    nombre = _sanitize_filename_part(
        cv_maestro.get("datos_personales", {}).get("nombre_completo", "Candidato")
    )
    empresa = _sanitize_filename_part(vacante_analizada.get("empresa", ""))
    puesto = _sanitize_filename_part(vacante_analizada.get("titulo_puesto", ""))
    parts = [p for p in ["CV", nombre, empresa, puesto] if p]
    return f"{'_'.join(parts)}.{extension}"


def _format_date(value: str) -> str:
    if not value:
        return ""
    match = re.fullmatch(r"(\d{4})-(\d{2})", value.strip())
    if match:
        year, month = match.groups()
        return f"{month}/{year}"
    return value.strip()


def _set_run_font(run, *, bold=False, size=BODY_SIZE, italic=False):
    run.font.name = ATS_FONT
    run.font.size = size
    run.bold = bold
    run.italic = italic


def _add_section_header(document: Document, label: str):
    document.add_paragraph()
    p = document.add_paragraph()
    run = p.add_run(label.upper())
    _set_run_font(run, bold=True, size=SECTION_HEADER_SIZE)
    border = p.paragraph_format
    border.space_after = Pt(4)


def _add_bullet(document: Document, text: str):
    p = document.add_paragraph()
    run = p.add_run(f"• {text}")
    _set_run_font(run, size=BODY_SIZE)
    p.paragraph_format.left_indent = Pt(14)
    p.paragraph_format.space_after = Pt(2)


def _experience_bullets(exp: dict) -> list[str]:
    for key in ("logros_y_responsabilidades", "bullets", "logros"):
        if key in exp and exp[key]:
            return list(exp[key])
    return []


def generate_docx(
    cv_maestro: dict,
    cv_adaptado: dict,
    vacante_analizada: dict,
    output_dir: str,
) -> str:
    """Genera el .docx ATS-safe y devuelve la ruta absoluta del archivo."""
    idioma = cv_adaptado.get("idioma_cv", "es")
    labels = SECTION_LABELS_EN if idioma == "en" else SECTION_LABELS_ES

    document = Document()
    for section in document.sections:
        section.header.is_linked_to_previous = True
        section.footer.is_linked_to_previous = True

    style = document.styles["Normal"]
    style.font.name = ATS_FONT
    style.font.size = BODY_SIZE

    datos = cv_maestro.get("datos_personales", {})

    # Encabezado
    name_p = document.add_paragraph()
    name_run = name_p.add_run(datos.get("nombre_completo", ""))
    _set_run_font(name_run, bold=True, size=NAME_SIZE)

    headline = cv_maestro.get("titular_headline", "")
    if headline:
        headline_p = document.add_paragraph()
        headline_run = headline_p.add_run(headline)
        _set_run_font(headline_run, size=HEADLINE_SIZE, italic=False)

    contact_bits = [
        datos.get("ubicacion", ""),
        datos.get("email", ""),
        datos.get("telefono", ""),
        datos.get("linkedin", ""),
    ]
    contact_line = " | ".join(b for b in contact_bits if b)
    if contact_line:
        contact_p = document.add_paragraph()
        contact_run = contact_p.add_run(contact_line)
        _set_run_font(contact_run, size=CONTACT_SIZE)

    # Perfil
    perfil = cv_adaptado.get("perfil_resumen", "")
    if perfil:
        _add_section_header(document, labels["perfil"])
        p = document.add_paragraph()
        run = p.add_run(perfil)
        _set_run_font(run, size=BODY_SIZE)

    # Experiencia
    experiencia = cv_adaptado.get("experiencia_seleccionada", [])
    if experiencia:
        _add_section_header(document, labels["experiencia"])
        for exp in experiencia:
            header_p = document.add_paragraph()
            title_run = header_p.add_run(f"{exp.get('puesto', '')} — {exp.get('empresa', '')}")
            _set_run_font(title_run, bold=True, size=BODY_SIZE)

            fecha_inicio = _format_date(exp.get("fecha_inicio", ""))
            fecha_fin = _format_date(exp.get("fecha_fin", ""))
            fechas = " - ".join(f for f in [fecha_inicio, fecha_fin] if f)
            ubicacion = exp.get("ubicacion", "")
            meta_bits = [b for b in [fechas, ubicacion] if b]
            if meta_bits:
                meta_p = document.add_paragraph()
                meta_run = meta_p.add_run(" | ".join(meta_bits))
                _set_run_font(meta_run, size=CONTACT_SIZE, italic=True)

            for bullet in _experience_bullets(exp):
                _add_bullet(document, bullet)

    # Competencias y Herramientas
    herramientas = cv_adaptado.get("herramientas_destacadas", [])
    if herramientas:
        _add_section_header(document, labels["competencias"])
        p = document.add_paragraph()
        run = p.add_run(" | ".join(herramientas))
        _set_run_font(run, size=BODY_SIZE)

    # Educación
    educacion = cv_maestro.get("educacion", [])
    if educacion:
        _add_section_header(document, labels["educacion"])
        for edu in educacion:
            p = document.add_paragraph()
            title_run = p.add_run(f"{edu.get('titulo', '')} — {edu.get('institucion', '')}")
            _set_run_font(title_run, bold=True, size=BODY_SIZE)
            fechas = " - ".join(
                f
                for f in [_format_date(edu.get("fecha_inicio", "")), _format_date(edu.get("fecha_fin", ""))]
                if f
            )
            if fechas:
                meta_p = document.add_paragraph()
                meta_run = meta_p.add_run(fechas)
                _set_run_font(meta_run, size=CONTACT_SIZE, italic=True)

    # Certificaciones
    certificaciones = cv_maestro.get("certificaciones", [])
    if certificaciones:
        _add_section_header(document, labels["certificaciones"])
        for cert in certificaciones:
            anio = _format_date(cert.get("anio", ""))
            texto = f"{cert.get('nombre', '')} — {cert.get('institucion', '')} ({anio})"
            vigencia = cert.get("vigencia", "")
            if vigencia:
                texto += f" · Vigencia: {vigencia}"
            _add_bullet(document, texto)

    # Idiomas
    idiomas = cv_maestro.get("idiomas", [])
    if idiomas:
        _add_section_header(document, labels["idiomas"])
        p = document.add_paragraph()
        texto = " | ".join(f"{i.get('idioma', '')}: {i.get('nivel', '')}" for i in idiomas)
        run = p.add_run(texto)
        _set_run_font(run, size=BODY_SIZE)

    os.makedirs(output_dir, exist_ok=True)
    filename = build_filename(cv_maestro, vacante_analizada, "docx")
    output_path = os.path.join(output_dir, filename)
    document.save(output_path)
    return output_path
