"""
Paso 5 — Google Takeout.

Detecta paquetes Takeout (carpetas "Takeout/" que contienen "Google Fotos/")
y enruta su contenido:

  Google Fotos/   → 01_fotos/YYYY/MM_nombre_mes/  (usa JSON companion para fecha)
  Meet Recordings/→ 02_videos/
  Classroom/      → 05_cursos/
  YouTube/        → 02_videos/
  Otros           → _pendientes/checar/

Los JSON companion de Google Fotos (.jpg.json, .png.json) se omiten del
movimiento — su información de fecha ya fue consumida en la clasificación.
"""
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .paso4 import EXTENSIONES_IMAGEN, MESES_ES, _fecha_desde_json_companion
from .utils import resolver_colision, resolver_destino

# Extensiones que se saltan (JSON companions y metadatos Takeout)
_EXTENSIONES_SKIP = frozenset({".json"})

# Mapeo carpeta Takeout → subcarpeta destino
_RUTAS_TAKEOUT: dict[str, str] = {
    "google fotos":      "01_fotos",
    "fotos de google":   "01_fotos",
    "google photos":     "01_fotos",
    "meet recordings":   "02_videos",
    "grabaciones meet":  "02_videos",
    "youtube":           "02_videos",
    "classroom":         "05_cursos",
    "google classroom":  "05_cursos",
    "drive":             "_pendientes/checar",
    "gmail":             "_pendientes/checar",
    "contactos":         "_pendientes/checar",
    "contacts":          "_pendientes/checar",
}

_CARPETA_DEFAULT = "_pendientes/checar"

EXTENSIONES_VIDEO = frozenset({
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
    ".webm", ".m4v", ".mpg", ".mpeg", ".3gp",
})


@dataclass
class ArchivoTakeout:
    ruta: Path
    categoria_takeout: str  # "fotos" | "videos" | "cursos" | "pendiente"
    fecha: datetime | None
    fuente_fecha: str
    tamanio: int


@dataclass
class ResultadoPaso5:
    archivos: list[ArchivoTakeout] = field(default_factory=list)
    paquetes_detectados: list[Path] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.archivos)

    @property
    def total_bytes(self) -> int:
        return sum(a.tamanio for a in self.archivos)

    def por_categoria(self) -> dict[str, int]:
        conteo: dict[str, int] = {}
        for a in self.archivos:
            conteo[a.categoria_takeout] = conteo.get(a.categoria_takeout, 0) + 1
        return dict(sorted(conteo.items(), key=lambda x: -x[1]))


@dataclass
class PlanPaso5:
    movimientos: list[dict] = field(default_factory=list)
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


# ─── Detección ────────────────────────────────────────────────────────────────

def _es_paquete_takeout(directorio: Path) -> bool:
    """Un directorio es Takeout si contiene al menos una subcarpeta Takeout conocida."""
    if not directorio.is_dir():
        return False
    nombres = {d.name.lower() for d in directorio.iterdir() if d.is_dir()}
    return bool(nombres & set(_RUTAS_TAKEOUT.keys()))


def _categoria_desde_carpeta(nombre_carpeta: str) -> str:
    return _RUTAS_TAKEOUT.get(nombre_carpeta.lower(), _CARPETA_DEFAULT)


def _fecha_foto_takeout(ruta: Path) -> tuple[datetime | None, str]:
    """Fecha desde JSON companion primero, luego mtime."""
    json_fecha = _fecha_desde_json_companion(ruta)
    if json_fecha:
        return json_fecha, "json_companion"
    try:
        return datetime.fromtimestamp(ruta.stat().st_mtime), "mtime"
    except OSError:
        return None, "ninguna"


