"""
Genera _README.md en cada carpeta raíz del HDD organizado.

Cada README explica:
  - Qué tipo de contenido va en esa carpeta
  - Subcarpetas y sus reglas de clasificación
  - Stats actuales de archivos
  - Cómo usar el organizador para agregar contenido
  - Criterios para decidir si algo encaja aquí

Uso:
    from organizador_hdd.readme_carpetas import generar_todos
    archivos = generar_todos(Path("/media/HDD/HDD_organizado"))
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import date
from pathlib import Path


# ─── Definición estática de cada carpeta ─────────────────────────────────────

_CARPETAS: dict[str, dict] = {
    "01_fotos": {
        "titulo": "Fotos Personales",
        "descripcion": (
            "Fotos de cámara, WhatsApp y dispositivos personales. "
            "Organizadas automáticamente por año y mes usando EXIF o fecha en el nombre."
        ),
        "pasos": "paso5, paso6",
        "subcarpetas": [
            ("YYYY/",             "Un directorio por año"),
            ("YYYY/MM_mes/",      "Un directorio por mes (ej. 05_mayo/)"),
        ],
        "reglas": [
            "Nombre con patrón cámara: VID_YYYYMMDD, GOPR_NNN, YYYYMMDD_HHMMSS",
            "WhatsApp: WA_, IMG-YYYYMMDD-",
            "EXIF DateTimeOriginal presente → fecha extraída del metadata",
            "Carpetas de origen: dcim/, camera/, whatsapp/, pictures/",
        ],
        "extensiones": ".jpg .jpeg .heic .png .raw .cr2 .dng .arw .nef (fotos) | .mp4 .mov (videos cámara)",
        "encaja_si": [
            "La foto la tomaste tú (cámara, celular, cámara de acción)",
            "Tiene fecha de toma visible en el nombre o en el EXIF",
            "Viene de WhatsApp, Snapchat u otra app de mensajes",
        ],
        "no_encaja_si": [
            "Es un wallpaper o imagen descargada de internet → va a 01b_imagenes/",
            "Es un video que no es tuyo (película, serie) → va a 02_videos/",
        ],
    },
    "01b_imagenes": {
        "titulo": "Imágenes y Recursos Gráficos",
        "descripcion": (
            "Imágenes que no son fotos personales: wallpapers, capturas de pantalla, "
            "recursos web, arte digital, memes, iconos."
        ),
        "pasos": "paso6",
        "subcarpetas": [
            ("paisajes/",      "Fondos y paisajes"),
            ("autos/",         "Fotografía de autos"),
            ("superheroes/",   "Arte de superhéroes y cómics"),
            ("arte/",          "Arte digital, ilustraciones"),
            ("memes/",         "Memes e imágenes de humor"),
            ("_sin_categoria/","Sin subcategoría identificada"),
        ],
        "reglas": [
            "Resolución exacta de pantalla (1920x1080, 2560x1440, 3840x2160) → wallpaper",
            "Nombre con Screenshot, Captura, screen_shot → captura pantalla",
            "Tamaño < 50KB y PNG → probablemente ícono o recurso web",
            "Carpetas llamadas: wallpapers/, downloads/, recursos/, assets/",
        ],
        "extensiones": ".jpg .jpeg .png .gif .bmp .webp .svg",
        "encaja_si": [
            "Es una imagen descargada de internet (no tuya)",
            "Es un wallpaper, fondo de pantalla o recurso gráfico",
            "Es una captura de pantalla",
        ],
        "no_encaja_si": [
            "La tomaste tú con cámara → va a 01_fotos/",
        ],
    },
    "02_videos": {
        "titulo": "Videos",
        "descripcion": (
            "Videos clasificados: series de TV, películas, videos personales, "
            "cursos en video, documentales, musicales y fitness."
        ),
        "pasos": "paso6",
        "subcarpetas": [
            ("series/<Nombre>/Temporada N/", "Series detectadas por SxxExx o 'Temporada N'"),
            ("peliculas/",                   "Películas por calidad: bluray, 1080p, x265, webrip"),
            ("personales/",                  "Videos propios: cámara, WhatsApp, GoPro"),
            ("cursos/",                      "Cursos en video: Udemy, Platzi, lección numerada"),
            ("documentales/",                "Documentales: BBC Earth, Nat Geo, Discovery"),
            ("musicales/",                   "Videoclips y videos musicales oficiales"),
            ("fitness/",                     "Yoga, CrossFit, Tapout, entrenamiento"),
            ("idiomas/",                     "BBC Learning, cursos de idioma en video"),
        ],
        "reglas": [
            "SxxExx o 'Temporada N' en nombre/carpeta → series/",
            "bluray, 1080p, 720p, x265, webrip, yts → peliculas/",
            "VID_, GOPR_, YYYYMMDD_HHMMSS → personales/ (misma lógica que 01_fotos)",
            "Lección numerada (01_, 02_, 'Lección') + carpeta de plataforma → cursos/",
            "'official video', 'music video', carpeta videoclips → musicales/",
            "yoga, tapout, workout, crossfit, fisicoculturismo → fitness/",
            "BBC Learning, 'learning language' → idiomas/",
        ],
        "extensiones": ".mp4 .mkv .avi .mov .wmv .flv .webm .m4v .ts .vob .rm .rmvb",
        "encaja_si": [
            "Es un video que quieres mantener a largo plazo",
            "Tiene nombre de serie con número de episodio",
            "Es una película completa",
            "Es un curso en video de alguna plataforma",
        ],
        "no_encaja_si": [
            "Es un video tuyo de cámara → va a 01_fotos/",
            "Es un video de un curso que ya está en 04_libros/cursos/ → no duplicar",
        ],
    },
    "03_musica": {
        "titulo": "Música",
        "descripcion": (
            "Biblioteca musical organizada por artista. "
            "Compatible con reproductores que leen tags ID3/Vorbis."
        ),
        "pasos": "paso5",
        "subcarpetas": [
            ("por_artista/<Artista>/",       "Un directorio por artista"),
            ("por_artista/<Artista>/<Álbum>/","Un directorio por álbum dentro del artista"),
        ],
        "reglas": [
            "Tag ID3 Artist presente → carpeta con nombre del artista",
            "Sin tag → nombre del archivo o carpeta padre como artista",
            "Paso 5 usa mutagen para leer tags antes de mover",
        ],
        "extensiones": ".mp3 .flac .wav .m4a .ogg .aac .wma .opus .ape .alac",
        "encaja_si": [
            "Es música que quieres conservar localmente",
            "Tiene tags ID3 con artista y álbum (o se pueden agregar)",
        ],
        "no_encaja_si": [
            "Es un audiolibro → va a 04_libros/audiolibros/",
            "Es un podcast → va a 04_libros/ o carpeta dedicada",
        ],
    },
    "04_libros": {
        "titulo": "Libros, Ebooks y Cursos Escritos",
        "descripcion": (
            "PDFs, ebooks, audiolibros y material escrito de cursos. "
            "PDFs > 30 páginas son considerados libros automáticamente."
        ),
        "pasos": "paso6",
        "subcarpetas": [
            ("cursos/",       "Material escrito de cursos: slides, notas, PDFs de lecciones"),
            ("audiolibros/",  "Audiolibros: .mp3/.m4b en ruta o nombre 'audiolibro/audiobook'"),
            ("idiomas/",      "Material de aprendizaje de idiomas"),
            ("tecnico/",      "Libros técnicos de programación, AWS, ingeniería"),
        ],
        "reglas": [
            "PDF con > 30 páginas → 04_libros/ (clasificado como 'libro')",
            ".mp3/.m4b en ruta 'audiolibros/audiobooks' → 04_libros/audiolibros/",
            "Carpeta con slides/PDFs de Udemy/Coursera → 04_libros/cursos/",
            "Keywords 'machine learning', 'aws certified', 'devops' en nombre → tecnico/",
        ],
        "extensiones": ".pdf .epub .mobi .azw3 .djvu .cbr .cbz (libros) | .mp3 .m4b (audiolibros)",
        "encaja_si": [
            "Es un libro o ebook (PDF, EPUB)",
            "Es material escrito de un curso (slides, notas)",
            "Es un audiolibro",
            "Es material de estudio de idiomas",
        ],
        "no_encaja_si": [
            "Es un documento personal (factura, contrato) → va a 08_documentos/",
            "Es código fuente de un curso → va a 09_codigo/",
        ],
    },
    "06_trabajo": {
        "titulo": "Trabajo",
        "descripcion": (
            "Proyectos y documentos laborales. "
            "Organizado con --contexto trabajo para separar carpetas por cliente/área."
        ),
        "pasos": "paso6 --contexto trabajo",
        "subcarpetas": [
            ("ine/",        "Proyectos INE/PREP"),
            ("accenture/",  "Proyectos Accenture/CLAN"),
            ("otros/",      "Otros clientes o empleadores"),
        ],
        "reglas": [
            "Detectado por ruta o nombre con keywords de trabajo: ine, deppp, mcad, tca",
            "Se requiere --contexto trabajo para activar estas reglas",
        ],
        "extensiones": "Todos los tipos de archivo",
        "encaja_si": [
            "Es un proyecto o entregable de trabajo",
            "Pertenece a un cliente o empleador específico",
        ],
        "no_encaja_si": [
            "Es código personal tuyo → va a 09_codigo/",
            "Es un recibo de nómina → va a 08_documentos/personales/nominas/",
        ],
    },
    "07_escuela": {
        "titulo": "Escuela y Universidad",
        "descripcion": (
            "Material académico organizado por semestre y materia. "
            "Paso 8 detecta la estructura Semestre N/Materia/ automáticamente."
        ),
        "pasos": "paso8",
        "subcarpetas": [
            ("carrera/Semestre N/<Materia>/", "Material por semestre y materia de la carrera"),
            ("prepa/",                        "Material de preparatoria"),
        ],
        "reglas": [
            "Carpeta con patrón 'Semestre N/' o 'Sem N/' → escuela/carrera/",
            "Dentro: código (.py, .java) → escuela/codigo/, documentos → escuela/docs/",
            "Paso 8 genera notas Obsidian por semestre automáticamente",
        ],
        "extensiones": "Todos los tipos de archivo",
        "encaja_si": [
            "Es material de la universidad o prepa (tareas, proyectos, apuntes)",
            "Tiene estructura Semestre/Materia reconocible",
        ],
        "no_encaja_si": [
            "Es un curso online pagado → va a 04_libros/cursos/ o 02_videos/cursos/",
        ],
    },
    "08_documentos": {
        "titulo": "Documentos Personales",
        "descripcion": (
            "Documentos personales clasificados: identificaciones, comprobantes, "
            "facturas, contratos, salud y trabajo."
        ),
        "pasos": "paso6",
        "subcarpetas": [
            ("personales/identificaciones/", "IDs, pasaporte, actas, FIEL SAT"),
            ("personales/comprobantes/",     "Comprobantes de pago, recibos"),
            ("personales/facturas/YYYY/",    "Facturas por año"),
            ("personales/contratos/",        "Contratos"),
            ("salud/recetas/",               "Recetas médicas"),
            ("salud/estudios/",              "Estudios y análisis médicos"),
            ("trabajo/nominas/YYYY/",        "Recibos de nómina por año"),
        ],
        "reglas": [
            "Ruta o nombre con FIEL, claveprivada → identificaciones/",
            "Pensionissste, pensión → comprobantes/ (no confundir con ISSSTE salud)",
            "SAT, CFDI, factura → facturas/YYYY/",
            "Receta, análisis, laboratorio → salud/",
            "Nómina, sueldo, payroll → trabajo/nominas/",
        ],
        "extensiones": ".pdf .doc .docx .jpg .png .xml (CFDI) .key .cer .req (FIEL)",
        "encaja_si": [
            "Es un documento legal, fiscal o de identidad",
            "Es un comprobante de pago o factura",
            "Es un documento médico",
            "Es un recibo de nómina",
        ],
        "no_encaja_si": [
            "Es material académico → va a 07_escuela/",
            "Es un libro o ebook → va a 04_libros/",
        ],
    },
    "09_codigo": {
        "titulo": "Proyectos de Código",
        "descripcion": (
            "Proyectos de programación completos detectados por archivos de build: "
            "package.json, pom.xml, .git, pyproject.toml, etc."
        ),
        "pasos": "paso6",
        "subcarpetas": [
            ("proyectos/personales/", "Proyectos propios: Python, web, scripts"),
            ("proyectos/java/",       "Proyectos Java/Maven/Gradle"),
            ("proyectos/web/",        "Proyectos web: React, Vue, Angular"),
        ],
        "reglas": [
            "Carpeta con package.json → web/",
            "Carpeta con pom.xml o build.gradle → java/",
            "Carpeta con pyproject.toml o setup.py → personales/",
            "Carpeta con .git como indicador de proyecto completo",
            "NUNCA mover archivo por archivo — se mueve la carpeta entera",
        ],
        "extensiones": ".py .js .ts .java .go .rs .kt .swift .php .rb (entre otros)",
        "encaja_si": [
            "Es un proyecto de programación completo (tiene su estructura de archivos)",
            "Tiene archivos de build, dependencias o .git",
        ],
        "no_encaja_si": [
            "Es un script suelto → puede ir en 08_documentos/ o 07_escuela/",
            "Es código de un curso → puede ir en 04_libros/cursos/ junto al material",
        ],
    },
    "10_software": {
        "titulo": "Software e Instaladores",
        "descripcion": "Instaladores y programas descargados, organizados por sistema operativo.",
        "pasos": "paso6",
        "subcarpetas": [
            ("windows/", "Instaladores .exe, .msi"),
            ("linux/",   "Instaladores .deb, .rpm, .AppImage, .sh"),
            ("mac/",     "Instaladores .dmg, .pkg"),
        ],
        "reglas": [
            ".exe, .msi → windows/",
            ".deb, .rpm, .AppImage → linux/",
            ".dmg, .pkg → mac/",
            ".iso, .img → se quedan en 10_software/ raíz",
        ],
        "extensiones": ".exe .msi .deb .rpm .appimage .dmg .pkg .apk .jar .iso .img",
        "encaja_si": [
            "Es un instalador de programa",
            "Es una imagen ISO de sistema operativo o software",
        ],
        "no_encaja_si": [
            "Es un juego → considera subcarpeta 10_software/juegos/",
        ],
    },
    "_pendientes": {
        "titulo": "Pendientes — Archivos sin Clasificar",
        "descripcion": (
            "Carpeta de trabajo del organizador. Los archivos llegan aquí cuando "
            "no pudieron ser clasificados automáticamente y requieren revisión manual."
        ),
        "pasos": "paso1, paso6, deduplicador",
        "subcarpetas": [
            ("artefactos/",      "Archivos técnicos sin valor: .class, .pyc, caches (paso1)"),
            ("sin_clasificar/",  "Archivos sin categoría conocida — revisar manualmente"),
            ("zips_revisar/",    "ZIPs que requieren descomprimir antes de clasificar"),
            ("subtitulos/",      "Archivos .vtt, .srt, .sub separados de sus videos"),
            ("duplicados/",      "Posibles duplicados detectados por el deduplicador"),
        ],
        "reglas": [
            "El organizador NUNCA borra — siempre mueve a _pendientes/ primero",
            "Revisar duplicados/ antes de borrar cualquier cosa",
            "Descomprimir zips_revisar/ y re-ejecutar el organizador",
        ],
        "extensiones": "Cualquier tipo de archivo",
        "encaja_si": [
            "El archivo necesita revisión manual antes de clasificar",
            "El organizador no pudo determinar la categoría",
        ],
        "no_encaja_si": [],
    },
}

_TIPOS_ARCHIVO: dict[str, frozenset[str]] = {
    "audio":      frozenset({".mp3",".flac",".wav",".m4a",".ogg",".aac",".wma",".opus",".m4b",".alac"}),
    "video":      frozenset({".mp4",".mkv",".avi",".mov",".wmv",".flv",".webm",".m4v",".ts",".vob",".mpg",".rm",".rmvb"}),
    "imagen":     frozenset({".jpg",".jpeg",".png",".gif",".bmp",".tiff",".heic",".raw",".cr2",".nef",".webp",".svg"}),
    "documento":  frozenset({".pdf",".doc",".docx",".xls",".xlsx",".ppt",".pptx",".txt",".epub",".mobi",".csv"}),
    "codigo":     frozenset({".py",".java",".js",".ts",".c",".cpp",".h",".cs",".php",".sql",".sh",".rb",".go",".rs"}),
    "comprimido": frozenset({".zip",".rar",".7z",".tar",".gz",".bz2"}),
}


def _cat_archivo(ext: str) -> str:
    e = ext.lower()
    for nombre, exts in _TIPOS_ARCHIVO.items():
        return nombre if e in exts else None  # type: ignore[return-value]
    return "otro"


def _stats_carpeta(path: Path) -> Counter:
    """Cuenta archivos por tipo de forma recursiva."""
    counts: Counter = Counter()
    if not path.exists():
        return counts
    for _, _, filenames in os.walk(path):
        for fname in filenames:
            ext = Path(fname).suffix.lower()
            cat = "otro"
            for nombre, exts in _TIPOS_ARCHIVO.items():
                if ext in exts:
                    cat = nombre
                    break
            counts[cat] += 1
    return counts


# ─── Generadores ─────────────────────────────────────────────────────────────

def generar_readme_carpeta(carpeta: Path, con_stats: bool = True) -> Path:
    """
    Genera <carpeta>/_README.md con descripción, reglas y stats de esa carpeta.

    Args:
        carpeta:    path de la carpeta destino (ej. HDD_organizado/02_videos)
        con_stats:  si True, incluye conteo de archivos actuales

    Returns:
        path del _README.md generado
    """
    nombre = carpeta.name
    info = _CARPETAS.get(nombre, {})

    titulo = info.get("titulo", nombre)
    descripcion = info.get("descripcion", "Carpeta del HDD organizado.")
    pasos = info.get("pasos", "hdd-organizar paso6")
    subcarpetas: list[tuple[str, str]] = info.get("subcarpetas", [])
    reglas: list[str] = info.get("reglas", [])
    extensiones: str = info.get("extensiones", "—")
    encaja_si: list[str] = info.get("encaja_si", [])
    no_encaja_si: list[str] = info.get("no_encaja_si", [])

    hoy = date.today().isoformat()
    stats = _stats_carpeta(carpeta) if con_stats else Counter()
    total = sum(stats.values())

    lineas: list[str] = [
        "---",
        f"tipo: hdd-readme",
        f"carpeta: {nombre}",
        f"actualizado: {hoy}",
        "---",
        "",
        f"# {nombre} — {titulo}",
        "",
        f"> {descripcion}",
        f"> Gestionado por: `{pasos}`",
        f"> Actualizar stats: `hdd-organizar generar-readme <ruta_raiz>`",
        "",
        "---",
        "",
    ]

    # Subcarpetas
    if subcarpetas:
        lineas += [
            "## Subcarpetas",
            "",
            "| Subcarpeta | Contenido |",
            "|---|---|",
        ]
        for sub, desc in subcarpetas:
            lineas.append(f"| `{sub}` | {desc} |")
        lineas.append("")

    # Reglas del organizador
    if reglas:
        lineas += ["## Reglas del organizador", ""]
        for i, regla in enumerate(reglas, 1):
            lineas.append(f"{i}. {regla}")
        lineas.append("")

    # Extensiones
    lineas += [
        "## Extensiones habituales",
        "",
        f"`{extensiones}`",
        "",
    ]

    # Stats actuales
    lineas += [
        "## Stats actuales",
        "",
        f"_Generado el {hoy} — {total:,} archivos totales_",
        "",
    ]
    if stats:
        lineas += ["| Tipo | Archivos |", "|---|---|"]
        for tipo, count in stats.most_common():
            lineas.append(f"| {tipo} | {count:,} |")
    else:
        lineas.append("_Carpeta vacía o no disponible al generar este archivo._")
    lineas.append("")

    # ¿Encaja aquí?
    if encaja_si or no_encaja_si:
        lineas += ["## ¿Este contenido va aquí?", ""]
        if encaja_si:
            lineas.append("**Sí encaja si:**")
            for item in encaja_si:
                lineas.append(f"- {item}")
            lineas.append("")
        if no_encaja_si:
            lineas.append("**No encaja si:**")
            for item in no_encaja_si:
                lineas.append(f"- {item}")
            lineas.append("")

    # Cómo agregar contenido
    lineas += [
        "## Agregar contenido nuevo",
        "",
        "```bash",
        "# Dry-run: ver qué haría el organizador (sin mover nada)",
        f"hdd-organizar {pasos.split(',')[0].strip()} /ruta/HDD_organizado --dry-run",
        "",
        "# Confirmar:",
        f"hdd-organizar {pasos.split(',')[0].strip()} /ruta/HDD_organizado --confirmar",
        "```",
        "",
    ]

    archivo = carpeta / "_README.md"
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo.write_text("\n".join(lineas), encoding="utf-8")
    return archivo


def generar_readme_raiz(hdd_organizado: Path, con_stats: bool = True) -> Path:
    """
    Genera HDD_organizado/_README.md con la vista general de toda la estructura.
    """
    hoy = date.today().isoformat()

    lineas: list[str] = [
        "---",
        "tipo: hdd-readme-raiz",
        f"actualizado: {hoy}",
        "---",
        "",
        "# HDD Organizado — Guía de Estructura",
        "",
        "> Este HDD fue organizado con `hdd-organizar`.",
        "> Cada carpeta tiene su propio `_README.md` con reglas detalladas.",
        "> Actualizar: `hdd-organizar generar-readme /ruta/HDD_organizado`",
        "",
        "---",
        "",
        "## Estructura de carpetas",
        "",
        "| Carpeta | Contenido | Pasos |",
        "|---|---|---|",
    ]

    for nombre, info in _CARPETAS.items():
        titulo = info.get("titulo", nombre)
        pasos = info.get("pasos", "paso6")
        stats = _stats_carpeta(hdd_organizado / nombre) if con_stats else Counter()
        total = sum(stats.values())
        total_str = f" ({total:,} archivos)" if total else ""
        lineas.append(f"| [`{nombre}/`](./{nombre}/_README.md) | {titulo}{total_str} | `{pasos}` |")

    lineas += [
        "",
        "---",
        "",
        "## Flujo de organización",
        "",
        "```",
        "paso1  → Eliminar artefactos técnicos (caches, .class, .DS_Store)",
        "paso2  → Mover proyectos de código detectados por package.json/pom.xml",
        "paso3  → Detectar duplicados exactos (SHA256)",
        "paso4  → Mover fotos con EXIF a 01_fotos/",
        "paso5  → Organizar música por artista/álbum (tags ID3)",
        "paso6  → Clasificar el resto: videos, documentos, libros, software",
        "paso7  → Deduplicador inteligente con scoring",
        "paso8  → Detectar material escolar (Semestre N/Materia/)",
        "```",
        "",
        "## Comandos de uso habitual",
        "",
        "```bash",
        "# Organizar completamente (recomendado: primero dry-run)",
        "hdd-organizar paso1 /ruta/HDD --dry-run",
        "hdd-organizar paso6 /ruta/HDD --dry-run",
        "",
        "# Ver qué hay en el HDD",
        "hdd-organizar mapa /ruta/HDD ~/vault",
        "",
        "# Regenerar estos READMEs con stats actualizadas",
        "hdd-organizar generar-readme /ruta/HDD",
        "```",
        "",
    ]

    archivo = hdd_organizado / "_README.md"
    hdd_organizado.mkdir(parents=True, exist_ok=True)
    archivo.write_text("\n".join(lineas), encoding="utf-8")
    return archivo


def generar_todos(hdd_organizado: Path, con_stats: bool = True) -> list[Path]:
    """
    Genera _README.md en el raíz + en cada subcarpeta conocida.

    Crea las carpetas si no existen (útil antes de mover archivos al HDD).

    Returns:
        lista de archivos _README.md creados/actualizados
    """
    archivos: list[Path] = [generar_readme_raiz(hdd_organizado, con_stats)]
    for nombre in _CARPETAS:
        carpeta = hdd_organizado / nombre
        archivos.append(generar_readme_carpeta(carpeta, con_stats))
    return archivos
