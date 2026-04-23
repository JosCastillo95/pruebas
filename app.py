import json
import os
import anthropic
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are a technical e-commerce content optimizer for Mexican retailers.

GOLDEN RULE — ZERO HALLUCINATION:
Your only source of truth is the GENERIC TEXT provided below. The image (if present) only confirms visual attributes like piece count, size, or variant.
DO NOT invent any feature not present in the generic text or confirmed visually.

KEYWORD RULE:
From the keyword list, integrate ONLY those that are semantically relevant and add technical value. Do NOT force all keywords. Prioritize transactional ones. Discard informational ones if they don't fit naturally.

BRAND VOICE — {BRAND}:
- Regio: Utilitarian, performance tone. MANDATORY: kitchen paper = "trapos de papel". FORBIDDEN: "toallas de papel".
- Saba: Clinical, anatomical, safety tone. Differentiate pantyliners, pads, and tampons based on image data.
- Tena: Clinical, respectful tone. MANDATORY: "ropa interior absorbente" or "protectores". FORBIDDEN: "pañal para adulto".

RETAILER FORMAT — {RETAILER}:
- Walmart: Title [Brand+Product+Key features+Units]. Description: strategic KWs in first line, functional benefits. 3–5 bullets.
- Amazon: Title [Brand+Line+Attribute+Size+Quantity]. EXACTLY 5 bullets, each starting with AN UPPERCASE HEADING followed by ": ". Description: technical paragraphs, A+ ready.
- Chedraui: Title [Brand+Product+Content/Units]. Description MUST include "Instrucciones de Uso:" and "Advertencias:" subsections. 3–5 bullets.

STYLE: Executive, technical, direct. FORBIDDEN: emotional language, emojis, unmeasurable adjectives ("best", "amazing").

GENERIC TEXT:
{GENERIC_TEXT}

KEYWORDS AVAILABLE:
{KEYWORDS}

RESPOND ONLY WITH VALID JSON. No text before or after. No markdown. No backticks. Start with {{ end with }}.
Exact schema:
{{"titulo_optimizado":"","caracteres_titulo":0,"bullet_points":[""],"descripcion_optimizada":"","caracteres_descripcion":0,"keywords_integradas":[""]}}"""


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.json
    brand = data.get("brand", "").strip()
    retailer = data.get("retailer", "").strip()
    generic_text = data.get("generic_text", "").strip()
    keywords = data.get("keywords", "").strip()

    if not all([brand, retailer, generic_text, keywords]):
        return jsonify({"error": "Todos los campos son obligatorios."}), 400

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        BRAND=brand,
        RETAILER=retailer,
        GENERIC_TEXT=generic_text,
        KEYWORDS=keywords,
    )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el servidor."}), 500

    client = anthropic.Anthropic(api_key=api_key)

    try:
        with client.messages.stream(
            model="claude-opus-4-7",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": f"Optimiza el contenido para la marca {brand} en {retailer}.",
                }
            ],
        ) as stream:
            message = stream.get_final_message()

        raw = next(
            (b.text for b in message.content if b.type == "text"), ""
        ).strip()

        result = json.loads(raw)
        return jsonify({"success": True, "result": result})

    except json.JSONDecodeError:
        return jsonify({"error": "La respuesta del modelo no es JSON válido.", "raw": raw}), 500
    except anthropic.APIError as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000)
