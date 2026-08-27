"""Sección 5 — Metodología de Refinamiento en 4 Fases.

Orquesta las 4 fases sobre el borrador que produce el motor de adaptación
(adaptation_engine.generate_draft). Ninguna fase puede inventar información
fuera del CV_MAESTRO — esa regla de la Sección 3 aplica sin excepción.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .claude_client import ClaudeClient

MAX_CICLOS_REINTENTO = 2
UMBRAL_APROBACION = 70

FASE1_SYSTEM_PROMPT = """\
Actúa como un reclutador senior de la empresa de la vacante. Lee el CV_ADAPTADO como lo
harías en la vida real, buscando razones para descartarlo. Identifica las 3 señales de
alerta más fuertes que un gerente de contratación detectaría en menos de 10 segundos.

Solo puedes señalar problemas de REDACCIÓN, ENFOQUE o AUSENCIA DE MÉTRICA — nunca sugieras
agregar información que no exista en CV_MAESTRO.

INPUT: CV_ADAPTADO, VACANTE_ANALIZADA

OUTPUT (JSON):
{
  "señales_detectadas": [
    {"señal": "...", "bullet_afectado": "...", "severidad": "alta|media|baja"}
  ]
}
"""

FASE2_SYSTEM_PROMPT = """\
Eres un experto en redacción de CVs ATS-optimizados que sigue reglas estrictas de veracidad.

REGLAS INQUEBRANTABLES (heredadas, sin excepción):
1. Solo puedes usar información contenida en el CV_MAESTRO proporcionado.
2. NO inventes cifras, porcentajes, herramientas, certificaciones, empresas, fechas ni responsabilidades.
3. Si un campo del CV_MAESTRO está vacío, NO lo completes ni lo infieras.
4. Puedes reordenar, priorizar, reformular con sinónimos y ajustar nivel de detalle.
5. El HECHO subyacente de cada bullet debe seguir siendo idéntico y verificable en CV_MAESTRO.

REGLA ADICIONAL DE ESTA FASE:
Cada bullet de experiencia_seleccionada debe seguir la fórmula XYZ de Google:
"Logré [X], medido por [Y], haciendo [Z]".

Si un bullet del CV_MAESTRO es genérico y no tiene métrica verificable, NO inventes
la métrica faltante. En su lugar: (a) prioriza otro bullet del mismo puesto que sí
tenga métrica, o (b) si no existe otro, reformula usando alcance/escala verificable
(ej. "para 3 marcas en 8 países" en vez de un porcentaje inventado), o (c) déjalo en
gaps_detectados como "requiere métrica que el usuario debe proporcionar".

Usa las señales_detectadas de la Fase 1 (y, si existen, las secciones_en_riesgo de un
ciclo previo de Fase 3) como lista de pendientes a resolver — cada señal de severidad
"alta" debe quedar resuelta o justificada en gaps_detectados.

INPUT: CV_MAESTRO, CV_ADAPTADO, VACANTE_ANALIZADA, señales_detectadas, secciones_en_riesgo

OUTPUT (JSON):
{
  "experiencia_reescrita": [...],
  "señales_resueltas": [...],
  "señales_no_resueltas_por_falta_de_dato": [...]
}
"""

FASE3_SYSTEM_PROMPT = """\
Actúa simultáneamente como (a) un filtro ATS que compara CV_ADAPTADO contra
VACANTE_ANALIZADA por coincidencia de keywords, y (b) un gerente de contratación
que ha leído 200 CVs en esta sesión y decide en segundos qué sigue leyendo.

Da un puntaje de compatibilidad de 1 a 100 y señala qué secciones se saltaría
un lector así de rápido, con la razón exacta (no genérica).

INPUT: CV_ADAPTADO (post-Fase 2), VACANTE_ANALIZADA

OUTPUT (JSON):
{
  "puntaje_compatibilidad": 0-100,
  "secciones_en_riesgo": [{"seccion": "...", "razon": "..."}]
}
"""

FASE4_SYSTEM_PROMPT = """\
Reescribe el perfil_resumen para que un reclutador sienta que ignorar a este
candidato sería un error. Usa tensión y una frase de cierre memorable, sin
inventar ni exagerar ningún hecho fuera de CV_MAESTRO.

Al final, incluye una advertencia: si esta frase se usará en un CV/LinkedIn
escrito (no narrado en video), evalúa si el cierre puede leerse como arrogante
fuera de contexto, y ofrece una versión suavizada alternativa.

INPUT: CV_MAESTRO, CV_ADAPTADO

