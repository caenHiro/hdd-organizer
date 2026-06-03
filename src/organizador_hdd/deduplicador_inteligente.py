"""
Deduplicador inteligente — 100% local, sin tokens.

Identifica grupos de archivos idénticos (mismo SHA256) y decide cuál
conservar aplicando un sistema de puntuación por calidad.

Scoring (suma, mayor = mejor candidato a conservar):
  +5  ruta en carpeta organizada (01_fotos, 03_musica, 07_escuela, etc.)
  +3  tiene metadata enriquecida (EXIF fecha/cámara, ID3 artista/álbum, PDF autor)
  +2  nombre significativo (no IMG_001, DSC_1234, 20240101_123456)
  +1  archivo más grande del grupo (calidad/resolución probable)
  +1  mtime más antiguo (el original suele ser el más viejo)

Empate exacto → conservar el de mtime más antiguo (original más probable).

Los archivos a descartar se mueven a _pendientes/duplicados/{tipo}/{ruta_codificada}/.
La subcarpeta codifica la ruta original del archivo usando '__' como separador,
permitiendo reconstruir el origen si se necesita restaurar.
NUNCA se borran automáticamente.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .verificador import _codificar_ruta

# ─── Constantes de scoring ────────────────────────────────────────────────────

_CARPETAS_ORGANIZADAS = {
    "01_fotos", "01b_imagenes", "02_videos", "03_musica",
    "04_libros", "05_cursos", "06_trabajo", "07_escuela",
    "08_documentos", "09_codigo", "10_software", "11_recursos",
}

_RE_NOMBRE_CAMARA    = re.compile(r"^(?:IMG|DSC|DSCN|MVI|VID|WA|PANO|P\d{4})[_\s-]?\d", re.I)
_RE_NOMBRE_TIMESTAMP = re.compile(r"^\d{8}[_\-]\d{6}")

_EXT_AUDIO   = {".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wav", ".wma", ".opus"}
_EXT_IMAGEN  = {".jpg", ".jpeg", ".heic", ".heif", ".tiff", ".tif", ".png"}
_EXT_VIDEO   = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg"}
_EXT_DOCUMENTO = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt"}

_TIPO_POR_EXT: dict[str, str] = {
    **{e: "audio" for e in _EXT_AUDIO},
    **{e: "imagen" for e in _EXT_IMAGEN},
    **{e: "video" for e in _EXT_VIDEO},
    **{e: "documento" for e in _EXT_DOCUMENTO},
}


# ─── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class GrupoDuplicados:
    hash_sha256: str
    archivos: list[dict]    # cada dict: ruta, tamanio, fecha_modificacion, tipo (opcional)

    @property
    def total(self) -> int:
        return len(self.archivos)

    @property
    def espacio_recuperable(self) -> int:
        """Bytes que se liberarían conservando solo la mejor copia."""
        tamanios = sorted((a["tamanio"] for a in self.archivos), reverse=True)
        return sum(tamanios[1:])


@dataclass
class DecisionDuplicado:
    hash_sha256: str
    conservar: dict
    descartar: list[dict]
    razon: str
    espacio_recuperable: int


@dataclass
class MovimientoDuplicado:
    origen: Path
    destino: Path
    hash_sha256: str
    tipo: str   # imagen | audio | video | documento | otro


@dataclass
class ResultadoEjecucion:
    movidos: list[dict] = field(default_factory=list)
    omitidos: list[dict] = field(default_factory=list)
    errores: list[dict] = field(default_factory=list)
    log_path: str = ""


# ─── Scoring ─────────────────────────────────────────────────────────────────

def _puntaje_ruta(ruta: Path) -> int:
    partes = {p.lower() for p in ruta.parts}
    if partes & _CARPETAS_ORGANIZADAS:
        return 5
    if "_pendientes" in partes:
        return 0
    return 2


def _puntaje_nombre(ruta: Path) -> int:
    nombre = ruta.stem
    if _RE_NOMBRE_CAMARA.match(nombre) or _RE_NOMBRE_TIMESTAMP.match(nombre):
        return 0
    return 2


def _puntaje_metadata(ruta: Path) -> int:
    """Comprueba si el archivo tiene metadata enriquecida. Lectura rápida de cabecera."""
    if not ruta.exists():
        return 0
    ext = ruta.suffix.lower()
    try:
        if ext in _EXT_AUDIO:
            from mutagen import File as MutagenFile
            tags = MutagenFile(str(ruta), easy=True)
            if tags and (tags.get("title") or tags.get("artist")):
                return 3
        elif ext in _EXT_IMAGEN:
            from PIL import Image
            img = Image.open(ruta)
            exif = getattr(img, "_getexif", lambda: None)()
            if exif:
                from PIL.ExifTags import TAGS
                utiles = {"DateTimeOriginal", "Make", "Model"}
                if any(TAGS.get(k) in utiles for k in exif):
                    return 3
        elif ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(ruta), strict=False)
            meta = reader.metadata
            if meta and (meta.get("/Title") or meta.get("/Author")):
                return 3
    except Exception:
        pass
    return 0


def puntaje_archivo(ruta: Path) -> int:
    """Puntuación total de un archivo como candidato a conservar."""
    return _puntaje_ruta(ruta) + _puntaje_nombre(ruta) + _puntaje_metadata(ruta)


# ─── Agrupación y decisión ────────────────────────────────────────────────────

def agrupar_por_hash(archivos: list[dict]) -> list[GrupoDuplicados]:
    """Agrupa registros de archivo por hash_sha256. Solo incluye grupos con ≥2 archivos."""
    grupos: dict[str, list[dict]] = {}
    for a in archivos:
        h = a.get("hash_sha256", "")
        if h:
            grupos.setdefault(h, []).append(a)
    return [GrupoDuplicados(h, lst) for h, lst in grupos.items() if len(lst) >= 2]


def decidir(grupo: GrupoDuplicados) -> DecisionDuplicado:
    """
    Aplica scoring para decidir cuál copia conservar.
    Empate → conserva el de mtime más antiguo.
    """
    scored: list[tuple[int, int, str, dict]] = []
    tamanios = [a["tamanio"] for a in grupo.archivos]
    max_tam = max(tamanios) if tamanios else 0

    for archivo in grupo.archivos:
        ruta = Path(archivo["ruta"])
        score = puntaje_archivo(ruta)
        # +1 si es el más grande del grupo (puede empatar entre varios del mismo tamaño)
        if archivo["tamanio"] == max_tam:
            score += 1
        # fecha_modificacion como string ISO → orden ascendente = más antiguo primero
        fecha = archivo.get("fecha_modificacion", "")
        scored.append((score, archivo["tamanio"], fecha, archivo))

    # Ordenar: mayor score → mayor tamaño → mtime más antiguo
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))

    ganador = scored[0][3]
    perdedores = [s[3] for s in scored[1:]]

    score_g = scored[0][0]
    score_p = scored[1][0] if len(scored) > 1 else 0
    if score_g > score_p:
        razon = f"score {score_g} vs {score_p}"
    else:
        razon = f"score igual ({score_g}) — conservado por mtime más antiguo"

    return DecisionDuplicado(
        hash_sha256=grupo.hash_sha256,
        conservar=ganador,
        descartar=perdedores,
        razon=razon,
        espacio_recuperable=grupo.espacio_recuperable,
    )


def planificar(grupos: list[GrupoDuplicados]) -> list[DecisionDuplicado]:
    return [decidir(g) for g in grupos]


# ─── Plan de movimiento ───────────────────────────────────────────────────────

def _tipo_archivo(ruta: Path) -> str:
    return _TIPO_POR_EXT.get(ruta.suffix.lower(), "otro")


def construir_plan(
    decisiones: list[DecisionDuplicado],
    base_hdd: Path,
) -> list[MovimientoDuplicado]:
    """
    Mapea cada archivo a descartar a _pendientes/duplicados/{tipo}/{ruta_codificada}/.

    La subcarpeta codifica la ruta original del archivo (su directorio padre relativo
    a base_hdd) usando '__' como separador, igual que _pendientes/dañados/.
    Esto permite reconstruir el origen del duplicado si se necesita restaurar.
    """
    movimientos: list[MovimientoDuplicado] = []
    usados: set[Path] = set()

    for dec in decisiones:
        for archivo in dec.descartar:
            ruta_orig = Path(archivo["ruta"])
            tipo = _tipo_archivo(ruta_orig)
            carpeta_encoded = _codificar_ruta(ruta_orig.parent, base_hdd)
            dest_dir = base_hdd / "_pendientes" / "duplicados" / tipo / carpeta_encoded
            dest = dest_dir / ruta_orig.name

            # Resolver colisión de nombre
            if dest in usados or (dest.exists() and dest != ruta_orig):
                stem, suffix = ruta_orig.stem, ruta_orig.suffix
                n = 2
                while dest in usados or dest.exists():
                    dest = dest_dir / f"{stem}_{n}{suffix}"
                    n += 1

            usados.add(dest)
            movimientos.append(MovimientoDuplicado(
                origen=ruta_orig,
                destino=dest,
                hash_sha256=dec.hash_sha256,
                tipo=tipo,
            ))

    return movimientos


# ─── Ejecución ────────────────────────────────────────────────────────────────

def ejecutar_plan(
    movimientos: list[MovimientoDuplicado],
    log_path: Path,
    dry_run: bool = True,
) -> ResultadoEjecucion:
    """
    Mueve duplicados a _pendientes/duplicados/.
    dry_run=True solo reporta, no mueve.
    """
    resultado = ResultadoEjecucion(log_path=str(log_path))

    if dry_run:
        resultado.movidos = [
            {"origen": str(m.origen), "destino": str(m.destino),
             "tipo": m.tipo, "hash": m.hash_sha256}
            for m in movimientos
        ]
        return resultado

    reversion = {
        "timestamp": datetime.now().isoformat(),
        "operacion": "deduplicacion",
        "movimientos": [
            {"origen": str(m.destino), "destino": str(m.origen)}
            for m in movimientos
        ],
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(reversion, indent=2, ensure_ascii=False), encoding="utf-8")

    for mov in movimientos:
        if not mov.origen.exists():
            resultado.omitidos.append({"ruta": str(mov.origen), "motivo": "no_existe"})
            continue
        try:
            mov.destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(mov.origen), str(mov.destino))
            resultado.movidos.append({
                "origen": str(mov.origen), "destino": str(mov.destino),
                "tipo": mov.tipo, "hash": mov.hash_sha256,
            })
        except (OSError, shutil.Error) as e:
            resultado.errores.append({"origen": str(mov.origen), "error": str(e)})

    return resultado


# ─── Resumen legible ──────────────────────────────────────────────────────────

def resumen_texto(decisiones: list[DecisionDuplicado]) -> str:
    """Genera un resumen de texto para mostrar en CLI o Obsidian."""
    total_grupos = len(decisiones)
    total_descartar = sum(len(d.descartar) for d in decisiones)
    espacio = sum(d.espacio_recuperable for d in decisiones)

    def _fmt(n: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.1f} {unit}"
            n //= 1024
        return f"{n:.1f} TB"

    lineas = [
        f"Grupos duplicados: {total_grupos}",
        f"Archivos a descartar: {total_descartar}",
        f"Espacio recuperable: {_fmt(espacio)}",
        "",
    ]
    for d in decisiones[:20]:   # mostrar solo los primeros 20
        conservar_nombre = Path(d.conservar["ruta"]).name
        lineas.append(f"  ✅ conservar: {conservar_nombre}  ({d.razon})")
        for arc in d.descartar:
            lineas.append(f"  ❌ descartar: {Path(arc['ruta']).name}")
        lineas.append("")

    if total_grupos > 20:
        lineas.append(f"  … y {total_grupos - 20} grupos más")

    return "\n".join(lineas)
