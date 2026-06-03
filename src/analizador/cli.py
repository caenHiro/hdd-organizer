import click
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, MofNCompleteColumn
from rich.table import Table
from rich.prompt import Confirm
from .scanner import escanear_directorio
from .db import BaseDatos
from .reportes import generar_reporte_obsidian, fmt_bytes
from .organizador import ReglaMovimiento, construir_plan, ejecutar_plan, deshacer_movimiento

console = Console()
_LOTE = 500


@click.group()
def cli():
    """Analizador y organizador de archivos HDD/SSD.

    Lee el sistema de archivos sin modificarlo (salvo el comando 'mover' con --confirmar).
    El único archivo que escribe por defecto es la base de datos SQLite de inventario.
    """


# ─── SCAN ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("ruta", type=click.Path(exists=True, file_okay=False))
@click.option("--db", default="inventario.db", show_default=True, help="Archivo SQLite de salida")
@click.option("--sin-hashes", is_flag=True, help="Omite SHA256 (más rápido, sin detección de duplicados)")
@click.option("--dry-run", is_flag=True, help="Solo muestra qué haría, sin escribir nada")
@click.option("--desde", default=None, help="Fecha mínima de modificación (YYYY-MM-DD)")
@click.option("--hasta", default=None, help="Fecha máxima de modificación (YYYY-MM-DD)")
def scan(ruta, db, sin_hashes, dry_run, desde, hasta):
    """Escanea RUTA y guarda el inventario en la base de datos."""
    if dry_run:
        console.print(f"[yellow][DRY-RUN][/yellow] Ruta analizada : {ruta}")
        console.print(f"[yellow][DRY-RUN][/yellow] BD de salida   : {db}")
        if desde or hasta:
            console.print(f"[yellow][DRY-RUN][/yellow] Filtro fechas  : {desde or '*'} → {hasta or '*'}")
        console.print("[yellow][DRY-RUN][/yellow] Sin cambios en el disco analizado.")
        return

    base = BaseDatos(db)
    lote: list = []
    contador = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        MofNCompleteColumn(),
        console=console,
        transient=True,
    ) as prog:
        tarea = prog.add_task("Escaneando…", total=None)

        for info in escanear_directorio(ruta, calcular_hashes=not sin_hashes):
            # Filtro por fecha si se especificó
            if desde and info.fecha_modificacion.date().isoformat() < desde:
                continue
            if hasta and info.fecha_modificacion.date().isoformat() > hasta:
                continue

            lote.append(info)
            contador += 1
            if len(lote) >= _LOTE:
                base.insertar_lote(lote)
                lote.clear()
            prog.update(tarea, completed=contador,
                        description=f"[cyan]{info.nombre[:50]}")

        if lote:
            base.insertar_lote(lote)

    stats = base.estadisticas()
    console.print(f"[green]✓[/green] Escaneo completo")
    console.print(f"  Archivos procesados : {contador:,}")
    console.print(f"  Espacio analizado   : {fmt_bytes(stats.get('espacio_total') or 0)}")
    console.print(f"  Base de datos       : {db}")
    if desde or hasta:
        console.print(f"  Filtro aplicado     : {desde or '*'} → {hasta or '*'}")
    if sin_hashes:
        console.print("[dim]  (hashes omitidos — detección de duplicados no disponible)[/dim]")


# ─── STATS ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--db", default="inventario.db", show_default=True)
@click.option("--desde", default=None, help="Mostrar solo archivos desde fecha (YYYY-MM-DD)")
@click.option("--hasta", default=None, help="Mostrar solo archivos hasta fecha (YYYY-MM-DD)")
def stats(db, desde, hasta):
    """Muestra estadísticas del inventario."""
    if not Path(db).exists():
        console.print(f"[red]BD no encontrada:[/red] {db}")
        return

    base = BaseDatos(db)

    if desde or hasta:
        archivos = base.archivos_por_fecha(desde=desde, hasta=hasta)
        total = len(archivos)
        espacio = sum(a.get("tamanio", 0) or 0 for a in archivos)
        console.print(f"Archivos en rango {desde or '*'} → {hasta or '*'}: [bold]{total:,}[/bold] · [yellow]{fmt_bytes(espacio)}[/yellow]")
        return

    s = base.estadisticas()
    tabla = Table(title="Inventario — por tipo de archivo")
    tabla.add_column("Tipo", style="cyan")
    tabla.add_column("Archivos", justify="right")
    tabla.add_column("Espacio", justify="right", style="yellow")

    for t in s.get("por_tipo", []):
        tabla.add_row(t["tipo"], f"{t['cantidad']:,}", fmt_bytes(t["espacio"] or 0))

    console.print(tabla)
    console.print(
        f"\nTotal: [bold]{s.get('total_archivos', 0):,}[/bold] archivos · "
        f"[yellow]{fmt_bytes(s.get('espacio_total') or 0)}[/yellow]"
    )


