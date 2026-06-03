"""
Paso 7 — Homologación de nombres de archivo + renombrado EXIF.

Funciones principales:
  1. homologar_nombre(nombre) — limpia un nombre:
       - Transliteración cirílica, elimina emojis, basura decorativa
       - Normaliza fechas DD-MM-YYYY → YYYY-MM-DD
       - Colapsa separadores múltiples
  2. generar_reporte(directorio) → propuestas de renombrado (CSV)
  3. ejecutar_renombrado(resultado, log) → aplica cambios con log de reversión
  4. renombrar_por_exif(directorio) → renombra fotos sin prefijo de fecha
       usando la fecha de la etiqueta EXIF DateTimeOriginal.
       Requiere: Pillow (pip install Pillow)

Flujo seguro:
  1. generar_reporte() → revisar CSV
  2. ejecutar_renombrado(dry_run=True) → preview
  3. ejecutar_renombrado(dry_run=False) → aplica
"""
import csv
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from .utils import transliterar

# Emojis y símbolos Unicode
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FFFF"   # Misc symbols, emoticons, transport, etc.
    "\U00002600-\U000027BF"   # Misc symbols (☀☁☂…)
    "\U0001F1E0-\U0001F1FF"   # Flags (🇲🇽)
    "\U00002702-\U000027B0"   # Dingbats
    "︀-️"            # Variation selectors (modificadores de emoji)
    "‍"                   # Zero-width joiner
    "]+",
    flags=re.UNICODE,
)

# Cadenas decorativas a eliminar (case-insensitive)
_BASURA_RE = re.compile(
    r"[!]{2,}"           # !!! o más
    r"|[=:;][)\(]"       # =) :) ;)
    r"|\(\?\)"           # (?)
    r"|\(!+\)"           # (!) o (!!)
    r"|[-_]\s*copi[ao]"  # -copia, _Copia, - copia
    r"|[-_]\s*copy"      # -Copy, - copy
    r"|\bCopia\b"
    r"|\bCopy\b",
    re.IGNORECASE,
)

# Normalizar fechas DD-MM-YYYY o DD/MM/YYYY → YYYY-MM-DD
_FECHA_DMY = re.compile(r"(?<!\d)(\d{2})[-/](\d{2})[-/](\d{4})(?!\d)")

# Separadores múltiples
_MULTI_GUION = re.compile(r"-{2,}")
_MULTI_BAJO = re.compile(r"_{2,}")
_MULTI_ESPACIO = re.compile(r" {2,}")

# Caracteres inválidos en nombres de archivo
_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Ya tiene prefijo de fecha YYYY-MM-DD
_DATE_PREFIX_RE = re.compile(r"^\d{4}[-_]\d{2}[-_]\d{2}")

# Extensiones de imagen/foto
_EXT_FOTO = frozenset({
    ".jpg", ".jpeg", ".png", ".heic", ".heif",
    ".tiff", ".tif", ".raw", ".cr2", ".nef", ".dng", ".arw",
})


def _eliminar_emojis(texto: str) -> str:
    """Elimina emojis y símbolos Unicode de un nombre."""
    return _EMOJI_RE.sub("", texto)


def _detectar_causa(original: str, nuevo: str) -> Literal[
    "cirilico", "emoji", "basura", "fecha", "separadores", "invalidos", "combinado"
]:
    """Clasifica el tipo de cambio para estadísticas."""
    causas = set()
    if transliterar(original) != original:
        causas.add("cirilico")
    if _EMOJI_RE.search(original):
        causas.add("emoji")
    if _BASURA_RE.search(original):
        causas.add("basura")
    if _FECHA_DMY.search(original):
        causas.add("fecha")
    if _INVALIDOS.search(original):
        causas.add("invalidos")
    if "__" in original or "--" in original or "  " in original:
        causas.add("separadores")
    if len(causas) > 1:
        return "combinado"
    return next(iter(causas), "combinado")


def homologar_nombre(nombre: str) -> str:
    """
    Limpia un nombre de archivo (sin extensión):
    - Elimina emojis Unicode
    - Transliteración cirílica
    - Elimina decoraciones
    - Normaliza fechas DD-MM-YYYY → YYYY-MM-DD
    - Colapsa separadores múltiples
    - Recorta espacios/guiones/subrayados extremos
    """
    resultado = _eliminar_emojis(nombre)
    resultado = transliterar(resultado)
    resultado = _BASURA_RE.sub("", resultado)
    resultado = _FECHA_DMY.sub(r"\3-\2-\1", resultado)
    resultado = _INVALIDOS.sub("_", resultado)
    resultado = _MULTI_GUION.sub("-", resultado)
    resultado = _MULTI_BAJO.sub("_", resultado)
    resultado = _MULTI_ESPACIO.sub(" ", resultado)
    resultado = resultado.strip(" -_.")
    return resultado or "_archivo"


