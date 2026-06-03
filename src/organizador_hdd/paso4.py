"""
Paso 4 — Fotos vs Imágenes descargadas.

Clasifica imágenes usando un sistema de puntuación (score):
  score > 0  → foto real     → 01_fotos/YYYY/MM_nombre_mes/
  score <= 0 → imagen        → 01b_imagenes/_sin_categoria/
  sin fecha  → 01_fotos/_sin_fecha/

Fuentes de fecha (en orden de prioridad):
  1. EXIF DateTimeOriginal
  2. JSON companion Google Photos ({nombre}.json → photoTakenTime.timestamp)
  3. Fecha de modificación del archivo (último recurso)

Clasificación 100% local — sin API de IA.
"""
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .utils import resolver_colision, resolver_destino
from .verificador import verificar_archivo, ruta_danado
from .fotos.subcategorias import detectar_subcategoria

try:
    from commons.metadata.exif import extraer as _extraer_exif, ResultadoExif
    _PIL_DISPONIBLE = True
except ImportError:
    _PIL_DISPONIBLE = False
    ResultadoExif = None  # type: ignore[assignment,misc]

_RE_ID_INVENTARIO = re.compile(r"^(PKM|VJG|CON|MON|ELC|PLT)-\d{3,}")

def _leer_id_inventario_exif(ruta: Path) -> str | None:
    """Lee EXIF ImageDescription y retorna el ID si es un ítem de inventario."""
    try:
        import piexif
        exif_dict = piexif.load(str(ruta))
        raw = exif_dict.get("0th", {}).get(piexif.ImageIFD.ImageDescription, b"")
        valor = raw.decode("ascii", errors="ignore").strip() if isinstance(raw, bytes) else ""
        if _RE_ID_INVENTARIO.match(valor):
            return valor
    except Exception:
        pass
    return None

EXTENSIONES_IMAGEN = frozenset({
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp",
    ".tiff", ".tif", ".bmp", ".gif", ".cr2", ".arw",
    ".dng", ".nef", ".orf", ".rw2", ".sr2",
})

MESES_ES = {
    1: "01_enero",    2: "02_febrero",  3: "03_marzo",
    4: "04_abril",    5: "05_mayo",     6: "06_junio",
    7: "07_julio",    8: "08_agosto",   9: "09_septiembre",
    10: "10_octubre", 11: "11_noviembre", 12: "12_diciembre",
}

_CARPETAS_FOTO = frozenset({
    "dcim", "camera", "whatsapp", "fotos", "photos",
    "pictures", "imágenes", "imagenes", "mis fotos",
})
_CARPETAS_IMAGEN = frozenset({
    "wallpaper", "wallpapers", "download", "downloads",
    "recursos", "assets", "icons", "web", "internet",
})

_RE_CAMARA = re.compile(
    r"^(img_|dsc_|dscn|p\d{8}|vid_|\d{8}_\d{6}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_RE_SCREENSHOT = re.compile(
    r"^(screenshot|captura|screen_?shot|pantalla|capture|snap)",
    re.IGNORECASE,
)

_CARPETA_FOTOS = "01_fotos"
_CARPETA_IMAGENES = "01b_imagenes"
_SUBCARPETA_SIN_FECHA = "_sin_fecha"
_SUBCARPETA_SIN_CATEGORIA = "_sin_categoria"


@dataclass
class ArchivoImagen:
    ruta: Path
    tamanio: int
    tipo: str          # "foto" | "imagen" | "indeterminado" | "inventario"
    score: int         # positivo = foto, negativo = imagen
    fecha: datetime | None
    fuente_fecha: str  # "exif" | "json_companion" | "mtime" | "ninguna"
    tiene_camara: bool
    tiene_gps: bool
    id_inventario: str | None = None  # ID de ítem si la foto pertenece al inventario
    _ancho: int = 0   # píxeles — para subcategoría de 01b_imagenes/
    _alto: int = 0


@dataclass
class ResultadoPaso4:
    archivos: list[ArchivoImagen] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.archivos)

    @property
    def fotos(self) -> int:
        return sum(1 for a in self.archivos if a.tipo == "foto")

    @property
    def imagenes(self) -> int:
        return sum(1 for a in self.archivos if a.tipo == "imagen")

    @property
    def total_bytes(self) -> int:
        return sum(a.tamanio for a in self.archivos)

    @property
    def con_fecha_exif(self) -> int:
        return sum(1 for a in self.archivos if a.fuente_fecha == "exif")


