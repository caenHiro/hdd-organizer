"""
Paso 6 — Clasificar _pendientes/checar/.

Toma los archivos sin categoría y los enruta a su destino final según:
  1. Extensión del archivo
  2. Magic bytes (python-magic si está disponible)
  3. Tamaño como señal adicional

Destinos:
  imagen    → 01b_imagenes/_sin_categoria/
  video     → 02_videos/
  audio     → 03_musica/_sin_artista/
  documento → 08_documentos/
  comic     → 04_libros/comics/          (.cbr, .cbz)
  fitness   → 08_documentos/personal/salud/fitness/  (.tcx, .fit, .gpx)
  subtitulo → _pendientes/subtitulos/    (.srt, .vtt — pendientes de asociar a su video)
  codigo    → 09_codigo/_pendientes/
  proyecto  → 09_codigo/{lenguaje}/_trabajo|escuela|personales  (carpeta completa, unidad atómica)
  comprimido→ _pendientes/zips_revisar/  (requiere revisión manual)
  dañado    → _pendientes/dañados/{ruta_codificada}/
  otro/desconocido → _pendientes/sin_clasificar/

Contextos (--contexto):
  trabajo   → proyectos van a 09_codigo/{lenguaje}/_trabajo/
  escuela   → proyectos van a 07_escuela/_pendientes_clasificar/
  personal  → proyectos van a 09_codigo/proyectos/personales/
  (ninguno) → proyectos van a 09_codigo/_pendientes/
"""
import json
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .utils import resolver_colision, resolver_destino, contar_paginas_pdf, es_carpeta_privada
from .verificador import verificar_archivo, ruta_danado

_UMBRAL_LIBRO_PAGINAS = 30

try:
    import magic as _magic
    _MAGIC_DISPONIBLE = True
except ImportError:
    _MAGIC_DISPONIBLE = False

# Mapeo extensión → categoría
_EXT_A_CATEGORIA: dict[str, str] = {
    # Imágenes
    ".jpg": "imagen", ".jpeg": "imagen", ".png": "imagen", ".gif": "imagen",
    ".bmp": "imagen", ".tiff": "imagen", ".tif": "imagen", ".webp": "imagen",
    ".svg": "imagen", ".ico": "imagen", ".heic": "imagen", ".heif": "imagen",
    # Video
    ".mp4": "video", ".mkv": "video", ".avi": "video", ".mov": "video",
    ".wmv": "video", ".flv": "video", ".webm": "video", ".m4v": "video",
    ".mpg": "video", ".mpeg": "video", ".3gp": "video", ".ts": "video",
    ".rm": "video", ".rmvb": "video", ".vob": "video",    # RealMedia, DVD
    # Audio
    ".mp3": "audio", ".flac": "audio", ".m4a": "audio", ".aac": "audio",
    ".ogg": "audio", ".wav": "audio", ".wma": "audio", ".opus": "audio",
    ".ram": "audio", ".ra": "audio",                       # RealAudio
    # Documentos
    ".pdf": "documento", ".doc": "documento", ".docx": "documento",
    ".xls": "documento", ".xlsx": "documento", ".ppt": "documento",
    ".pptx": "documento", ".txt": "documento", ".rtf": "documento",
    ".odt": "documento", ".ods": "documento", ".odp": "documento",
    ".epub": "documento", ".mobi": "documento",
    ".htm": "documento", ".xhtml": "documento", ".opf": "documento",
    ".csv": "documento", ".tsv": "documento",
    ".mwb": "documento",                           # MySQL Workbench
    ".drawio": "documento", ".dia": "documento",   # Diagramas
    ".cer": "documento", ".pem": "documento",      # Certificados
    ".p12": "documento", ".pfx": "documento",      # Certificados PKCS
    ".key": "documento", ".req": "documento",      # FIEL SAT: clave privada y requerimiento
    ".db": "documento",                            # SQLite y otras bases de datos portables
    # Código
    ".py": "codigo", ".js": "codigo", ".ts": "codigo", ".java": "codigo",
    ".c": "codigo", ".cpp": "codigo", ".h": "codigo", ".cs": "codigo",
    ".go": "codigo", ".rs": "codigo", ".php": "codigo", ".rb": "codigo",
    ".sh": "codigo", ".bat": "codigo", ".ps1": "codigo", ".sql": "codigo",
    ".html": "codigo", ".css": "codigo", ".xml": "codigo", ".json": "codigo",
    ".yaml": "codigo", ".yml": "codigo", ".toml": "codigo", ".md": "codigo",
    ".pyi": "codigo", ".scss": "codigo", ".jsx": "codigo", ".tsx": "codigo",
    ".jsp": "codigo", ".hpp": "codigo", ".xsd": "codigo",
    ".tex": "codigo", ".sty": "codigo", ".bib": "codigo", # LaTeX
    ".jsonc": "codigo", ".jsonl": "codigo",                # JSON variantes
    ".ini": "codigo", ".cfg": "codigo", ".conf": "codigo", # Configuración
    # Comics — son libros de lectura, van a 04_libros/comics/
    ".cbr": "comic", ".cbz": "comic",
    # Fitness / GPS — datos de actividades físicas
    ".tcx": "fitness", ".fit": "fitness", ".gpx": "fitness",
    # Subtítulos — pendientes de asociar a su video
    ".srt": "subtitulo", ".vtt": "subtitulo",
    # Comprimidos (requieren revisión)
    ".zip": "comprimido", ".rar": "comprimido", ".7z": "comprimido",
    ".tar": "comprimido", ".gz": "comprimido", ".bz2": "comprimido",
    ".xz": "comprimido", ".iso": "comprimido",
}

