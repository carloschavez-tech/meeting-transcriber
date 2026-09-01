"""Genera una especificación de dominio (metodología del skill
'entrevista-a-spec') a partir de la transcripción completa de una reunión,
vía Claude a través de OpenRouter.

A diferencia de report.py (un resumen ejecutivo corto), esto produce un
documento de dominio riguroso: qué se mide, con qué reglas, y qué tiene que
ser imposible — con IDs estables (RF, C, P, R, I), sin inventar cifras, y
marcando explícitamente supuestos y decisiones pendientes."""

import os

from openai import OpenAI

from src.report import OPENROUTER_BASE_URL, REPORT_MODEL

SYSTEM_PROMPT = (
    "Sos un analista de requerimientos senior que aplica la metodología 'entrevista a "
    "spec': tu trabajo es convertir la transcripción de una reunión en una especificación "
    "de dominio — qué se mide, con qué reglas, y qué tiene que ser imposible. NUNCA "
    "describís implementación (nada de bases de datos, pantallas, endpoints, ni "
    "tecnologías). Si de una línea se puede deducir el stack técnico, esa línea está mal "
    "ubicada.\n\n"
    "El valor está en lo que la persona NO dijo porque le pareció obvio — la ambigüedad "
    "vive ahí. Cazá los disparadores de ambigüedad en la transcripción ('normalmente', "
    "'en general', 'el sistema valida', 'automáticamente', 'debería', 'obvio', 'se "
    "notifica', 'rápido'/'muchos'/'un tiempo' sin cifra) y, como no podés volver a "
    "preguntar, marcá esos huecos explícitamente como supuesto o como pendiente en la "
    "sección 11 — nunca los rellenes inventando.\n\n"
    "Reglas de estilo, no negociables:\n"
    "- NO INVENTES CIFRAS. Si no hay número en la transcripción, la regla se escribe sin "
    "número y el dato faltante va a la sección 11.\n"
    "- Los supuestos se marcan explícitamente como tales, nunca se cuelan como si fueran "
    "hechos confirmados.\n"
    "- Lenguaje llano y del negocio (las palabras que usó la persona en la reunión), sin "
    "adjetivos de folleto ('robusto', 'escalable', 'de clase mundial').\n"
    "- Cada regla o decisión que sorprenda lleva su porqué en la misma línea.\n"
    "- IDs estables: RF# (requerimientos funcionales), C# (cualidades), P# (principios), "
    "R# (reglas de negocio), I# (invariantes). Nunca reciclar un ID. Las reglas se "
    "referencian entre sí por ID entre paréntesis.\n"
    "- Si una sección no tiene material en la transcripción, se deja con una línea que "
    "explique por qué está vacía — no se borra la sección.\n\n"
    "Respondé siempre en español."
)

