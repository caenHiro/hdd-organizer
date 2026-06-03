"""
Generador de notas Obsidian para el HDD organizado.

Genera:
  - Índice general del HDD: Proyectos/HDD_Indice.md
  - Mapa detallado:         Proyectos/HDD_Mapa.md  (conteos por tipo por carpeta)
  - Notas por semestre:     Conocimiento/Universidad/Semestres/SemN.md
  - Índices por categoría:  Proyectos/HDD_Musica.md, HDD_Libros.md, etc.
"""
import os
from collections.abc import Callable
from datetime import date
from pathlib import Path

# ─── Clasificación de archivos por tipo ──────────────────────────────────────

_CATS: dict[str, frozenset[str]] = {
    "audio":      frozenset({".mp3",".flac",".wav",".m4a",".ogg",".aac",".wma",".opus",".ape",".alac"}),
    "video":      frozenset({".mp4",".mkv",".avi",".mov",".wmv",".flv",".webm",".m4v",".ts",".vob",".mpg",".mpeg",".3gp"}),
    "imagen":     frozenset({".jpg",".jpeg",".png",".gif",".bmp",".tiff",".tif",".heic",".raw",".cr2",".nef",".arw",".webp",".svg"}),
    "documento":  frozenset({".pdf",".doc",".docx",".xls",".xlsx",".ppt",".pptx",".txt",".odt",".ods",".odp",".rtf",".csv",".epub",".mobi"}),
    "programa":   frozenset({".exe",".msi",".dmg",".deb",".rpm",".appimage",".apk",".jar",".iso",".img"}),
    "codigo":     frozenset({".py",".java",".js",".ts",".c",".cpp",".h",".cs",".php",".sql",".sh",".rb",".go",".rs",".kt",".swift"}),
    "comprimido": frozenset({".zip",".rar",".7z",".tar",".gz",".bz2",".xz",".zst",".cab"}),
}
def _cat(ext: str) -> str:
    e = ext.lower()
    for nombre, exts in _CATS.items():
        if e in exts:
            return nombre
    return "otro"


def _stats_dir(path: Path) -> dict[str, int]:
    """Cuenta archivos por categoría de forma recursiva usando os.walk."""
    counts: dict[str, int] = {}
    for _, _, filenames in os.walk(path):
        for fname in filenames:
            c = _cat(Path(fname).suffix)
            counts[c] = counts.get(c, 0) + 1
    return counts


def _tipos_ordenados(stats: dict[str, int]) -> list[tuple[str, int]]:
    """Devuelve tipos con count > 0, ordenados de mayor a menor."""
    return [(k, v) for k, v in sorted(stats.items(), key=lambda x: -x[1]) if v > 0]


# ─── Árbol de texto del HDD ───────────────────────────────────────────────────

def _arbol_texto(
    nombre_raiz: str,
    datos: list[tuple[str, dict[str, int], list[tuple[str, dict[str, int]]]]],
) -> list[str]:
    """Genera las líneas del árbol de carpetas con conteos por tipo.

    Formato:
        HDD/
        ├── 01_musica/  (8,432)
        │   - audio:    8,210
        │   - imagen:     180
        │   ├── Rock/  (2,100)
        │   │   - audio: 2,090
        │   └── Pop/   (1,850)
        │       - audio: 1,840
        │
        └── 02_videos/  (3,200)
            - video:    3,180
    """
    lineas: list[str] = [f"{nombre_raiz}/"]

    for i, (nombre1, stats1, subs) in enumerate(datos):
        ultimo1 = (i == len(datos) - 1)
        total1 = sum(stats1.values())

        c1 = "└── " if ultimo1 else "├── "
        p1 = "    " if ultimo1 else "│   "

        lineas.append(f"{c1}{nombre1}/  ({total1:,})")

        for tipo, count in _tipos_ordenados(stats1):
            lineas.append(f"{p1}- {tipo}: {count:,}")

        for j, (nombre2, stats2) in enumerate(subs):
            ultimo2 = (j == len(subs) - 1)
            total2 = sum(stats2.values())

            c2 = "└── " if ultimo2 else "├── "
            p2 = "    " if ultimo2 else "│   "

            lineas.append(f"{p1}{c2}{nombre2}/  ({total2:,})")

            for tipo, count in _tipos_ordenados(stats2):
                lineas.append(f"{p1}{p2}- {tipo}: {count:,}")

        if not ultimo1:
            lineas.append("│")

    return lineas


# ─── Mapa detallado del HDD ───────────────────────────────────────────────────

