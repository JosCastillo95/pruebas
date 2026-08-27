"""Sección 4 — Validación anti-alucinación (obligatoria, no opcional).

Capa 1: validación programática (sin IA) de herramientas, empresas y cifras.
Capa 2: validación semántica vía la API de Claude, oración por oración.

Regla de bloqueo: cualquier discrepancia "crítica" (de cualquiera de las dos
capas) impide la generación de archivos. Las "matiz" solo se muestran como
advertencia.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from .claude_client import ClaudeClient

NUMBER_PATTERN = re.compile(r"\d[\d,.]*\s*%?")
PARENTHETICAL_PATTERN = re.compile(r"\s*\([^)]*\)")


def _normalize(text: str) -> str:
    """Minúsculas, sin acentos, sin paréntesis, espacios colapsados.

    Se usa para comparar empresas/herramientas del CV_ADAPTADO contra el
    CV_MAESTRO tolerando variaciones superficiales (acentos, un paréntesis
    aclaratorio como "Grupo Peñafiel (Keurig Dr Pepper)") sin abrir la
    puerta a falsos negativos: solo colapsa forma, nunca contenido.
    """
    text = PARENTHETICAL_PATTERN.sub("", text or "")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text).strip().lower()

CAPA2_SYSTEM_PROMPT = """\
Compara el CV_ADAPTADO contra el CV_MAESTRO, oración por oración.
Marca CUALQUIER frase, cifra, herramienta, fecha o logro en CV_ADAPTADO que no tenga
un respaldo directo y verificable en CV_MAESTRO — incluyendo matices de exageración
(ej. "lideré" cuando el CV_MAESTRO dice "participé en").
Responde solo con una lista de discrepancias (vacía si no hay ninguna), clasificadas
como "crítica" (dato inventado) o "matiz" (verbo/tono exagerado).

