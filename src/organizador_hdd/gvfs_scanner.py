"""
Escáner de directorios GVFS (Google Drive montado localmente).

Google Drive GVFS presenta dos limitaciones para el HDD Organizer normal:
  1. Los archivos tienen IDs de Drive como nombre (sin extensión legible).
  2. Los archivos nativos de Google (Docs/Sheets/Slides) son symlinks rotos.
  3. Leer magic bytes sobre GVFS es muy lento (acceso en red).

Este módulo escanea usando solo stat() y is_symlink(), sin leer contenido.
Clasifica mediante heurística de tamaño y detecta Google Docs como `google_doc`.

Categorías por tamaño (Mejora 3 del backlog — 2026-05-18):
  > 50 MB           → probable_video
  5 MB – 50 MB      → probable_video_o_imagen_grande
  100 KB – 5 MB     → probable_imagen_o_documento
  < 100 KB          → probable_documento
  symlink           → google_doc
  directorio        → carpeta
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# ─── Umbrales de tamaño ──────────────────────────────────────────────────────

_50_MB  = 50 * 1024 * 1024
_5_MB   =  5 * 1024 * 1024
_100_KB =      100 * 1024

# Categorías de archivos GVFS (heurística de tamaño — sin extensión)
CATEGORIA_GOOGLE_DOC            = "google_doc"
CATEGORIA_PROBABLE_VIDEO        = "probable_video"
CATEGORIA_PROBABLE_VIDEO_IMAGEN = "probable_video_o_imagen_grande"
CATEGORIA_PROBABLE_IMAGEN_DOC   = "probable_imagen_o_documento"
CATEGORIA_PROBABLE_DOCUMENTO    = "probable_documento"
CATEGORIA_CARPETA               = "carpeta"

# Categorías para archivos locales con extensión conocida
CATEGORIA_DOCUMENTO             = "documento"
CATEGORIA_IMAGEN                = "imagen"
CATEGORIA_VIDEO                 = "video"
CATEGORIA_MUSICA                = "musica"
CATEGORIA_HOJA_CALCULO          = "hoja_de_calculo"
CATEGORIA_PRESENTACION          = "presentacion"
CATEGORIA_CODIGO                = "codigo"

_EXT_CATEGORIA: dict[str, str] = {
    ".pdf":  CATEGORIA_DOCUMENTO,  ".docx": CATEGORIA_DOCUMENTO,
    ".doc":  CATEGORIA_DOCUMENTO,  ".txt":  CATEGORIA_DOCUMENTO,
    ".html": CATEGORIA_DOCUMENTO,  ".htm":  CATEGORIA_DOCUMENTO,
    ".odt":  CATEGORIA_DOCUMENTO,
    ".xlsx": CATEGORIA_HOJA_CALCULO, ".xls": CATEGORIA_HOJA_CALCULO,
    ".csv":  CATEGORIA_HOJA_CALCULO, ".ods": CATEGORIA_HOJA_CALCULO,
    ".pptx": CATEGORIA_PRESENTACION, ".ppt": CATEGORIA_PRESENTACION,
    ".odp":  CATEGORIA_PRESENTACION,
    ".jpg":  CATEGORIA_IMAGEN, ".jpeg": CATEGORIA_IMAGEN,
    ".png":  CATEGORIA_IMAGEN, ".gif":  CATEGORIA_IMAGEN,
    ".webp": CATEGORIA_IMAGEN, ".bmp":  CATEGORIA_IMAGEN,
    ".tiff": CATEGORIA_IMAGEN, ".tif":  CATEGORIA_IMAGEN,
    ".svg":  CATEGORIA_IMAGEN, ".raw":  CATEGORIA_IMAGEN,
    ".mp4":  CATEGORIA_VIDEO,  ".avi":  CATEGORIA_VIDEO,
    ".mkv":  CATEGORIA_VIDEO,  ".mov":  CATEGORIA_VIDEO,
    ".wmv":  CATEGORIA_VIDEO,  ".webm": CATEGORIA_VIDEO,
    ".mp3":  CATEGORIA_MUSICA, ".flac": CATEGORIA_MUSICA,
    ".wav":  CATEGORIA_MUSICA, ".m4a":  CATEGORIA_MUSICA,
    ".aac":  CATEGORIA_MUSICA, ".ogg":  CATEGORIA_MUSICA,
    ".py":   CATEGORIA_CODIGO, ".js":   CATEGORIA_CODIGO,
    ".ts":   CATEGORIA_CODIGO, ".json": CATEGORIA_CODIGO,
    ".yaml": CATEGORIA_CODIGO, ".yml":  CATEGORIA_CODIGO,
    ".sh":   CATEGORIA_CODIGO, ".toml": CATEGORIA_CODIGO,
}

# Destinos estimados por categoría
_DESTINO_ESTIMADO: dict[str, str] = {
    CATEGORIA_GOOGLE_DOC:            "(no descargable vía GVFS — usar Google Takeout)",
    CATEGORIA_PROBABLE_VIDEO:        "02_videos/",
    CATEGORIA_PROBABLE_VIDEO_IMAGEN: "02_videos/ o 01b_imagenes/",
    CATEGORIA_PROBABLE_IMAGEN_DOC:   "01b_imagenes/ o 08_documentos/",
    CATEGORIA_PROBABLE_DOCUMENTO:    "08_documentos/",
    CATEGORIA_CARPETA:               "(contiene archivos)",
    CATEGORIA_DOCUMENTO:             "08_documentos/",
    CATEGORIA_IMAGEN:                "01b_imagenes/",
    CATEGORIA_VIDEO:                 "02_videos/",
    CATEGORIA_MUSICA:                "03_musica/",
    CATEGORIA_HOJA_CALCULO:          "08_documentos/hojas_calculo/",
    CATEGORIA_PRESENTACION:          "08_documentos/presentaciones/",
    CATEGORIA_CODIGO:                "07_proyectos_prog/",
}


# ─── Clasificación por tamaño ─────────────────────────────────────────────────

def clasificar_por_tamanio(tamanio: int) -> str:
    """Categoría estimada de un archivo GVFS basándose solo en su tamaño."""
    if tamanio >= _50_MB:
        return CATEGORIA_PROBABLE_VIDEO
    if tamanio >= _5_MB:
        return CATEGORIA_PROBABLE_VIDEO_IMAGEN
    if tamanio >= _100_KB:
        return CATEGORIA_PROBABLE_IMAGEN_DOC
    return CATEGORIA_PROBABLE_DOCUMENTO


def clasificar_por_extension(nombre: str) -> str | None:
    """Categoría basada en la extensión del archivo. Retorna None si no es reconocida."""
    ext = Path(nombre).suffix.lower()
    return _EXT_CATEGORIA.get(ext)


# ─── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class GvfsEntrada:
    ruta: Path
    es_symlink: bool
    es_directorio: bool
    tamanio: int
    mtime: str

    @property
    def categoria(self) -> str:
        if self.es_symlink:
            return CATEGORIA_GOOGLE_DOC
        if self.es_directorio:
            return CATEGORIA_CARPETA
        ext_cat = _EXT_CATEGORIA.get(self.ruta.suffix.lower())
        if ext_cat:
            return ext_cat
        return clasificar_por_tamanio(self.tamanio)

    @property
    def es_duplicado_drive(self) -> bool:
        """True si el nombre sigue el patrón de duplicado de Drive: 'nombre (N).ext'."""
        import re
        return bool(re.search(r'\s*\(\d+\)$', self.ruta.stem))

    @property
    def destino_estimado(self) -> str:
        return _DESTINO_ESTIMADO.get(self.categoria, "_pendientes/sin_clasificar/")

    @property
    def tamanio_legible(self) -> str:
        t = self.tamanio
        for u in ("B", "KB", "MB", "GB"):
            if t < 1024:
                return f"{t:.0f} {u}"
            t /= 1024
        return f"{t:.1f} TB"


@dataclass
class GvfsResumen:
    ruta_base: Path
    total_entradas: int
    archivos_regulares: int
    google_docs: int
    carpetas: int
    tamanio_total: int
    duplicados_drive: int = 0
    por_categoria: dict[str, int] = field(default_factory=dict)
    tamanio_por_categoria: dict[str, int] = field(default_factory=dict)

    @property
    def tamanio_legible(self) -> str:
        return _bytes_legible(self.tamanio_total)


def _bytes_legible(b: int) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.0f} {u}"
        b //= 1024
    return f"{b} TB"


def resumir(entradas: list[GvfsEntrada]) -> GvfsResumen:
    """Construye un GvfsResumen a partir de la lista de entradas escaneadas."""
    archivos_regulares = sum(1 for e in entradas if not e.es_directorio and not e.es_symlink)
    google_docs = sum(1 for e in entradas if e.es_symlink)
    carpetas = sum(1 for e in entradas if e.es_directorio)
    tamanio_total = sum(e.tamanio for e in entradas if not e.es_directorio)
    duplicados = sum(1 for e in entradas if not e.es_directorio and e.es_duplicado_drive)
    por_cat: dict[str, int] = {}
    tam_cat: dict[str, int] = {}
    for e in entradas:
        por_cat[e.categoria] = por_cat.get(e.categoria, 0) + 1
        tam_cat[e.categoria] = tam_cat.get(e.categoria, 0) + e.tamanio
    return GvfsResumen(
        ruta_base=entradas[0].ruta.parent if entradas else Path("."),
        total_entradas=len(entradas),
        archivos_regulares=archivos_regulares,
        google_docs=google_docs,
        carpetas=carpetas,
        tamanio_total=tamanio_total,
        duplicados_drive=duplicados,
        por_categoria=por_cat,
        tamanio_por_categoria=tam_cat,
    )


# ─── Escaneo ──────────────────────────────────────────────────────────────────

def escanear_gvfs(ruta_base: Path, max_prof: int = 4) -> list[GvfsEntrada]:
    """
    Escanea un directorio GVFS usando solo stat() — sin leer contenido de archivos.

    Retorna una lista plana de GvfsEntrada con todos los nodos (archivos + dirs + symlinks).
    Los directorios se incluyen para tener la estructura completa.
    """
    entradas: list[GvfsEntrada] = []

    def _walk(ruta: Path, prof: int) -> None:
        if prof > max_prof:
            return
        try:
            items = list(os.scandir(ruta))
        except (PermissionError, OSError):
            return

        for item in items:
            p = Path(item.path)
            try:
                es_symlink = item.is_symlink()
                es_dir = item.is_dir(follow_symlinks=False)
                stat = item.stat(follow_symlinks=False)
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
                tamanio = stat.st_size if not es_dir and not es_symlink else 0
            except OSError:
                es_symlink = False
                es_dir = False
                mtime = "?"
                tamanio = 0

            entradas.append(GvfsEntrada(
                ruta=p,
                es_symlink=es_symlink,
                es_directorio=es_dir,
                tamanio=tamanio,
                mtime=mtime,
            ))

            if es_dir and not es_symlink:
                _walk(p, prof + 1)

    _walk(ruta_base, 0)
    return entradas


# ─── Generación de reporte Markdown ──────────────────────────────────────────

def generar_reporte_md(
    nombre_seccion: str,
    entradas: list[GvfsEntrada],
    ruta_base: Path,
    is_local: bool = False,
) -> str:
    """
    Genera el contenido Markdown del reporte de escaneo.

    is_local=False → modo GVFS (heurística de tamaño, texto GVFS)
    is_local=True  → modo local (extensiones reales, tabla por carpeta, duplicados)
    """
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    resumen = resumir(entradas)

    archivos_solo = [e for e in entradas if not e.es_directorio]
    total_arch = len(archivos_solo)

    def _pct(n: int) -> str:
        return f"{n / total_arch * 100:.1f}%" if total_arch else "0%"

    tipo_reporte = "mapa-local" if is_local else "mapa-gvfs"
    titulo = f"Mapa {'Local' if is_local else 'GVFS'} — {nombre_seccion}"
    metodo = ("clasificación por extensión + heurística de tamaño"
              if is_local else "stat() sin leer contenido — GVFS seguro y rápido")

    lineas = [
        "---",
        f"tipo: {tipo_reporte}",
        f"fecha: {fecha}",
        f"ruta: {ruta_base}",
        f"total_archivos: {total_arch}",
        f"google_docs: {resumen.google_docs}",
        f"duplicados_drive: {resumen.duplicados_drive}",
        "tags: [hdd-organizer, google-drive, mapa]",
        "---",
        "",
        f"# {titulo}",
        "",
        f"> Ruta: `{ruta_base}`  ",
        f"> Generado: {fecha}  ",
        f"> Método: {metodo}",
        "",
        "---",
        "",
        "## Resumen",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Entradas totales | {resumen.total_entradas:,} |",
        f"| Archivos regulares | {resumen.archivos_regulares:,} |",
        f"| **Google Docs/Sheets/Slides** (no descargables vía GVFS) | **{resumen.google_docs:,}** |",
        f"| Carpetas | {resumen.carpetas:,} |",
        f"| Duplicados Drive (patrón `nombre (N).ext`) | {resumen.duplicados_drive:,} |",
        f"| Tamaño total (archivos regulares) | {resumen.tamanio_legible} |",
        "",
    ]

    if resumen.google_docs > 0:
        pct_gdoc = resumen.google_docs / max(total_arch, 1) * 100
        lineas += [
            f"> **{resumen.google_docs} archivos nativos de Google ({pct_gdoc:.0f}% del total)** no son descargables",
            f"> vía GVFS. Para incluirlos en el HDD organizado: **Google Takeout → paso5 del organizador**.",
            "",
        ]

    # ── Distribución por categoría ─────────────────────────────────────────────
    lineas += [
        "---",
        "",
        "## Distribución por categoría",
        "",
        "| Categoría | Archivos | % | Tamaño | Destino estimado HDD |",
        "|---|---|---|---|---|",
    ]

    cats_local = [
        CATEGORIA_DOCUMENTO, CATEGORIA_HOJA_CALCULO, CATEGORIA_PRESENTACION,
        CATEGORIA_IMAGEN, CATEGORIA_VIDEO, CATEGORIA_MUSICA, CATEGORIA_CODIGO,
    ]
    cats_gvfs = [
        CATEGORIA_GOOGLE_DOC,
        CATEGORIA_PROBABLE_VIDEO,
        CATEGORIA_PROBABLE_VIDEO_IMAGEN,
        CATEGORIA_PROBABLE_IMAGEN_DOC,
        CATEGORIA_PROBABLE_DOCUMENTO,
    ]
    orden_cats = cats_local + cats_gvfs if is_local else cats_gvfs + cats_local

    for cat in orden_cats:
        cnt = resumen.por_categoria.get(cat, 0)
        if cnt == 0:
            continue
        sz = _bytes_legible(resumen.tamanio_por_categoria.get(cat, 0))
        destino = _DESTINO_ESTIMADO.get(cat, "?")
        negrita = "**" if cat == CATEGORIA_GOOGLE_DOC else ""
        lineas.append(f"| {negrita}`{cat}`{negrita} | {negrita}{cnt}{negrita} ({_pct(cnt)}) | {_pct(cnt)} | {sz} | {destino} |")

    # ── Por carpeta (solo modo local) ──────────────────────────────────────────
    if is_local:
        lineas += [
            "",
            "---",
            "",
            "## Por carpeta (nivel 1)",
            "",
            "| Carpeta | Archivos | Tamaño | Categorías principales |",
            "|---|---|---|---|",
        ]
        carpeta_stats: dict[str, dict] = {}
        for e in archivos_solo:
            try:
                partes = e.ruta.relative_to(ruta_base).parts
            except ValueError:
                partes = (e.ruta.name,)
            nivel1 = partes[0] if len(partes) > 1 else "(raíz)"
            if nivel1 not in carpeta_stats:
                carpeta_stats[nivel1] = {"cnt": 0, "tam": 0, "cats": {}}
            carpeta_stats[nivel1]["cnt"] += 1
            carpeta_stats[nivel1]["tam"] += e.tamanio
            c = e.categoria
            carpeta_stats[nivel1]["cats"][c] = carpeta_stats[nivel1]["cats"].get(c, 0) + 1

        for folder, stats in sorted(carpeta_stats.items(), key=lambda x: -x[1]["cnt"]):
            top_cats = sorted(stats["cats"].items(), key=lambda x: -x[1])[:2]
            cats_str = ", ".join(f"`{c}` ({n})" for c, n in top_cats)
            lineas.append(
                f"| `{folder}` | {stats['cnt']:,} | {_bytes_legible(stats['tam'])} | {cats_str} |"
            )

    # ── Duplicados probables (solo modo local si hay) ──────────────────────────
    if is_local and resumen.duplicados_drive > 0:
        dups = [e for e in archivos_solo if e.es_duplicado_drive]
        lineas += [
            "",
            "---",
            "",
            f"## Duplicados probables de Drive ({len(dups)})",
            "",
            "> Archivos con patrón `nombre (N).ext` — generados por Google Drive al descargar duplicados.",
            "",
            "| Archivo | Categoría | Tamaño |",
            "|---|---|---|",
        ]
        for e in sorted(dups, key=lambda x: x.ruta.name)[:100]:
            try:
                rel = str(e.ruta.relative_to(ruta_base))
            except ValueError:
                rel = e.ruta.name
            lineas.append(f"| `{rel}` | {e.categoria} | {e.tamanio_legible} |")
        if len(dups) > 100:
            lineas.append(f"\n> ... y {len(dups) - 100} más.")

    # ── Detalle de archivos ────────────────────────────────────────────────────
    lineas += [
        "",
        "---",
        "",
        "## Detalle de archivos",
        "",
        "> Solo archivos (excluye carpetas). Ordenados por categoría.",
        "",
        "| Archivo | Categoría | Tamaño | Últ. modificación | Destino estimado |",
        "|---|---|---|---|---|",
    ]

    for e in sorted(archivos_solo, key=lambda x: (x.categoria, x.tamanio)):
        try:
            rel = str(e.ruta.relative_to(ruta_base))
        except ValueError:
            rel = e.ruta.name
        lineas.append(
            f"| `{rel}` | {e.categoria} | {e.tamanio_legible} | {e.mtime} | {e.destino_estimado} |"
        )

    # ── Notas ──────────────────────────────────────────────────────────────────
    lineas += ["", "---", ""]

    if is_local:
        lineas += [
            "## Notas sobre clasificación local",
            "",
            "### Clasificación por extensión",
            "",
            "| Extensiones | Categoría | Destino HDD |",
            "|---|---|---|",
            "| `.pdf .docx .doc .txt .html .odt` | `documento` | `08_documentos/` |",
            "| `.xlsx .xls .csv .ods` | `hoja_de_calculo` | `08_documentos/hojas_calculo/` |",
            "| `.pptx .ppt .odp` | `presentacion` | `08_documentos/presentaciones/` |",
            "| `.jpg .jpeg .png .gif .webp .raw` | `imagen` | `01b_imagenes/` |",
            "| `.mp4 .avi .mkv .mov .wmv` | `video` | `02_videos/` |",
            "| `.mp3 .flac .wav .m4a .aac` | `musica` | `03_musica/` |",
            "| `.py .js .ts .json .yaml .sh` | `codigo` | `07_proyectos_prog/` |",
            "| Sin extensión reconocida | heurística de tamaño | (ver tabla GVFS) |",
            "",
            "### Sobre los duplicados Drive",
            "",
            "Google Drive crea duplicados con sufijos `(1)`, `(2)`, etc. cuando hay conflictos de versiones.",
            "Se recomienda revisar y eliminar los duplicados antes de migrar al HDD organizado.",
        ]
    else:
        lineas += [
            "## Notas sobre clasificación GVFS",
            "",
            "### Por qué los archivos no tienen nombres legibles",
            "",
            "Google Drive GVFS monta los archivos con sus IDs internos (p.ej. `1BTM61dd...`).",
            "El HDD Organizer normal usa extensión + nombre para clasificar — ambas señales faltan aquí.",
            "",
            "### Clasificación por tamaño (heurística)",
            "",
            "Sin extensión ni nombre, este escáner usa el tamaño como señal:",
            "",
            "| Tamaño | Categoría | Razonamiento |",
            "|---|---|---|",
            "| > 50 MB | `probable_video` | Videos, presentaciones grandes, ISOs |",
            "| 5 MB – 50 MB | `probable_video_o_imagen_grande` | Videos cortos, RAW, PDFs ilustrados |",
            "| 100 KB – 5 MB | `probable_imagen_o_documento` | Imágenes, PDFs, documentos Office |",
            "| < 100 KB | `probable_documento` | Docs de texto, CSVs, código |",
            "| symlink | `google_doc` | Google Docs/Sheets/Slides — no descargables |",
            "",
            "### Cómo organizar el contenido de Google Drive",
            "",
            "```",
            "1. google.com/takeout → seleccionar Google Drive → Exportar",
            "2. Descomprimir: unzip 'Takeout-*.zip' -d ~/gdrive_takeout/",
            "3. hdd-organizar paso5 ~/gdrive_takeout/   ← reconoce carpeta Takeout",
            "4. hdd-organizar paso6 ~/gdrive_takeout/_pendientes/checar/  ← clasifica el resto",
            "```",
        ]

    return "\n".join(lineas) + "\n"
