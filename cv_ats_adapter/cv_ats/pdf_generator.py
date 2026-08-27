"""Sección 7 — Generación de PDF y verificación anti-corrupción.

Usa LibreOffice headless para convertir el .docx a PDF (multiplataforma,
sin depender de Word instalado). Nunca rasteriza el contenido: el resultado
siempre es texto seleccionable, porque LibreOffice exporta texto real.

Tras generar el PDF se verifica automáticamente extrayendo su texto con
pdfplumber: si la extracción falla o vuelve vacía, el PDF se considera
defectuoso, se reintenta una vez, y si sigue fallando se notifica al
usuario en vez de entregarlo en silencio (el .docx siempre queda
disponible como respaldo).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


class PDFGenerationError(RuntimeError):
    """La conversión a PDF falló o el PDF resultante quedó vacío/corrupto."""


@dataclass
class PDFResult:
    pdf_path: str | None
    verificado: bool
    texto_extraido_preview: str
    error: str | None = None


def _find_soffice() -> str:
    for candidate in ("soffice", "libreoffice"):
        path = shutil.which(candidate)
        if path:
            return path
    raise PDFGenerationError(
        "No se encontró LibreOffice ('soffice'/'libreoffice') en el sistema. "
        "Instálalo para poder exportar a PDF, o usa el .docx generado como respaldo."
    )


def _convert_with_libreoffice(docx_path: str, output_dir: str) -> str:
    soffice = _find_soffice()
    result = subprocess.run(
        [
            soffice,
            "--headless",
            "--norestore",
            "--convert-to",
            "pdf",
            "--outdir",
            output_dir,
            docx_path,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    expected_pdf = os.path.join(
        output_dir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf"
    )
    if result.returncode != 0 or not os.path.exists(expected_pdf):
        raise PDFGenerationError(
            "LibreOffice no pudo convertir el .docx a PDF. "
            f"stdout={result.stdout.strip()!r} stderr={result.stderr.strip()!r}"
        )
    return expected_pdf


def _extract_text(pdf_path: str) -> str:
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages).strip()


def generate_and_verify_pdf(
    docx_path: str,
    output_dir: str,
    expected_name_fragment: str,
    *,
    max_attempts: int = 2,
) -> PDFResult:
    """Convierte docx_path a PDF y verifica que el texto sea extraíble.

    `expected_name_fragment` (ej. el nombre del candidato) se usa como
    chequeo mínimo de sanidad: si no aparece en el texto extraído, el PDF
    se considera sospechoso de estar corrupto/rasterizado.
    """
    last_error: str | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            pdf_path = _convert_with_libreoffice(docx_path, output_dir)
            texto = _extract_text(pdf_path)
            if not texto:
                raise PDFGenerationError(
                    "El PDF se generó pero no se pudo extraer texto seleccionable "
                    "(posible rasterización)."
                )
            if expected_name_fragment and expected_name_fragment.lower() not in texto.lower():
                raise PDFGenerationError(
                    "El texto extraído del PDF no contiene el contenido esperado "
                    "(posible corrupción en la conversión)."
                )
            return PDFResult(
                pdf_path=pdf_path,
                verificado=True,
                texto_extraido_preview=texto[:300],
            )
        except PDFGenerationError as exc:
            last_error = str(exc)
            continue

    return PDFResult(
        pdf_path=None,
        verificado=False,
        texto_extraido_preview="",
        error=(
            f"No se pudo generar un PDF verificado tras {max_attempts} intento(s): "
            f"{last_error}. Se entrega únicamente el .docx."
        ),
    )
