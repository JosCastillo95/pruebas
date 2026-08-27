"""Sección 8 — Flujo completo de la app.

[vacante] -> analisis -> borrador (Sección 3)
  -> Fase 1 -> Fase 2 <-> Fase 3 (reintentos) (Sección 5)
  -> ¿aprobado? no -> detener, mostrar motivo
  -> validación anti-alucinación Capas 1 y 2 (Sección 4)
  -> ¿discrepancias críticas? sí -> detener, mostrar al usuario
  -> generar .docx + .pdf (Secciones 6 y 7)
  -> ¿generar_variante_gancho? -> Fase 4, guardar aparte
  -> entregar archivos + gaps_detectados + señales_no_resueltas + campos_incompletos_relevantes
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import adaptation_engine, docx_generator, pdf_generator, refinement, validator
from .claude_client import ClaudeClient
from .vacancy_analyzer import analyze_vacancy


@dataclass
class PipelineResult:
    detenido: bool
    motivo_detencion: str | None = None
    vacante_analizada: dict | None = None
    cv_adaptado_final: dict | None = None
    puntaje_compatibilidad: int | None = None
    ciclos_reintento: int = 0
    señales_detectadas: list = field(default_factory=list)
    señales_resueltas: list = field(default_factory=list)
    señales_no_resueltas_por_falta_de_dato: list = field(default_factory=list)
    secciones_en_riesgo: list = field(default_factory=list)
    gaps_detectados: list = field(default_factory=list)
    campos_incompletos_relevantes: list = field(default_factory=list)
    discrepancias_criticas: list = field(default_factory=list)
    discrepancias_matiz: list = field(default_factory=list)
    docx_path: str | None = None
    pdf_path: str | None = None
    pdf_error: str | None = None
    perfil_resumen_variante_gancho: str | None = None
    advertencia_tono_gancho: str | None = None
    version_suavizada_gancho: str | None = None


def run_pipeline(
    cv_maestro: dict,
    vacancy_text: str,
    output_dir: str,
    *,
    generar_variante_gancho: bool = False,
    client: ClaudeClient | None = None,
) -> PipelineResult:
    client = client or ClaudeClient()

    vacante_analizada = analyze_vacancy(vacancy_text, client)

    draft = adaptation_engine.generate_draft(cv_maestro, vacante_analizada, client)

    refinado = refinement.run_refinement(
        cv_maestro,
        vacante_analizada,
        draft,
        generar_variante_gancho=generar_variante_gancho,
        client=client,
    )

    gaps_detectados = list(draft.get("gaps_detectados", []))
    campos_incompletos_relevantes = list(draft.get("campos_incompletos_relevantes", []))

    if not refinado.aprobado:
        return PipelineResult(
            detenido=True,
            motivo_detencion=refinado.motivo_no_aprobado,
            vacante_analizada=vacante_analizada,
            cv_adaptado_final=refinado.cv_adaptado_final,
            puntaje_compatibilidad=refinado.puntaje_compatibilidad,
            ciclos_reintento=refinado.ciclos_reintento,
            señales_detectadas=refinado.señales_detectadas,
            señales_resueltas=refinado.señales_resueltas,
            señales_no_resueltas_por_falta_de_dato=refinado.señales_no_resueltas_por_falta_de_dato,
            secciones_en_riesgo=refinado.secciones_en_riesgo,
            gaps_detectados=gaps_detectados,
            campos_incompletos_relevantes=campos_incompletos_relevantes,
        )

    cv_adaptado_final = refinado.cv_adaptado_final

    validacion = validator.validar(cv_maestro, cv_adaptado_final, client)

    if validacion["bloqueado"]:
        return PipelineResult(
            detenido=True,
            motivo_detencion=(
                "Se detectaron discrepancias críticas frente al CV_MAESTRO. "
                "No se generó ningún archivo. Corrige el CV_MAESTRO, ajusta "
                "manualmente el bullet en cuestión, o descártalo."
            ),
            vacante_analizada=vacante_analizada,
            cv_adaptado_final=cv_adaptado_final,
            puntaje_compatibilidad=refinado.puntaje_compatibilidad,
            ciclos_reintento=refinado.ciclos_reintento,
            señales_detectadas=refinado.señales_detectadas,
            señales_resueltas=refinado.señales_resueltas,
            señales_no_resueltas_por_falta_de_dato=refinado.señales_no_resueltas_por_falta_de_dato,
            secciones_en_riesgo=refinado.secciones_en_riesgo,
            gaps_detectados=gaps_detectados,
            campos_incompletos_relevantes=campos_incompletos_relevantes,
            discrepancias_criticas=validacion["discrepancias_criticas"],
            discrepancias_matiz=validacion["discrepancias_matiz"],
        )

    docx_path = docx_generator.generate_docx(
        cv_maestro, cv_adaptado_final, vacante_analizada, output_dir
    )

    nombre_candidato = cv_maestro.get("datos_personales", {}).get("nombre_completo", "")
    pdf_result = pdf_generator.generate_and_verify_pdf(docx_path, output_dir, nombre_candidato)

    return PipelineResult(
        detenido=False,
        vacante_analizada=vacante_analizada,
        cv_adaptado_final=cv_adaptado_final,
        puntaje_compatibilidad=refinado.puntaje_compatibilidad,
        ciclos_reintento=refinado.ciclos_reintento,
        señales_detectadas=refinado.señales_detectadas,
        señales_resueltas=refinado.señales_resueltas,
        señales_no_resueltas_por_falta_de_dato=refinado.señales_no_resueltas_por_falta_de_dato,
        secciones_en_riesgo=refinado.secciones_en_riesgo,
        gaps_detectados=gaps_detectados,
        campos_incompletos_relevantes=campos_incompletos_relevantes,
        discrepancias_criticas=[],
        discrepancias_matiz=validacion["discrepancias_matiz"],
        docx_path=docx_path,
        pdf_path=pdf_result.pdf_path,
        pdf_error=pdf_result.error,
        perfil_resumen_variante_gancho=refinado.perfil_resumen_variante_gancho,
        advertencia_tono_gancho=refinado.advertencia_tono_gancho,
        version_suavizada_gancho=refinado.version_suavizada_gancho,
    )
