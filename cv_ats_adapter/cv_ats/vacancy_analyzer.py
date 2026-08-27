"""Sección 2 — Módulo de análisis de vacante.

Toma el texto plano de una vacante y le pide a Claude que lo convierta en
JSON estructurado (título, empresa, requisitos, keywords, seniority, idioma).
"""

from __future__ import annotations

from .claude_client import ClaudeClient

SYSTEM_PROMPT = """\
Extrae de la siguiente vacante:
- Título exacto del puesto
- Empresa
- Responsabilidades clave (lista)
- Requisitos indispensables vs. deseables
- Herramientas/plataformas mencionadas explícitamente
- Keywords recurrentes y su frecuencia (para optimización ATS)
- Seniority implícito (junior/mid/senior/manager/director)
- Idioma predominante de la vacante (para decidir si el CV debe ir en español o inglés)

Responde solo en JSON, sin explicación adicional. Usa esta forma exacta:
{
  "titulo_puesto": "...",
  "empresa": "...",
  "responsabilidades_clave": ["..."],
  "requisitos_indispensables": ["..."],
  "requisitos_deseables": ["..."],
  "herramientas_mencionadas": ["..."],
  "keywords_frecuencia": [{"keyword": "...", "frecuencia": 0}],
  "seniority": "junior|mid|senior|manager|director",
  "idioma_vacante": "es|en"
}
"""


def analyze_vacancy(vacancy_text: str, client: ClaudeClient | None = None) -> dict:
    """Analiza el texto de una vacante y devuelve el JSON estructurado.

    No hace ninguna referencia al CV_MAESTRO: este paso solo entiende la
    vacante en sí misma.
    """
    if not vacancy_text or not vacancy_text.strip():
        raise ValueError("El texto de la vacante está vacío.")

    client = client or ClaudeClient()
    return client.call_json(SYSTEM_PROMPT, vacancy_text.strip())