def generar_mapa_hdd(
    hdd: Path,
    vault: Path,
    profundidad: int = 2,
    progreso: Callable[[str], None] | None = None,
) -> Path:
    """Genera Proyectos/HDD_Mapa.md como árbol de carpetas con conteos por tipo.

    Ejemplo de salida (dentro de bloque de código en el .md):
        HDD/
        ├── 01_musica/  (8,432)
        │   - audio: 8,210
        │   ├── Rock/  (2,100)
        │   │   - audio: 2,090
        │   └── Pop/  (1,850)
        │       - audio: 1,840
        │
        └── 02_videos/  (3,200)
            - video: 3,180
    """
    ruta_nota = vault / "Proyectos" / "HDD_Mapa.md"
    ruta_nota.parent.mkdir(parents=True, exist_ok=True)

    dirs1 = sorted([d for d in hdd.iterdir() if d.is_dir()])

    datos: list[tuple[str, dict[str, int], list[tuple[str, dict[str, int]]]]] = []
    for d1 in dirs1:
        if progreso:
            progreso(d1.name)
        s1 = _stats_dir(d1)
        subs: list[tuple[str, dict[str, int]]] = []
        if profundidad >= 2:
            subs = [
                (d2.name, _stats_dir(d2))
                for d2 in sorted(d1.iterdir())
                if d2.is_dir()
            ]
        datos.append((d1.name, s1, subs))

    total_global = sum(sum(s.values()) for _, s, _ in datos)
    arbol = _arbol_texto(hdd.name, datos)

    lineas = [
        "---",
        "aliases: [HDD Mapa, Estructura HDD, Análisis HDD]",
        "tags: [hdd, archivos, mapa, analisis]",
        "---",
        "",
        "# HDD — Mapa de estructura",
        "",
        f"> Generado: {date.today()}  ",
        f"> Fuente: `{hdd}`  ",
        f"> Total: {total_global:,} archivos · {len(dirs1)} carpetas raíz",
        "",
        "---",
        "",
        "```",
        *arbol,
        "```",
        "",
        "---",
        "",
        "## Ver también",
        "",
        "- [[HDD_Indice]] — índice general",
        "- [[Sistema_Archivos_HDD]] — proyecto y metodología",
    ]

    ruta_nota.write_text("\n".join(lineas), encoding="utf-8")
    return ruta_nota


# ─── Índice general del HDD ──────────────────────────────────────────────────

def generar_indice_hdd(destino_hdd: Path, vault: Path) -> Path:
    """
    Genera o actualiza Proyectos/HDD_Indice.md con las carpetas de primer nivel
    del HDD organizado y sus conteos de archivos.
    """
    ruta_nota = vault / "Proyectos" / "HDD_Indice.md"
    ruta_nota.parent.mkdir(parents=True, exist_ok=True)

    carpetas = _contar_por_carpeta(destino_hdd)

    lineas = [
        "---",
        "aliases: [HDD Índice, Disco duro organizado]",
        "tags: [hdd, archivos, indice]",
        "---",
        "",
        "# HDD — Índice de archivos organizados",
        "",
        f"> Generado: {date.today()}  ",
        f"> Fuente: `{destino_hdd}`",
        "",
        "---",
        "",
        "## Estructura",
        "",
        "| Carpeta | Archivos |",
        "|---|---|",
    ]
    for carpeta, total in sorted(carpetas.items()):
        lineas.append(f"| `{carpeta}` | {total:,} |")

    lineas += [
        "",
        "---",
        "",
        "## Ver también",
        "",
        "- [[Sistema_Archivos_HDD]] — proyecto y metodología",
        "- [[_Indice_Universidad]] — libros escolares y relación por materia",
    ]

    ruta_nota.write_text("\n".join(lineas), encoding="utf-8")
    return ruta_nota


def _contar_por_carpeta(base: Path) -> dict[str, int]:
    conteo: dict[str, int] = {}
    if not base.exists():
        return conteo
    for carpeta in sorted(base.iterdir()):
        if not carpeta.is_dir():
            continue
        total = sum(1 for _ in carpeta.rglob("*") if Path(_).is_file())
        conteo[carpeta.name] = total
    return conteo


# ─── Notas por semestre ───────────────────────────────────────────────────────

def generar_notas_semestre(resultado_paso8, vault: Path) -> list[Path]:
    """
    Genera una nota Obsidian por semestre detectado en el paso 8.
    Ruta: Conocimiento/Universidad/Semestres/SemN.md
    """
    carpeta = vault / "Conocimiento" / "Universidad" / "Semestres"
    carpeta.mkdir(parents=True, exist_ok=True)

    notas_creadas: list[Path] = []
    por_semestre = resultado_paso8.por_semestre()

    for sem_id, archivos in por_semestre.items():
        ruta_nota = carpeta / f"{sem_id}.md"
        contenido = _nota_semestre(sem_id, archivos)
        ruta_nota.write_text(contenido, encoding="utf-8")
        notas_creadas.append(ruta_nota)

    _actualizar_indice_semestres(vault, list(por_semestre.keys()))
    return notas_creadas