Responde solo en JSON con esta forma exacta:
{
  "discrepancias": [
    {"fragmento_cv_adaptado": "...", "respaldo_cv_maestro": "... | null", "clasificacion": "crítica|matiz", "explicacion": "..."}
  ]
}
"""


def _collect_strings(obj: Any, out: list[str]) -> None:
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            _collect_strings(value, out)
    elif isinstance(obj, list):
        for item in obj:
            _collect_strings(item, out)


def _flatten_text(obj: Any) -> str:
    strings: list[str] = []
    _collect_strings(obj, strings)
    return " | ".join(strings)


def _master_tool_set(cv_maestro: dict) -> set[str]:
    tools: set[str] = set()
    for exp in cv_maestro.get("experiencia", []):
        for tool in exp.get("herramientas_usadas", []) or []:
            tools.add(_normalize(tool))
    competencias = cv_maestro.get("herramientas_y_competencias", {}) or {}
    for grupo in competencias.values():
        for item in grupo or []:
            tools.add(_normalize(str(item)))
    return {t for t in tools if t}


def _master_company_set(cv_maestro: dict) -> set[str]:
    return {
        _normalize(exp.get("empresa", ""))
        for exp in cv_maestro.get("experiencia", [])
        if exp.get("empresa")
    }


def _experience_bullets(exp: dict) -> list[str]:
    for key in ("logros_y_responsabilidades", "bullets", "logros"):
        if key in exp and exp[key]:
            return list(exp[key])
    return []


def _collect_adapted_tools(cv_adaptado: dict) -> list[str]:
    tools = list(cv_adaptado.get("herramientas_destacadas", []) or [])
    for exp in cv_adaptado.get("experiencia_seleccionada", []) or []:
        tools.extend(exp.get("herramientas_usadas", []) or [])
    return [t for t in tools if isinstance(t, str) and t.strip()]


def _collect_adapted_companies(cv_adaptado: dict) -> list[str]:
    return [
        exp.get("empresa", "")
        for exp in cv_adaptado.get("experiencia_seleccionada", []) or []
        if exp.get("empresa")
    ]


def _collect_adapted_numbers(cv_adaptado: dict) -> list[str]:
    text_parts = [cv_adaptado.get("perfil_resumen", "") or ""]
    for exp in cv_adaptado.get("experiencia_seleccionada", []) or []:
        text_parts.extend(_experience_bullets(exp))
    blob = " | ".join(text_parts)
    return [m.group(0).strip() for m in NUMBER_PATTERN.finditer(blob)]


def validar_capa1(cv_maestro: dict, cv_adaptado: dict) -> list[dict]:
    """Validación programática: sin llamadas a la API.

    Cualquier herramienta, empresa o cifra del CV_ADAPTADO que no tenga un
    match literal (o de subcadena) en el CV_MAESTRO se marca como
    discrepancia crítica automáticamente.
    """
    discrepancias: list[dict] = []

    master_tools = _master_tool_set(cv_maestro)
    for tool in _collect_adapted_tools(cv_adaptado):
        normalized = _normalize(tool)
        if normalized in master_tools:
            continue
        # Subcadena permitida solo en un sentido y con un largo mínimo, para
        # tolerar variantes de redacción ("API de Anthropic" vs "Anthropic
        # API") sin dejar pasar coincidencias parciales de abreviaturas
        # cortas (ej. "SEM" no debe "matchear" dentro de una palabra inventada).
        if len(normalized) >= 6 and any(
            normalized in mt or mt in normalized for mt in master_tools if len(mt) >= 6
        ):
            continue
        discrepancias.append(
            {
                "capa": 1,
                "tipo": "herramienta",
                "valor": tool,
                "clasificacion": "crítica",
                "explicacion": (
                    f"La herramienta/plataforma '{tool}' no aparece en el CV_MAESTRO."
                ),
            }
        )

    master_companies = _master_company_set(cv_maestro)
    for company in _collect_adapted_companies(cv_adaptado):
        normalized_company = _normalize(company)
        if normalized_company in master_companies:
            continue
        # Igual que con herramientas: subcadena tolerada solo con largo
        # mínimo, para permitir que se omita un calificativo entre
        # paréntesis (ej. "Grupo Peñafiel" vs "Grupo Peñafiel (Keurig Dr
        # Pepper)") sin aceptar coincidencias parciales espurias.
        if len(normalized_company) >= 6 and any(
            normalized_company in mc or mc in normalized_company
            for mc in master_companies
            if len(mc) >= 6
        ):
            continue
        discrepancias.append(
                {
                    "capa": 1,
                    "tipo": "empresa",
                    "valor": company,
                    "clasificacion": "crítica",
                    "explicacion": f"La empresa '{company}' no aparece en el CV_MAESTRO.",
                }
            )

    master_text = _flatten_text(cv_maestro)
    master_numbers = {
        m.group(0).strip() for m in NUMBER_PATTERN.finditer(master_text)
    }
    for number in _collect_adapted_numbers(cv_adaptado):
        if number in master_numbers:
            continue
        discrepancias.append(
            {
                "capa": 1,
                "tipo": "cifra",
                "valor": number,
                "clasificacion": "crítica",
                "explicacion": (
                    f"La cifra '{number}' no aparece de forma literal en el CV_MAESTRO."
                ),
            }
        )

    return discrepancias


def validar_capa2(
    cv_maestro: dict, cv_adaptado: dict, client: ClaudeClient | None = None
) -> list[dict]:
    """Validación semántica vía la API de Claude (oración por oración)."""
    client = client or ClaudeClient()
    user_content = json.dumps(
        {"CV_MAESTRO": cv_maestro, "CV_ADAPTADO": cv_adaptado}, ensure_ascii=False
    )
    result = client.call_json(CAPA2_SYSTEM_PROMPT, user_content)
    discrepancias = result.get("discrepancias", []) if isinstance(result, dict) else result
    for d in discrepancias:
        d["capa"] = 2
    return discrepancias


def validar(
    cv_maestro: dict, cv_adaptado: dict, client: ClaudeClient | None = None
) -> dict:
    """Ejecuta ambas capas y aplica la regla de bloqueo.

    Devuelve:
      {
        "bloqueado": bool,
        "discrepancias_criticas": [...],
        "discrepancias_matiz": [...],
      }
    """
    client = client or ClaudeClient()

    capa1 = validar_capa1(cv_maestro, cv_adaptado)
    capa2 = validar_capa2(cv_maestro, cv_adaptado, client)

    criticas = list(capa1) + [d for d in capa2 if d.get("clasificacion") == "crítica"]
    matices = [d for d in capa2 if d.get("clasificacion") == "matiz"]

    return {
        "bloqueado": len(criticas) > 0,
        "discrepancias_criticas": criticas,
        "discrepancias_matiz": matices,
    }
