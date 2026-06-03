"""
Paso 3 — Música.

Consolida archivos de audio en 03_musica/por_artista/<artista>/<album>/.
Lee tags ID3/Vorbis/MP4 con mutagen (via commons.metadata.audio).
Transliteración cirílica ISO 9 para nombres de artista y álbum.
Compilaciones → 03_musica/compilaciones/<album>/
Sin artista   → 03_musica/_sin_artista/
"""
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .utils import sanitizar_nombre, resolver_colision, resolver_destino

try:
    from commons.metadata.audio import leer_tags, TagsAudio
    _MUTAGEN_DISPONIBLE = True
except ImportError:
    _MUTAGEN_DISPONIBLE = False
    TagsAudio = None  # type: ignore[assignment,misc]


EXTENSIONES_AUDIO = frozenset({
    ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav",
    ".wma", ".opus", ".aiff", ".ape", ".m4b", ".mp4",
})

_ARTISTAS_COMPILACION = frozenset({
    "various artists", "various", "va", "v.a.",
    "varios artistas", "varios", "compilation",
    "assorted artists", "multiple artists",
})

_CARPETA_POR_ARTISTA = "por_artista"
_CARPETA_COMPILACIONES = "compilaciones"
_CARPETA_SIN_ARTISTA = "_sin_artista"


@dataclass
class ArchivoMusica:
    ruta: Path
    artista: str
    album: str
    titulo: str
    anio: str
    tamanio: int
    tiene_tags: bool
    es_compilacion: bool


@dataclass
class ResultadoPaso3:
    archivos: list[ArchivoMusica] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.archivos)

    @property
    def con_tags(self) -> int:
        return sum(1 for a in self.archivos if a.tiene_tags)

    @property
    def sin_tags(self) -> int:
        return self.total - self.con_tags

    @property
    def compilaciones(self) -> int:
        return sum(1 for a in self.archivos if a.es_compilacion)

    @property
    def total_bytes(self) -> int:
        return sum(a.tamanio for a in self.archivos)

    def por_artista(self) -> dict[str, int]:
        conteo: dict[str, int] = {}
        for a in self.archivos:
            key = a.artista or "_sin_artista"
            conteo[key] = conteo.get(key, 0) + 1
        return dict(sorted(conteo.items(), key=lambda x: -x[1]))


@dataclass
class MovimientoMusica:
    origen: Path
    destino: Path
    artista: str
    album: str
    tipo: str   # "normal" | "compilacion" | "sin_artista"
    tamanio: int


@dataclass
class PlanPaso3:
    movimientos: list[MovimientoMusica] = field(default_factory=list)
    omitidos_identicos: list[str] = field(default_factory=list)
    total_bytes: int = 0

    def __len__(self) -> int:
        return len(self.movimientos)


@dataclass
class ResultadoEjecucion:
    movidos: list[dict] = field(default_factory=list)
    omitidos: list[dict] = field(default_factory=list)
    omitidos_identicos: list[str] = field(default_factory=list)
    errores: list[dict] = field(default_factory=list)
    log_path: str = ""


def _es_compilacion(artista: str) -> bool:
    return artista.lower().strip() in _ARTISTAS_COMPILACION


def _nombre_album_carpeta(album: str, anio: str) -> str:
    """Genera el nombre de carpeta para un álbum: 'Album (2003)' o solo 'Album'."""
    album_s = sanitizar_nombre(album) if album else ""
    anio_s = anio[:4] if anio and anio[:4].isdigit() else ""
    if album_s and anio_s:
        return f"{album_s} ({anio_s})"
    return album_s or "_sin_album"