USER_PROMPT_TEMPLATE = """Esta es la transcripción completa de una reunión (puede tener errores \
de transcripción y no indica quién habla). Generá la especificación de dominio completa. \
Seguí EXACTAMENTE esta estructura de 11 secciones, en este orden, con estos encabezados:

## 1. Objetivo
Dos o tres párrafos en lenguaje llano: para qué existe esto, para quién. Después, una lista \
numerada de "las preguntas que el sistema responde", en las palabras usadas en la reunión — \
es el índice real del documento, cada una debe tener después su regla. Después "### \
Granularidad" (cuál es la unidad de decisión y cuál la de captura, si se puede inferir) y \
"### Fuera de alcance" (qué se dijo explícitamente que no se va a hacer, y por qué).

## 2. Requerimientos
Tabla "### Lo que el sistema hace": columnas ID (RF#) | Requerimiento | Estado. Una capacidad \
por fila, en infinitivo, en lenguaje de negocio. Si una fila necesitaría "y" dos veces, son \
dos requerimientos separados. Después tabla "### Cómo tiene que comportarse": columnas ID \
(C#) | Cualidad — cada cualidad tiene que poder fallar de forma observable ("rápido" no \
sirve; "cargar un mes no toma más de 15 minutos" sí, pero solo si esa cifra se mencionó de \
verdad en la reunión).

## 3. Principios
Tabla P# | Principio (en negrita, como frase tajante) | Consecuencia práctica. Solo \
principios que realmente se dijeron o se desprenden con claridad de la transcripción — no \
inventes principios genéricos.

## 4. Glosario
Si aplica, tabla de traducción dominio → pantalla (palabras internas del negocio vs. cómo \
las vería un usuario). Después, lista de términos del negocio usados en la reunión, cada uno \
definido sin apoyarse en otro término indefinido.

## 5. Reglas de negocio
La sección más larga. Cada regla como "### R# — Nombre corto". Si la regla calcula algo, la \
fórmula va en un bloque de código (solo si los datos para armarla están realmente en la \
transcripción — si no, escribí la regla en palabras y marcá la fórmula como pendiente en la \
sección 11). Si la regla decide, listá todos los casos mencionados, incluido el que nadie \
mencionó explícitamente pero se puede inferir que existe. El porqué de lo que sorprenda, en \
la misma línea. Referencias cruzadas entre reglas por ID (ej. "ver R4, P2").

## 6. Invariantes
Tabla ID (I#) | Invariante — afirmaciones verificables que tienen que ser ciertas siempre \
("un depósito pertenece a un solo proceso" sí; "el sistema debe ser seguro" no). Si hay \
aislamiento entre entidades (multi-cliente, multi-proceso, multi-tenant), decilo explícito \
acá y notá que se construye antes que la primera tabla de datos.

## 7. Dependencias externas
Por cada tercero mencionado en la reunión: qué se le pide, qué se guarda de la respuesta, y \
qué pasa si no responde (si se habló de eso en la reunión; si no se mencionó, decilo así en \
la sección 11 en vez de inventarlo).

## 8. Rituales
Momentos recurrentes del proceso mencionados (cierres, cortes, radicaciones, conciliaciones) \
con qué se hace en cada uno y cada cuánto.

## 9. Cómo se verifica
Tabla Situación | Resultado esperado, con cifras reales SOLO si se mencionaron en la \
transcripción, indicando de dónde salieron (memoria de la persona, un archivo que \
mencionaron, etc.). Si no hay cifras reales en toda la reunión, decilo explícitamente en vez \
de inventar ejemplos.

## 10. Estado
Qué existe hoy construido, según lo que se dijo en la reunión, sin optimismo — si nada está \
construido, decilo con esas palabras. Tabla de frentes en el orden sugerido de construcción, \
con las reglas que cubre cada uno.

## 11. Lo que falta
Tres tablas separadas:
- "### Datos faltantes": la regla ya está escrita pero falta un número/dato concreto (no \
bloquea la entrega).
- "### Decisiones pendientes": nadie definió qué debe pasar (si se puede inferir quién \
debería decidirlo, decilo; esto SÍ bloquea).
- "### Supuestos": cosas que vos asumiste al escribir esta spec porque no quedaron \
explícitas en la reunión, numeradas S1, S2, etc.

No agregues secciones fuera de esta lista de 11. Si una sección no tiene contenido real de \
la transcripción, dejala con una sola línea explicando por qué está vacía, no la inventes ni \
la borres.

Transcripción:
---
{transcript}
---
"""


def generate_spec(transcript_path: str, output_dir: str) -> str:
    """Genera spec.md en output_dir a partir de transcript_path. Devuelve la ruta al spec."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta OPENROUTER_API_KEY. Configurala en tu .env (ver .env.example)."
        )

    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = f.read()

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
    print(f"Generando spec de dominio con {REPORT_MODEL} (vía OpenRouter)...")
    response = client.chat.completions.create(
        model=REPORT_MODEL,
        max_tokens=16000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(transcript=transcript)},
        ],
    )

    spec_text = response.choices[0].message.content

    os.makedirs(output_dir, exist_ok=True)
    spec_path = os.path.join(output_dir, "spec.md")
    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(spec_text + "\n")

    print(f"Spec de dominio guardado en {spec_path}")
    return spec_path