_DESTINO_POR_CATEGORIA: dict[str, str] = {
    "imagen":     "01b_imagenes/_sin_categoria",
    "video":      "02_videos",
    "audio":      "03_musica/_sin_artista",
    "documento":  "08_documentos",
    "libro":      "04_libros",
    "comic":      "04_libros/comics",
    "fitness":    "08_documentos/personal/salud/fitness",
    "subtitulo":  "_pendientes/subtitulos",
    "codigo":     "09_codigo/_pendientes",
    "proyecto":   "09_codigo/_pendientes",  # fallback — normalmente se enruta por contexto en construir_plan
    "curso":      "04_libros/cursos",       # fallback — normalmente se sub-clasifica en construir_plan
    "audiolibro": "04_libros/audiolibros",
    "comprimido": "_pendientes/zips_revisar",
    "privado":    ".privado/varios",        # fallback — normalmente se sub-clasifica en construir_plan
    "dañado":     "_pendientes/dañados",    # ruta codificada generada por ruta_danado()
    "desconocido":"_pendientes/sin_clasificar",
}

# Indicadores de proyecto de programación — carpeta es unidad atómica si contiene alguno
_INDICADORES_PROYECTO: frozenset[str] = frozenset({
    "package.json", "pom.xml", "requirements.txt", "build.gradle",
    "Cargo.toml", "go.mod", "Makefile", "CMakeLists.txt", "Gemfile",
    "composer.json", "pyproject.toml", "setup.py", "setup.cfg", ".git",
})

_LENGUAJE_POR_INDICADOR: dict[str, str] = {
    "package.json": "nodejs", "pom.xml": "java", "build.gradle": "java",
    "requirements.txt": "python", "pyproject.toml": "python",
    "setup.py": "python", "setup.cfg": "python",
    "Cargo.toml": "rust", "go.mod": "go",
    "Gemfile": "ruby", "composer.json": "php", "CMakeLists.txt": "cpp",
}

# ─── Constantes para detección de cursos ─────────────────────────────────────