OUTPUT (JSON):
{
  "perfil_resumen_variante_gancho": "...",
  "advertencia_tono": "...",
  "version_suavizada_alternativa": "..."
}
"""


@dataclass
class RefinementResult:
    aprobado: bool
    cv_adaptado_final: dict
    señales_detectadas: list = field(default_factory=list)
    señales_resueltas: list = field(default_factory=list)
    señales_no_resueltas_por_falta_de_dato: list = field(default_factory=list)
    puntaje_compatibilidad: int | None = None
    secciones_en_riesgo: list = field(default_factory=list)
    ciclos_reintento: int = 0
    motivo_no_aprobado: str | None = None
    perfil_resumen_variante_gancho: str | None = None
    advertencia_tono_gancho: str | None = None
    version_suavizada_gancho: str | None = None


def _run_fase1(cv_adaptado: dict, vacante_analizada: dict, client: ClaudeClient) -> dict:
    user_content = json.dumps(
        {"CV_ADAPTADO": cv_adaptado, "VACANTE_ANALIZADA": vacante_analizada},
        ensure_ascii=False,
    )
    result = client.call_json(FASE1_SYSTEM_PROMPT, user_content)
    result.setdefault("señales_detectadas", [])
    return result


def _run_fase2(
    cv_maestro: dict,
    cv_adaptado: dict,
    vacante_analizada: dict,
    señales_detectadas: list,
    secciones_en_riesgo: list,
    client: ClaudeClient,
) -> dict:
    user_content = json.dumps(
        {
            "CV_MAESTRO": cv_maestro,
            "CV_ADAPTADO": cv_adaptado,
            "VACANTE_ANALIZADA": vacante_analizada,
            "señales_detectadas": señales_detectadas,
            "secciones_en_riesgo": secciones_en_riesgo,
        },
        ensure_ascii=False,
    )
    result = client.call_json(FASE2_SYSTEM_PROMPT, user_content)
    result.setdefault("experiencia_reescrita", cv_adaptado.get("experiencia_seleccionada", []))
    result.setdefault("señales_resueltas", [])
    result.setdefault("señales_no_resueltas_por_falta_de_dato", [])
    return result


def _run_fase3(cv_adaptado_actual: dict, vacante_analizada: dict, client: ClaudeClient) -> dict:
    user_content = json.dumps(
        {"CV_ADAPTADO": cv_adaptado_actual, "VACANTE_ANALIZADA": vacante_analizada},
        ensure_ascii=False,
    )
    result = client.call_json(FASE3_SYSTEM_PROMPT, user_content)
    result.setdefault("puntaje_compatibilidad", 0)
    result.setdefault("secciones_en_riesgo", [])
    return result


def _run_fase4(cv_maestro: dict, cv_adaptado: dict, client: ClaudeClient) -> dict:
    user_content = json.dumps(
        {"CV_MAESTRO": cv_maestro, "CV_ADAPTADO": cv_adaptado}, ensure_ascii=False
    )
    return client.call_json(FASE4_SYSTEM_PROMPT, user_content)


def run_refinement(
    cv_maestro: dict,
    vacante_analizada: dict,
    draft: dict,
    *,
    generar_variante_gancho: bool = False,
    client: ClaudeClient | None = None,
) -> RefinementResult:
    """Ejecuta las 4 fases sobre `draft` (salida de adaptation_engine.generate_draft).

    Devuelve un RefinementResult con `aprobado=False` si tras
    MAX_CICLOS_REINTENTO ciclos el puntaje sigue por debajo de
    UMBRAL_APROBACION — en ese caso el pipeline debe detenerse antes de
    llegar a la validación anti-alucinación.
    """
    client = client or ClaudeClient()

    cv_adaptado = dict(draft)

    fase1 = _run_fase1(cv_adaptado, vacante_analizada, client)
    señales_detectadas = fase1["señales_detectadas"]

    secciones_en_riesgo: list = []
    señales_resueltas: list = []
    señales_no_resueltas: list = []
    puntaje = 0
    ciclo = 0

    while True:
        fase2 = _run_fase2(
            cv_maestro,
            cv_adaptado,
            vacante_analizada,
            señales_detectadas,
            secciones_en_riesgo,
            client,
        )
        cv_adaptado = {
            **cv_adaptado,
            "experiencia_seleccionada": fase2["experiencia_reescrita"],
        }
        señales_resueltas = fase2["señales_resueltas"]
        señales_no_resueltas = fase2["señales_no_resueltas_por_falta_de_dato"]

        fase3 = _run_fase3(cv_adaptado, vacante_analizada, client)
        puntaje = fase3["puntaje_compatibilidad"]
        secciones_en_riesgo = fase3["secciones_en_riesgo"]

        if puntaje >= UMBRAL_APROBACION:
            break
        if ciclo >= MAX_CICLOS_REINTENTO:
            break
        ciclo += 1

    aprobado = puntaje >= UMBRAL_APROBACION
    resultado = RefinementResult(
        aprobado=aprobado,
        cv_adaptado_final=cv_adaptado,
        señales_detectadas=señales_detectadas,
        señales_resueltas=señales_resueltas,
        señales_no_resueltas_por_falta_de_dato=señales_no_resueltas,
        puntaje_compatibilidad=puntaje,
        secciones_en_riesgo=secciones_en_riesgo,
        ciclos_reintento=ciclo,
        motivo_no_aprobado=(
            None
            if aprobado
            else (
                f"Tras {ciclo} ciclo(s) de reintento el puntaje de compatibilidad "
                f"sigue en {puntaje} (< {UMBRAL_APROBACION}). Probable gap real de "
                "experiencia frente a la vacante, no de redacción. Revisa "
                "secciones_en_riesgo y gaps_detectados."
            )
        ),
    )

    if aprobado and generar_variante_gancho:
        fase4 = _run_fase4(cv_maestro, cv_adaptado, client)
        resultado.perfil_resumen_variante_gancho = fase4.get("perfil_resumen_variante_gancho")
        resultado.advertencia_tono_gancho = fase4.get("advertencia_tono")
        resultado.version_suavizada_gancho = fase4.get("version_suavizada_alternativa")

    return resultado
