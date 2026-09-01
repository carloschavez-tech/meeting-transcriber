"""Genera un informe de reunión en Markdown a partir de una transcripción,
usando Claude a través de OpenRouter (API compatible con OpenAI)."""

import os

from openai import OpenAI

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
REPORT_MODEL = "anthropic/claude-sonnet-4.5"

SYSTEM_PROMPT = (
    "Sos un analista de requerimientos senior, con años de experiencia levantando "
    "requerimientos de software en reuniones con clientes. Tu trabajo es leer la "
    "transcripción de una reunión y extraer, estructurar y documentar TODOS los "
    "requerimientos mencionados por el cliente — explícitos e implícitos — sin omitir "
    "ningún detalle, por menor que parezca. Sos riguroso, preciso, y distinguís claramente "
    "entre lo que el cliente pidió, lo que quedó ambiguo, y lo que todavía falta confirmar. "
    "Respondé siempre en español, con lenguaje profesional y claro."
)

USER_PROMPT_TEMPLATE = """Esta es la transcripción de una reunión con un cliente (puede tener \
errores de transcripción y no indica quién habla). Analizala como lo haría un analista de \
requerimientos profesional y generá un documento de levantamiento de requerimientos en \
Markdown con esta estructura exacta:

## Contexto de la reunión
Párrafo breve: de qué proyecto/producto se trata y cuál fue el propósito de la reunión.

## Requerimientos funcionales
Lista con viñetas (una línea por ítem, empezando con "- ") de cada funcionalidad o
característica pedida por el cliente. Sé específico: qué debe hacer, para quién, y bajo qué
condiciones, usando las palabras del cliente cuando sea posible. No agrupes requerimientos
distintos en un solo punto.

## Requerimientos no funcionales
Requisitos de rendimiento, seguridad, usabilidad, integraciones con otros sistemas,
plataformas/dispositivos soportados, escalabilidad, disponibilidad, etc., si se mencionaron.

## Restricciones y condiciones
Presupuesto, plazos, tecnologías obligatorias o prohibidas, dependencias externas, u otras
limitaciones mencionadas por el cliente.

## Puntos ambiguos o a confirmar
Cosas que quedaron poco claras, contradictorias, o que un analista debería volver a
preguntarle al cliente antes de avanzar. Esta sección es tan importante como las anteriores:
señalá activamente cualquier vacío de información.

## Decisiones tomadas
Decisiones concretas ya acordadas en la reunión.

## Próximos pasos / tareas
Tareas o acciones mencionadas, con responsable si se indica.

Si una sección no tiene contenido, escribí "No se identificaron" en esa sección. Priorizá
exhaustividad sobre brevedad: es preferible un requerimiento de más (aunque parezca menor)
que uno omitido.

Transcripción:
---
{transcript}
---
"""


def generate_report(transcript_path: str, output_dir: str) -> str:
    """Genera report.md en output_dir a partir de transcript_path. Devuelve la ruta al informe."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta OPENROUTER_API_KEY. Configurala en tu .env (ver .env.example)."
        )

    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = f.read()

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
    print(f"Generando informe con {REPORT_MODEL} (vía OpenRouter)...")
    response = client.chat.completions.create(
        model=REPORT_MODEL,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(transcript=transcript)},
        ],
    )

    report_text = response.choices[0].message.content

    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text + "\n")

    print(f"Informe guardado en {report_path}")
    return report_path