@dataclass
class PlanPaso4:
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


# ─── Lógica de scoring ────────────────────────────────────────────────────────

def _puntaje_foto(ruta: Path, exif, tamanio: int) -> int:
    """Score positivo → foto, negativo → imagen descargada."""
    score = 0

    if _PIL_DISPONIBLE and exif is not None:
        if exif.tiene_camara:
            score += 5
        if exif.tiene_gps:
            score += 2
        if exif.fecha is not None:
            score += 2
        if exif.es_screenshot_nombre:
            score -= 4
        if exif.es_resolucion_pantalla:
            score -= 3

    nombre_lower = ruta.stem.lower()
    if _RE_SCREENSHOT.match(nombre_lower):
        score -= 4
    elif _RE_CAMARA.match(nombre_lower):
        score += 3

    # Heurística de tamaño
    ext = ruta.suffix.lower()
    if tamanio < 50_000 and ext == ".png":
        score -= 2
    if tamanio > 1_500_000 and ext in {".jpg", ".jpeg", ".heic", ".heif"}:
        score += 2

    # Heurística de carpeta
    partes = {p.lower() for p in ruta.parts}
    if partes & _CARPETAS_FOTO:
        score += 3
    if partes & _CARPETAS_IMAGEN:
        score -= 3

    return score


# ─── Fecha ────────────────────────────────────────────────────────────────────

def _fecha_desde_json_companion(ruta: Path) -> datetime | None:
    """Lee el JSON companion de Google Photos ({nombre}.json) si existe."""
    for candidato in [ruta.parent / f"{ruta.name}.json",
                      ruta.parent / f"{ruta.stem}.json"]:
        if candidato.exists():
            try:
                datos = json.loads(candidato.read_text(encoding="utf-8"))
                ts = datos.get("photoTakenTime", {}).get("timestamp")
                if ts:
                    return datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(tzinfo=None)
            except (ValueError, KeyError, OSError):
                pass
    return None


def _fecha_archivo(ruta: Path, exif) -> tuple[datetime | None, str]:
    """Determina la fecha de la imagen con su fuente."""
    if _PIL_DISPONIBLE and exif is not None and exif.fecha:
        return exif.fecha, "exif"
    json_fecha = _fecha_desde_json_companion(ruta)
    if json_fecha:
        return json_fecha, "json_companion"
    try:
        mtime = ruta.stat().st_mtime
        return datetime.fromtimestamp(mtime), "mtime"
    except OSError:
        return None, "ninguna"


# ─── Detección ────────────────────────────────────────────────────────────────

def detectar_imagenes(directorio: str | Path) -> ResultadoPaso4:
    """Escanea directorio buscando imágenes y las clasifica. Solo lectura."""
    directorio = Path(directorio)
    resultado = ResultadoPaso4()

    for raiz, dirs, archivos in os.walk(str(directorio)):
        # No descender en los destinos ya organizados
        dirs[:] = [d for d in dirs if d not in (_CARPETA_FOTOS, _CARPETA_IMAGENES)]

        for nombre in archivos:
            ruta = Path(raiz) / nombre
            if ruta.suffix.lower() not in EXTENSIONES_IMAGEN:
                continue

            try:
                tamanio = ruta.stat().st_size
            except OSError:
                tamanio = 0

            exif = _extraer_exif(ruta) if _PIL_DISPONIBLE else None
            score = _puntaje_foto(ruta, exif, tamanio)
            fecha, fuente = _fecha_archivo(ruta, exif)

            tiene_camara = exif.tiene_camara if _PIL_DISPONIBLE and exif else False
            tiene_gps = exif.tiene_gps if _PIL_DISPONIBLE and exif else False
            ancho = exif.ancho if _PIL_DISPONIBLE and exif else 0
            alto = exif.alto if _PIL_DISPONIBLE and exif else 0

            # Detectar fotos etiquetadas como ítems de inventario
            id_inv = None
            if ruta.suffix.lower() in {".jpg", ".jpeg"}:
                id_inv = _leer_id_inventario_exif(ruta)

            if id_inv:
                tipo = "inventario"
            elif score > 0:
                tipo = "foto"
            elif score < 0:
                tipo = "imagen"
            else:
                tipo = "indeterminado"

            resultado.archivos.append(ArchivoImagen(
                ruta=ruta,
                tamanio=tamanio,
                tipo=tipo,
                score=score,
                fecha=fecha,
                fuente_fecha=fuente,
                tiene_camara=tiene_camara,
                tiene_gps=tiene_gps,
                id_inventario=id_inv,
                _ancho=ancho,
                _alto=alto,
            ))

    return resultado