# Plataformas educativas que actúan como CONTENEDORES (folder = múltiples cursos)
_PLATAFORMAS_CONTENEDOR: frozenset[str] = frozenset({
    "udemy", "coursera", "platzi", "edureka", "pluralsight",
    "linkedin learning", "linkedin_learning", "onehack",
})

# Keywords genéricas — si aparecen en el nombre de la carpeta → es un curso
_CURSO_RUTA_ESPECIFICO: frozenset[str] = frozenset({
    "cursos", "curso", "courses", "course",
    "tutoriales", "tutorials", "aws training", "bbc learning",
})

# Keywords en el nombre de carpeta que indican contenido de audiolibro
_AUDIOLIBRO_RUTA_KEYS: frozenset[str] = frozenset({
    "audiolibros", "audiolibro", "audiobooks", "audiobook",
    "audio libros", "audio_libros",
})

# Patrón de lección numerada: "001 Intro.mp4", "32. Topic.mkv", "0308 AMI.mp4"
_RE_LECCION_CURSO = re.compile(r"^\d{1,4}[\s._-]")

# Extensiones de video — para decidir destino del curso (02_videos vs 04_libros)
_VIDEO_EXTS_CURSO: frozenset[str] = frozenset({
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".flv", ".wmv",
})

# Extensiones de descarga incompleta — archivos a reportar dentro de un curso
_EXTS_INCOMPLETAS: frozenset[str] = frozenset({
    ".tmp", ".partial", ".crdownload", ".download",
})

# Extensiones de código — usadas para detectar carpetas "bloque de código"
_EXT_BLOQUE_CODIGO: frozenset[str] = frozenset({
    ".py", ".java", ".js", ".ts", ".c", ".cpp", ".h", ".cs",
    ".go", ".rs", ".php", ".rb", ".sql", ".sh", ".bat", ".ps1",
    ".html", ".css", ".jsx", ".tsx", ".xml", ".json", ".yaml",
    ".yml", ".toml", ".md", ".txt", ".ini", ".cfg", ".conf",
    ".tex", ".scss", ".pyi", ".hpp", ".jsp", ".xsd",
    ".class", ".jar",
    ".jsonc", ".jsonl", ".bib", ".sty",
})

# Extensiones para sub-clasificar archivos privados dentro de .privado/
_EXT_PRIVADO_FOTO = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
    ".webp", ".heic", ".heif", ".svg",
})
_EXT_PRIVADO_VIDEO = frozenset({
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
    ".webm", ".m4v", ".mpg", ".mpeg", ".3gp", ".ts",
})
_EXT_PRIVADO_AUDIO = frozenset({
    ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav", ".wma", ".opus",
})


@dataclass
class ArchivoClasificado:
    ruta: Path
    categoria: str      # imagen | video | audio | documento | libro | comic | fitness | subtitulo | codigo | proyecto | curso | comprimido | privado | dañado | desconocido
    metodo: str         # "extension" | "magic" | "paginas_pdf" | "carpeta_privada" | "proyecto_programacion" | "verificador" | "defecto"
    tamanio: int
    es_privado: bool = False
    ruta_danado: Path | None = None
    error_integridad: str = ""
    contexto_tag: str | None = None  # "trabajo" | "escuela" | "personal" | None


@dataclass
class ResultadoPaso6:
    archivos: list[ArchivoClasificado] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.archivos)

    @property
    def total_bytes(self) -> int:
        return sum(a.tamanio for a in self.archivos)

    def por_categoria(self) -> dict[str, int]:
        conteo: dict[str, int] = {}
        for a in self.archivos:
            conteo[a.categoria] = conteo.get(a.categoria, 0) + 1
        return dict(sorted(conteo.items(), key=lambda x: -x[1]))


@dataclass
class PlanPaso6:
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


# ─── Proyectos de programación ───────────────────────────────────────────────

def es_proyecto_programacion(directorio: Path) -> bool:
    """True si el directorio contiene indicadores de proyecto (package.json, pom.xml, .git, etc.)."""
    try:
        entradas = {e.name for e in directorio.iterdir()}
    except OSError:
        return False
    return bool(entradas & _INDICADORES_PROYECTO)


