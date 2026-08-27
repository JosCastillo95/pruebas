"""App web local — Adaptador de CV a Vacantes (ATS Expert Edition).

Flujo (ver cv_ats/pipeline.py para el detalle sección por sección):
  1. El usuario mantiene su CV Maestro en JSON (editable desde /).
  2. Pega el texto de una vacante.
  3. La app corre el pipeline completo (análisis, adaptación, refinamiento
     en 4 fases, validación anti-alucinación, generación de .docx/.pdf).
  4. Descarga los archivos finales, o revisa por qué se detuvo el proceso.
"""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

from cv_ats.claude_client import ClaudeClient, ClaudeClientError, ClaudeJSONError
from cv_ats.pipeline import run_pipeline

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
CV_MAESTRO_PATH = os.path.join(DATA_DIR, "cv_maestro.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")


def _load_cv_maestro() -> dict:
    with open(CV_MAESTRO_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def index():
    from flask import render_template

    return render_template("index.html")


@app.route("/api/cv_maestro", methods=["GET"])
def get_cv_maestro():
    return jsonify(_load_cv_maestro())


@app.route("/api/cv_maestro", methods=["POST"])
def save_cv_maestro():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "JSON inválido."}), 400
    try:
        json.dumps(payload)
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"JSON no serializable: {exc}"}), 400

    with open(CV_MAESTRO_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True})


@app.route("/api/process", methods=["POST"])
def process():
    body = request.get_json(silent=True) or {}
    vacancy_text = (body.get("vacancy_text") or "").strip()
    generar_variante_gancho = bool(body.get("generar_variante_gancho", False))

    if not vacancy_text:
        return jsonify({"error": "Falta el texto de la vacante."}), 400

    cv_maestro = _load_cv_maestro()

    try:
        client = ClaudeClient()
        result = run_pipeline(
            cv_maestro,
            vacancy_text,
            OUTPUT_DIR,
            generar_variante_gancho=generar_variante_gancho,
            client=client,
        )
    except ClaudeClientError as exc:
        return jsonify({"error": str(exc)}), 400
    except ClaudeJSONError as exc:
        return (
            jsonify(
                {
                    "error": (
                        "El modelo no devolvió JSON válido en uno de los pasos del "
                        "pipeline. Intenta de nuevo."
                    ),
                    "detalle": str(exc),
                    "respuesta_cruda": exc.raw_text[:2000],
                }
            ),
            502,
        )

    response = {
        "detenido": result.detenido,
        "motivo_detencion": result.motivo_detencion,
        "vacante_analizada": result.vacante_analizada,
        "cv_adaptado_final": result.cv_adaptado_final,
        "puntaje_compatibilidad": result.puntaje_compatibilidad,
        "ciclos_reintento": result.ciclos_reintento,
        "señales_detectadas": result.señales_detectadas,
        "señales_resueltas": result.señales_resueltas,
        "señales_no_resueltas_por_falta_de_dato": result.señales_no_resueltas_por_falta_de_dato,
        "secciones_en_riesgo": result.secciones_en_riesgo,
        "gaps_detectados": result.gaps_detectados,
        "campos_incompletos_relevantes": result.campos_incompletos_relevantes,
        "discrepancias_criticas": result.discrepancias_criticas,
        "discrepancias_matiz": result.discrepancias_matiz,
        "pdf_error": result.pdf_error,
        "perfil_resumen_variante_gancho": result.perfil_resumen_variante_gancho,
        "advertencia_tono_gancho": result.advertencia_tono_gancho,
        "version_suavizada_gancho": result.version_suavizada_gancho,
        "docx_filename": os.path.basename(result.docx_path) if result.docx_path else None,
        "pdf_filename": os.path.basename(result.pdf_path) if result.pdf_path else None,
    }
    return jsonify(response)


@app.route("/api/download/<path:filename>")
def download(filename: str):
    safe_name = secure_filename(filename)
    return send_from_directory(OUTPUT_DIR, safe_name, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