def detectar_musica(
    directorio: str | Path,
    extensiones: frozenset[str] | None = None,
) -> ResultadoPaso3:
    """
    Escanea directorio buscando archivos de audio.
    Lee sus tags con mutagen. Solo lectura.
    """
    directorio = Path(directorio)
    exts = extensiones or EXTENSIONES_AUDIO
    resultado = ResultadoPaso3()

    for raiz, dirs, archivos in os.walk(str(directorio)):
        # No descender en los destinos ya organizados
        dirs[:] = [d for d in dirs if d not in (
            _CARPETA_POR_ARTISTA, _CARPETA_COMPILACIONES, _CARPETA_SIN_ARTISTA
        )]
        for nombre in archivos:
            ruta = Path(raiz) / nombre
            if ruta.suffix.lower() not in exts:
                continue

            try:
                tamanio = ruta.stat().st_size
            except OSError:
                tamanio = 0

            if _MUTAGEN_DISPONIBLE:
                tags = leer_tags(ruta)
                artista = tags.artista.strip()
                album = tags.album.strip()
                titulo = tags.titulo.strip()
                anio = tags.anio.strip()
                tiene_tags = tags.disponible and bool(artista or album or titulo)
            else:
                artista = album = titulo = anio = ""
                tiene_tags = False

            resultado.archivos.append(ArchivoMusica(
                ruta=ruta,
                artista=artista,
                album=album,
                titulo=titulo,
                anio=anio,
                tamanio=tamanio,
                tiene_tags=tiene_tags,
                es_compilacion=_es_compilacion(artista) if artista else False,
            ))

    return resultado


def construir_plan(resultado: ResultadoPaso3, destino: str | Path) -> PlanPaso3:
    """Construye el plan de movimiento con la estructura destino/por_artista/etc."""
    destino = Path(destino)
    plan = PlanPaso3()

    for archivo in resultado.archivos:
        if archivo.es_compilacion:
            carpeta_album = _nombre_album_carpeta(archivo.album, archivo.anio)
            carpeta_dest = destino / _CARPETA_COMPILACIONES / carpeta_album
        elif not archivo.artista:
            carpeta_dest = destino / _CARPETA_SIN_ARTISTA
        else:
            artista_s = sanitizar_nombre(archivo.artista)
            carpeta_album = _nombre_album_carpeta(archivo.album, archivo.anio)
            carpeta_dest = destino / _CARPETA_POR_ARTISTA / artista_s / carpeta_album

        ruta_dest = resolver_destino(archivo.ruta, carpeta_dest / archivo.ruta.name)
        if ruta_dest is None:
            plan.omitidos_identicos.append(str(archivo.ruta))
            continue

        tipo = (
            "compilacion" if archivo.es_compilacion
            else "sin_artista" if not archivo.artista
            else "normal"
        )
        plan.movimientos.append(MovimientoMusica(
            origen=archivo.ruta,
            destino=ruta_dest,
            artista=archivo.artista,
            album=archivo.album,
            tipo=tipo,
            tamanio=archivo.tamanio,
        ))
        plan.total_bytes += archivo.tamanio

    return plan


def ejecutar_plan(
    plan: PlanPaso3,
    log_path: str | Path,
    dry_run: bool = True,
) -> ResultadoEjecucion:
    """Ejecuta el plan de Paso 3. dry_run=True solo reporta."""
    log_path = Path(log_path)
    resultado = ResultadoEjecucion(log_path=str(log_path))

    if dry_run:
        resultado.omitidos_identicos = list(plan.omitidos_identicos)
        for mov in plan.movimientos:
            resultado.movidos.append({
                "origen": str(mov.origen),
                "destino": str(mov.destino),
                "artista": mov.artista,
                "tipo": mov.tipo,
            })
        return resultado

    # Log de reversión antes de mover
    reversion = {
        "timestamp": datetime.now().isoformat(),
        "paso": 3,
        "movimientos": [
            {"origen": str(m.destino), "destino": str(m.origen)}
            for m in plan.movimientos
        ],
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps(reversion, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    for mov in plan.movimientos:
        if not mov.origen.exists():
            resultado.omitidos.append({"origen": str(mov.origen), "motivo": "no_existe"})
            continue
        try:
            mov.destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(mov.origen), str(mov.destino))
            resultado.movidos.append({
                "origen": str(mov.origen),
                "destino": str(mov.destino),
                "artista": mov.artista,
                "tipo": mov.tipo,
            })
        except (OSError, shutil.Error) as e:
            resultado.errores.append({
                "origen": str(mov.origen),
                "error": str(e),
            })

    return resultado