def _detectar_lenguaje(directorio: Path) -> str:
    """Devuelve el lenguaje principal del proyecto según sus indicadores. 'varios' si no se puede determinar."""
    try:
        for entrada in directorio.iterdir():
            if entrada.name in _LENGUAJE_POR_INDICADOR:
                return _LENGUAJE_POR_INDICADOR[entrada.name]
    except OSError:
        pass
    return "varios"


def _es_carpeta_codigo_bloque(directorio: Path, umbral: float = 0.70) -> bool:
    """
    True si ≥70% de los archivos directos del directorio son código/texto.
    Detecta carpetas de prácticas/labs que deben moverse como unidad atómica
    aunque no tengan package.json, pom.xml ni otros marcadores de proyecto.
    """
    try:
        entradas = [
            e for e in directorio.iterdir()
            if e.is_file() and not e.name.startswith("._")
        ]
    except OSError:
        return False
    if len(entradas) < 2:
        return False
    n_codigo = sum(1 for f in entradas if f.suffix.lower() in _EXT_BLOQUE_CODIGO)
    return (n_codigo / len(entradas)) >= umbral


_EXCLUSIONES_CURSO = frozenset({
    "documentacion", "documentos", "documentation",
    "curriculum", "curriculo", "cv",
    "profesional", "profesionales",
    "personal", "privado",
    "expediente", "recursos humanos",
    "imss", "beneficiarios", "checklist",
})

def _es_carpeta_curso(directorio: Path) -> bool:
    """
    True si la carpeta parece un curso estructurado en lecciones.

    Señales (en orden):
    1. El padre inmediato es una plataforma conocida (udemy/, coursera/, …)
    2. El nombre propio contiene keyword de plataforma + texto adicional
       ("udemy_python_course" sí; "udemy" solo no — es contenedor, se recursará)
    3. El nombre contiene keyword genérica de curso ("cursos", "tutorials", …)
    4. ≥50 % de archivos directos tienen numeración de lección (001_, 32., 0308_)
       — solo si el nombre NO contiene keywords de carpeta de documentos personales
    """
    nombre = directorio.name.lower()
    padre_nombre = directorio.parent.name.lower()

    # Señal 1: padre es plataforma → esta carpeta es un curso concreto dentro de ella
    if any(k in padre_nombre for k in _PLATAFORMAS_CONTENEDOR):
        return True

    # Señal 2: nombre incluye plataforma pero tiene texto adicional
    for k in _PLATAFORMAS_CONTENEDOR:
        if k in nombre and len(nombre) > len(k) + 1:
            return True

    # Señal 3: keyword genérica de curso en el nombre de la carpeta
    if any(k in nombre for k in _CURSO_RUTA_ESPECIFICO):
        return True

    # Exclusión: carpetas de documentos personales/trabajo nunca son cursos
    if any(exc in nombre for exc in _EXCLUSIONES_CURSO):
        return False

    # Señal 4: mayoría de archivos directos son lecciones numeradas
    try:
        archivos = [
            f for f in directorio.iterdir()
            if f.is_file() and not f.name.startswith("._")
        ]
    except OSError:
        return False
    if len(archivos) < 3:
        return False
    n_leccion = sum(1 for f in archivos if _RE_LECCION_CURSO.match(f.name))
    return (n_leccion / len(archivos)) >= 0.50


def _destino_carpeta_curso(directorio: Path, base: Path) -> Path:
    """
    Retorna el directorio PADRE de destino para una carpeta de curso (sin el nombre del curso).

    Si ≥40 % de los archivos del curso (recursivo) son video → 02_videos/cursos/.
    En caso contrario → 04_libros/cursos/.
    """
    try:
        archivos = [
            f for f in directorio.rglob("*")
            if f.is_file() and not f.name.startswith("._")
        ]
        n_video = sum(1 for f in archivos if f.suffix.lower() in _VIDEO_EXTS_CURSO)
        proporcion = n_video / len(archivos) if archivos else 0
    except OSError:
        proporcion = 0

    carpeta_base = "02_videos/cursos" if proporcion >= 0.40 else "04_libros/cursos"
    return base / carpeta_base