def _necesita_renombrar(nombre: str) -> bool:
    """True si el nombre cambiaría tras homologar."""
    return homologar_nombre(nombre) != nombre


@dataclass
class PropuestaRenombrado:
    ruta: Path
    nombre_original: str
    nombre_nuevo: str
    extension: str
    causa: str = "combinado"


@dataclass
class ResultadoPaso7:
    propuestas: list[PropuestaRenombrado] = field(default_factory=list)

    @property
    def total_cambios(self) -> int:
        return len(self.propuestas)

    @property
    def total_archivos_revisados(self) -> int:
        return self._total

    @property
    def stats_por_causa(self) -> dict[str, int]:
        acc: dict[str, int] = {}
        for p in self.propuestas:
            acc[p.causa] = acc.get(p.causa, 0) + 1
        return acc

    def __post_init__(self):
        self._total = 0


@dataclass
class ResultadoEjecucion:
    renombrados: list[dict] = field(default_factory=list)
    omitidos: list[dict] = field(default_factory=list)
    errores: list[dict] = field(default_factory=list)
    log_path: str = ""


# ─── Generación de reporte ───────────────────────────────────────────────────

def generar_reporte(
    directorio: str | Path,
    ruta_csv: str | Path | None = None,
) -> ResultadoPaso7:
    """
    Analiza todos los archivos bajo directorio y propone renombrados.
    Si se indica ruta_csv, escribe el reporte en ese archivo.
    Solo lectura — no renombra nada.
    """
    directorio = Path(directorio)
    resultado = ResultadoPaso7()
    total = 0

    for raiz, _, archivos in os.walk(str(directorio)):
        for nombre in archivos:
            total += 1
            ruta = Path(raiz) / nombre
            stem = ruta.stem
            ext = ruta.suffix
            nuevo_stem = homologar_nombre(stem)
            if nuevo_stem != stem:
                resultado.propuestas.append(PropuestaRenombrado(
                    ruta=ruta,
                    nombre_original=nombre,
                    nombre_nuevo=nuevo_stem + ext,
                    extension=ext,
                    causa=_detectar_causa(stem, nuevo_stem),
                ))

    resultado._total = total

    if ruta_csv and resultado.propuestas:
        _escribir_csv(resultado.propuestas, Path(ruta_csv))

    return resultado


def _escribir_csv(propuestas: list[PropuestaRenombrado], ruta_csv: Path) -> None:
    """Escribe el reporte de propuestas en CSV."""
    ruta_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["carpeta", "nombre_original", "nombre_nuevo"])
        for p in propuestas:
            writer.writerow([str(p.ruta.parent), p.nombre_original, p.nombre_nuevo])


# ─── Ejecución ────────────────────────────────────────────────────────────────