def _nota_semestre(sem_id: str, archivos) -> str:
    num = int(sem_id.replace("Sem", ""))

    # Agrupar por materia
    por_materia: dict[str, dict[str, list]] = {}
    for a in archivos:
        mat = por_materia.setdefault(a.materia, {"codigo": [], "libro": [], "documento": [], "otro": []})
        mat[a.categoria if a.categoria in mat else "otro"].append(a.ruta.name)

    libros_todos = [a.ruta.name for a in archivos if a.categoria == "libro"]

    lineas = [
        "---",
        f"aliases: [Semestre {num}]",
        f"tags: [universidad, semestre, sem{num:02d}, cs, unam]",
        "---",
        "",
        f"# Semestre {num} — Ciencias de la Computación · UNAM FC",
        "",
        f"> Generado: {date.today()}  ",
        "> Ver también: [[_Indice_Universidad]] · [[HDD_Indice]]",
        "",
        "---",
        "",
        "## Materias",
        "",
        "| Materia | Prácticas/Código | Documentos | Libros |",
        "|---|---|---|---|",
    ]

    for mat, cats in sorted(por_materia.items()):
        if mat == "_general":
            continue
        n_cod = len(cats["codigo"])
        n_doc = len(cats["documento"])
        n_lib = len(cats["libro"])
        lineas.append(f"| {mat} | {n_cod} | {n_doc} | {n_lib} |")

    lineas += [
        "",
        "---",
        "",
        "## Libros en Calibre",
        "",
    ]

    if libros_todos:
        for libro in sorted(libros_todos):
            lineas.append(f"- `{libro}` → `04_libros/escolar/`")
    else:
        lineas.append("_(ninguno detectado en este semestre)_")

    lineas += [
        "",
        "---",
        "",
        "## Rutas en el HDD organizado",
        "",
        f"| Tipo | Ruta |",
        f"|---|---|",
        f"| Código/Prácticas | `09_codigo/escolar/{sem_id}/` |",
        f"| Documentos | `08_documentos/escolar/{sem_id}/` |",
        f"| Libros | `04_libros/escolar/` |",
    ]

    return "\n".join(lineas)


def _actualizar_indice_semestres(vault: Path, semestres: list[str]) -> None:
    """Actualiza _Indice_Universidad.md para incluir link a los semestres."""
    ruta = vault / "Conocimiento" / "Universidad" / "_Indice_Universidad.md"
    if not ruta.exists():
        return

    contenido = ruta.read_text(encoding="utf-8")
    bloque = "\n## Semestres documentados\n\n"
    for sem in sorted(semestres):
        num = int(sem.replace("Sem", ""))
        bloque += f"- [[{sem}|Semestre {num}]]\n"

    if "## Semestres documentados" in contenido:
        import re
        contenido = re.sub(
            r"## Semestres documentados\n.*?(?=\n##|\Z)",
            bloque.lstrip("\n"),
            contenido,
            flags=re.DOTALL,
        )
    else:
        contenido = contenido.rstrip() + "\n" + bloque

    ruta.write_text(contenido, encoding="utf-8")


# ─── Índices por categoría ────────────────────────────────────────────────────

def generar_indice_musica(hdd: Path, vault: Path) -> Path:
    return _indice_categoria(
        hdd / "03_musica",
        vault / "Proyectos" / "HDD_Musica.md",
        titulo="Música organizada",
        etiquetas="[hdd, musica, indice]",
        dos_niveles=True,  # artista/album
    )


def generar_indice_libros(hdd: Path, vault: Path) -> Path:
    return _indice_categoria(
        hdd / "04_libros",
        vault / "Proyectos" / "HDD_Libros.md",
        titulo="Libros organizados",
        etiquetas="[hdd, libros, indice, calibre]",
        dos_niveles=False,
    )


def _indice_categoria(
    carpeta: Path,
    ruta_nota: Path,
    titulo: str,
    etiquetas: str,
    dos_niveles: bool,
) -> Path:
    ruta_nota.parent.mkdir(parents=True, exist_ok=True)

    lineas = [
        "---",
        f"tags: {etiquetas}",
        "---",
        "",
        f"# {titulo}",
        "",
        f"> Generado: {date.today()}  ",
        f"> Fuente: `{carpeta}`",
        "",
        "---",
        "",
    ]

    if not carpeta.exists():
        lineas.append("_(carpeta no encontrada)_")
        ruta_nota.write_text("\n".join(lineas), encoding="utf-8")
        return ruta_nota

    if dos_niveles:
        for nivel1 in sorted(carpeta.iterdir()):
            if not nivel1.is_dir():
                continue
            lineas.append(f"## {nivel1.name}")
            lineas.append("")
            for nivel2 in sorted(nivel1.iterdir()):
                if nivel2.is_dir():
                    n = sum(1 for _ in nivel2.iterdir() if Path(_).is_file())
                    lineas.append(f"- **{nivel2.name}** — {n} archivos")
                else:
                    lineas.append(f"- {nivel2.name}")
            lineas.append("")
    else:
        for item in sorted(carpeta.rglob("*")):
            if item.is_file():
                rel = item.relative_to(carpeta)
                lineas.append(f"- `{rel}`")

    ruta_nota.write_text("\n".join(lineas), encoding="utf-8")
    return ruta_nota
