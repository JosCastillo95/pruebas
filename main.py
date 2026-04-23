import os
import json
import anthropic
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

CHAR_LIMITS = {
    "Amazon":   {"title": 200, "bullet": 250,  "description": 2000},
    "Walmart":  {"title": 75,  "bullet": 200,  "description": 4000},
    "Chedraui": {"title": 100, "bullet": 200,  "description": 2000},
}

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
- Walmart: Title [Brand+Product+Key features+Units]. Description: strategic KWs in first line, functional benefits. 3-5 bullets.
- Amazon: Title [Brand+Line+Attribute+Size+Quantity]. EXACTLY 5 bullets, each starting with AN UPPERCASE HEADING followed by ": ". Description: technical paragraphs, A+ ready.
- Chedraui: Title [Brand+Product+Content/Units]. Description MUST include "Instrucciones de Uso:" and "Advertencias:" subsections. 3-5 bullets.

STYLE: Executive, technical, direct. FORBIDDEN: emotional language, emojis, unmeasurable adjectives ("best", "amazing").

GENERIC TEXT:
{GENERIC_TEXT}

KEYWORDS AVAILABLE:
{KEYWORDS}

RESPOND ONLY WITH VALID JSON. No text before or after. No markdown. No backticks. Start with {{ end with }}.
Exact schema:
{{"titulo_optimizado":"","caracteres_titulo":0,"bullet_points":[""],"descripcion_optimizada":"","caracteres_descripcion":0,"keywords_integradas":[""],"vision_insights":""}}"""


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.json
    brand        = data.get("brand", "").strip()
    retailer     = data.get("retailer", "").strip()
    generic_text = data.get("generic_text", "").strip()
    keywords     = data.get("keywords", "").strip()
    image_b64    = data.get("image_b64", "")
    image_type   = data.get("image_type", "image/jpeg")

    if not brand or not retailer or not keywords:
        return jsonify({"error": "Brand, retailer y keywords son requeridos."}), 400

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en Secrets."}), 500

    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        BRAND=brand,
        RETAILER=retailer,
        GENERIC_TEXT=generic_text or "(Sin texto genérico — inferir atributos del contexto visual)",
        KEYWORDS=keywords,
    )

    user_content = []
    if image_b64:
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": image_type, "data": image_b64},
        })
    user_content.append({
        "type": "text",
        "text": f"Optimiza el contenido para la marca {brand} en {retailer}.",
    })

    try:
        with client.messages.stream(
            model="claude-opus-4-7",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            message = stream.get_final_message()

        raw = next((b.text for b in message.content if b.type == "text"), "").strip()
        result = json.loads(raw)
        result["char_limits"] = CHAR_LIMITS.get(retailer, CHAR_LIMITS["Amazon"])
        return jsonify({"success": True, "result": result})

    except json.JSONDecodeError:
        return jsonify({"error": "La respuesta no es JSON válido.", "raw": raw}), 500
    except anthropic.APIError as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