def _normalizar_nombre_archivo(nombre: str) -> str:
    """
    Homologa el nombre de un archivo sin cambiar su extensión:
    - Quita acentos
    - Espacios → guiones bajos
    - Elimina caracteres no seguros (mantiene alfanumérico, _, -, .)
    - Colapsa múltiples _ consecutivos
    Devuelve el nombre original si el resultado quedaría vacío.
    """
    p = Path(nombre)
    stem, ext = p.stem, p.suffix

    stem_n = "".join(
        c for c in unicodedata.normalize("NFD", stem)
        if unicodedata.category(c) != "Mn"
    )
    stem_n = stem_n.replace(" ", "_")
    stem_n = re.sub(r"[^\w\-.]", "", stem_n)
    stem_n = re.sub(r"_+", "_", stem_n)
    stem_n = stem_n.strip("_.-")

    return (stem_n + ext) if stem_n else nombre


def _calcular_renombres_curso(directorio: Path) -> list[dict]:
    """
    Lista de archivos dentro del curso cuyo nombre normalizado difiere del original.
    Cada entrada: {"ruta_relativa": str, "nombre_nuevo": str}
    Las rutas son relativas al directorio del curso para que sean válidas
    tanto en origen como en destino.
    """
    renombres = []
    try:
        for ruta in sorted(directorio.rglob("*")):
            if not ruta.is_file() or ruta.name.startswith("._"):
                continue
            nombre_nuevo = _normalizar_nombre_archivo(ruta.name)
            if nombre_nuevo != ruta.name:
                renombres.append({
                    "ruta_relativa": str(ruta.relative_to(directorio)),
                    "nombre_nuevo": nombre_nuevo,
                })
    except OSError:
        pass
    return renombres


def _revisar_archivos_curso(directorio: Path) -> list[dict]:
    """
    Detecta archivos problemáticos dentro de la carpeta del curso (check ligero, sin leer contenido).
    No mueve nada — solo informa para que aparezca en el plan.
    Motivos detectados: "vacio" (0 bytes) | "descarga_incompleta" (ext .tmp, .crdownload, etc.)
    """
    problemas = []
    try:
        for ruta in sorted(directorio.rglob("*")):
            if not ruta.is_file() or ruta.name.startswith("._"):
                continue
            relativa = str(ruta.relative_to(directorio))
            try:
                tam = ruta.stat().st_size
            except OSError:
                continue
            if tam == 0:
                problemas.append({"ruta_relativa": relativa, "motivo": "vacio"})
            elif ruta.suffix.lower() in _EXTS_INCOMPLETAS:
                problemas.append({"ruta_relativa": relativa, "motivo": "descarga_incompleta"})
    except OSError:
        pass
    return problemas


def _destino_proyecto(proyecto_dir: Path, base: Path, contexto: str | None) -> Path:
    """
    Calcula el directorio destino para un proyecto de programación según el contexto.

    trabajo   → 09_codigo/{lenguaje}/_trabajo/
    escuela   → 07_escuela/_pendientes_clasificar/
    personal  → 09_codigo/proyectos/personales/
    (ninguno) → 09_codigo/_pendientes/
    """
    lenguaje = _detectar_lenguaje(proyecto_dir)
    if contexto == "trabajo":
        return base / "09_codigo" / lenguaje / "_trabajo"
    if contexto == "escuela":
        return base / "07_escuela" / "_pendientes_clasificar"
    if contexto == "personal":
        return base / "09_codigo" / "proyectos" / "personales"
    return base / "09_codigo" / "_pendientes"


# ─── Clasificación ────────────────────────────────────────────────────────────

