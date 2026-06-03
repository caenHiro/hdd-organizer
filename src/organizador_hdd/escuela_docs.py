"""
Procesamiento de documentos escolares para Obsidian. Sin tokens de IA.

Cuatro mecanismos locales (zero tokens):

1. TXT  → nota Obsidian (crea o actualiza cuerpo; frontmatter manual se preserva)
2. PDF  < 30 pág → extrae texto local → nota Obsidian
          PDFs ≥ 30 pág = libro → Calibre (responsabilidad de paso8)
3. Imagen escolar → clasifica: foto_escolar | captura_clase | diagrama | otro
4. TEX  ↔ Obsidian → sync bidireccional (pandoc si disponible, regex como fallback)
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


# ─── Dependencias opcionales ──────────────────────────────────────────────────

try:
    from pypdf import PdfReader as _PdfReader
    _PYPDF_OK = True
except ImportError:
    try:
        from PyPDF2 import PdfReader as _PdfReader  # type: ignore[no-redef]
        _PYPDF_OK = True
    except ImportError:
        _PYPDF_OK = False

try:
    import pdfplumber as _pdfplumber
    _PLUMBER_OK = True
except ImportError:
    _pdfplumber = None  # type: ignore[assignment]
    _PLUMBER_OK = False

try:
    from markitdown import MarkItDown as _MarkItDown
    _MARKITDOWN_OK = True
except ImportError:
    _MarkItDown = None  # type: ignore[assignment]
    _MARKITDOWN_OK = False

try:
    from PIL import Image as _PIL
    _PIL_OK = True
except ImportError:
    _PIL = None  # type: ignore[assignment]
    _PIL_OK = False

UMBRAL_LIBRO = 30  # páginas — mayor o igual → libro/Calibre

# Resoluciones típicas de capturas de presentaciones
_RES_SLIDES = {
    (1920, 1080), (1280, 720), (1366, 768), (1024, 768),
    (1280, 960), (800, 600), (1600, 900), (2560, 1440),
}

_RE_CAMARA = re.compile(
    r"^(img_|dsc_|dscn|p\d{8}|vid_|\d{8}_\d{6}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)

_TAG_MAKE = 271
_TAG_MODEL = 272


# ─── Dataclasses de resultado ─────────────────────────────────────────────────

@dataclass
class ResultadoDoc:
    """Resultado de convertir un archivo a nota Obsidian."""
    ruta_nota: Path
    creado: bool         # True = nota nueva
    sin_cambios: bool    # True = ya estaba al día, no se tocó
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass
class ResultadoSync:
    """Resultado de sincronizar .tex ↔ .md."""
    ruta_origen: Path
    ruta_destino: Path
    sincronizado: bool
    direccion: str       # "tex_a_md" | "md_a_tex" | "sin_cambios"
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass
class ClasificacionImagen:
    categoria: str        # foto_escolar | captura_clase | diagrama | otro
    confianza: str        # exif | heuristica | defecto
    ancho: int = 0
    alto: int = 0
    tiene_camara_exif: bool = False


# ─── Utilidades internas ──────────────────────────────────────────────────────

def _hash_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def _ruta_nota(vault: Path, semestre: str, materia: str, stem: str) -> Path:
    """Devuelve la ruta canónica de la nota en el vault bajo Semestres/SXX_YYYY-P/<materia>/."""
    return vault / "Conocimiento" / "Universidad" / "Semestres" / semestre / materia / f"{stem}.md"


def _frontmatter(stem: str, semestre: str, materia: str, tipo: str, fuente: str) -> str:
    return (
        "---\n"
        f"aliases: [{stem}]\n"
        f"tags: [universidad, {semestre.lower()}, {materia.lower()}, {tipo}]\n"
        f"fuente: {fuente}\n"
        f"tipo: {tipo}\n"
        f"fecha_procesado: {date.today()}\n"
        "---\n"
    )


def _escribir_nota(
    ruta: Path,
    frontmatter: str,
    cuerpo: str,
) -> tuple[bool, bool]:
    """
    Escribe o actualiza la nota.
    Retorna (creado, sin_cambios).

    Si la nota ya existe se reemplaza solo la sección entre los marcadores de cuerpo,
    preservando cualquier contenido añadido manualmente después de los marcadores.
    """
    contenido_nuevo = frontmatter + "\n" + _MARCA_INICIO + "\n" + cuerpo + "\n" + _MARCA_FIN + "\n"

    if ruta.exists():
        actual = ruta.read_text(encoding="utf-8")
        # Reemplazar solo el bloque entre marcadores
        patron = re.compile(
            re.escape(_MARCA_INICIO) + r".*?" + re.escape(_MARCA_FIN),
            re.DOTALL,
        )
        if patron.search(actual):
            bloque_nuevo = _MARCA_INICIO + "\n" + cuerpo + "\n" + _MARCA_FIN
            nuevo = patron.sub(bloque_nuevo, actual)
            if nuevo == actual:
                return False, True   # sin cambios
            ruta.write_text(nuevo, encoding="utf-8")
            return False, False     # actualizado
        # Nota existe pero sin marcadores → sobrescribir
        if _hash_texto(actual) == _hash_texto(contenido_nuevo):
            return False, True
        ruta.write_text(contenido_nuevo, encoding="utf-8")
        return False, False

    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido_nuevo, encoding="utf-8")
    return True, False


_MARCA_INICIO = "<!-- fuente:inicio -->"
_MARCA_FIN    = "<!-- fuente:fin -->"


# ─── 1. TXT → Obsidian ────────────────────────────────────────────────────────

def txt_a_obsidian(
    ruta_txt: str | Path,
    vault: str | Path,
    semestre: str,
    materia: str,
) -> ResultadoDoc:
    """
    Lee un .txt y crea/actualiza una nota Obsidian.
    El contenido del .txt queda entre marcadores para permitir edición manual fuera de ellos.
    Nota: codificaciones intentadas en orden: utf-8, latin-1, cp1252.
    """
    ruta_txt = Path(ruta_txt)
    vault = Path(vault)

    texto = _leer_txt(ruta_txt)
    if texto is None:
        nota = _ruta_nota(vault, semestre, materia, ruta_txt.stem)
        return ResultadoDoc(nota, creado=False, sin_cambios=False,
                            error=f"no se pudo leer {ruta_txt}")

    fm = _frontmatter(ruta_txt.stem, semestre, materia, "txt", str(ruta_txt))
    ruta_nota = _ruta_nota(vault, semestre, materia, ruta_txt.stem)
    creado, sin_cambios = _escribir_nota(ruta_nota, fm, texto)
    return ResultadoDoc(ruta_nota, creado=creado, sin_cambios=sin_cambios)


def _leer_txt(ruta: Path) -> str | None:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return ruta.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            pass
    return None


# ─── 2. PDF → Obsidian (< 30 páginas) ────────────────────────────────────────

def pdf_a_obsidian(
    ruta_pdf: str | Path,
    vault: str | Path,
    semestre: str,
    materia: str,
) -> ResultadoDoc:
    """
    Extrae texto de un PDF < 30 páginas y crea nota Obsidian.
    PDFs ≥ 30 páginas deben ir a Calibre (responsabilidad del caller / paso8).
    Si ni pypdf ni pdfplumber están disponibles, crea nota con solo los metadatos.
    """
    ruta_pdf = Path(ruta_pdf)
    vault = Path(vault)
    ruta_nota = _ruta_nota(vault, semestre, materia, ruta_pdf.stem)

    paginas, texto = _extraer_pdf(ruta_pdf)

    if paginas >= UMBRAL_LIBRO:
        return ResultadoDoc(
            ruta_nota, creado=False, sin_cambios=False,
            error=f"PDF con {paginas} páginas ≥ {UMBRAL_LIBRO} → clasificar como libro/Calibre",
        )

    if texto is None:
        texto = f"_(texto no extraído — instalar pypdf o pdfplumber)_\n\nArchivo original: `{ruta_pdf}`"

    cuerpo = f"# {ruta_pdf.stem}\n\n{texto}"
    fm = _frontmatter(ruta_pdf.stem, semestre, materia, "pdf", str(ruta_pdf))
    fm = fm.rstrip("---\n") + f"\npaginas: {paginas}\n---\n"

    creado, sin_cambios = _escribir_nota(ruta_nota, fm, cuerpo)
    return ResultadoDoc(ruta_nota, creado=creado, sin_cambios=sin_cambios)


def _extraer_pdf(ruta: Path) -> tuple[int, str | None]:
    """
    Retorna (num_paginas, texto_extraido). texto=None si ninguna lib disponible.
    Prioridad: markitdown (mejor formato) → pdfplumber → pypdf.
    El conteo de páginas se obtiene con pdfplumber/pypdf (liviano) antes de extraer.
    """
    # Contar páginas primero (sin extraer texto completo)
    paginas = 0
    if _PLUMBER_OK:
        try:
            with _pdfplumber.open(str(ruta)) as pdf:
                paginas = len(pdf.pages)
        except Exception:
            pass
    if paginas == 0 and _PYPDF_OK:
        try:
            paginas = len(_PdfReader(str(ruta), strict=False).pages)
        except Exception:
            pass

    if paginas >= UMBRAL_LIBRO:
        return paginas, None

    # Extraer texto: markitdown → pdfplumber → pypdf
    if _MARKITDOWN_OK:
        try:
            texto = (_MarkItDown().convert(str(ruta)).text_content or "").strip()
            if texto:
                return paginas, texto
        except Exception:
            pass

    if _PLUMBER_OK:
        try:
            with _pdfplumber.open(str(ruta)) as pdf:
                partes = [p.extract_text() or "" for p in pdf.pages]
                texto = "\n\n".join(t for t in partes if t.strip())
                if texto:
                    return paginas, texto
        except Exception:
            pass

    if _PYPDF_OK:
        try:
            partes = [p.extract_text() or "" for p in _PdfReader(str(ruta)).pages]
            texto = "\n\n".join(t for t in partes if t.strip())
            if texto:
                return paginas, texto
        except Exception:
            pass

    return paginas, None


# ─── 3. Clasificación de imágenes escolares ───────────────────────────────────

def clasificar_imagen_escolar(ruta_img: str | Path) -> ClasificacionImagen:
    """
    Clasifica una imagen escolar sin IA:
    - foto_escolar   → tiene datos de cámara EXIF o nombre tipo cámara
    - captura_clase  → resolución de presentación/slides, sin EXIF de cámara
    - diagrama       → imagen sin EXIF y sin resolución slide (generada por computadora)
    - otro           → no se pudo abrir o formato no soportado

    No lanza excepciones.
    """
    ruta_img = Path(ruta_img)
    nombre = ruta_img.stem

    if ruta_img.suffix.lower() == ".svg":
        return ClasificacionImagen("diagrama", "heuristica")

    if not _PIL_OK:
        if _RE_CAMARA.match(nombre):
            return ClasificacionImagen("foto_escolar", "heuristica")
        return ClasificacionImagen("diagrama", "defecto")

    try:
        with _PIL.open(str(ruta_img)) as img:
            ancho, alto = img.size
            exif = dict(img.getexif() or {})
    except Exception:
        return ClasificacionImagen("otro", "defecto")

    tiene_camara = bool(exif.get(_TAG_MAKE) or exif.get(_TAG_MODEL))

    if tiene_camara or _RE_CAMARA.match(nombre):
        return ClasificacionImagen(
            "foto_escolar", "exif" if tiene_camara else "heuristica",
            ancho=ancho, alto=alto, tiene_camara_exif=tiene_camara,
        )

    if (ancho, alto) in _RES_SLIDES or (alto, ancho) in _RES_SLIDES:
        return ClasificacionImagen("captura_clase", "heuristica", ancho=ancho, alto=alto)

    return ClasificacionImagen("diagrama", "heuristica", ancho=ancho, alto=alto)


# ─── 4. TEX ↔ Obsidian sync ──────────────────────────────────────────────────

def tex_a_obsidian(
    ruta_tex: str | Path,
    vault: str | Path,
    semestre: str,
    materia: str,
) -> ResultadoDoc:
    """
    Convierte un archivo .tex a nota Obsidian.
    Usa pandoc si está disponible; fallback a conversión por regex.
    """
    ruta_tex = Path(ruta_tex)
    vault = Path(vault)
    ruta_nota = _ruta_nota(vault, semestre, materia, ruta_tex.stem)

    try:
        tex_content = ruta_tex.read_text(encoding="utf-8")
    except OSError as e:
        return ResultadoDoc(ruta_nota, creado=False, sin_cambios=False, error=str(e))

    md_cuerpo = _tex_a_markdown(tex_content)
    fm = _frontmatter(ruta_tex.stem, semestre, materia, "tex", str(ruta_tex))
    creado, sin_cambios = _escribir_nota(ruta_nota, fm, md_cuerpo)
    return ResultadoDoc(ruta_nota, creado=creado, sin_cambios=sin_cambios)


def obsidian_a_tex(
    ruta_md: str | Path,
    ruta_tex_dest: str | Path,
) -> ResultadoSync:
    """
    Actualiza (o crea) un .tex a partir del contenido editable de una nota Obsidian.
    Solo convierte el contenido entre los marcadores fuente:inicio / fuente:fin.
    Si no hay marcadores, convierte todo el body (sin frontmatter).
    """
    ruta_md = Path(ruta_md)
    ruta_tex_dest = Path(ruta_tex_dest)

    try:
        md_content = ruta_md.read_text(encoding="utf-8")
    except OSError as e:
        return ResultadoSync(ruta_md, ruta_tex_dest, False, "md_a_tex", error=str(e))

    cuerpo = _extraer_cuerpo_editable(md_content)
    tex_nuevo = _markdown_a_tex(cuerpo, titulo=ruta_md.stem)

    if ruta_tex_dest.exists():
        actual = ruta_tex_dest.read_text(encoding="utf-8")
        if actual == tex_nuevo:
            return ResultadoSync(ruta_md, ruta_tex_dest, False, "sin_cambios")

    ruta_tex_dest.parent.mkdir(parents=True, exist_ok=True)
    ruta_tex_dest.write_text(tex_nuevo, encoding="utf-8")
    return ResultadoSync(ruta_md, ruta_tex_dest, True, "md_a_tex")


def sincronizar_tex(
    ruta_tex: str | Path,
    ruta_md: str | Path,
    vault: str | Path = "",
    semestre: str = "Sem00",
    materia: str = "general",
) -> ResultadoSync:
    """
    Sincronización bidireccional .tex ↔ .md.
    Detecta cuál fue modificado más recientemente y actualiza el otro.
    Si .md no existe, lo crea desde .tex.
    """
    ruta_tex = Path(ruta_tex)
    ruta_md = Path(ruta_md)

    if not ruta_md.exists():
        vault_path = Path(vault) if vault else ruta_md.parent
        res = tex_a_obsidian(ruta_tex, vault_path, semestre, materia)
        return ResultadoSync(ruta_tex, ruta_md, res.creado or not res.sin_cambios, "tex_a_md", error=res.error)

    if not ruta_tex.exists():
        return ResultadoSync(ruta_tex, ruta_md, False, "sin_cambios",
                             error=f"archivo .tex no encontrado: {ruta_tex}")

    try:
        mtime_tex = ruta_tex.stat().st_mtime
        mtime_md = ruta_md.stat().st_mtime
    except OSError as e:
        return ResultadoSync(ruta_tex, ruta_md, False, "sin_cambios", error=str(e))

    if mtime_tex > mtime_md:
        # .tex es más nuevo → actualizar .md
        try:
            tex_content = ruta_tex.read_text(encoding="utf-8")
        except OSError as e:
            return ResultadoSync(ruta_tex, ruta_md, False, "tex_a_md", error=str(e))
        md_cuerpo = _tex_a_markdown(tex_content)
        md_actual = ruta_md.read_text(encoding="utf-8")
        patron = re.compile(
            re.escape(_MARCA_INICIO) + r".*?" + re.escape(_MARCA_FIN), re.DOTALL
        )
        bloque_nuevo = _MARCA_INICIO + "\n" + md_cuerpo + "\n" + _MARCA_FIN
        if patron.search(md_actual):
            nuevo = patron.sub(bloque_nuevo, md_actual)
            if nuevo == md_actual:
                return ResultadoSync(ruta_tex, ruta_md, False, "sin_cambios")
            ruta_md.write_text(nuevo, encoding="utf-8")
        else:
            ruta_md.write_text(md_actual.rstrip() + "\n\n" + bloque_nuevo + "\n", encoding="utf-8")
        return ResultadoSync(ruta_tex, ruta_md, True, "tex_a_md")

    if mtime_md > mtime_tex:
        # .md es más nuevo → actualizar .tex
        return obsidian_a_tex(ruta_md, ruta_tex)

    return ResultadoSync(ruta_tex, ruta_md, False, "sin_cambios")


# ─── Conversión LaTeX ↔ Markdown (sin pandoc requerido) ──────────────────────

def _pandoc_disponible() -> bool:
    try:
        subprocess.run(["pandoc", "--version"], capture_output=True, timeout=3)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _tex_a_markdown(tex: str) -> str:
    """Convierte LaTeX a Markdown. Usa pandoc si disponible, regex como fallback."""
    if _pandoc_disponible():
        try:
            resultado = subprocess.run(
                ["pandoc", "--from=latex", "--to=markdown", "--wrap=none"],
                input=tex, capture_output=True, text=True, timeout=30, encoding="utf-8",
            )
            if resultado.returncode == 0:
                return resultado.stdout
        except (subprocess.TimeoutExpired, OSError):
            pass
    return _tex_a_markdown_regex(tex)


def _markdown_a_tex(md: str, titulo: str = "") -> str:
    """Convierte Markdown a LaTeX. Usa pandoc si disponible, regex como fallback."""
    if _pandoc_disponible():
        try:
            resultado = subprocess.run(
                ["pandoc", "--from=markdown", "--to=latex", "--standalone",
                 f"--metadata=title:{titulo}"],
                input=md, capture_output=True, text=True, timeout=30, encoding="utf-8",
            )
            if resultado.returncode == 0:
                return resultado.stdout
        except (subprocess.TimeoutExpired, OSError):
            pass
    return _markdown_a_tex_regex(md, titulo)


def _tex_a_markdown_regex(tex: str) -> str:
    """Conversión básica de LaTeX a Markdown sin dependencias externas."""
    # Extraer solo el cuerpo del documento si tiene \begin{document}
    m = re.search(r"\\begin\{document\}(.*?)\\end\{document\}", tex, re.DOTALL)
    if m:
        tex = m.group(1)

    # Eliminar comentarios LaTeX
    tex = re.sub(r"%.*$", "", tex, flags=re.MULTILINE)

    # Secciones
    tex = re.sub(r"\\section\*?\{([^}]+)\}", r"## \1", tex)
    tex = re.sub(r"\\subsection\*?\{([^}]+)\}", r"### \1", tex)
    tex = re.sub(r"\\subsubsection\*?\{([^}]+)\}", r"#### \1", tex)
    tex = re.sub(r"\\chapter\*?\{([^}]+)\}", r"# \1", tex)

    # Formato de texto
    tex = re.sub(r"\\textbf\{([^}]+)\}", r"**\1**", tex)
    tex = re.sub(r"\\textit\{([^}]+)\}", r"*\1*", tex)
    tex = re.sub(r"\\emph\{([^}]+)\}", r"*\1*", tex)
    tex = re.sub(r"\\underline\{([^}]+)\}", r"<u>\1</u>", tex)
    tex = re.sub(r"\\texttt\{([^}]+)\}", r"`\1`", tex)

    # Entornos de lista
    tex = re.sub(r"\\begin\{itemize\}", "", tex)
    tex = re.sub(r"\\end\{itemize\}", "", tex)
    tex = re.sub(r"\\begin\{enumerate\}", "", tex)
    tex = re.sub(r"\\end\{enumerate\}", "", tex)
    tex = re.sub(r"\\item\s+", "- ", tex)

    # Matemáticas: entorno equation → $$
    tex = re.sub(r"\\begin\{equation\*?\}(.*?)\\end\{equation\*?\}", r"$$\1$$", tex, flags=re.DOTALL)
    tex = re.sub(r"\\begin\{align\*?\}(.*?)\\end\{align\*?\}", r"$$\1$$", tex, flags=re.DOTALL)

    # Entornos de bloque de código
    tex = re.sub(r"\\begin\{verbatim\}(.*?)\\end\{verbatim\}", r"```\n\1\n```", tex, flags=re.DOTALL)
    tex = re.sub(r"\\begin\{lstlisting\}.*?\n(.*?)\\end\{lstlisting\}", r"```\n\1\n```", tex, flags=re.DOTALL)

    # Abstract
    tex = re.sub(r"\\begin\{abstract\}", "## Abstract\n", tex)
    tex = re.sub(r"\\end\{abstract\}", "\n---", tex)

    # Saltos de línea
    tex = tex.replace("\\\\", "\n")
    tex = tex.replace("\\newline", "\n")
    tex = re.sub(r"\\newpage", "\n---\n", tex)
    tex = re.sub(r"\\clearpage", "\n---\n", tex)

    # Citas y referencias
    tex = re.sub(r"\\cite\{([^}]+)\}", r"[\1]", tex)
    tex = re.sub(r"\\ref\{[^}]+\}", "", tex)
    tex = re.sub(r"\\label\{[^}]+\}", "", tex)

    # Comandos a eliminar
    tex = re.sub(r"\\(documentclass|usepackage|input|include|maketitle|tableofcontents|clearpage)\b[^{}\n]*(\{[^}]*\})*", "", tex)
    tex = re.sub(r"\\(hline|toprule|midrule|bottomrule)\b", "", tex)
    tex = re.sub(r"\\(centering|raggedright|raggedleft)\b", "", tex)
    tex = re.sub(r"\\(noindent|indent)\b", "", tex)
    tex = re.sub(r"\\vspace\*?\{[^}]*\}", "", tex)
    tex = re.sub(r"\\hspace\*?\{[^}]*\}", "", tex)

    # Entornos que solo eliminamos (figure, table, minipage, center)
    tex = re.sub(r"\\begin\{(figure|table|minipage|center|tabular)[^}]*\}.*?\\end\{\1\}", "", tex, flags=re.DOTALL)

    # Llaves sobrantes
    tex = re.sub(r"\{([^{}]*)\}", r"\1", tex)

    # Espacios de LaTeX
    tex = tex.replace("~", " ")
    tex = tex.replace("---", "—")
    tex = tex.replace("--", "–")
    tex = re.sub(r"``|''", '"', tex)

    # Limpiar líneas en blanco excesivas
    tex = re.sub(r"\n{3,}", "\n\n", tex)

    return tex.strip()


def _markdown_a_tex_regex(md: str, titulo: str = "") -> str:
    """Convierte Markdown básico a LaTeX sin dependencias externas."""
    lineas = md.splitlines()
    cuerpo: list[str] = []
    en_lista = False
    en_codigo = False

    for linea in lineas:
        if linea.startswith("```"):
            if en_codigo:
                cuerpo.append("\\end{verbatim}")
                en_codigo = False
            else:
                cuerpo.append("\\begin{verbatim}")
                en_codigo = True
            continue

        if en_codigo:
            cuerpo.append(linea)
            continue

        # Headings
        if linea.startswith("#### "):
            cuerpo.append(f"\\subsubsection{{{linea[5:]}}}")
            continue
        if linea.startswith("### "):
            cuerpo.append(f"\\subsection{{{linea[4:]}}}")
            continue
        if linea.startswith("## "):
            cuerpo.append(f"\\section{{{linea[3:]}}}")
            continue
        if linea.startswith("# "):
            cuerpo.append(f"\\chapter{{{linea[2:]}}}")
            continue

        # Listas
        if linea.startswith("- ") or linea.startswith("* "):
            if not en_lista:
                cuerpo.append("\\begin{itemize}")
                en_lista = True
            cuerpo.append(f"\\item {linea[2:]}")
            continue

        if en_lista:
            cuerpo.append("\\end{itemize}")
            en_lista = False

        # Formato inline
        linea = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", linea)
        linea = re.sub(r"\*(.+?)\*", r"\\emph{\1}", linea)
        linea = re.sub(r"`(.+?)`", r"\\texttt{\1}", linea)
        linea = re.sub(r"\$\$(.+?)\$\$", r"\\begin{equation}\1\\end{equation}", linea)

        cuerpo.append(linea)

    if en_lista:
        cuerpo.append("\\end{itemize}")

    titulo_tex = titulo.replace("_", "\\_")
    cuerpo_str = "\n".join(cuerpo)

    return (
        "\\documentclass{article}\n"
        "\\usepackage[utf8]{inputenc}\n"
        "\\usepackage[spanish]{babel}\n"
        "\\usepackage{amsmath}\n"
        f"\\title{{{titulo_tex}}}\n"
        "\\begin{document}\n"
        "\\maketitle\n\n"
        f"{cuerpo_str}\n\n"
        "\\end{document}\n"
    )


def _extraer_cuerpo_editable(md_content: str) -> str:
    """Extrae el contenido entre marcadores fuente:inicio y fuente:fin."""
    patron = re.compile(
        re.escape(_MARCA_INICIO) + r"\n?(.*?)\n?" + re.escape(_MARCA_FIN),
        re.DOTALL,
    )
    m = patron.search(md_content)
    if m:
        return m.group(1).strip()
    # Sin marcadores: quitar frontmatter y devolver el resto
    sin_fm = re.sub(r"^---\n.*?---\n", "", md_content, flags=re.DOTALL)
    return sin_fm.strip()