# ─── DUPLICADOS ────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--db", default="inventario.db", show_default=True)
@click.option("--min-mb", default=1, show_default=True, help="Tamaño mínimo en MB para reportar como duplicado")
def duplicados(db, min_mb):
    """Lista grupos de archivos duplicados (por hash SHA256)."""
    if not Path(db).exists():
        console.print(f"[red]BD no encontrada:[/red] {db}  —  ejecuta primero 'scan'")
        return

    base = BaseDatos(db)
    grupos = base.duplicados(min_bytes=min_mb * 1024 * 1024)

    if not grupos:
        console.print(f"[green]Sin duplicados >= {min_mb} MB.[/green]")
        return

    espacio_recuperable = sum(
        g["espacio_total"] - (g["espacio_total"] // g["copias"])
        for g in grupos
    )

    tabla = Table(title=f"Duplicados encontrados ({len(grupos)} grupos)", show_lines=False)
    tabla.add_column("#", style="dim", width=4)
    tabla.add_column("Hash (parcial)", style="cyan")
    tabla.add_column("Copias", justify="right")
    tabla.add_column("Por archivo", justify="right")
    tabla.add_column("Total", justify="right", style="yellow")

    for i, g in enumerate(grupos[:20], 1):
        tam = fmt_bytes(g["espacio_total"] // g["copias"])
        tabla.add_row(
            str(i),
            g["hash_sha256"][:16] + "…",
            str(g["copias"]),
            tam,
            fmt_bytes(g["espacio_total"]),
        )

    console.print(tabla)
    if len(grupos) > 20:
        console.print(f"[dim]  … y {len(grupos) - 20} grupos más. Usa 'reporte' para el detalle completo.[/dim]")
    console.print(f"\n[yellow]Espacio recuperable estimado:[/yellow] {fmt_bytes(espacio_recuperable)}")
    console.print("[dim]NUNCA eliminar automáticamente. Verificar cada grupo manualmente.[/dim]")


# ─── DEDUPLICAR ────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--db", default="inventario.db", show_default=True)
@click.option("--min-mb", default=1, show_default=True)
def deduplicar(db, min_mb):
    """Deduplicación interactiva — revisa grupos de duplicados uno por uno.

    Muestra cada grupo de archivos con el mismo hash y permite marcar cuál conservar.
    NO elimina ningún archivo — genera un reporte Markdown con las recomendaciones.
    """
    if not Path(db).exists():
        console.print(f"[red]BD no encontrada:[/red] {db}")
        return

    base = BaseDatos(db)
    grupos = base.duplicados(min_bytes=min_mb * 1024 * 1024)

    if not grupos:
        console.print(f"[green]Sin duplicados >= {min_mb} MB.[/green]")
        return

    console.print(f"\n[bold]Deduplicación interactiva[/bold] — {len(grupos)} grupos\n")
    console.print("[dim]Para cada grupo, indica qué archivo conservar (o 's' para saltar).[/dim]\n")

    recomendaciones: list[dict] = []

    for i, g in enumerate(grupos, 1):
        rutas = g["rutas"].split("|||")
        tam = fmt_bytes(g["espacio_total"] // g["copias"])

        tabla = Table(title=f"Grupo {i}/{len(grupos)} — {tam} × {g['copias']} copias", show_lines=True)
        tabla.add_column("#", style="dim", width=3)
        tabla.add_column("Ruta", style="cyan")
        tabla.add_column("Tamaño", justify="right")

        for j, ruta in enumerate(rutas, 1):
            tabla.add_row(str(j), ruta, tam)

        console.print(tabla)

        while True:
            opcion = click.prompt(
                "  Conservar # (1-{}) / 's' saltar / 'q' salir".format(len(rutas)),
                default="s",
            )
            if opcion.lower() == "q":
                console.print("[yellow]Sesión terminada.[/yellow]")
                _guardar_recomendaciones(recomendaciones)
                return
            if opcion.lower() == "s":
                break
            try:
                idx = int(opcion) - 1
                if 0 <= idx < len(rutas):
                    conservar = rutas[idx]
                    eliminar = [r for r in rutas if r != conservar]
                    recomendaciones.append({
                        "conservar": conservar,
                        "eliminar": eliminar,
                        "espacio_liberado": g["espacio_total"] - (g["espacio_total"] // g["copias"]),
                    })
                    console.print(f"  [green]✓[/green] Conservar: {conservar}")
                    break
            except ValueError:
                pass
            console.print("[red]  Opción inválida.[/red]")

        console.print()

    _guardar_recomendaciones(recomendaciones)


def _guardar_recomendaciones(recomendaciones: list[dict]) -> None:
    if not recomendaciones:
        return
    from datetime import datetime
    salida = Path(f"deduplicacion_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.md")
    espacio_total = sum(r["espacio_liberado"] for r in recomendaciones)
    lineas = [
        "---",
        "tags: [inventario, duplicados, deduplicacion]",
        f"fecha: {datetime.now().strftime('%Y-%m-%d')}",
        "---",
        "",
        "# Recomendaciones de Deduplicación",
        "",
        f"> {len(recomendaciones)} grupos revisados · {fmt_bytes(espacio_total)} recuperables",
        "",
        "> **Revisar antes de eliminar.** Este archivo es solo una guía.",
        "",
    ]
    for i, rec in enumerate(recomendaciones, 1):
        lineas += [
            f"## Grupo {i}",
            "",
            f"**Conservar:** `{rec['conservar']}`",
            "",
            "**Eliminar:**",
        ]
        for r in rec["eliminar"]:
            lineas.append(f"- `{r}`")
        lineas += [f"", f"Espacio a liberar: {fmt_bytes(rec['espacio_liberado'])}", ""]

    salida.write_text("\n".join(lineas), encoding="utf-8")
    console.print(f"\n[green]✓[/green] Recomendaciones guardadas en: {salida}")


# ─── REPORTE ───────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--db", default="inventario.db", show_default=True)
@click.option("--salida", default="./reportes-obsidian", show_default=True)
@click.option("--nombre", default="", help="Etiqueta del escaneo (ej: 'Disco externo 2TB')")
def reporte(db, salida, nombre):
    """Genera reportes Markdown listos para importar en Obsidian."""
    if not Path(db).exists():
        console.print(f"[red]BD no encontrada:[/red] {db}")
        return

    base = BaseDatos(db)
    archivos = generar_reporte_obsidian(base, salida, nombre)

    console.print(f"[green]✓[/green] {len(archivos)} reportes en: {salida}")
    for f in archivos:
        console.print(f"  → {Path(f).name}")
    console.print("\n[dim]Copia los archivos .md a brain/vault/ o donde prefieras en Obsidian.[/dim]")


# ─── EXPORTAR ──────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--db", default="inventario.db", show_default=True)
@click.option("--salida", default="inventario.csv", show_default=True, help="Archivo CSV de salida")
@click.option("--desde", default=None, help="Fecha mínima de modificación (YYYY-MM-DD)")
@click.option("--hasta", default=None, help="Fecha máxima de modificación (YYYY-MM-DD)")
def exportar(db, salida, desde, hasta):
    """Exporta el inventario a CSV."""
    if not Path(db).exists():
        console.print(f"[red]BD no encontrada:[/red] {db}")
        return

    base = BaseDatos(db)
    total = base.exportar_csv(salida, desde=desde, hasta=hasta)
    console.print(f"[green]✓[/green] {total:,} registros exportados → {salida}")
    if desde or hasta:
        console.print(f"  Filtro: {desde or '*'} → {hasta or '*'}")


# ─── VIEJOS ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("directorio")
@click.option("--db", default="inventario.db", show_default=True)
@click.option("--meses", default=6, show_default=True, help="Antigüedad mínima en meses")
@click.option("--min-mb", default=0, show_default=True, help="Tamaño mínimo en MB")
@click.option("--top", default=50, show_default=True, help="Máximo de archivos a mostrar")
def viejos(directorio, db, meses, min_mb, top):
    """Muestra archivos 'olvidados' en DIRECTORIO (sin modificar en N meses).

    Útil para revisar ~/Downloads, ~/Desktop, etc.
    """
    if not Path(db).exists():
        console.print(f"[red]BD no encontrada:[/red] {db}")
        return

    dias = meses * 30
    base = BaseDatos(db)
    archivos = base.archivos_viejos(directorio, dias=dias, min_bytes=min_mb * 1024 * 1024)

    if not archivos:
        console.print(f"[green]Sin archivos viejos (>{meses} meses) en {directorio}[/green]")
        return

    total_espacio = sum(a.get("tamanio", 0) or 0 for a in archivos)
    titulo = f"Archivos no modificados en >{meses} meses — {directorio} ({len(archivos)} archivos)"
    tabla = Table(title=titulo, show_lines=False)
    tabla.add_column("Nombre", style="cyan", max_width=40)
    tabla.add_column("Tipo")
    tabla.add_column("Tamaño", justify="right", style="yellow")
    tabla.add_column("Última modificación")
    tabla.add_column("Ruta", style="dim", max_width=55)

    for a in archivos[:top]:
        fecha = (a.get("fecha_modificacion") or "")[:10]
        tabla.add_row(
            a["nombre"],
            a.get("tipo", ""),
            fmt_bytes(a.get("tamanio", 0) or 0),
            fecha,
            a["ruta"],
        )

    console.print(tabla)
    if len(archivos) > top:
        console.print(f"[dim]  … y {len(archivos) - top} archivos más.[/dim]")
    console.print(f"\nTotal: [bold]{len(archivos):,}[/bold] archivos · [yellow]{fmt_bytes(total_espacio)}[/yellow]")
    console.print("[dim]Usa 'reporte' o 'exportar' para obtener el listado completo.[/dim]")


# ─── MOVER ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--db", default="inventario.db", show_default=True)
@click.option("--tipo", default=None, help="Mover archivos de este tipo (imagen, video, audio, documento…)")
@click.option("--extension", default=None, help="Mover archivos con esta extensión (ej: .pdf)")
@click.option("--desde-dir", default=None, help="Mover solo archivos bajo este directorio")
@click.option("--destino", required=True, help="Directorio de destino")
@click.option("--excluir", multiple=True, help="Rutas a excluir (repetible: --excluir /ruta1 --excluir /ruta2)")
@click.option("--log", default="reversion.json", show_default=True, help="Archivo de log de reversión")
@click.option("--confirmar", is_flag=True, help="Ejecutar el movimiento (sin este flag es siempre dry-run)")
def mover(db, tipo, extension, desde_dir, destino, excluir, log, confirmar):
    """Mueve archivos en bloque según criterios.

    Por defecto es DRY-RUN. Añade --confirmar para ejecutar el movimiento real.
    Escribe un log de reversión (reversion.json) antes de mover, usable con 'deshacer'.

    Ejemplos:

      hdd-scan mover --tipo imagen --destino /disco/Fotos/ --confirmar

      hdd-scan mover --extension .pdf --destino /disco/Docs/ --dry-run

      hdd-scan mover --desde-dir /Downloads --destino /disco/Pendientes/ --confirmar
    """
    if not Path(db).exists():
        console.print(f"[red]BD no encontrada:[/red] {db}")
        return

    if not tipo and not extension and not desde_dir:
        console.print("[red]Especifica al menos --tipo, --extension o --desde-dir[/red]")
        return

    base = BaseDatos(db)

    # Construir lista de archivos candidatos
    if tipo:
        archivos = base.buscar_por_tipo(tipo)
    elif extension:
        archivos = base.buscar_por_extension(extension)
    elif desde_dir:
        archivos = base.archivos_viejos(desde_dir, dias=0)  # todos los del directorio
    else:
        archivos = []

    if not archivos:
        console.print("[yellow]No se encontraron archivos con los criterios indicados.[/yellow]")
        return

    regla = ReglaMovimiento(destino=destino, tipo=tipo, extension=extension, directorio_origen=desde_dir)
    plan = construir_plan(archivos, regla, excluir=list(excluir))

    if not plan:
        console.print("[yellow]Plan vacío — todos los archivos fueron excluidos.[/yellow]")
        return

    espacio_total = sum(m.tamanio for m in plan)
    dry_run = not confirmar

    if dry_run:
        console.print(f"\n[yellow][DRY-RUN][/yellow] Plan de movimiento — {len(plan):,} archivos · {fmt_bytes(espacio_total)}\n")
    else:
        console.print(f"\n[bold red]⚠  MOVIMIENTO REAL[/bold red] — {len(plan):,} archivos · {fmt_bytes(espacio_total)}")
        console.print(f"   Log de reversión → {log}\n")
        if not Confirm.ask("¿Confirmas el movimiento?"):
            console.print("Cancelado.")
            return

    tabla = Table(show_lines=False, show_header=True)
    tabla.add_column("Nombre", style="cyan", max_width=35)
    tabla.add_column("Tipo")
    tabla.add_column("Tamaño", justify="right")
    tabla.add_column("Destino", style="dim", max_width=55)

    for m in plan[:30]:
        tabla.add_row(m.nombre, m.tipo, fmt_bytes(m.tamanio), m.destino)

    console.print(tabla)
    if len(plan) > 30:
        console.print(f"[dim]  … y {len(plan) - 30} archivos más.[/dim]")

    resultado = ejecutar_plan(plan, log_path=log, dry_run=dry_run)

    if dry_run:
        console.print(f"\n[yellow]DRY-RUN:[/yellow] {len(resultado.movidos):,} archivos se moverían a {destino}")
        console.print("  Agrega [bold]--confirmar[/bold] para ejecutar el movimiento real.")
    else:
        console.print(f"\n[green]✓[/green] {len(resultado.movidos):,} archivos movidos")
        if resultado.errores:
            console.print(f"[red]  {len(resultado.errores)} errores[/red]")
            for e in resultado.errores[:5]:
                console.print(f"    [red]✗[/red] {e['origen']} → {e['error']}")
        console.print(f"  Log de reversión: [bold]{log}[/bold]")
        console.print("[dim]  Usa 'deshacer --log {log}' para revertir.[/dim]".format(log=log))


# ─── DESHACER ──────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--log", default="reversion.json", show_default=True, help="Archivo de log de reversión")
@click.option("--confirmar", is_flag=True, help="Ejecutar la reversión (sin este flag es dry-run)")
def deshacer(log, confirmar):
    """Deshace un movimiento usando el log de reversión generado por 'mover'.

    Por defecto es DRY-RUN. Añade --confirmar para ejecutar la reversión real.
    """
    dry_run = not confirmar
    try:
        resultado = deshacer_movimiento(log, dry_run=dry_run)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return

    if dry_run:
        console.print(f"\n[yellow][DRY-RUN][/yellow] Reversión — {len(resultado.movidos):,} archivos se devolverían\n")
        for m in resultado.movidos[:20]:
            console.print(f"  [cyan]{m['origen']}[/cyan] → {m['destino']}")
        if len(resultado.movidos) > 20:
            console.print(f"  [dim]… y {len(resultado.movidos) - 20} más[/dim]")
        console.print("\n  Agrega [bold]--confirmar[/bold] para ejecutar la reversión real.")
    else:
        console.print(f"\n[green]✓[/green] {len(resultado.movidos):,} archivos revertidos")
        if resultado.errores:
            console.print(f"[red]  {len(resultado.errores)} errores[/red]")
            for e in resultado.errores[:5]:
                console.print(f"    [red]✗[/red] {e['origen']}: {e['error']}")


if __name__ == "__main__":
    cli()