def _categoria_por_magic(ruta: Path) -> str | None:
    """Intenta determinar la categoría por magic bytes. None si no disponible."""
    if not _MAGIC_DISPONIBLE:
        return None
    try:
        mime = _magic.from_file(str(ruta), mime=True)
        tipo_principal = mime.split("/")[0]
        if tipo_principal == "image":
            return "imagen"
        if tipo_principal == "video":
            return "video"
        if tipo_principal == "audio":
            return "audio"
        if tipo_principal == "text":
            return "documento"
        if "zip" in mime or "compressed" in mime or "archive" in mime:
            return "comprimido"
    except Exception:
        pass
    return None


def _en_carpeta_audiolibro(ruta: Path) -> bool:
    """True si algún directorio padre del archivo tiene nombre de audiolibro."""
    ruta_t = "/".join(p.lower() for p in ruta.parent.parts)
    return any(k in ruta_t for k in _AUDIOLIBRO_RUTA_KEYS)


def clasificar(ruta: Path, es_privada: bool = False) -> tuple[str, str]:
    """Devuelve (categoría, método). PDFs con >30 páginas → 'libro'. Carpetas privadas → 'privado'."""
    if es_privada:
        return "privado", "carpeta_privada"
    ext = ruta.suffix.lower()
    if ext == ".pdf":
        paginas = contar_paginas_pdf(ruta)
        if paginas is not None and paginas > _UMBRAL_LIBRO_PAGINAS:
            return "libro", "paginas_pdf"
        return "documento", "extension"
    # Audio en carpeta de audiolibros → libro, no música
    if ext in {".mp3", ".m4a", ".m4b", ".aac", ".ogg", ".opus", ".flac", ".wma"} and _en_carpeta_audiolibro(ruta):
        return "audiolibro", "ruta_audiolibro"
    if ext in _EXT_A_CATEGORIA:
        return _EXT_A_CATEGORIA[ext], "extension"
    magic_cat = _categoria_por_magic(ruta)
    if magic_cat:
        return magic_cat, "magic"
    return "desconocido", "defecto"


def detectar_pendientes(
    directorio: str | Path,
    base_hdd: str | Path | None = None,
    forzar_privado: bool = False,
    contexto: str | None = None,
) -> ResultadoPaso6:
    """Escanea directorio (normalmente _pendientes/checar/) y clasifica sus archivos.

    forzar_privado: marca todos los archivos como privados, independientemente de
    su ruta. Usado con el flag --privado del CLI para procesar carpetas como .other/.

    contexto: "trabajo" | "escuela" | "personal" | None.
    Controla el destino de proyectos de programación detectados como unidades atómicas.

    Si base_hdd se proporciona, los archivos dañados se registran con ruta_danado()
    apuntando al destino correcto dentro del HDD organizado.
    """
    directorio = Path(directorio)
    base = Path(base_hdd) if base_hdd else directorio.parent.parent
    resultado = ResultadoPaso6()

    for raiz, dirs, archivos in os.walk(str(directorio), topdown=True):
        raiz_path = Path(raiz)

        # Detectar subdirectorios como unidades atómicas — proyectos, bloque-código y cursos
        dirs_filtrados = []
        for d in list(dirs):
            subdir = raiz_path / d
            es_proyecto = es_proyecto_programacion(subdir)
            es_bloque   = not es_proyecto and _es_carpeta_codigo_bloque(subdir)
            es_curso    = not es_proyecto and not es_bloque and _es_carpeta_curso(subdir)
            if es_proyecto or es_bloque or es_curso:
                try:
                    tamanio_total = sum(
                        f.stat().st_size for f in subdir.rglob("*") if f.is_file()
                    )
                except OSError:
                    tamanio_total = 0
                privada = forzar_privado or es_carpeta_privada(subdir)
                if es_proyecto:
                    cat, metodo = "proyecto", "proyecto_programacion"
                elif es_bloque:
                    cat, metodo = "proyecto", "codigo_bloque"
                else:
                    cat, metodo = "curso", "carpeta_curso"
                resultado.archivos.append(ArchivoClasificado(
                    ruta=subdir,
                    categoria=cat,
                    metodo=metodo,
                    tamanio=tamanio_total,
                    es_privado=privada,
                    contexto_tag=contexto,
                ))
            else:
                dirs_filtrados.append(d)
        dirs[:] = dirs_filtrados  # No recursar dentro de unidades atómicas

        for nombre in archivos:
            # Archivos Apple Double Format (._xxxx) — resource forks macOS, sin valor en Linux
            if nombre.startswith("._"):
                continue
            ruta = raiz_path / nombre
            try:
                tamanio = ruta.stat().st_size
            except OSError:
                tamanio = 0
            privada = forzar_privado or es_carpeta_privada(ruta)
            categoria, metodo = clasificar(ruta, es_privada=privada)

            # Verificar integridad — archivos dañados van a _pendientes/dañados/
            ok, error_msg = verificar_archivo(ruta)
            if not ok:
                subcarpeta = _DESTINO_POR_CATEGORIA.get(categoria, "_pendientes/sin_clasificar")
                destino_intendido = base / subcarpeta / nombre
                ruta_dan = ruta_danado(destino_intendido, base)
                resultado.archivos.append(ArchivoClasificado(
                    ruta=ruta,
                    categoria="dañado",
                    metodo="verificador",
                    tamanio=tamanio,
                    es_privado=privada,
                    ruta_danado=ruta_dan,
                    error_integridad=error_msg,
                ))
                continue

            resultado.archivos.append(ArchivoClasificado(
                ruta=ruta,
                categoria=categoria,
                metodo=metodo,
                tamanio=tamanio,
                es_privado=privada,
            ))

    return resultado


