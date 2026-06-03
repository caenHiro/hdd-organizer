"""
Detecta la subcarpeta de 01b_imagenes/ para una imagen descargada.

Clasificación por prioridad (sin modelos, solo nombre/ruta/tamaño):
  1. Screenshot  → _sin_categoria/  (ya venía clasificada en paso4 score)
  2. Wallpaper   → wallpapers/      (resolución de pantalla o carpeta/nombre)
  3. Superheroes → superheroes/     (keywords Marvel, DC, anime superhéroe)
  4. Anime/arte  → arte/            (keywords anime, manga, ilustración)
  5. Autos       → autos/           (keywords car, auto, vehiculo)
  6. Memes       → memes/           (keywords meme, humor, funny)
  7. Default     → _sin_categoria/
"""
from __future__ import annotations

import re
from pathlib import Path

# Subcarpetas canónicas de 01b_imagenes/
SUBCARPETAS_IMAGEN = {
    "wallpapers",
    "superheroes",
    "arte",
    "autos",
    "memes",
    "_sin_categoria",
}

_RESOLUCIONES_PANTALLA = {
    (1920, 1080), (2560, 1440), (3840, 2160),
    (1366, 768), (1280, 720), (1440, 900), (1600, 900),
    (2560, 1600), (1280, 800), (2880, 1800), (1024, 768), (2560, 1080),
}

_RE_WALLPAPER = re.compile(
    r"wallpaper|fondo|background|pantalla|desktop|lockscreen",
    re.IGNORECASE,
)
_RE_SUPERHEROES = re.compile(
    r"marvel|dc[_\-\s]?comic|batman|superman|spiderman|spider.?man|"
    r"ironman|iron.?man|avenger|xmen|x.?men|thor|wolverine|"
    r"dragonball|dragon.?ball|naruto|goku|bleach|onepiece|one.?piece",
    re.IGNORECASE,
)
_RE_ANIME = re.compile(
    r"anime|manga|ilustrac|illustration|digital.?art|artwork|fanart|"
    r"pokemon|pikachu|zelda|fantasy|elden.?ring",
    re.IGNORECASE,
)
_RE_AUTOS = re.compile(
    r"\bauto\b|\bcar\b|\bcoche\b|\bvehiculo\b|vehicle|supercar|"
    r"lamborghini|ferrari|porsche|bmw|mustang|dodge|mclaren",
    re.IGNORECASE,
)
_RE_MEMES = re.compile(
    r"meme|humor|funny|lol|dank|shitpost|trollface|pepe|crying.?laugh",
    re.IGNORECASE,
)


def detectar_subcategoria(
    ruta: Path,
    ancho: int = 0,
    alto: int = 0,
) -> str:
    """
    Retorna el nombre de subcarpeta de 01b_imagenes/ para esta imagen.

    Args:
        ruta:  ruta del archivo (se usan nombre + partes del path)
        ancho: ancho en píxeles (opcional, mejora detección de wallpapers)
        alto:  alto en píxeles (opcional)

    Returns:
        nombre de subcarpeta: "wallpapers" | "superheroes" | "arte" | "autos" | "memes" | "_sin_categoria"
    """
    nombre = ruta.stem.lower()
    path_str = " ".join(p.lower() for p in ruta.parts)

    # Wallpaper: resolución de pantalla o keyword en nombre/carpeta
    if (ancho, alto) in _RESOLUCIONES_PANTALLA or (alto, ancho) in _RESOLUCIONES_PANTALLA:
        return "wallpapers"
    if _RE_WALLPAPER.search(path_str):
        return "wallpapers"

    # Superhéroes / fandom específico (antes de anime genérico)
    if _RE_SUPERHEROES.search(path_str):
        return "superheroes"

    # Anime / arte digital
    if _RE_ANIME.search(path_str):
        return "arte"

    # Autos
    if _RE_AUTOS.search(path_str):
        return "autos"

    # Memes
    if _RE_MEMES.search(path_str):
        return "memes"

    return "_sin_categoria"