# ─── Plan ────────────────────────────────────────────────────────────────────

def _nombre_estandarizado(archivo: ArchivoImagen) -> str:
    """
    Genera nombre estándar YYYY-MM-DD_HHMMSS.ext cuando la fecha proviene de EXIF o JSON.
    Para fechas de mtime o sin fecha, conserva el nombre original.
    """
    if archivo.fecha and archivo.fuente_fecha in ("exif", "json_companion"):
        ts = archivo.fecha.strftime("%Y-%m-%d_%H%M%S")
        return f"{ts}{archivo.ruta.suffix.lower()}"
    return archivo.ruta.name


def _destino_foto(archivo: ArchivoImagen, base: Path) -> Path:
    """Calcula la ruta destino para una foto: base/YYYY/MM_nombre_mes/nombre_estandarizado."""
    nombre = _nombre_estandarizado(archivo)
    if archivo.fecha:
        anio = str(archivo.fecha.year)
        mes = MESES_ES.get(archivo.fecha.month, f"{archivo.fecha.month:02d}")
        return base / _CARPETA_FOTOS / anio / mes / nombre
    return base / _CARPETA_FOTOS / _SUBCARPETA_SIN_FECHA / nombre


def _destino_imagen(archivo: ArchivoImagen, base: Path, ancho: int = 0, alto: int = 0) -> Path:
    """Calcula la ruta destino para una imagen descargada con subcategoría heurística."""
    subcategoria = detectar_subcategoria(archivo.ruta, ancho, alto)
    return base / _CARPETA_IMAGENES / subcategoria / archivo.ruta.name


def _nombre_foto_inventario(ruta: Path, id_item: str, directorio: Path) -> str:
    """Genera nombre secuencial para foto de inventario: <ID>_01.ext, _02.ext..."""
    import re as _re
    patron = _re.compile(rf"^{_re.escape(id_item)}_(\d+)\.", _re.IGNORECASE)
    max_seq = 0
    if directorio.exists():
        for f in directorio.iterdir():
            m = patron.match(f.name)
            if m:
                max_seq = max(max_seq, int(m.group(1)))
    seq = max_seq + 1
    return f"{id_item}_{seq:02d}{ruta.suffix.lower()}"