# ─── Destino privado ─────────────────────────────────────────────────────────

def _destino_privado(ruta: Path, base: Path) -> Path:
    """
    Calcula la ruta destino para un archivo privado dentro de .privado/.

    Aplica las mismas convenciones de organización que las carpetas públicas:
      imagen/foto → .privado/fotos/YYYY/MM_nombre_mes/
      video       → .privado/videos/{tipo}/   (usando clasificador_videos)
      audio       → .privado/audio/
      otro        → .privado/varios/
    """
    ext = ruta.suffix.lower()
    priv = base / ".privado"

    if ext in _EXT_PRIVADO_FOTO:
        from .clasificador_videos import _extraer_fecha, MESES_ES
        año, mes = _extraer_fecha(ruta)
        mes_str = MESES_ES.get(mes, f"{mes:02d}")
        return priv / "fotos" / año / mes_str / ruta.name

    if ext in _EXT_PRIVADO_VIDEO:
        from .clasificador_videos import clasificar_video
        clase = clasificar_video(ruta)
        return priv / "videos" / clase.tipo / ruta.name

    if ext in _EXT_PRIVADO_AUDIO:
        return priv / "audio" / ruta.name

    return priv / "varios" / ruta.name


# ─── Plan ────────────────────────────────────────────────────────────────────