def detectar_takeout(directorio: str | Path) -> ResultadoPaso5:
    """Busca paquetes Takeout y clasifica su contenido. Solo lectura."""
    directorio = Path(directorio)
    resultado = ResultadoPaso5()

    # Buscar paquetes Takeout (carpetas que contienen subcarpetas Takeout conocidas)
    paquetes: list[Path] = []
    for raiz, dirs, _ in os.walk(str(directorio)):
        raiz_path = Path(raiz)
        if _es_paquete_takeout(raiz_path):
            paquetes.append(raiz_path)
            dirs.clear()  # no descender dentro de un paquete — lo procesamos aparte

    resultado.paquetes_detectados = paquetes

    for paquete in paquetes:
        for subcarpeta in paquete.iterdir():
            if not subcarpeta.is_dir():
                continue
            categoria = _categoria_desde_carpeta(subcarpeta.name)
            es_fotos = categoria == "01_fotos"

            for raiz, _, archivos in os.walk(str(subcarpeta)):
                for nombre in archivos:
                    ruta = Path(raiz) / nombre
                    if ruta.suffix.lower() in _EXTENSIONES_SKIP:
                        continue

                    try:
                        tamanio = ruta.stat().st_size
                    except OSError:
                        tamanio = 0

                    if es_fotos:
                        fecha, fuente = _fecha_foto_takeout(ruta)
                    else:
                        fecha, fuente = None, "ninguna"

                    resultado.archivos.append(ArchivoTakeout(
                        ruta=ruta,
                        categoria_takeout=categoria,
                        fecha=fecha,
                        fuente_fecha=fuente,
                        tamanio=tamanio,
                    ))

    return resultado


# ─── Plan ────────────────────────────────────────────────────────────────────

def construir_plan(resultado: ResultadoPaso5, destino: str | Path) -> PlanPaso5:
    """Construye el plan para mover archivos Takeout a sus destinos."""
    destino = Path(destino)
    plan = PlanPaso5()

    for archivo in resultado.archivos:
        if archivo.categoria_takeout == "01_fotos" and archivo.fecha:
            anio = str(archivo.fecha.year)
            mes = MESES_ES.get(archivo.fecha.month, f"{archivo.fecha.month:02d}")
            ruta_dest = destino / "01_fotos" / anio / mes / archivo.ruta.name
        else:
            ruta_dest = destino / archivo.categoria_takeout / archivo.ruta.name

        ruta_dest = resolver_destino(archivo.ruta, ruta_dest)
        if ruta_dest is None:
            plan.omitidos_identicos.append(str(archivo.ruta))
            continue
        plan.movimientos.append({
            "origen": str(archivo.ruta),
            "destino": str(ruta_dest),
            "categoria": archivo.categoria_takeout,
            "fuente_fecha": archivo.fuente_fecha,
            "tamanio": archivo.tamanio,
        })
        plan.total_bytes += archivo.tamanio

    return plan


# ─── Ejecución ────────────────────────────────────────────────────────────────

def ejecutar_plan(
    plan: PlanPaso5,
    log_path: str | Path,
    dry_run: bool = True,
) -> ResultadoEjecucion:
    """Ejecuta el plan del Paso 5. dry_run=True solo reporta."""
    log_path = Path(log_path)
    resultado = ResultadoEjecucion(log_path=str(log_path), omitidos_identicos=list(plan.omitidos_identicos))

    if dry_run:
        resultado.movidos = list(plan.movimientos)
        return resultado

    reversion = {
        "timestamp": datetime.now().isoformat(),
        "paso": 5,
        "movimientos": [
            {"origen": m["destino"], "destino": m["origen"]}
            for m in plan.movimientos
        ],
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps(reversion, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    for mov in plan.movimientos:
        origen = Path(mov["origen"])
        destino = Path(mov["destino"])
        if not origen.exists():
            resultado.omitidos.append({**mov, "motivo": "no_existe"})
            continue
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(origen), str(destino))
            resultado.movidos.append(mov)
        except (OSError, shutil.Error) as e:
            resultado.errores.append({**mov, "error": str(e)})

    return resultado