def construir_plan(
    resultado: ResultadoPaso4,
    destino: str | Path,
    base_hdd: str | Path | None = None,
    vault_dir: str | Path | None = None,
) -> PlanPaso4:
    """Construye el plan de movimientos para Paso 4.

    base_hdd: raíz del HDD organizado. Si se proporciona, archivos dañados
    se enrutan a _pendientes/dañados/ con el path intendido codificado.
    vault_dir: si se proporciona, fotos con EXIF de inventario se enrutan a
    Personal/_fotos_inventario/<PREFIJO>/ dentro del vault.
    """
    destino = Path(destino)
    base = Path(base_hdd) if base_hdd else destino
    vault = Path(vault_dir) if vault_dir else None
    plan = PlanPaso4()

    for archivo in resultado.archivos:
        # Verificar integridad antes de planificar el movimiento
        ok, error_msg = verificar_archivo(archivo.ruta)
        if not ok:
            if archivo.tipo == "foto":
                dest_intendida = _destino_foto(archivo, destino)
            elif archivo.tipo == "imagen":
                dest_intendida = _destino_imagen(archivo, destino)
            else:
                dest_intendida = destino / _CARPETA_IMAGENES / _SUBCARPETA_SIN_CATEGORIA / archivo.ruta.name
            ruta_rev = ruta_danado(dest_intendida, base)
            ruta_rev = resolver_colision(ruta_rev)
            plan.movimientos.append({
                "origen": str(archivo.ruta),
                "destino": str(ruta_rev),
                "tipo": "dañado",
                "score": archivo.score,
                "fuente_fecha": archivo.fuente_fecha,
                "tamanio": archivo.tamanio,
                "error_integridad": error_msg,
            })
            plan.total_bytes += archivo.tamanio
            continue

        # Fotos de inventario — enrutar al vault si se conoce
        if archivo.tipo == "inventario" and archivo.id_inventario and vault:
            prefijo = archivo.id_inventario.split("-")[0].upper()
            dir_inv = vault / "Personal" / "_fotos_inventario" / prefijo
            nombre = _nombre_foto_inventario(archivo.ruta, archivo.id_inventario, dir_inv)
            ruta_dest = resolver_destino(archivo.ruta, dir_inv / nombre)
            if ruta_dest is None:
                plan.omitidos_identicos.append(str(archivo.ruta))
                continue
            plan.movimientos.append({
                "origen": str(archivo.ruta),
                "destino": str(ruta_dest),
                "tipo": "inventario",
                "id_inventario": archivo.id_inventario,
                "score": archivo.score,
                "fuente_fecha": archivo.fuente_fecha,
                "tamanio": archivo.tamanio,
            })
            plan.total_bytes += archivo.tamanio
            continue

        if archivo.tipo == "foto" or archivo.tipo == "inventario":
            ruta_dest = _destino_foto(archivo, destino)
        elif archivo.tipo == "imagen":
            ancho = getattr(archivo, "_ancho", 0)
            alto = getattr(archivo, "_alto", 0)
            ruta_dest = _destino_imagen(archivo, destino, ancho, alto)
        else:
            ruta_dest = destino / _CARPETA_IMAGENES / _SUBCARPETA_SIN_CATEGORIA / _nombre_estandarizado(archivo)

        ruta_dest = resolver_destino(archivo.ruta, ruta_dest)
        if ruta_dest is None:
            plan.omitidos_identicos.append(str(archivo.ruta))
            continue
        plan.movimientos.append({
            "origen": str(archivo.ruta),
            "destino": str(ruta_dest),
            "tipo": archivo.tipo,
            "score": archivo.score,
            "fuente_fecha": archivo.fuente_fecha,
            "tamanio": archivo.tamanio,
        })
        plan.total_bytes += archivo.tamanio

    return plan


# ─── Ejecución ───────────────────────────────────────────────────────────────

_EXTS_MEJORA = frozenset({".jpg", ".jpeg"})
_EXTS_MEJORA_PILLOW = frozenset({".jpg", ".jpeg", ".png", ".webp"})


def _mejorar_imagen(ruta: Path) -> None:
    """Aplica autocontraste + nitidez suave (Pillow). Solo para formatos sin pérdida razonable."""
    try:
        from PIL import Image, ImageEnhance, ImageOps
        with Image.open(ruta) as img:
            img = img.convert("RGB") if img.mode not in ("RGB", "L") else img
            img = ImageOps.autocontrast(img, cutoff=1)
            img = ImageEnhance.Sharpness(img).enhance(1.3)
            img.save(ruta, quality=92, optimize=True)
    except Exception:
        pass  # no penalizar si Pillow no está o falla


def ejecutar_plan(
    plan: PlanPaso4,
    log_path: str | Path,
    dry_run: bool = True,
    mejorar_fotos: bool = False,
) -> ResultadoEjecucion:
    """Ejecuta el plan del Paso 4. dry_run=True solo reporta.

    mejorar_fotos: aplica autocontraste + nitidez leve con Pillow tras mover cada foto JPEG/PNG/WebP.
    """
    log_path = Path(log_path)
    resultado = ResultadoEjecucion(log_path=str(log_path), omitidos_identicos=list(plan.omitidos_identicos))

    if dry_run:
        resultado.movidos = list(plan.movimientos)
        return resultado

    reversion = {
        "timestamp": datetime.now().isoformat(),
        "paso": 4,
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
            if mejorar_fotos and mov.get("tipo") == "foto" and destino.suffix.lower() in _EXTS_MEJORA_PILLOW:
                _mejorar_imagen(destino)
            resultado.movidos.append(mov)
        except (OSError, shutil.Error) as e:
            resultado.errores.append({**mov, "error": str(e)})

    return resultado
