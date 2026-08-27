# Adaptador de CV a Vacantes — ATS Expert Edition

App web local que adapta un CV Maestro (JSON) a una vacante específica,
usando la API de Claude bajo reglas estrictas de veracidad, y entrega el
resultado en `.docx` y `.pdf` con mejores prácticas de formato ATS.

## Principio rector

El `data/cv_maestro.json` es la **única fuente de verdad**. Ningún CV
generado puede contener una herramienta, empresa, cifra, fecha o logro que
no exista literalmente en ese archivo. Esto se aplica en dos niveles:

1. **Prompts de sistema** (Secciones 3 y 5 del spec) instruyen al modelo a
   no inventar nada y a dejar constancia de vacíos en `gaps_detectados`.
2. **Validación anti-alucinación** (`cv_ats/validator.py`, Sección 4): antes
   de generar cualquier archivo, se corre una Capa 1 programática (sin IA,
   por regex/substring) y una Capa 2 semántica (vía Claude). Si cualquiera
   de las dos detecta una discrepancia **crítica**, el pipeline se detiene
   y **no se genera ningún archivo**.

## Flujo

```
vacante (texto) → análisis (Sección 2)
  → borrador de adaptación (Sección 3)
  → Fase 1 (señales de alerta) → Fase 2 (reescritura XYZ) ⇄ Fase 3 (ATS/Recruiter Score)
      (hasta 2 reintentos si el puntaje < 70; si no se alcanza, se detiene aquí)
  → Validación anti-alucinación (Capas 1 y 2)
      (si hay discrepancias críticas, se detiene aquí — no se genera nada)
  → Generación de .docx (python-docx) y .pdf (LibreOffice headless + verificación con pdfplumber)
  → Fase 4 opcional: variante "gancho" del perfil (solo para LinkedIn/outreach, nunca reemplaza el CV formal)
```

## Instalación

```bash
cd cv_ats_adapter
pip install -r requirements.txt
cp .env.example .env   # y completa ANTHROPIC_API_KEY
```

Para exportar a PDF se necesita LibreOffice instalado en el sistema
(`soffice`/`libreoffice` en el PATH, con el componente **Writer** — en
Debian/Ubuntu: `apt-get install libreoffice-writer`). Si no está disponible,
la app sigue entregando el `.docx` y notifica el error de PDF en vez de
fallar en silencio.

## Uso

```bash
python app.py
```

Abre `http://localhost:5000`:

1. **CV Maestro**: edítalo directamente en el textarea (JSON) y guarda. Es
   el único lugar donde se agregan datos reales — la app nunca los inventa.
2. **Vacante**: pega el texto completo de la vacante.
3. **Adaptar CV a esta vacante**: corre todo el pipeline. Si se detiene
   (puntaje bajo persistente o discrepancia crítica), verás el motivo y,
   si aplica, el detalle de las discrepancias para decidir cómo continuar
   (editar el CV Maestro, ajustar el bullet a mano, o descartarlo).
4. Si el pipeline llega al final, descarga el `.docx` y/o `.pdf`, y revisa
   los paneles de `gaps_detectados`, `campos_incompletos_relevantes`,
   discrepancias tipo "matiz" (no bloquean) y secciones en riesgo.

## Estructura

```
cv_ats_adapter/
  app.py                     # Flask: UI + endpoints /api/*
  data/cv_maestro.json       # única fuente de verdad, editable desde la UI
  cv_ats/
    claude_client.py         # wrapper de la API de Claude (parseo JSON tolerante)
    vacancy_analyzer.py       # Sección 2
    adaptation_engine.py      # Sección 3 (reglas inquebrantables de veracidad)
    refinement.py              # Sección 5 (4 fases + ciclo de reintento)
    validator.py                # Sección 4 (Capas 1 y 2, regla de bloqueo)
    docx_generator.py           # Sección 6 (formato ATS-safe)
    pdf_generator.py            # Sección 7 (conversión + verificación con pdfplumber)
    pipeline.py                  # Sección 8 (orquestación completa)
  templates/, static/          # UI mínima
  output/                       # archivos generados (ignorado por git salvo .gitkeep)
```

## Variables de entorno

| Variable            | Descripción                                   | Default          |
|---------------------|------------------------------------------------|-------------------|
| `ANTHROPIC_API_KEY` | API key de Anthropic (requerida)                | —                 |
| `CLAUDE_MODEL`      | Modelo a usar en todas las llamadas             | `claude-sonnet-5` |
| `PORT`              | Puerto del servidor Flask                       | `5000`            |
| `FLASK_DEBUG`       | `1` para modo debug                             | `1`               |

## Notas

- Los seis `proyectos_destacados` sin métrica documentada nunca se rellenan
  con cifras inventadas; si una vacante los requiere con evidencia de
  resultado, el motor de adaptación debe dejarlo en `gaps_detectados`.
- Ver `.env.example` para la configuración mínima.
