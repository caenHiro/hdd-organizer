"""
Clasificador de imágenes usando Ollama (modelo de visión local).

Usa modelos como moondream o llava corriendo en Ollama para categorizar imágenes
sin enviar datos a la nube. Ideal para M4 Pro con Ollama instalado via brew.

Categorías disponibles:
  wallpaper   Fondos de pantalla, paisajes artísticos, abstractos
  arte        Ilustraciones, arte digital, pinturas, diseño gráfico
  autos       Vehículos, coches, motos, transportes
  memes       Memes, capturas con texto, humor
  casa        Interior del hogar, muebles, decoración, plantas
  personas    Retratos, grupos, selfies, eventos sociales
  naturaleza  Paisajes, flora, fauna, cielos, mar
  animales    Mascotas, reptiles, animales de compañía
  screenshots Capturas de pantalla de aplicaciones o webs
  documentos  Fotos de documentos, textos, formularios
  otro        No encaja en ninguna categoría anterior

Uso:
    from organizador_hdd.clasificador_fotos_ollama import clasificar_foto_ollama
    cat = clasificar_foto_ollama(Path("foto.jpg"), model="moondream")
    print(cat)  # "naturaleza"

    # Batch (genera CSV con resultados)
    from organizador_hdd.clasificador_fotos_ollama import clasificar_directorio_ollama
    resultados = clasificar_directorio_ollama(Path("02_imagenes/"), model="moondream")
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# Extensiones de imagen soportadas
_EXT_IMAGEN = frozenset({
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".bmp", ".heic", ".heif", ".tiff", ".tif",
})

CATEGORIAS = [
    "wallpaper", "arte", "autos", "memes", "casa",
    "personas", "naturaleza", "animales", "screenshots", "documentos", "otro",
]

_PROMPT = (
    "Look at this image and classify it into EXACTLY ONE of these categories:\n"
    f"{', '.join(CATEGORIAS)}\n\n"
    "Rules:\n"
    "- wallpaper: artistic landscapes, abstract designs, desktop backgrounds\n"
    "- arte: illustrations, digital art, paintings, graphics\n"
    "- autos: vehicles, cars, motorcycles, trucks\n"
    "- memes: screenshots with text overlay, humorous images\n"
    "- casa: indoor home spaces, furniture, decor, home plants\n"
    "- personas: portraits, selfies, groups, people\n"
    "- naturaleza: outdoor landscapes, plants, sky, sea, wilderness\n"
    "- animales: pets, reptiles, wildlife, any animal\n"
    "- screenshots: app/web/desktop screenshots, UI captures\n"
    "- documentos: photos of documents, text, forms, IDs\n"
    "- otro: everything else\n\n"
    "Respond with ONLY the category name, nothing else."
)

_OLLAMA_URL = "http://localhost:11434/api/generate"


@dataclass
class ResultadoClasificacion:
    ruta: Path
    categoria: str
    confianza: str = "model"
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def clasificar_foto_ollama(
    ruta: Path,
    model: str = "moondream",
    timeout: int = 30,
) -> ResultadoClasificacion:
    """Clasifica una imagen usando un modelo de visión local en Ollama."""
    if ruta.suffix.lower() not in _EXT_IMAGEN:
        return ResultadoClasificacion(ruta=ruta, categoria="otro", error="extension_no_soportada")

    try:
        img_b64 = base64.b64encode(ruta.read_bytes()).decode()
    except OSError as e:
        return ResultadoClasificacion(ruta=ruta, categoria="otro", error=str(e))

    payload = json.dumps({
        "model": model,
        "prompt": _PROMPT,
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.1},
    }).encode()

    req = urllib.request.Request(
        _OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read())["response"].strip().lower()
    except urllib.error.URLError as e:
        return ResultadoClasificacion(ruta=ruta, categoria="otro", error=f"ollama_no_disponible: {e}")
    except Exception as e:
        return ResultadoClasificacion(ruta=ruta, categoria="otro", error=str(e))

    # Extraer categoría de la respuesta
    for cat in CATEGORIAS:
        if cat in raw:
            return ResultadoClasificacion(ruta=ruta, categoria=cat)

    return ResultadoClasificacion(ruta=ruta, categoria="otro")


def clasificar_directorio_ollama(
    directorio: Path,
    model: str = "moondream",
    timeout: int = 30,
    max_size_mb: float = 10.0,
) -> Iterator[ResultadoClasificacion]:
    """
    Itera sobre imágenes en un directorio y las clasifica con Ollama.
    Yields ResultadoClasificacion por imagen.

    max_size_mb: omite imágenes mayores a este tamaño (evita timeouts).
    """
    max_bytes = int(max_size_mb * 1024 * 1024)
    for ruta in sorted(directorio.rglob("*")):
        if not ruta.is_file():
            continue
        if ruta.suffix.lower() not in _EXT_IMAGEN:
            continue
        if ruta.stat().st_size > max_bytes:
            yield ResultadoClasificacion(ruta=ruta, categoria="otro", error="archivo_muy_grande")
            continue
        yield clasificar_foto_ollama(ruta, model=model, timeout=timeout)


def verificar_ollama(model: str = "moondream") -> tuple[bool, str]:
    """Verifica que Ollama esté disponible y el modelo esté descargado."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        modelos = [m["name"].split(":")[0] for m in data.get("models", [])]
        model_base = model.split(":")[0]
        if model_base not in modelos:
            return False, f"Modelo '{model}' no encontrado. Modelos disponibles: {', '.join(modelos)}"
        return True, f"Ollama OK — modelo {model} disponible"
    except urllib.error.URLError:
        return False, "Ollama no está corriendo. Iniciar con: ollama serve"
    except Exception as e:
        return False, str(e)
