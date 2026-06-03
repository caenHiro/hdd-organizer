"""
hdd-organizar — Organizador HDD en 8 pasos.

Uso básico:
    hdd-organizar paso1 /ruta/hdd
    hdd-organizar paso1 /ruta/hdd --destino /ruta/hdd/_pendientes/artefactos --confirmar
"""
import click
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.table import Table

from . import paso1 as _paso1
from . import paso2 as _paso2
from . import paso3 as _paso3
from . import paso4 as _paso4
from . import paso5 as _paso5
from . import paso6 as _paso6
from . import paso7 as _paso7
from . import paso8 as _paso8
from . import obsidian_writer as _obsidian
from . import clasificador_fotos_ollama as _ollama_fotos
from . import readme_carpetas as _readme
from . import gvfs_scanner as _gvfs
from .utils import fmt_bytes

try:
    from . import clasificador_clip as _clip
    _CLIP_DISPONIBLE = True
except ImportError:
    _CLIP_DISPONIBLE = False

console = Console()




@click.group()
def cli():
    """Organizador HDD/SSD en 7 pasos — opera sobre una copia o con --confirmar explícito."""


# ─── PASO 1 ───────────────────────────────────────────────────────────────────

@cli.command(name="paso1")
@click.argument("directorio", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--destino",
    default=None,
    help="Directorio donde mover los artefactos. "
         "Por defecto: <directorio>/_pendientes/artefactos",
)
@click.option(
    "--log",
    default=None,
    help="Ruta del log de reversión JSON. "
         "Por defecto: logs/reversion_paso1_<timestamp>.json",
)
@click.option(
    "--confirmar",
    is_flag=True,
    default=False,
    help="Ejecutar el movimiento real (sin este flag es siempre dry-run).",
)
@click.option(
    "--resumen",
    is_flag=True,
    default=False,
    help="Mostrar solo el resumen, sin listar archivos individuales.",
)
def paso1(directorio, destino, log, confirmar, resumen):
    """Paso 1 — detecta y mueve artefactos técnicos a _pendientes/artefactos.

    Artefactos detectados:

    \b
      Extensiones: .class .sha1 .pom .lastupdated .svn-base .crdownload .part ...
      Archivos:    Thumbs.db .DS_Store desktop.ini
      Carpetas:    __pycache__ .svn .gradle node_modules .idea target (si tiene .class)
                   .m2/repository

    \b
    Ejemplos:
      hdd-organizar paso1 /media/hdd
      hdd-organizar paso1 /media/hdd --destino /media/hdd/_pendientes/artefactos --confirmar
    """
    directorio_path = Path(directorio)

    destino_path = Path(destino) if destino else directorio_path / "_pendientes" / "artefactos"
    log_path = (
        Path(log) if log
        else Path("logs") / f"reversion_paso1_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    console.print(f"\n[bold]Paso 1 — Artefactos técnicos[/bold]")
    console.print(f"  Directorio : {directorio_path}")
    if confirmar:
        console.print(f"  Destino    : {destino_path}")
        console.print(f"  Log        : {log_path}")
    console.print()

    # Detección
    with console.status("[cyan]Escaneando artefactos…[/cyan]"):
        resultado = _paso1.detectar_artefactos(directorio_path)

    if resultado.total_archivos == 0 and not resultado.carpetas:
        console.print("[green]Sin artefactos detectados.[/green]")
        return

    # Resumen por extensión
    if not resumen:
        tabla = Table(title="Archivos artefacto detectados", show_lines=False)
        tabla.add_column("Extensión / Nombre", style="cyan")
        tabla.add_column("Cantidad", justify="right")
        for ext, cantidad in resultado.por_extension().items():
            tabla.add_row(ext, f"{cantidad:,}")
        console.print(tabla)

    if resultado.carpetas:
        tabla_c = Table(title="Carpetas artefacto completas", show_lines=False)
        tabla_c.add_column("Carpeta", style="yellow")
        tabla_c.add_column("Ruta", style="dim")
        for c in resultado.carpetas[:20]:
            tabla_c.add_row(c.name, str(c))
        if len(resultado.carpetas) > 20:
            console.print(f"[dim]  … y {len(resultado.carpetas) - 20} carpetas más.[/dim]")
        console.print(tabla_c)

    console.print(
        f"\nTotal: [bold]{resultado.total_archivos:,}[/bold] archivos sueltos · "
        f"[bold]{len(resultado.carpetas)}[/bold] carpetas completas · "
        f"[yellow]{fmt_bytes(resultado.total_bytes)}[/yellow]"
    )

    if not confirmar:
        console.print(
            "\n[yellow][DRY-RUN][/yellow] Sin cambios en el disco. "
            "Agrega [bold]--confirmar[/bold] para mover los artefactos."
        )
        return

    # Construir y ejecutar plan
    plan = _paso1.construir_plan(resultado, destino_path)

    console.print(f"\n[bold red]⚠  MOVIMIENTO REAL[/bold red] — {len(plan):,} elementos · {fmt_bytes(plan.total_bytes)}")
    console.print(f"   Destino: {destino_path}")
    console.print(f"   Log de reversión → {log_path}\n")

    if not click.confirm("¿Confirmas el movimiento de artefactos?"):
        console.print("Cancelado.")
        return

    ejec = _paso1.ejecutar_plan(plan, log_path=log_path, dry_run=False)

    console.print(f"\n[green]✓[/green] {len(ejec.movidos):,} elementos movidos a {destino_path}")
    if ejec.omitidos:
        console.print(f"[dim]  {len(ejec.omitidos)} omitidos (ya no existían)[/dim]")
    if ejec.errores:
        console.print(f"[red]  {len(ejec.errores)} errores[/red]")
        for e in ejec.errores[:5]:
            console.print(f"    [red]✗[/red] {e.get('origen')}: {e.get('error')}")
    console.print(f"  Log de reversión: [bold]{log_path}[/bold]")
    console.print("[dim]  Usa 'hdd-deshacer --log <archivo>' para revertir si es necesario.[/dim]")


# ─── PASO 2 ───────────────────────────────────────────────────────────────────

@cli.command(name="paso2")
@click.argument("directorio", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--destino",
    default=None,
    help="Directorio de libros. Por defecto: <directorio>/04_libros",
)
@click.option("--log", default=None, help="Ruta del log de reversión JSON.")
@click.option("--confirmar", is_flag=True, default=False)
def paso2(directorio, destino, log, confirmar):
    """Paso 2 — detecta y mueve la biblioteca Calibre a 04_libros/calibre/.

    Detecta la raíz de una biblioteca Calibre buscando directorios con metadata.opf
    (cada libro Calibre contiene un metadata.opf dentro de su carpeta de título).

    \b
    Ejemplos:
      hdd-organizar paso2 /media/hdd
      hdd-organizar paso2 /media/hdd --destino /media/hdd/04_libros --confirmar
    """
    directorio_path = Path(directorio)
    destino_path = Path(destino) if destino else directorio_path / "04_libros"
    log_path = (
        Path(log) if log
        else Path("logs") / f"reversion_paso2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    console.print("\n[bold]Paso 2 — Biblioteca Calibre[/bold]")
    console.print(f"  Directorio : {directorio_path}\n")

    with console.status("[cyan]Buscando biblioteca Calibre…[/cyan]"):
        resultado = _paso2.detectar_calibre(directorio_path)

    if not resultado.encontrada:
        console.print("[yellow]No se encontró una biblioteca Calibre en el directorio.[/yellow]")
        console.print("[dim]  (Se requieren >= 3 libros con metadata.opf)[/dim]")
        return

    console.print(f"  Biblioteca : [cyan]{resultado.biblioteca}[/cyan]")
    console.print(f"  Libros     : [bold]{resultado.total_libros:,}[/bold]")
    console.print(f"  Tamaño     : [yellow]{fmt_bytes(resultado.total_bytes)}[/yellow]")

    plan = _paso2.construir_plan(resultado, destino_path)
    console.print(f"  Destino    : {plan.destino}")

    if not confirmar:
        console.print(
            "\n[yellow][DRY-RUN][/yellow] Sin cambios. "
            "Agrega [bold]--confirmar[/bold] para mover la biblioteca."
        )
        return

    console.print(f"\n[bold red]⚠  MOVIMIENTO REAL[/bold red]")
    console.print(f"   {resultado.biblioteca} → {plan.destino}")
    if not click.confirm("¿Confirmas mover la biblioteca Calibre?"):
        console.print("Cancelado.")
        return

    ejec = _paso2.ejecutar_plan(plan, log_path=log_path, dry_run=False)
    if ejec.exito:
        console.print(f"\n[green]✓[/green] Biblioteca movida a {plan.destino}")
        console.print(f"  Log de reversión: [bold]{log_path}[/bold]")
    else:
        console.print(f"[red]✗ Error:[/red] {ejec.error}")


# ─── PASO 3 ───────────────────────────────────────────────────────────────────

@cli.command(name="paso3")
@click.argument("directorio", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--destino",
    default=None,
    help="Directorio de música. Por defecto: <directorio>/03_musica",
)
@click.option("--log", default=None, help="Ruta del log de reversión JSON.")
@click.option("--confirmar", is_flag=True, default=False)
@click.option("--top", default=20, show_default=True, help="Top N artistas a mostrar en resumen.")
def paso3(directorio, destino, log, confirmar, top):
    """Paso 3 — consolida música en 03_musica/por_artista/<artista>/<album>/.

    Lee tags ID3/Vorbis/MP4 con mutagen. Transliteración cirílica ISO 9.
    Compilaciones → 03_musica/compilaciones/
    Sin artista   → 03_musica/_sin_artista/

    \b
    Ejemplos:
      hdd-organizar paso3 /media/hdd
      hdd-organizar paso3 /media/hdd --destino /media/hdd/03_musica --confirmar
    """
    directorio_path = Path(directorio)
    destino_path = Path(destino) if destino else directorio_path / "03_musica"
    log_path = (
        Path(log) if log
        else Path("logs") / f"reversion_paso3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    console.print("\n[bold]Paso 3 — Música[/bold]")
    console.print(f"  Directorio : {directorio_path}\n")

    with console.status("[cyan]Escaneando archivos de audio…[/cyan]"):
        resultado = _paso3.detectar_musica(directorio_path)

    if resultado.total == 0:
        console.print("[yellow]No se encontraron archivos de audio.[/yellow]")
        return

    # Resumen por artista (top N)
    por_artista = resultado.por_artista()
    tabla = Table(title=f"Top {top} artistas detectados", show_lines=False)
    tabla.add_column("Artista", style="cyan")
    tabla.add_column("Canciones", justify="right")
    for artista, cant in list(por_artista.items())[:top]:
        tabla.add_row(artista or "[dim]_sin_artista[/dim]", f"{cant:,}")
    console.print(tabla)

    console.print(
        f"\nTotal: [bold]{resultado.total:,}[/bold] archivos · "
        f"con tags: [green]{resultado.con_tags:,}[/green] · "
        f"sin tags: [yellow]{resultado.sin_tags:,}[/yellow] · "
        f"compilaciones: [cyan]{resultado.compilaciones:,}[/cyan] · "
        f"[yellow]{fmt_bytes(resultado.total_bytes)}[/yellow]"
    )

    plan = _paso3.construir_plan(resultado, destino_path)

    if not confirmar:
        console.print(
            "\n[yellow][DRY-RUN][/yellow] Sin cambios. "
            "Agrega [bold]--confirmar[/bold] para organizar la música."
        )
        return

    console.print(f"\n[bold red]⚠  MOVIMIENTO REAL[/bold red] — {len(plan):,} archivos · {fmt_bytes(plan.total_bytes)}")
    console.print(f"   Destino: {destino_path}")
    if not click.confirm("¿Confirmas organizar la música?"):
        console.print("Cancelado.")
        return

    ejec = _paso3.ejecutar_plan(plan, log_path=log_path, dry_run=False)

    console.print(f"\n[green]✓[/green] {len(ejec.movidos):,} archivos organizados en {destino_path}")
    if ejec.omitidos:
        console.print(f"[dim]  {len(ejec.omitidos)} omitidos (ya no existían)[/dim]")
    if ejec.errores:
        console.print(f"[red]  {len(ejec.errores)} errores[/red]")
        for e in ejec.errores[:5]:
            console.print(f"    [red]✗[/red] {e.get('origen')}: {e.get('error')}")
    console.print(f"  Log de reversión: [bold]{log_path}[/bold]")


# ─── PASO 4 ───────────────────────────────────────────────────────────────────

@cli.command(name="paso4")
@click.argument("directorio", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--destino",
    default=None,
    help="Base destino. Por defecto: <directorio> (crea 01_fotos/ y 01b_imagenes/ ahí mismo).",
)
@click.option("--log", default=None, help="Ruta del log de reversión JSON.")
@click.option("--confirmar", is_flag=True, default=False)
@click.option("--mejorar-fotos", is_flag=True, default=False,
              help="Aplicar autocontraste + nitidez suave con Pillow tras mover cada foto JPEG/PNG.")
@click.option("--vault", default=None,
              help="Ruta al vault Obsidian. Fotos con EXIF de inventario se mueven ahí.")
@click.option("--top", default=5, show_default=True, help="Años más frecuentes a mostrar.")
def paso4(directorio, destino, log, confirmar, mejorar_fotos, vault, top):
    """Paso 4 — clasifica y organiza fotos e imágenes descargadas.

    \b
    Fotos reales  → 01_fotos/YYYY/MM_nombre_mes/  (renombradas YYYY-MM-DD_HHMMSS.ext si EXIF)
    Imágenes      → 01b_imagenes/_sin_categoria/
    Sin fecha     → 01_fotos/_sin_fecha/
    Dañadas       → _pendientes/dañados/<ruta_codificada>/

    \b
    Clasificación por score (sin IA):
      +5 EXIF con cámara, +2 GPS, +2 fecha EXIF, +3 nombre IMG_/DSC_
      -4 screenshot, -3 resolución de pantalla, -2 PNG pequeño
      ±3 carpeta DCIM/Camera vs Downloads/Wallpapers

    \b
    Ejemplos:
      hdd-organizar paso4 /media/hdd
      hdd-organizar paso4 /media/hdd --confirmar --mejorar-fotos
    """
    directorio_path = Path(directorio)
    destino_path = Path(destino) if destino else directorio_path
    log_path = (
        Path(log) if log
        else Path("logs") / f"reversion_paso4_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    console.print("\n[bold]Paso 4 — Fotos vs Imágenes[/bold]")
    console.print(f"  Directorio : {directorio_path}\n")

    with console.status("[cyan]Escaneando y clasificando imágenes…[/cyan]"):
        resultado = _paso4.detectar_imagenes(directorio_path)

    if resultado.total == 0:
        console.print("[yellow]No se encontraron imágenes.[/yellow]")
        return

    tabla = Table(title="Clasificación de imágenes", show_lines=False)
    tabla.add_column("Categoría", style="cyan")
    tabla.add_column("Cantidad", justify="right")
    tabla.add_column("Espacio", justify="right", style="yellow")

    fotos = [a for a in resultado.archivos if a.tipo == "foto"]
    imagenes = [a for a in resultado.archivos if a.tipo == "imagen"]
    indeterminadas = [a for a in resultado.archivos if a.tipo == "indeterminado"]

    tabla.add_row("Fotos reales",     f"{len(fotos):,}",         fmt_bytes(sum(a.tamanio for a in fotos)))
    tabla.add_row("Imágenes",         f"{len(imagenes):,}",      fmt_bytes(sum(a.tamanio for a in imagenes)))
    tabla.add_row("Indeterminadas",   f"{len(indeterminadas):,}", fmt_bytes(sum(a.tamanio for a in indeterminadas)))
    console.print(tabla)

    console.print(
        f"\nTotal: [bold]{resultado.total:,}[/bold] archivos · "
        f"con EXIF cámara: [green]{resultado.con_fecha_exif:,}[/green] · "
        f"[yellow]{fmt_bytes(resultado.total_bytes)}[/yellow]"
    )

    vault_path = Path(vault).expanduser() if vault else None
    plan = _paso4.construir_plan(resultado, destino_path, base_hdd=destino_path, vault_dir=vault_path)
    danados_count = sum(1 for m in plan.movimientos if m.get("tipo") == "dañado")
    inv_count = sum(1 for m in plan.movimientos if m.get("tipo") == "inventario")
    if inv_count:
        console.print(f"[cyan]  {inv_count} fotos de inventario → vault[/cyan]")
    if danados_count:
        console.print(f"[yellow]  {danados_count} archivos dañados → _pendientes/dañados/[/yellow]")

    if plan.omitidos_identicos:
        console.print(f"[dim]  {len(plan.omitidos_identicos)} ya organizados (idempotente)[/dim]")

    if not confirmar:
        console.print(
            "\n[yellow][DRY-RUN][/yellow] Sin cambios. "
            "Agrega [bold]--confirmar[/bold] para organizar las imágenes."
        )
        if mejorar_fotos:
            console.print("[dim]  (--mejorar-fotos se aplicará al confirmar)[/dim]")
        return

    console.print(f"\n[bold red]⚠  MOVIMIENTO REAL[/bold red] — {len(plan):,} archivos · {fmt_bytes(plan.total_bytes)}")
    if mejorar_fotos:
        console.print("[cyan]  Mejora de calidad Pillow activada para fotos JPEG/PNG[/cyan]")
    if not click.confirm("¿Confirmas organizar fotos e imágenes?"):
        console.print("Cancelado.")
        return

    ejec = _paso4.ejecutar_plan(plan, log_path=log_path, dry_run=False, mejorar_fotos=mejorar_fotos)

    console.print(f"\n[green]✓[/green] {len(ejec.movidos):,} archivos organizados")
    if ejec.omitidos_identicos:
        console.print(f"[dim]  {len(ejec.omitidos_identicos)} omitidos (ya existían)[/dim]")
    if ejec.omitidos:
        console.print(f"[dim]  {len(ejec.omitidos)} omitidos (ya no existían)[/dim]")
    if ejec.errores:
        console.print(f"[red]  {len(ejec.errores)} errores[/red]")
        for e in ejec.errores[:5]:
            console.print(f"    [red]✗[/red] {e.get('origen')}: {e.get('error')}")
    console.print(f"  Log de reversión: [bold]{log_path}[/bold]")


# ─── PASO 5 ───────────────────────────────────────────────────────────────────

@cli.command(name="paso5")
@click.argument("directorio", type=click.Path(exists=True, file_okay=False))
@click.option("--destino", default=None,
              help="Base destino. Por defecto: <directorio>.")
@click.option("--log", default=None)
@click.option("--confirmar", is_flag=True, default=False)
def paso5(directorio, destino, log, confirmar):
    """Paso 5 — enruta paquetes Google Takeout a sus destinos.

    \b
    Google Fotos/   → 01_fotos/YYYY/MM_nombre_mes/
    Meet Recordings/→ 02_videos/
    Classroom/      → 05_cursos/
    Otros           → _pendientes/checar/
    """
    directorio_path = Path(directorio)
    destino_path = Path(destino) if destino else directorio_path
    log_path = (
        Path(log) if log
        else Path("logs") / f"reversion_paso5_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    console.print("\n[bold]Paso 5 — Google Takeout[/bold]")
    with console.status("[cyan]Buscando paquetes Takeout…[/cyan]"):
        resultado = _paso5.detectar_takeout(directorio_path)

    if resultado.total == 0:
        console.print("[yellow]No se encontraron paquetes Takeout.[/yellow]")
        return

    console.print(f"  Paquetes detectados: [bold]{len(resultado.paquetes_detectados)}[/bold]")
    tabla = Table(title="Archivos por categoría Takeout", show_lines=False)
    tabla.add_column("Categoría destino", style="cyan")
    tabla.add_column("Archivos", justify="right")
    for cat, cnt in resultado.por_categoria().items():
        tabla.add_row(cat, f"{cnt:,}")
    console.print(tabla)
    console.print(f"\nTotal: [bold]{resultado.total:,}[/bold] · [yellow]{fmt_bytes(resultado.total_bytes)}[/yellow]")

    plan = _paso5.construir_plan(resultado, destino_path)
    if not confirmar:
        console.print("\n[yellow][DRY-RUN][/yellow] Agrega [bold]--confirmar[/bold] para mover.")
        return

    console.print(f"\n[bold red]⚠  MOVIMIENTO REAL[/bold red] — {len(plan):,} archivos")
    if not click.confirm("¿Confirmas?"):
        return
    ejec = _paso5.ejecutar_plan(plan, log_path, dry_run=False)
    console.print(f"\n[green]✓[/green] {len(ejec.movidos):,} archivos movidos")
    if ejec.errores:
        console.print(f"[red]  {len(ejec.errores)} errores[/red]")


# ─── PASO 6 ───────────────────────────────────────────────────────────────────

@cli.command(name="paso6")
@click.argument("directorio", type=click.Path(exists=True, file_okay=False),
                metavar="DIRECTORIO  (normalmente _pendientes/checar/)")
@click.option("--destino", default=None,
              help="Base destino. Por defecto: carpeta padre de DIRECTORIO.")
@click.option("--log", default=None)
@click.option("--confirmar", is_flag=True, default=False)
@click.option(
    "--privado",
    is_flag=True,
    default=False,
    help="Tratar todos los archivos del directorio como privados. "
         "Los archivos irán a .privado/{fotos,videos,audio,varios}/ "
         "organizados con las mismas convenciones que el resto del HDD.",
)
@click.option(
    "--contexto",
    type=click.Choice(["trabajo", "escuela", "personal"], case_sensitive=False),
    default=None,
    help="Tipo de contenido a organizar. Controla el destino de proyectos de programación:\n"
         "trabajo → 09_codigo/{lenguaje}/_trabajo/  |  "
         "escuela → 07_escuela/_pendientes_clasificar/  |  "
         "personal → 09_codigo/proyectos/personales/",
)
def paso6(directorio, destino, log, confirmar, privado, contexto):
    """Paso 6 — clasifica _pendientes/checar/ por extensión y magic bytes.

    \b
    imagen    → 01b_imagenes/_sin_categoria/
    video     → 02_videos/{tipo}/
    audio     → 03_musica/_sin_artista/
    documento → 08_documentos/
    comic     → 04_libros/comics/
    fitness   → 08_documentos/personal/salud/fitness/
    subtitulo → _pendientes/subtitulos/
    código    → 09_codigo/_pendientes/
    proyecto  → 09_codigo/{lenguaje}/_trabajo|escuela|personales/  (carpeta completa)
    comprimido→ _pendientes/zips_revisar/
    otro      → _pendientes/sin_clasificar/

    Proyectos de programación (package.json, pom.xml, requirements.txt, .git, etc.)
    se detectan y mueven como carpeta completa. Usa --contexto para enrutarlos:
    \b
    --contexto trabajo   → 09_codigo/{lenguaje}/_trabajo/
    --contexto escuela   → 07_escuela/_pendientes_clasificar/
    --contexto personal  → 09_codigo/proyectos/personales/

    Con --privado todos los archivos van a .privado/ (carpeta oculta):
    \b
    imagen → .privado/fotos/YYYY/MM_mes/
    video  → .privado/videos/{tipo}/
    audio  → .privado/audio/
    otro   → .privado/varios/

    \b
    Ejemplos:
      hdd-organizar paso6 /media/respaldo/_pendientes/checar
      hdd-organizar paso6 /Downloads/INE --destino /Downloads/respaldo --contexto trabajo
      hdd-organizar paso6 /media/respaldo/z.checar/.other --privado --confirmar
    """
    directorio_path = Path(directorio)
    destino_path = Path(destino) if destino else directorio_path.parent
    log_path = (
        Path(log) if log
        else Path("logs") / f"reversion_paso6_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    console.print("\n[bold]Paso 6 — Clasificar pendientes[/bold]")
    if privado:
        console.print(f"  [magenta]Modo privado activo[/magenta] → destino: [cyan]{destino_path / '.privado'}[/cyan]")
    if contexto:
        console.print(f"  [cyan]Contexto:[/cyan] {contexto} — proyectos de programación enrutados automáticamente")

    with console.status("[cyan]Clasificando archivos…[/cyan]"):
        resultado = _paso6.detectar_pendientes(
            directorio_path, forzar_privado=privado, contexto=contexto,
        )

    if resultado.total == 0:
        console.print("[yellow]Directorio vacío.[/yellow]")
        return

    tabla = Table(title="Clasificación por categoría", show_lines=False)
    tabla.add_column("Categoría", style="cyan")
    tabla.add_column("Archivos/Proyectos", justify="right")
    for cat, cnt in resultado.por_categoria().items():
        tabla.add_row(cat, f"{cnt:,}")
    console.print(tabla)

    proyectos = [a for a in resultado.archivos if a.categoria == "proyecto"]
    if proyectos:
        console.print(f"\n  [green]{len(proyectos):,} proyecto(s) detectados[/green] — se moverán como carpeta completa")
        for p in proyectos[:10]:
            from .paso6 import _detectar_lenguaje
            lang = _detectar_lenguaje(p.ruta)
            console.print(f"    [cyan]▸[/cyan] {p.ruta.name}  [dim]({lang})[/dim]")
        if len(proyectos) > 10:
            console.print(f"    [dim]… y {len(proyectos) - 10} más[/dim]")

    console.print(f"\nTotal: [bold]{resultado.total:,}[/bold] · [yellow]{fmt_bytes(resultado.total_bytes)}[/yellow]")

    plan = _paso6.construir_plan(resultado, destino_path)
    if plan.omitidos_identicos:
        console.print(f"[dim]  {len(plan.omitidos_identicos)} ya organizados (idempotente)[/dim]")
    if not confirmar:
        console.print("\n[yellow][DRY-RUN][/yellow] Agrega [bold]--confirmar[/bold] para mover.")
        return

    console.print(f"\n[bold red]⚠  MOVIMIENTO REAL[/bold red] — {len(plan):,} archivos/proyectos")
    if not click.confirm("¿Confirmas?"):
        return
    ejec = _paso6.ejecutar_plan(plan, log_path, dry_run=False)
    console.print(f"\n[green]✓[/green] {len(ejec.movidos):,} archivos/proyectos clasificados")
    if ejec.errores:
        console.print(f"[red]  {len(ejec.errores)} errores[/red]")


# ─── PASO 7 ───────────────────────────────────────────────────────────────────

@cli.command(name="paso7")
@click.argument("directorio", type=click.Path(exists=True, file_okay=False))
@click.option("--csv", "csv_path", default=None,
              help="Ruta del reporte CSV. Por defecto: reporte_paso7.csv")
@click.option("--log", default=None)
@click.option("--confirmar", is_flag=True, default=False)
def paso7(directorio, csv_path, log, confirmar):
    """Paso 7 — homologa nombres de archivo (cirílico, basura, fechas).

    Genera reporte CSV ANTES de renombrar. Requiere --confirmar para aplicar.

    \b
    Transformaciones:
      Cirílico → ISO 9 (Иванов → Ivanov)
      !!! =) (copia) → eliminados
      DD-MM-YYYY → YYYY-MM-DD
      Separadores múltiples → uno solo
    """
    directorio_path = Path(directorio)
    csv_ruta = Path(csv_path) if csv_path else Path("reporte_paso7.csv")
    log_path = (
        Path(log) if log
        else Path("logs") / f"reversion_paso7_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    console.print("\n[bold]Paso 7 — Homologar nombres[/bold]")
    console.print("  Limpia: emojis · cirílico · decoraciones · fechas DD-MM → YYYY-MM-DD · separadores\n")
    with console.status("[cyan]Analizando nombres…[/cyan]"):
        resultado = _paso7.generar_reporte(directorio_path, ruta_csv=csv_ruta if not confirmar else None)

    console.print(f"  Archivos revisados:    [bold]{resultado._total:,}[/bold]")
    console.print(f"  Con cambios:           [bold]{resultado.total_cambios:,}[/bold]")

    if resultado.total_cambios == 0:
        console.print("[green]  Todos los nombres ya están homologados.[/green]")
        return

    # Stats por causa
    stats = resultado.stats_por_causa
    _CAUSA_COLOR = {
        "cirilico": "blue", "emoji": "magenta", "basura": "yellow",
        "fecha": "cyan", "separadores": "dim", "invalidos": "red", "combinado": "white",
    }
    causa_str = "  Causas: " + "  ".join(
        f"[{_CAUSA_COLOR.get(k,'white')}]{k}[/{_CAUSA_COLOR.get(k,'white')}]=[bold]{v}[/bold]"
        for k, v in sorted(stats.items(), key=lambda x: -x[1])
    )
    console.print(causa_str)

    # Tabla de preview
    tabla = Table(
        title=f"Propuestas — {'todos' if len(resultado.propuestas) <= 20 else 'primeros 20'}",
        show_lines=False,
    )
    tabla.add_column("Causa", style="dim", width=12)
    tabla.add_column("Original", style="yellow")
    tabla.add_column("→", width=2)
    tabla.add_column("Nuevo", style="green")
    for p in resultado.propuestas[:20]:
        tabla.add_row(p.causa, p.nombre_original, "→", p.nombre_nuevo)
    console.print(tabla)
    if len(resultado.propuestas) > 20:
        console.print(f"[dim]  … y {len(resultado.propuestas) - 20} más (ver CSV completo)[/dim]")

    if not confirmar:
        _paso7._escribir_csv(resultado.propuestas, csv_ruta)
        console.print(f"\n[yellow][DRY-RUN][/yellow] CSV completo en [bold]{csv_ruta}[/bold]")
        console.print("  Agrega [bold]--confirmar[/bold] para aplicar los renombrados.")
        return

    console.print(f"\n[bold red]⚠  RENOMBRADO REAL[/bold red] — {resultado.total_cambios:,} archivos")
    if not click.confirm("¿Confirmas renombrar?"):
        return
    ejec = _paso7.ejecutar_renombrado(resultado, log_path, dry_run=False)
    console.print(f"\n[green]✓[/green] {len(ejec.renombrados):,} archivos renombrados")
    console.print(f"  Log de reversión: [bold]{log_path}[/bold]")
    if ejec.errores:
        console.print(f"[red]  {len(ejec.errores)} errores[/red]")


# ─── PASO 8 ───────────────────────────────────────────────────────────────────

@cli.command(name="paso8")
@click.argument("directorio", type=click.Path(exists=True, file_okay=False))
@click.option("--destino", default=None,
              help="Base destino. Por defecto: carpeta padre de DIRECTORIO.")
@click.option("--vault", default=None,
              help="Ruta del vault Obsidian para generar notas de semestres.")
@click.option("--log", default=None)
@click.option("--confirmar", is_flag=True, default=False)
def paso8(directorio, destino, vault, log, confirmar):
    """Paso 8 — Organiza datos escolares (semestres y materias).

    Detecta estructura Semestre N / Materia / archivos y los clasifica:

    \b
      código/prácticas  → 09_codigo/escolar/<sem>/<materia>/
      PDFs > 30 páginas → 04_libros/escolar/
      documentos        → 08_documentos/escolar/<sem>/<materia>/
      comprimidos       → _pendientes/checar/

    Si se provee --vault, genera notas Obsidian por semestre.

    \b
    Ejemplos:
      hdd-organizar paso8 /media/hdd/Universidad
      hdd-organizar paso8 /media/hdd/Universidad --vault ~/vault --confirmar
    """
    directorio_path = Path(directorio)
    destino_path = Path(destino) if destino else directorio_path.parent
    log_path = (
        Path(log) if log
        else Path("logs") / f"reversion_paso8_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    console.print("\n[bold]Paso 8 — Datos escolares[/bold]")
    console.print(f"  Directorio : {directorio_path}\n")

    with console.status("[cyan]Detectando estructura escolar…[/cyan]"):
        resultado = _paso8.detectar_estructura_escolar(directorio_path)

    if resultado.total == 0:
        console.print("[yellow]No se detectó estructura de semestres.[/yellow]")
        console.print("[dim]  Se esperan carpetas 'Semestre N' o 'SemN' en el directorio.[/dim]")
        return

    console.print(f"  Semestres  : [bold]{', '.join(resultado.semestres_detectados)}[/bold]")

    tabla = Table(title="Archivos por categoría", show_lines=False)
    tabla.add_column("Categoría", style="cyan")
    tabla.add_column("Archivos", justify="right")
    for cat, cnt in resultado.por_categoria().items():
        tabla.add_row(cat, f"{cnt:,}")
    console.print(tabla)
    console.print(f"\nTotal: [bold]{resultado.total:,}[/bold] · [yellow]{fmt_bytes(resultado.total_bytes)}[/yellow]")

    plan = _paso8.construir_plan(resultado, destino_path)

    if plan.omitidos_identicos:
        console.print(f"[dim]  {len(plan.omitidos_identicos)} ya organizados (idempotente)[/dim]")

    if not confirmar:
        console.print("\n[yellow][DRY-RUN][/yellow] Agrega [bold]--confirmar[/bold] para mover.")
        if vault:
            console.print(f"[dim]  (con --confirmar se generarán notas en {vault})[/dim]")
        return

    console.print(f"\n[bold red]⚠  MOVIMIENTO REAL[/bold red] — {len(plan):,} archivos")
    if not click.confirm("¿Confirmas organizar datos escolares?"):
        return

    ejec = _paso8.ejecutar_plan(plan, log_path, dry_run=False)
    console.print(f"\n[green]✓[/green] {len(ejec.movidos):,} archivos organizados")
    if ejec.omitidos_identicos:
        console.print(f"[dim]  {len(ejec.omitidos_identicos)} omitidos (ya existían)[/dim]")
    if ejec.errores:
        console.print(f"[red]  {len(ejec.errores)} errores[/red]")

    if vault:
        vault_path = Path(vault)
        notas = _obsidian.generar_notas_semestre(resultado, vault_path)
        console.print(f"\n[green]✓[/green] {len(notas)} notas Obsidian generadas:")
        for n in notas:
            console.print(f"  [dim]{n}[/dim]")


# ─── OBSIDIAN ─────────────────────────────────────────────────────────────────

@cli.command(name="obsidian-index")
@click.argument("hdd", type=click.Path(exists=True, file_okay=False))
@click.argument("vault", type=click.Path(file_okay=False))
@click.option("--musica", is_flag=True, default=False, help="Generar índice de música.")
@click.option("--libros", is_flag=True, default=False, help="Generar índice de libros.")
def obsidian_index(hdd, vault, musica, libros):
    """Genera índices Obsidian del HDD organizado.

    \b
    Siempre genera: Proyectos/HDD_Indice.md
    Opcional:       HDD_Musica.md, HDD_Libros.md

    \b
    Ejemplo:
      hdd-organizar obsidian-index /media/hdd ~/vault --musica --libros
    """
    hdd_path = Path(hdd)
    vault_path = Path(vault)

    console.print("\n[bold]Generando índices Obsidian[/bold]")

    nota = _obsidian.generar_indice_hdd(hdd_path, vault_path)
    console.print(f"[green]✓[/green] Índice general: [bold]{nota}[/bold]")

    if musica:
        nota_m = _obsidian.generar_indice_musica(hdd_path, vault_path)
        console.print(f"[green]✓[/green] Música: [bold]{nota_m}[/bold]")

    if libros:
        nota_l = _obsidian.generar_indice_libros(hdd_path, vault_path)
        console.print(f"[green]✓[/green] Libros: [bold]{nota_l}[/bold]")


@cli.command(name="mapa")
@click.argument("hdd", type=click.Path(exists=True, file_okay=False))
@click.argument("vault", type=click.Path(file_okay=False))
@click.option("--profundidad", default=2, show_default=True,
              help="Niveles a analizar: 1=solo primer nivel, 2=incluye subcarpetas.")
def mapa(hdd, vault, profundidad):
    """Genera HDD_Mapa.md con estructura completa y conteos por tipo de archivo.

    \b
    Para cada carpeta muestra cuántos archivos son: audio, video, imagen,
    documento (PDF/DOCX/EPUB…), programa, código, comprimido y otro.
    Con --profundidad 2 incluye la tabla de subcarpetas por cada carpeta raíz.

    \b
    Ejemplo:
      hdd-organizar mapa /media/caenhiro/MiHDD ~/vault
      hdd-organizar mapa /media/caenhiro/MiHDD ~/vault --profundidad 1
    """
    hdd_path = Path(hdd)
    vault_path = Path(vault)

    console.print("\n[bold]Analizando estructura del HDD[/bold]")
    console.print(f"  Fuente:     [cyan]{hdd_path}[/cyan]")
    console.print(f"  Vault:      [cyan]{vault_path}[/cyan]")
    console.print(f"  Profundidad: {profundidad}")
    console.print("")

    carpetas_raiz = sorted([d for d in hdd_path.iterdir() if d.is_dir()])
    procesadas = 0

    with console.status("[bold green]Escaneando…[/bold green]") as status:
        def _progreso(nombre: str) -> None:
            nonlocal procesadas
            procesadas += 1
            status.update(f"[bold green]Escaneando[/bold green] ({procesadas}/{len(carpetas_raiz)}) [cyan]{nombre}[/cyan]")

        nota = _obsidian.generar_mapa_hdd(hdd_path, vault_path, profundidad, _progreso)

    console.print(f"[green]✓[/green] Mapa generado: [bold]{nota}[/bold]")
    console.print(f"  {len(carpetas_raiz)} carpetas de primer nivel analizadas.")


@cli.command("mapa-gvfs")
@click.argument("ruta", type=click.Path(exists=True))
@click.option("--salida", default=None,
              help="Carpeta donde guardar el reporte .md. Por defecto: directorio de trabajo actual.")
@click.option("--profundidad", default=4, show_default=True,
              help="Niveles a escanear en profundidad.")
def mapa_gvfs(ruta: str, salida: str | None, profundidad: int) -> None:
    """Escanea un directorio GVFS (Google Drive montado) sin leer contenido de archivos.

    \b
    Usa solo stat() — rápido incluso sobre red. Clasifica por:
      - symlink                → google_doc (Google Docs/Sheets/Slides no descargables)
      - archivo > 50 MB        → probable_video
      - archivo 5 MB – 50 MB   → probable_video_o_imagen_grande
      - archivo 100 KB – 5 MB  → probable_imagen_o_documento
      - archivo < 100 KB       → probable_documento

    \b
    Genera un reporte Markdown con resumen, distribución y detalle de archivos.

    \b
    Ejemplos:
      hdd-organizar mapa-gvfs /run/user/1000/gvfs/google-drive:host=gmail.com,user=x/0AD...
      hdd-organizar mapa-gvfs /run/user/1000/gvfs/google-drive:host=gmail.com,user=x/GVfsSharedWithMe --salida ~/analisis/
    """
    ruta_path = Path(ruta)
    salida_path = Path(salida) if salida else Path.cwd()
    salida_path.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold]Escaneando directorio GVFS[/bold]")
    console.print(f"  Ruta:       [cyan]{ruta_path}[/cyan]")
    console.print(f"  Profundidad: {profundidad}")
    console.print("")

    with console.status("[bold green]Escaneando (stat only)…[/bold green]"):
        entradas = _gvfs.escanear_gvfs(ruta_path, profundidad)

    resumen = _gvfs.resumir(entradas)

    # Tabla resumen en consola
    tabla = Table(title="Resumen GVFS", show_header=True, header_style="bold")
    tabla.add_column("Categoría")
    tabla.add_column("Archivos", justify="right")
    tabla.add_column("Tamaño", justify="right")

    orden_cats = [
        _gvfs.CATEGORIA_GOOGLE_DOC,
        _gvfs.CATEGORIA_PROBABLE_VIDEO,
        _gvfs.CATEGORIA_PROBABLE_VIDEO_IMAGEN,
        _gvfs.CATEGORIA_PROBABLE_IMAGEN_DOC,
        _gvfs.CATEGORIA_PROBABLE_DOCUMENTO,
    ]
    for cat in orden_cats:
        cnt = resumen.por_categoria.get(cat, 0)
        if cnt == 0:
            continue
        sz = _gvfs._bytes_legible(resumen.tamanio_por_categoria.get(cat, 0))
        color = "red" if cat == _gvfs.CATEGORIA_GOOGLE_DOC else "green"
        tabla.add_row(f"[{color}]{cat}[/{color}]", str(cnt), sz)

    console.print(tabla)
    console.print(f"\n  Total: {resumen.total_entradas:,} entradas · {resumen.archivos_regulares:,} archivos · "
                  f"[red]{resumen.google_docs}[/red] Google Docs · {resumen.tamanio_legible}")

    if resumen.google_docs > 0:
        console.print(f"\n  [yellow]⚠[/yellow]  {resumen.google_docs} archivos nativos de Google no son descargables vía GVFS.")
        console.print(f"     Usar Google Takeout → paso5 para incluirlos en el HDD organizado.")

    # Guardar reporte Markdown
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    nombre_archivo = f"mapa_gvfs_{ruta_path.name}_{timestamp}.md"
    ruta_reporte = salida_path / nombre_archivo

    contenido = _gvfs.generar_reporte_md(ruta_path.name, entradas, ruta_path)
    ruta_reporte.write_text(contenido, encoding="utf-8")

    console.print(f"\n[green]✓[/green] Reporte guardado: [bold]{ruta_reporte}[/bold]")


@cli.command("mapa-local")
@click.argument("ruta", type=click.Path(exists=True))
@click.option("--salida", default=None,
              help="Carpeta donde guardar el reporte .md. Por defecto: directorio de trabajo actual.")
@click.option("--profundidad", default=6, show_default=True,
              help="Niveles a escanear en profundidad.")
def mapa_local(ruta: str, salida: str | None, profundidad: int) -> None:
    """Escanea un directorio local (export de Drive, pendientes) con clasificación por extensión.

    \b
    A diferencia de mapa-gvfs, usa la extensión real del archivo para clasificar:
      - .pdf .docx .doc .html .txt .odt  → documento
      - .xlsx .xls .csv .ods             → hoja_de_calculo
      - .pptx .ppt .odp                  → presentacion
      - .jpg .jpeg .png .gif .webp .raw  → imagen
      - .mp4 .avi .mkv .mov .wmv         → video
      - .mp3 .flac .wav .m4a .aac        → musica
      - Sin extensión reconocida         → heurística de tamaño

    \b
    Detecta archivos duplicados de Drive (patrón: nombre (N).ext).
    Genera tabla "Por carpeta (nivel 1)" para entender la estructura.

    \b
    Ejemplos:
      hdd-organizar mapa-local ~/Downloads/drive
      hdd-organizar mapa-local ~/Downloads/drive --salida ~/analisis/
    """
    ruta_path = Path(ruta)
    salida_path = Path(salida) if salida else Path.cwd()
    salida_path.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold]Escaneando directorio local[/bold]")
    console.print(f"  Ruta:        [cyan]{ruta_path}[/cyan]")
    console.print(f"  Profundidad:  {profundidad}")
    console.print("")

    with console.status("[bold green]Escaneando…[/bold green]"):
        entradas = _gvfs.escanear_gvfs(ruta_path, profundidad)

    resumen = _gvfs.resumir(entradas)

    # Tabla resumen en consola
    tabla = Table(title="Resumen Local", show_header=True, header_style="bold")
    tabla.add_column("Categoría")
    tabla.add_column("Archivos", justify="right")
    tabla.add_column("Tamaño", justify="right")

    cats_local = [
        _gvfs.CATEGORIA_DOCUMENTO,
        _gvfs.CATEGORIA_HOJA_CALCULO,
        _gvfs.CATEGORIA_PRESENTACION,
        _gvfs.CATEGORIA_IMAGEN,
        _gvfs.CATEGORIA_VIDEO,
        _gvfs.CATEGORIA_MUSICA,
        _gvfs.CATEGORIA_CODIGO,
        _gvfs.CATEGORIA_PROBABLE_VIDEO,
        _gvfs.CATEGORIA_PROBABLE_VIDEO_IMAGEN,
        _gvfs.CATEGORIA_PROBABLE_IMAGEN_DOC,
        _gvfs.CATEGORIA_PROBABLE_DOCUMENTO,
    ]
    for cat in cats_local:
        cnt = resumen.por_categoria.get(cat, 0)
        if cnt == 0:
            continue
        sz = _gvfs._bytes_legible(resumen.tamanio_por_categoria.get(cat, 0))
        tabla.add_row(cat, str(cnt), sz)

    console.print(tabla)
    console.print(
        f"\n  Total: {resumen.total_entradas:,} entradas · "
        f"{resumen.archivos_regulares:,} archivos · "
        f"{resumen.carpetas:,} carpetas · "
        f"[yellow]{resumen.duplicados_drive}[/yellow] duplicados Drive · "
        f"{resumen.tamanio_legible}"
    )

    if resumen.duplicados_drive > 0:
        console.print(
            f"\n  [yellow]⚠[/yellow]  {resumen.duplicados_drive} archivos con patrón `nombre (N).ext` "
            f"— posibles duplicados de Drive."
        )

    # Guardar reporte Markdown
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    nombre_archivo = f"mapa_local_{ruta_path.name}_{timestamp}.md"
    ruta_reporte = salida_path / nombre_archivo

    contenido = _gvfs.generar_reporte_md(ruta_path.name, entradas, ruta_path, is_local=True)
    ruta_reporte.write_text(contenido, encoding="utf-8")

    console.print(f"\n[green]✓[/green] Reporte guardado: [bold]{ruta_reporte}[/bold]")


@cli.command("generar-readme")
@click.argument("hdd_organizado")
@click.option("--sin-stats", is_flag=True, default=False, help="No contar archivos actuales (más rápido).")
@click.option("--solo-raiz", is_flag=True, default=False, help="Generar solo el _README.md raíz, no los de subcarpetas.")
def generar_readme(hdd_organizado: str, sin_stats: bool, solo_raiz: bool) -> None:
    """
    Genera _README.md en HDD_ORGANIZADO/ y en cada subcarpeta conocida.

    Cada README explica qué va en esa carpeta, las reglas del organizador,
    subcarpetas esperadas, extensiones y estadísticas actuales de archivos.

    \b
    Ejemplos:
      hdd-organizar generar-readme /media/caenhiro/MiHDD/HDD_organizado
      hdd-organizar generar-readme /media/caenhiro/MiHDD/HDD_organizado --sin-stats
      hdd-organizar generar-readme /media/caenhiro/MiHDD/HDD_organizado --solo-raiz
    """
    ruta = Path(hdd_organizado)
    con_stats = not sin_stats

    if not ruta.exists():
        console.print(f"[yellow]⚠[/yellow]  La ruta no existe. Se creará la estructura de carpetas.")

    console.print(f"\n[bold]Generando READMEs[/bold] en [cyan]{ruta}[/cyan]")
    if con_stats:
        console.print("  Contando archivos actuales (usa --sin-stats para omitir)…")

    with console.status("[bold green]Generando…[/bold green]"):
        if solo_raiz:
            archivos = [_readme.generar_readme_raiz(ruta, con_stats)]
        else:
            archivos = _readme.generar_todos(ruta, con_stats)

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Archivo generado", style="cyan")
    for arch in archivos:
        table.add_row(str(arch))

    console.print(table)
    console.print(f"\n[green]✓[/green] {len(archivos)} README(s) generados.")


@cli.command(name="clasificar-fotos")
@click.argument("directorio", type=click.Path(exists=True, file_okay=False))
@click.option("--model", default="moondream", show_default=True,
              help="Modelo Ollama a usar. Opciones: moondream, llava, llava:7b")
@click.option("--output", "output_csv", default="clasificacion_fotos.csv",
              show_default=True, help="Ruta del CSV con resultados.")
@click.option("--mover", is_flag=True, default=False,
              help="Mover imágenes a subcarpetas por categoría (requiere --confirmar).")
@click.option("--confirmar", is_flag=True, default=False)
@click.option("--max-mb", default=10.0, show_default=True,
              help="Omitir imágenes mayores a este tamaño en MB.")
def clasificar_fotos(directorio, model, output_csv, mover, confirmar, max_mb):
    """Clasifica imágenes con modelo de visión local (Ollama).

    \b
    Usa el modelo indicado (moondream por defecto) para categorizar
    imágenes en: wallpaper, arte, autos, memes, casa, personas,
    naturaleza, animales, screenshots, documentos, otro.

    Requiere Ollama corriendo: ollama serve
    Descargar modelo:          ollama pull moondream
    """
    import csv as _csv

    console.print("\n[bold]Clasificar fotos con Ollama[/bold]")

    # Verificar Ollama
    ok, msg = _ollama_fotos.verificar_ollama(model)
    if not ok:
        console.print(f"[red]✗[/red] {msg}")
        console.print(
            f"\nPara instalar Ollama en Mac: [cyan]brew install ollama[/cyan]\n"
            f"Para descargar el modelo:    [cyan]ollama pull {model}[/cyan]"
        )
        return
    console.print(f"[green]✓[/green] {msg}\n")

    dir_path = Path(directorio)
    imagenes = [
        p for p in sorted(dir_path.rglob("*"))
        if p.is_file() and p.suffix.lower() in _ollama_fotos._EXT_IMAGEN
    ]
    console.print(f"  Imágenes encontradas: [bold]{len(imagenes):,}[/bold]")

    if len(imagenes) == 0:
        console.print("[yellow]Sin imágenes en el directorio.[/yellow]")
        return

    # Clasificar con barra de progreso
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    resultados: list[_ollama_fotos.ResultadoClasificacion] = []

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), console=console,
    ) as progress:
        task = progress.add_task(f"Clasificando con {model}…", total=len(imagenes))
        for ruta in imagenes:
            res = _ollama_fotos.clasificar_foto_ollama(ruta, model=model, timeout=int(max_mb * 3 + 15))
            resultados.append(res)
            progress.advance(task)

    # Estadísticas
    from collections import Counter
    conteo = Counter(r.categoria for r in resultados)
    errores = [r for r in resultados if not r.ok]

    tabla = Table(title="Distribución por categoría", show_lines=False)
    tabla.add_column("Categoría", style="cyan")
    tabla.add_column("Imágenes", justify="right", style="bold")
    tabla.add_column("% del total", justify="right", style="dim")
    for cat, n in sorted(conteo.items(), key=lambda x: -x[1]):
        tabla.add_row(cat, str(n), f"{n / len(resultados) * 100:.1f}%")
    console.print(tabla)

    if errores:
        console.print(f"[yellow]  {len(errores)} errores (ver CSV)[/yellow]")

    # Guardar CSV
    csv_path = Path(output_csv)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = _csv.writer(f)
        writer.writerow(["ruta", "categoria", "error"])
        for r in resultados:
            writer.writerow([str(r.ruta), r.categoria, r.error or ""])
    console.print(f"\n[cyan]CSV guardado:[/cyan] [bold]{csv_path}[/bold]")

    if not mover:
        console.print("\n  Agrega [bold]--mover --confirmar[/bold] para mover a subcarpetas.")
        return

    if not confirmar:
        console.print("\n[yellow][DRY-RUN][/yellow] Agrega [bold]--confirmar[/bold] para mover archivos.")
        return

    # Mover a subcarpetas
    movidos = 0
    for r in resultados:
        if not r.ok:
            continue
        destino_dir = dir_path / r.categoria
        destino_dir.mkdir(exist_ok=True)
        destino = destino_dir / r.ruta.name
        if not destino.exists():
            r.ruta.rename(destino)
            movidos += 1
    console.print(f"\n[green]✓[/green] {movidos:,} imágenes movidas a subcarpetas.")


# ─── PASO 7-EXIF ─────────────────────────────────────────────────────────────

@cli.command(name="paso7-exif")
@click.argument("directorio", type=click.Path(exists=True, file_okay=False))
@click.option("--csv", "csv_path", default=None,
              help="Ruta del reporte CSV. Por defecto: reporte_paso7_exif.csv")
@click.option("--log", default=None)
@click.option("--confirmar", is_flag=True, default=False,
              help="Aplicar renombrado real (sin este flag es dry-run).")
def paso7_exif(directorio, csv_path, log, confirmar):
    """Renombra fotos sin fecha usando metadatos EXIF (DateTimeOriginal).

    Sólo afecta imágenes (.jpg .jpeg .png .heic .tiff .raw .cr2 .nef .dng).
    Sólo renombra las que NO tengan ya un prefijo YYYY-MM-DD.

    \b
    Resultado: foto_sin_nombre.jpg → 2024-03-15_143022_foto_sin_nombre.jpg
    Requiere: pip install Pillow  (incluido en extras [metadata])
    """
    import csv as _csv
    dir_path = Path(directorio)
    csv_ruta = Path(csv_path) if csv_path else Path("reporte_paso7_exif.csv")
    log_path = (
        Path(log) if log
        else Path("logs") / f"reversion_paso7_exif_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    console.print("\n[bold]Paso 7-EXIF — Renombrar fotos por fecha EXIF[/bold]")
    with console.status("[cyan]Leyendo metadatos EXIF…[/cyan]"):
        resultado = _paso7.generar_reporte_exif(dir_path, ruta_csv=csv_ruta if not confirmar else None)

    console.print(f"  Fotos analizadas:      [bold]{resultado._total:,}[/bold]")
    console.print(f"  Ya con fecha:          [dim]{resultado.ya_con_fecha:,}[/dim]")
    console.print(f"  Sin EXIF:              [dim]{resultado.sin_exif:,}[/dim]")
    console.print(f"  Con cambios:           [bold]{resultado.total_cambios:,}[/bold]")

    if resultado.total_cambios == 0:
        console.print("[green]  Sin cambios necesarios.[/green]")
        return

    tabla = Table(title=f"Preview — primeros {min(20, resultado.total_cambios)}")
    tabla.add_column("Fecha EXIF", style="cyan", width=18)
    tabla.add_column("Original", style="yellow")
    tabla.add_column("→", width=2)
    tabla.add_column("Nuevo", style="green")
    for p in resultado.propuestas[:20]:
        tabla.add_row(p.fecha_exif, p.nombre_original, "→", p.nombre_nuevo)
    console.print(tabla)
    if resultado.total_cambios > 20:
        console.print(f"[dim]  … y {resultado.total_cambios - 20} más[/dim]")

    if not confirmar:
        console.print(f"\n[yellow][DRY-RUN][/yellow] CSV en [bold]{csv_ruta}[/bold]")
        console.print("  Agrega [bold]--confirmar[/bold] para aplicar.")
        return

    console.print(f"\n[bold red]⚠  RENOMBRADO REAL[/bold red] — {resultado.total_cambios:,} fotos")
    if not click.confirm("¿Confirmas renombrar?"):
        return
    ejec = _paso7.ejecutar_renombrado_exif(resultado, log_path, dry_run=False)
    console.print(f"\n[green]✓[/green] {len(ejec.renombrados):,} fotos renombradas")
    console.print(f"  Log de reversión: [bold]{log_path}[/bold]")
    if ejec.errores:
        console.print(f"[red]  {len(ejec.errores)} errores[/red]")


# ─── CLIP ─────────────────────────────────────────────────────────────────────

@cli.command(name="clasificar-clip")
@click.argument("directorio", type=click.Path(exists=True, file_okay=False))
@click.option("--destino", default=None,
              help="Carpeta destino para subcategorías (por defecto: mismo directorio).")
@click.option("--modelo", default="ViT-B/32",
              help="Modelo CLIP (ViT-B/32, ViT-L/14). Default: ViT-B/32")
@click.option("--umbral", default=0.0, type=float,
              help="Confianza mínima 0.0-1.0 para asignar categoría (0=sin umbral).")
@click.option("--mover", is_flag=True, default=False)
@click.option("--confirmar", is_flag=True, default=False)
@click.option("--csv", "csv_path", default="reporte_clip.csv")
def clasificar_clip(directorio, destino, modelo, umbral, mover, confirmar, csv_path):
    """Clasifica imágenes en categorías semánticas usando CLIP (OpenAI).

    Categorías: wallpaper, arte_digital, autos, memes, casa_hogar,
    personas, naturaleza_plantas, animales_reptiles, tecnologia, comida, otro.

    \b
    Requisitos (pesados):
      pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
      pip install git+https://github.com/openai/CLIP.git

    \b
    Ejemplos:
      hdd-organizar clasificar-clip /fotos/sin_clasificar --csv reporte.csv
      hdd-organizar clasificar-clip /fotos/sin_clasificar --mover --confirmar
    """
    if not _CLIP_DISPONIBLE:
        console.print("[red]ERROR: clasificador_clip no disponible.[/red]")
        console.print("  Instala: pip install torch torchvision && "
                      "pip install git+https://github.com/openai/CLIP.git")
        return

    import csv as _csv

    try:
        console.print(f"\n[bold]CLIP[/bold] — cargando modelo {modelo}…")
        clf = _clip.ClasificadorCLIP(modelo=modelo)
    except ImportError as e:
        console.print(f"[red]ERROR: {e}[/red]")
        return

    dir_path  = Path(directorio)
    dest_path = Path(destino) if destino else dir_path
    dry_run   = not (mover and confirmar)

    resultado = clf.clasificar_directorio(
        directorio=dir_path,
        destino=dest_path,
        mover=mover,
        dry_run=dry_run,
        umbral=umbral,
    )

    # Stats por categoría
    cat_count: dict[str, int] = {}
    for c in resultado.clasificados:
        cat_count[c["categoria"]] = cat_count.get(c["categoria"], 0) + 1

    tabla = Table(title=f"Resumen CLIP — {resultado.total} imágenes")
    tabla.add_column("Categoría", style="cyan")
    tabla.add_column("Cantidad", justify="right")
    tabla.add_column("Estado", style="dim")
    for cat, n in sorted(cat_count.items(), key=lambda x: -x[1]):
        movidos = sum(1 for c in resultado.clasificados if c["categoria"] == cat and c.get("movido"))
        estado = f"{movidos} movidas" if movidos else ("pendiente" if mover else "solo clasificado")
        tabla.add_row(cat, str(n), estado)
    console.print(tabla)

    # Guardar CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = _csv.writer(f)
        writer.writerow(["nombre", "categoria", "confianza", "movido", "destino"])
        for c in resultado.clasificados:
            writer.writerow([c["nombre"], c["categoria"], c["confianza"],
                             c.get("movido", False), c["destino"]])
    console.print(f"\n[cyan]CSV:[/cyan] [bold]{csv_path}[/bold]")

    if dry_run and mover:
        console.print("\n[yellow][DRY-RUN][/yellow] Agrega [bold]--confirmar[/bold] para mover.")
    elif not mover:
        console.print("\n  Agrega [bold]--mover --confirmar[/bold] para mover a subcarpetas.")
    if resultado.errores:
        console.print(f"[red]  {len(resultado.errores)} errores al mover[/red]")


if __name__ == "__main__":
    cli()
