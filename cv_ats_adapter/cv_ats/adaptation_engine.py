"""Sección 3 — Motor de adaptación.

Genera el primer borrador del CV_ADAPTADO a partir del CV_MAESTRO y la
vacante analizada, bajo las reglas inquebrantables de veracidad. El prompt
de sistema se usa literal, tal como está definido en la especificación.
"""

from __future__ import annotations

import json

from .claude_client import ClaudeClient

SYSTEM_PROMPT = """\
Eres un experto en redacción de CVs ATS-optimizados que sigue reglas estrictas de veracidad.

REGLAS INQUEBRANTABLES:
1. Solo puedes usar información contenida en el CV_MAESTRO proporcionado.
2. NO inventes cifras, porcentajes, herramientas, certificaciones, empresas, fechas ni responsabilidades.
3. Si un campo del CV_MAESTRO está vacío (ej. fechas de Peñafiel, métricas no documentadas),
   NO lo completes ni lo infieras. Omite el dato o dejalo genérico sin inventar specifics.
4. Puedes: reordenar, priorizar, reformular con sinónimos, ajustar nivel de detalle,
   y elegir qué bullets mostrar u ocultar según relevancia para la vacante.
5. Puedes reformular la REDACCIÓN de un logro ya existente para usar el vocabulario de la
   vacante (ej. "aumenté ventas" → "impulsé el growth de..."), pero el HECHO subyacente
   debe ser idéntico y verificable en el CV_MAESTRO.
6. Prioriza términos transaccionales (accionables, orientados a resultado de negocio) sobre
   términos puramente informativos/educativos, en proporción aproximada 70/30, siempre que
   el CV_MAESTRO lo permita sin forzar el lenguaje.
7. Si la vacante requiere algo que el usuario no tiene en su CV_MAESTRO, NO lo agregues.
8. Al final de tu respuesta, incluye "gaps_detectados": requisitos de la vacante que el
   CV_MAESTRO no cubre, y "campos_incompletos_relevantes": campos vacíos del CV_MAESTRO que
   serían valiosos completar para esta vacante en particular (ej. "fechas de Peñafiel",
   "métricas de Grupo Peñafiel").

INPUT:
- CV_MAESTRO: {json completo}
- VACANTE_ANALIZADA: {json del paso 2}

OUTPUT (JSON):
{
  "idioma_cv": "es | en",
  "perfil_resumen": "...",
  "experiencia_seleccionada": [...],
  "herramientas_destacadas": [...],
  "orden_de_prioridad_bullets": {...},
  "gaps_detectados": [...],
  "campos_incompletos_relevantes": [...]
}
"""


def generate_draft(
    cv_maestro: dict,
    vacante_analizada: dict,
    client: ClaudeClient | None = None,
) -> dict:
    """Genera el primer borrador de CV_ADAPTADO (Sección 3)."""
    client = client or ClaudeClient()
    user_content = json.dumps(
        {"CV_MAESTRO": cv_maestro, "VACANTE_ANALIZADA": vacante_analizada},
        ensure_ascii=False,
    )
    draft = client.call_json(SYSTEM_PROMPT, user_content)
    draft.setdefault("gaps_detectados", [])
    draft.setdefault("campos_incompletos_relevantes", [])
    return draft
