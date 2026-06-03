"""
Clasificador de videos — 100% local, sin tokens.

Distingue entre videos personales (celular/cámara) y contenido multimedia
(películas, series, musicales, documentales).

  personal   → 01_fotos/YYYY/MM_nombre_mes/   (junto a las fotos personales)
  pelicula   → 02_videos/peliculas/
  serie      → 02_videos/series/
  musical    → 02_videos/musicales/
  documental → 02_videos/documentales/
  otro       → 02_videos/otros/

Prioridad de detección:
  1. Ruta (carpetas padre — señal más fuerte)
  2. Nombre del archivo (patrones de cámara, SxxExx, tags de calidad)
  3. Defecto → otro
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# ─── Constantes ───────────────────────────────────────────────────────────────

# Misma convención que paso4
MESES_ES: dict[int, str] = {
    1: "01_enero",   2: "02_febrero",  3: "03_marzo",
    4: "04_abril",   5: "05_mayo",     6: "06_junio",
    7: "07_julio",   8: "08_agosto",   9: "09_septiembre",
    10: "10_octubre", 11: "11_noviembre", 12: "12_diciembre",
}

_CARPETA_FOTOS     = "01_fotos"
_CARPETA_SIN_FECHA = "_sin_fecha"

# ─── Patrones de detección ────────────────────────────────────────────────────

# Personal / celular — nombre
_RE_PERSONAL_NOMBRE = re.compile(
    r"^(?:VID|MOV|GOPR|GX|DSCV|MVI|WA|GMT)[_\s-]?\d"  # VID_20240101, GMT20250129
    r"|^\d{8}[_\-]\d{6}"                                # 20240101_123456
    r"|^WA\d+",                                          # WhatsApp
    re.IGNORECASE,
)

# Series — extracción de nombre y temporada
_RE_SERIE_NOMBRE = re.compile(
    r"^(.{2,}?)[\s._-]*[Ss](\d{1,2})[Ee]\d{1,2}",
    re.IGNORECASE,
)
_RE_SEASON_EN_PATH = re.compile(
    r"^(.+?)\s+(?:[Ss]eason|[Tt]emporada)\s+(\d+)",
    re.IGNORECASE,
)

# Fecha embebida en nombre de archivo — dos formatos:
# 1. YYYYMMDD sin separadores (VID_20240101, GMT20250129)
# 2. YYYY-MM-DD con guiones (Dropbox "2026-04-13 22.14.15.jpg")
_RE_FECHA_NOMBRE = re.compile(r"(\d{4})(0[1-9]|1[0-2])\d{2}")
_RE_FECHA_ISO    = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])-\d{2}")

# Personal — carpetas
_PERSONAL_RUTA = (
    "whatsapp", "camera", "dcim", "celular", "camara", "phone",
    "snapchat", "telegram", "screen_record",
)

# Series — patrón SxxExx y variantes
_RE_SERIE = re.compile(
    r"[Ss]\d{1,2}[Ee]\d{1,2}"
    r"|[Tt]emporada[\s._-]*\d+"
    r"|[Ss]eason[\s._-]*\d+",
    re.IGNORECASE,
)

_SERIE_RUTA = ("series", "temporadas", "seasons", "season", "tv shows", "tv_shows")

# Películas — tags de calidad / distribución
_PELICULA_TAGS = (
    "bluray", "blu-ray", "webrip", "web-dl", "bdrip", "hdrip",
    "dvdrip", "1080p", "720p", "4k", "2160p", "hdtv", "brrip",
    "remux", "hevc", "x264", "x265", "h264", "h265",
)
_PELICULA_RUTA = ("peliculas", "movies", "films", "cine")

# Musicales
_MUSICAL_RUTA    = ("musicales", "video_musical", "music_video", "mv", "clips", "videoclips")
_MUSICAL_NOMBRE  = ("official video", "official mv", "music video", "lyric video", "audio oficial", "_mv_", "_ov_")

# Documentales
_DOCUMENTAL_RUTA   = ("documentales", "documentaries", "documentary")
_DOCUMENTAL_NOMBRE = ("documental", "documentary", "nat.geo", "national.geographic", "bbc.earth", "discovery")

# Cursos en video — señal de ruta (más fuerte) y de nombre (numeración de lección)
_CURSO_RUTA = (
    "cursos", "curso", "courses", "course",
    "tutorial", "tutoriales", "tutorials",
    "udemy", "coursera", "platzi", "edureka", "pluralsight",
    "linkedin learning", "linkedin_learning", "oneHack",
    "skills", "learning english", "learning_english",
    "aws training", "bbc learning",
    "100 days", "full stack", "cloud practitioner",
    "solutions architect", "serverless", "algorithmic trading",
    "ccna", "preparacion java", "bootcamp",
)
# Nombre numerado de lección: "001 Introduction.mp4", "32. API Gateway.mp4", "0308 Making An AMI.mp4"
_RE_LECCION_NUMERADA = re.compile(r"^\d{1,4}[\s._-]")

# Fitness en video — rutinas de ejercicio, yoga, crossfit
_FITNESS_RUTA = (
    "yoga", "tapout", "fitness", "crossfit", "workout",
    "fisicoculturismo", "rutinas", "zumba", "pilates",
    "ddp yoga", "insanity", "p90x",
)
_FITNESS_NOMBRE = (
    "yoga", "workout", "crossfit", "zumba", "pilates",
    "tapout", "insanity", "p90x",
)

# Idioma en video — audio/video de aprendizaje de idiomas
_IDIOMA_RUTA_VIDEO = (
    "bbc learning", "bbc_learning",
    "learning english", "learning_english",
    "idiomas", "language learning", "language_learning",
    "graded readers", "graded_readers",
    "english course", "english series",
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _norm(texto: str) -> str:
    return texto.lower()


def _limpiar_nombre_serie(raw: str) -> str:
    """'Breaking.Bad', 'Breaking_Bad' o 'Breaking-Bad' → 'Breaking Bad' con Title Case."""
    nombre = re.sub(r"[._-]", " ", raw)
    return re.sub(r"\s+", " ", nombre).strip().title()


def _extraer_nombre_serie(ruta: Path) -> tuple[str, int]:
    """
    Extrae (nombre_serie, num_temporada) de la ruta.
    1. Busca SxxExx en el stem del archivo: 'Breaking.Bad.S03E07' → ('Breaking Bad', 3)
    2. Si no, busca 'Season N' / 'Temporada N' en las carpetas padre.
    Retorna ("", 0) si no puede determinar.
    """
    m = _RE_SERIE_NOMBRE.match(ruta.stem)
    if m:
        return _limpiar_nombre_serie(m.group(1)), int(m.group(2))

    for part in reversed(ruta.parent.parts):
        m = _RE_SEASON_EN_PATH.match(part)
        if m:
            return _limpiar_nombre_serie(m.group(1)), int(m.group(2))

    return "", 0


def _ruta_str(ruta: Path) -> str:
    # Solo directorios padre — el filename no debe disparar keywords de ruta
    return _norm("/".join(ruta.parent.parts))


def _contiene(texto: str, *palabras: str) -> bool:
    t = _norm(texto)
    return any(p in t for p in palabras)


def _extraer_fecha(ruta: Path) -> tuple[str, int]:
    """
    Intenta extraer (año_str, mes_int) del nombre del archivo.
    Soporta dos formatos: YYYYMMDD (sin sep) y YYYY-MM-DD (Dropbox camera).
    Fallback: fecha de modificación.
    """
    # Formato ISO con guiones: "2026-04-13 22.14.15.jpg" (Dropbox camera uploads)
    m = _RE_FECHA_ISO.match(ruta.stem)
    if m:
        año = m.group(1)
        mes = int(m.group(2))
        if 2000 <= int(año) <= 2035:
            return año, mes

    # Formato compacto: YYYYMMDD (VID_20240101, GMT20250129)
    m = _RE_FECHA_NOMBRE.search(ruta.stem)
    if m:
        año = m.group(1)
        mes = int(m.group(2))
        if 2000 <= int(año) <= 2035:
            return año, mes

    try:
        mtime = ruta.stat().st_mtime
        dt = datetime.fromtimestamp(mtime)
        return str(dt.year), dt.month
    except OSError:
        now = datetime.now()
        return str(now.year), now.month


# ─── Dataclass ────────────────────────────────────────────────────────────────

@dataclass
class ClasificacionVideo:
    tipo: str         # personal | pelicula | serie | musical | documental | otro | curso | fitness | idioma
    confianza: str    # ruta | nombre | defecto
    año: str = ""     # solo para videos personales
    mes: int = 0      # solo para videos personales (1-12)
    serie_nombre: str = ""  # nombre de la serie (solo tipo="serie")
    temporada: int = 0      # número de temporada (solo tipo="serie")

    @property
    def carpeta_mes(self) -> str:
        return MESES_ES.get(self.mes, f"{self.mes:02d}") if self.mes else _CARPETA_SIN_FECHA


# ─── Clasificador principal ───────────────────────────────────────────────────

def clasificar_video(ruta: Path) -> ClasificacionVideo:
    """
    Clasifica un video en personal / pelicula / serie / musical / documental / otro.
    Sin llamadas a APIs, sin tokens.
    """
    ruta_t = _ruta_str(ruta)
    nombre = ruta.stem

    # ── 0. Nombre personal — señal muy fuerte, tiene prioridad sobre la ruta ──
    if _RE_PERSONAL_NOMBRE.match(nombre):
        año, mes = _extraer_fecha(ruta)
        return ClasificacionVideo("personal", "nombre", año=año, mes=mes)

    # ── 1. Por ruta ──────────────────────────────────────────────────────────
    if _contiene(ruta_t, *_PERSONAL_RUTA):
        año, mes = _extraer_fecha(ruta)
        return ClasificacionVideo("personal", "ruta", año=año, mes=mes)

    # Idioma antes que serie — "bbc_learning_english_series" contiene "series" como substring
    if _contiene(ruta_t, *_IDIOMA_RUTA_VIDEO):
        return ClasificacionVideo("idioma", "ruta")

    if _contiene(ruta_t, *_SERIE_RUTA):
        nombre_s, temp = _extraer_nombre_serie(ruta)
        return ClasificacionVideo("serie", "ruta", serie_nombre=nombre_s, temporada=temp)

    if _contiene(ruta_t, *_PELICULA_RUTA):
        return ClasificacionVideo("pelicula", "ruta")

    if _contiene(ruta_t, *_MUSICAL_RUTA):
        return ClasificacionVideo("musical", "ruta")

    if _contiene(ruta_t, *_DOCUMENTAL_RUTA):
        return ClasificacionVideo("documental", "ruta")

    if _contiene(ruta_t, *_CURSO_RUTA):
        return ClasificacionVideo("curso", "ruta")

    if _contiene(ruta_t, *_FITNESS_RUTA):
        return ClasificacionVideo("fitness", "ruta")

    # ── 2. Por nombre de archivo ──────────────────────────────────────────────
    if _RE_PERSONAL_NOMBRE.match(nombre):
        año, mes = _extraer_fecha(ruta)
        return ClasificacionVideo("personal", "nombre", año=año, mes=mes)

    if _RE_SERIE.search(nombre):
        nombre_s, temp = _extraer_nombre_serie(ruta)
        return ClasificacionVideo("serie", "nombre", serie_nombre=nombre_s, temporada=temp)

    nombre_low = _norm(nombre)
    if _contiene(nombre_low, *_PELICULA_TAGS):
        return ClasificacionVideo("pelicula", "nombre")

    if _contiene(nombre_low, *_MUSICAL_NOMBRE):
        return ClasificacionVideo("musical", "nombre")

    if _contiene(nombre_low, *_DOCUMENTAL_NOMBRE):
        return ClasificacionVideo("documental", "nombre")

    if _contiene(nombre_low, *_FITNESS_NOMBRE):
        return ClasificacionVideo("fitness", "nombre")

    # Lección numerada: "001 Introduction.mp4", "32. API Gateway.mp4"
    if _RE_LECCION_NUMERADA.match(nombre):
        return ClasificacionVideo("curso", "nombre")

    # ── 3. Defecto ────────────────────────────────────────────────────────────
    return ClasificacionVideo("otro", "defecto")


# ─── Destino ──────────────────────────────────────────────────────────────────

def destino_video(clase: ClasificacionVideo, base: Path) -> Path:
    """
    Devuelve el directorio destino (sin nombre de archivo).

    Videos personales → base/01_fotos/YYYY/MM_nombre_mes/
    Resto             → base/02_videos/{tipo}/
    """
    if clase.tipo == "personal":
        if clase.año and clase.mes:
            return base / _CARPETA_FOTOS / clase.año / clase.carpeta_mes
        return base / _CARPETA_FOTOS / _CARPETA_SIN_FECHA

    if clase.tipo == "serie":
        base_series = base / "02_videos" / "series"
        if clase.serie_nombre:
            if clase.temporada:
                return base_series / clase.serie_nombre / f"Temporada {clase.temporada:02d}"
            return base_series / clase.serie_nombre
        return base_series

    if clase.tipo == "idioma":
        return base / "04_libros" / "idiomas"

    subcarpeta = {
        "pelicula":   "peliculas",
        "musical":    "musicales",
        "documental": "documentales",
        "curso":      "cursos",
        "fitness":    "fitness",
        "otro":       "otros",
    }.get(clase.tipo, "otros")

    return base / "02_videos" / subcarpeta