def construir_plan(resultado: ResultadoPaso6, destino: str | Path) -> PlanPaso6:
    """Construye el plan de movimiento desde _pendientes/ a sus destinos finales."""
    destino = Path(destino)
    plan = PlanPaso6()

    for archivo in resultado.archivos:
        if archivo.categoria == "dañado" and archivo.ruta_danado is not None:
            ruta_dest = resolver_colision(archivo.ruta_danado)
            plan.movimientos.append({
                "origen": str(archivo.ruta),
                "destino": str(ruta_dest),
                "categoria": "dañado",
                "metodo": archivo.metodo,
                "tamanio": archivo.tamanio,
                "error_integridad": archivo.error_integridad,
            })
            plan.total_bytes += archivo.tamanio
            continue

        if archivo.categoria == "proyecto":
            dir_dest = _destino_proyecto(archivo.ruta, destino, archivo.contexto_tag)
            ruta_dest = resolver_colision(dir_dest / archivo.ruta.name)
        elif archivo.categoria == "curso":
            dir_dest = _destino_carpeta_curso(archivo.ruta, destino)
            ruta_dest = resolver_colision(dir_dest / archivo.ruta.name)
            renombres = _calcular_renombres_curso(archivo.ruta)
            revisar   = _revisar_archivos_curso(archivo.ruta)
            if ruta_dest is None:
                plan.omitidos_identicos.append(str(archivo.ruta))
                continue
            mov: dict = {
                "origen": str(archivo.ruta),
                "destino": str(ruta_dest),
                "categoria": "curso",
                "metodo": archivo.metodo,
                "tamanio": archivo.tamanio,
            }
            if renombres:
                mov["renombres_internos"] = renombres
            if revisar:
                mov["archivos_revisar"] = revisar
            plan.movimientos.append(mov)
            plan.total_bytes += archivo.tamanio
            continue
        elif archivo.categoria == "privado":
            ruta_dest = resolver_destino(
                archivo.ruta,
                _destino_privado(archivo.ruta, destino),
            )
        elif archivo.categoria == "documento":
            from .clasificador_documentos import clasificar_documento, destino_documento
            clase = clasificar_documento(archivo.ruta)
            if clase.categoria == "curso":
                dir_dest = destino / "04_libros" / "cursos"
            elif clase.categoria == "idioma":
                dir_dest = destino / "04_libros" / "idiomas" / clase.subcategoria
            else:
                dir_dest = destino_documento(clase, destino / "08_documentos")
            ruta_dest = resolver_destino(archivo.ruta, dir_dest / archivo.ruta.name)
        elif archivo.categoria == "video":
            from .clasificador_videos import clasificar_video, destino_video
            clase = clasificar_video(archivo.ruta)
            dir_dest = destino_video(clase, destino)
            ruta_dest = resolver_destino(archivo.ruta, dir_dest / archivo.ruta.name)
        else:
            subcarpeta = _DESTINO_POR_CATEGORIA.get(archivo.categoria, "_pendientes/sin_clasificar")
            ruta_dest = resolver_destino(archivo.ruta, destino / subcarpeta / archivo.ruta.name)
        if ruta_dest is None:
            plan.omitidos_identicos.append(str(archivo.ruta))
            continue
        plan.movimientos.append({
            "origen": str(archivo.ruta),
            "destino": str(ruta_dest),
            "categoria": archivo.categoria,
            "metodo": archivo.metodo,
            "tamanio": archivo.tamanio,
        })
        plan.total_bytes += archivo.tamanio

    return plan


# ─── Ejecución ────────────────────────────────────────────────────────────────

def ejecutar_plan(
    plan: PlanPaso6,
    log_path: str | Path,
    dry_run: bool = True,
) -> ResultadoEjecucion:
    """Ejecuta el plan del Paso 6. dry_run=True solo reporta."""
    log_path = Path(log_path)
    resultado = ResultadoEjecucion(log_path=str(log_path), omitidos_identicos=list(plan.omitidos_identicos))

    if dry_run:
        resultado.movidos = list(plan.movimientos)
        return resultado

    reversion = {
        "timestamp": datetime.now().isoformat(),
        "paso": 6,
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

            # Post-move: renombrar archivos internos del curso
            if mov.get("renombres_internos"):
                for r in mov["renombres_internos"]:
                    ruta_vieja = destino / r["ruta_relativa"]
                    ruta_nueva = ruta_vieja.parent / r["nombre_nuevo"]
                    if ruta_vieja.exists() and not ruta_nueva.exists():
                        try:
                            ruta_vieja.rename(ruta_nueva)
                        except OSError:
                            pass
        except (OSError, shutil.Error) as e:
            resultado.errores.append({**mov, "error": str(e)})

    return resultado