def ejecutar_renombrado(
    resultado: ResultadoPaso7,
    log_path: str | Path,
    dry_run: bool = True,
) -> ResultadoEjecucion:
    """
    Aplica los renombrados propuestos.
    - dry_run=True: solo reporta, no renombra.
    - dry_run=False: escribe log de reversión ANTES de renombrar el primer archivo.
    """
    log_path = Path(log_path)
    ejec = ResultadoEjecucion(log_path=str(log_path))

    if dry_run:
        for p in resultado.propuestas:
            ejec.renombrados.append({
                "carpeta": str(p.ruta.parent),
                "original": p.nombre_original,
                "nuevo": p.nombre_nuevo,
            })
        return ejec

    # Log de reversión (invertido: nuevo → original)
    reversion = {
        "timestamp": datetime.now().isoformat(),
        "paso": 7,
        "renombrados": [
            {
                "carpeta": str(p.ruta.parent),
                "origen": p.nombre_nuevo,    # nombre después del cambio
                "destino": p.nombre_original, # nombre antes (para deshacer)
            }
            for p in resultado.propuestas
        ],
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps(reversion, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    for p in resultado.propuestas:
        origen = p.ruta
        destino = p.ruta.parent / p.nombre_nuevo

        if not origen.exists():
            ejec.omitidos.append({"original": p.nombre_original, "motivo": "no_existe"})
            continue

        if destino.exists() and destino != origen:
            # Colisión: añadir sufijo al nuevo nombre
            stem, ext = Path(p.nombre_nuevo).stem, Path(p.nombre_nuevo).suffix
            i = 2
            while destino.exists():
                destino = p.ruta.parent / f"{stem}_{i}{ext}"
                i += 1

        try:
            origen.rename(destino)
            ejec.renombrados.append({
                "carpeta": str(p.ruta.parent),
                "original": p.nombre_original,
                "nuevo": destino.name,
            })
        except OSError as e:
            ejec.errores.append({
                "original": p.nombre_original,
                "nuevo": p.nombre_nuevo,
                "error": str(e),
            })

    return ejec


# ─── Renombrado EXIF ──────────────────────────────────────────────────────────

@dataclass
class PropuestaExif:
    ruta: Path
    nombre_original: str
    nombre_nuevo: str
    fecha_exif: str


@dataclass
class ResultadoExif:
    propuestas: list[PropuestaExif] = field(default_factory=list)
    sin_exif: int = 0
    ya_con_fecha: int = 0
    no_es_foto: int = 0
    _total: int = 0

    @property
    def total_cambios(self) -> int:
        return len(self.propuestas)


def _extraer_fecha_exif(ruta: Path) -> str | None:
    """
    Extrae DateTimeOriginal de la EXIF.
    Retorna 'YYYY-MM-DD_HHMMSS' o None.
    Requiere Pillow — si no está instalado retorna None silenciosamente.
    """
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
    except ImportError:
        return None

    try:
        with Image.open(ruta) as img:
            exif_data = img._getexif()
            if not exif_data:
                return None
            for tag_id, value in exif_data.items():
                tag = TAGS.get(tag_id, "")
                if tag in ("DateTimeOriginal", "DateTime", "DateTimeDigitized"):
                    if isinstance(value, str) and len(value) >= 19:
                        # "YYYY:MM:DD HH:MM:SS" → "YYYY-MM-DD_HHMMSS"
                        return value[:19].replace(":", "-", 2).replace(" ", "_").replace(":", "")
    except Exception:
        pass
    return None


def generar_reporte_exif(
    directorio: str | Path,
    ruta_csv: str | Path | None = None,
) -> ResultadoExif:
    """
    Analiza fotos bajo directorio y propone renombrar con prefijo EXIF.
    Solo afecta fotos sin prefijo de fecha ya existente.
    """
    directorio = Path(directorio)
    resultado = ResultadoExif()

    for raiz, _, archivos in os.walk(str(directorio)):
        for nombre in archivos:
            ruta = Path(raiz) / nombre
            ext  = ruta.suffix.lower()

            if ext not in _EXT_FOTO:
                resultado.no_es_foto += 1
                continue

            resultado._total += 1
            stem = ruta.stem

            if _DATE_PREFIX_RE.match(stem):
                resultado.ya_con_fecha += 1
                continue

            fecha = _extraer_fecha_exif(ruta)
            if not fecha:
                resultado.sin_exif += 1
                continue

            nuevo_stem = f"{fecha}_{homologar_nombre(stem)}".strip("_")
            resultado.propuestas.append(PropuestaExif(
                ruta=ruta,
                nombre_original=nombre,
                nombre_nuevo=nuevo_stem + ext,
                fecha_exif=fecha,
            ))

    if ruta_csv and resultado.propuestas:
        ruta_csv = Path(ruta_csv)
        ruta_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["carpeta", "nombre_original", "nombre_nuevo", "fecha_exif"])
            for p in resultado.propuestas:
                writer.writerow([str(p.ruta.parent), p.nombre_original, p.nombre_nuevo, p.fecha_exif])

    return resultado


def ejecutar_renombrado_exif(
    resultado: ResultadoExif,
    log_path: str | Path,
    dry_run: bool = True,
) -> ResultadoEjecucion:
    """Aplica los renombrados EXIF propuestos. dry_run=True solo reporta."""
    log_path = Path(log_path)
    ejec = ResultadoEjecucion(log_path=str(log_path))

    if dry_run:
        for p in resultado.propuestas:
            ejec.renombrados.append({
                "carpeta": str(p.ruta.parent), "original": p.nombre_original,
                "nuevo": p.nombre_nuevo, "fecha_exif": p.fecha_exif,
            })
        return ejec

    reversion = {
        "timestamp": datetime.now().isoformat(), "paso": "7-exif",
        "renombrados": [
            {"carpeta": str(p.ruta.parent), "origen": p.nombre_nuevo, "destino": p.nombre_original}
            for p in resultado.propuestas
        ],
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(reversion, indent=2, ensure_ascii=False), encoding="utf-8")

    for p in resultado.propuestas:
        origen  = p.ruta
        destino = p.ruta.parent / p.nombre_nuevo
        if not origen.exists():
            ejec.omitidos.append({"original": p.nombre_original, "motivo": "no_existe"})
            continue
        if destino.exists() and destino != origen:
            stem, ext = Path(p.nombre_nuevo).stem, Path(p.nombre_nuevo).suffix
            i = 2
            while destino.exists():
                destino = p.ruta.parent / f"{stem}_{i}{ext}"
                i += 1
        try:
            origen.rename(destino)
            ejec.renombrados.append({
                "carpeta": str(p.ruta.parent), "original": p.nombre_original,
                "nuevo": destino.name, "fecha_exif": p.fecha_exif,
            })
        except OSError as e:
            ejec.errores.append({"original": p.nombre_original, "error": str(e)})

    return ejec
