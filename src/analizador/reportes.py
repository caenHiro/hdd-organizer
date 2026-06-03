from pathlib import Path
from datetime import datetime
from .db import BaseDatos


def fmt_bytes(n: int) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def generar_reporte_obsidian(
    db: BaseDatos,
    directorio_salida: str,
    etiqueta: str = "",
) -> list[str]:
    """
    Escribe archivos .md en directorio_salida.
    No toca el HDD analizado — solo escribe en el destino especificado.
    Retorna lista de rutas creadas.
    """
    salida = Path(directorio_salida)
    salida.mkdir(parents=True, exist_ok=True)

    fecha_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    creados = []

    stats = db.estadisticas()
    p = salida / f"Inventario_{fecha_str}.md"
    _reporte_principal(p, stats, etiqueta)
    creados.append(str(p))

    filas = db.archivos_por_carpeta()
    if filas:
        p = salida / f"Indice_Archivos_{fecha_str}.md"
        _reporte_indice(p, filas, etiqueta, stats)
        creados.append(str(p))

    dups = db.duplicados()
    if dups:
        p = salida / f"Duplicados_{fecha_str}.md"
        _reporte_duplicados(p, dups)
        creados.append(str(p))

    grandes = db.archivos_grandes()
    if grandes:
        p = salida / f"Archivos_Grandes_{fecha_str}.md"
        _reporte_grandes(p, grandes)
        creados.append(str(p))

    return creados


def _reporte_principal(ruta: Path, stats: dict, etiqueta: str) -> None:
    fecha = datetime.now().strftime("%Y-%m-%d")
    titulo = f"Inventario HDD — {etiqueta}" if etiqueta else "Inventario HDD"
    lineas = [
        "---",
        "tags: [inventario, hdd, archivos]",
        f"fecha: {fecha}",
        "---",
        "",
        f"# {titulo}",
        "",
        "## Resumen",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Total archivos | {stats.get('total_archivos', 0):,} |",
        f"| Espacio total  | {fmt_bytes(stats.get('espacio_total') or 0)} |",
        "",
        "## Por tipo de archivo",
        "",
        "| Tipo | Archivos | Espacio |",
        "|---|---|---|",
    ]
    for t in stats.get("por_tipo", []):
        lineas.append(f"| {t['tipo']} | {t['cantidad']:,} | {fmt_bytes(t['espacio'] or 0)} |")
    lineas += ["", "## Notas", "", "- ", ""]
    ruta.write_text("\n".join(lineas), encoding="utf-8")


def _reporte_duplicados(ruta: Path, grupos: list[dict]) -> None:
    espacio_recuperable = sum(
        g["espacio_total"] - (g["espacio_total"] // g["copias"])
        for g in grupos
    )
    lineas = [
        "---",
        "tags: [inventario, duplicados, hdd]",
        f"fecha: {datetime.now().strftime('%Y-%m-%d')}",
        "---",
        "",
        "# Archivos Duplicados",
        "",
        f"> {len(grupos)} grupos · {fmt_bytes(espacio_recuperable)} recuperables",
        "",
        "> **NUNCA eliminar automáticamente.** Revisar cada grupo manualmente.",
        "",
    ]
    for i, g in enumerate(grupos[:100], 1):
        rutas = g["rutas"].split("|||")
        tam = fmt_bytes(g["espacio_total"] // g["copias"])
        lineas += [
            f"## Grupo {i} — {tam} × {g['copias']} copias",
            "",
            f"Hash: `{g['hash_sha256'][:20]}...`",
            "",
        ]
        for r in rutas:
            lineas.append(f"- `{r}`")
        lineas.append("")
    ruta.write_text("\n".join(lineas), encoding="utf-8")


def _reporte_indice(ruta_md: Path, filas: list[dict], etiqueta: str, stats: dict) -> None:
    """Índice completo: un bloque por carpeta con nombre, ruta y tamaño de cada archivo."""
    fecha = datetime.now().strftime("%Y-%m-%d")
    titulo = f"Índice de Archivos — {etiqueta}" if etiqueta else "Índice de Archivos"

    # Agrupar por carpeta manteniendo orden
    carpetas: dict[str, list[dict]] = {}
    for fila in filas:
        c = fila["carpeta"]
        carpetas.setdefault(c, []).append(fila)

    lineas = [
        "---",
        "tags: [inventario, indice, hdd]",
        f"fecha: {fecha}",
        "---",
        "",
        f"# {titulo}",
        "",
        f"> {stats.get('total_archivos', 0):,} archivos · {fmt_bytes(stats.get('espacio_total') or 0)}",
        "",
        "## Carpetas",
        "",
    ]

    # Tabla de contenido
    for carpeta, archivos_c in carpetas.items():
        espacio = sum(a["tamanio"] for a in archivos_c)
        lineas.append(f"- `{carpeta}` — {len(archivos_c)} archivos · {fmt_bytes(espacio)}")

    lineas += ["", "---", ""]

    # Listado por carpeta
    for carpeta, archivos_c in carpetas.items():
        espacio = sum(a["tamanio"] for a in archivos_c)
        lineas += [
            f"## `{carpeta}`",
            "",
            f"> {len(archivos_c)} archivos · {fmt_bytes(espacio)}",
            "",
            "| Nombre | Tipo | Tamaño | Ruta completa |",
            "|---|---|---|---|",
        ]
        for a in archivos_c:
            lineas.append(
                f"| {a['nombre']} | {a['tipo']} | {fmt_bytes(a['tamanio'])} | `{a['ruta']}` |"
            )
        lineas += ["", ""]

    ruta_md.write_text("\n".join(lineas), encoding="utf-8")


def _reporte_grandes(ruta: Path, archivos: list[dict]) -> None:
    lineas = [
        "---",
        "tags: [inventario, archivos-grandes, hdd]",
        f"fecha: {datetime.now().strftime('%Y-%m-%d')}",
        "---",
        "",
        "# Archivos Grandes (> 100 MB)",
        "",
        "| # | Nombre | Tipo | Tamaño | Ruta |",
        "|---|---|---|---|---|",
    ]
    for i, f in enumerate(archivos, 1):
        nombre = (f["nombre"][:45] + "…") if len(f["nombre"]) > 45 else f["nombre"]
        ruta_corta = (f["ruta"][:70] + "…") if len(f["ruta"]) > 70 else f["ruta"]
        lineas.append(f"| {i} | {nombre} | {f['tipo']} | {fmt_bytes(f['tamanio'])} | `{ruta_corta}` |")
    lineas.append("")
    ruta.write_text("\n".join(lineas), encoding="utf-8")
