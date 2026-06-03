"""
Clasificador de documentos — 100% local, sin tokens.

Determina si un documento (PDF, DOCX, etc.) es personal, de salud,
de trabajo u otro, y qué subcarpeta dentro de 08_documentos/ le corresponde.

Prioridad de detección:
  1. Ruta del archivo (carpetas padre — señal más fuerte)
  2. Nombre del archivo (stem sin extensión)
  3. Metadata PDF (título / autor / tema via pypdf)
  4. Texto primera página (pdfplumber, solo PDFs < 5 páginas)
  5. Defecto → otro / general
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# ─── Normalización ────────────────────────────────────────────────────────────

def _norm(texto: str) -> str:
    """Minúsculas + sin acentos para comparación uniforme."""
    texto = texto.lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def _contiene(texto: str, *palabras: str) -> bool:
    t = _norm(texto)
    return any(p in t for p in palabras)


def _ruta_str(ruta: Path) -> str:
    # Solo directorios padre — el filename no debe disparar keywords de ruta
    return _norm("/".join(ruta.parent.parts))


# ─── Keywords por categoría ───────────────────────────────────────────────────

# Personal — detección por ruta (debe ir ANTES de salud/trabajo para evitar falsos positivos)
# "fiel" detecta FIEL SAT; "pensionissste"/"pensionisste" evita que "issste" dispare salud
_PERSONAL_RUTA_IDENTIF      = ("fiel", "claveprivada", "clave_privada")
_PERSONAL_RUTA_COMPROBANTES = ("pensionissste", "pensionisste")

# SALUD
# OJO: "issste" es substring de "pensionissste" — no confundir (el check de personal va antes)
_SALUD_RUTA = (
    "salud", "clinica", "hospital", "imss", "issste",
    "medico", "doctor", "farmacia", "laboratorio_clinico",
)
_SALUD_NOMBRE = (
    "receta", "analisis", "laboratorio", "lab_",
    "radiografia", "rx_", "odontolog", "dental", "consulta",
    "diagnostico", "resultado_", "historial_clinico", "ficha_medica",
    "estudio_clinico", "ultrasonido",
)
_SALUD_CONTENIDO = (
    "diagnostico:", "paciente:", "medico tratante",
    "laboratorio clinico", "mg/dl", "peso del paciente",
    "analisis clinico", "resultado de laboratorio",
)

_SALUD_RECETAS   = ("receta", "prescripcion", "medicamento")
_SALUD_ESTUDIOS  = ("laboratorio", "analisis", "resultado", "radiografia", "rx", "ultrasonido", "estudio")
_SALUD_SEGUROS   = ("poliza", "seguro", "aseguradora", "prima")

# TRABAJO
_TRABAJO_RUTA = (
    "trabajo", "ine", "prep_", "accenture",
    "oficina", "laboral", "empresa",
)
_TRABAJO_NOMBRE = (
    "nomina", "recibo_nomina", "cfdi_nomina", "carta_oferta",
    "contrato_laboral", "constancia_trabajo", "carta_renuncia",
    "finiquito", "carta_trabajo",
)
_TRABAJO_CONTENIDO = (
    "nombre del trabajador", "numero de empleado",
    "percepciones", "deducciones", "imss obrero",
    "no de empleado", "registropatronal",
)

_TRABAJO_NOMINAS   = ("nomina", "cfdi_nomina", "recibo_nomina", "percepciones", "recibo_de_nomina")
_TRABAJO_CONTRATOS = ("contrato", "carta_oferta", "convenio", "finiquito", "carta_renuncia")

# PERSONAL
_PERSONAL_NOMBRE = (
    "curp", "acta_nacimiento", "acta_nac",
    "pasaporte", "credencial", "licencia",
    "titulo", "cedula", "diploma", "constancia",
    "fiel", "claveprivada", "clave_privada",   # FIEL SAT en nombre de archivo
    "comprobante_domicilio", "comprobante",           # cualquier comprobante
    "estado_cuenta", "estado de cuenta", "statement",  # estados de cuenta
    "cfe", "telmex", "izzi", "totalplay", "recibo_luz", "recibo_agua",
    "boleta_agua", "boleta_predial", "predio", "predial",  # recibos MX
    "poliza",                                           # pólizas de seguro
    "cotizacion",                                       # cotizaciones/presupuestos
    "factura", "cfdi", "xml_factura",
    "contrato_arrendamiento", "arrendamiento",
    # SAT / pagos gobierno
    "acuse",                                 # acuse de recibo SAT, IMSS, etc.
    "pago sat", "pago_sat", "declaracion anual",
)
_PERSONAL_CONTENIDO = (
    "clave unica de registro",
    "instituto nacional electoral",
    "acta de nacimiento",
    "comprobante de domicilio",
)

_PERSONAL_IDENTIFICACIONES = (
    "curp", "acta_nac", "acta_nacimiento", "pasaporte", "credencial", "licencia", "ine",
    # FIEL SAT — certificado digital y clave privada
    "fiel", "claveprivada", "clave_privada", "clav.txt",
)
_PERSONAL_CERTIFICADOS     = ("titulo", "cedula", "diploma", "certificado", "constancia_titulacion", "certificacion")
_PERSONAL_COMPROBANTES     = (
    "comprobante_domicilio", "comprobante",
    "estado_cuenta", "estado de cuenta", "statement",
    "recibo_luz", "recibo_agua", "boleta_agua", "boleta_predial",
    "predio", "predial",
    "poliza", "cotizacion",
    "cfe", "telmex", "izzi", "totalplay",
    "acuse", "pago sat", "pago_sat",
    "pensionissste", "pensionisste",           # estado de cuenta PENSIONISSSTE
    "registro_caes",                           # registro contribuyente
)
_PERSONAL_FACTURAS         = ("factura", "cfdi", "xml_factura")
_PERSONAL_CONTRATOS        = ("contrato_arr", "arrendamiento", "renta")

_RE_AÑO = re.compile(r"(?<!\d)(20\d{2})(?!\d)")

# IDIOMAS — va a 04_libros/idiomas/{lang}/ en lugar de 08_documentos/
_IDIOMA_RUTA = (
    "idiomas", "languages",
    "language learning", "language_learning", "language pack", "language_pack",
    "learning english", "learning_english", "english learning",
    "english course", "bbc learning",
    "collins english", "cambridge english",
    "graded readers", "graded_readers",
    "chinese language", "german graded", "spanish language",
    "thai language", "lao language", "japanese language",
)
_IDIOMA_NOMBRE = (
    "phonetic", "vocabulary", "vocabulario",
    "grammar", "gramatica", "pronunciation",
    "preposition", "preposicion", "adverb", "adverbio",
    "learning english", "learning_english",
    "easy english", "english made easy",
    "spoken english", "spoken_english",
    "fluent english", "fluent_english",
    "english vocabulary", "english_vocabulary",
    "english verbs", "english_verbs",
    "english grammar", "english_grammar",
    "phrasal",
    "reading comprehension", "listening comprehension",
)

# CURSOS / MATERIAL ESCOLAR — va a 04_libros/cursos/ en lugar de 08_documentos/
_CURSO_RUTA = (
    "cursos", "curso", "courses", "course",
    "tutoriales", "tutorials",
    "udemy", "coursera", "platzi", "edureka", "pluralsight",
    "linkedin learning", "linkedin_learning",
    "onehack",
    "fbd2026", "fbd_2026",
    "practica ", "practicas",         # espacio final evita coincidencia parcial
    "escuela", "universidad",
    "semestre",
    "ayudantia", "ayudantias",        # materiales de ayudantía universitaria
)
_CURSO_NOMBRE = (
    "practica",                              # practica1…practica12, practica_algo
    "reporte_", "informe_",
    "normalizacion", "algebra_lineal", "calculo_",
    "hands_on", "hands-on",
    "workshop",
    "diagrama_er", "diagrama_relacional", "modelo_relacional",   # diagramas BD
    "entidad_relacion", "caso_de_uso",
    "proyecto_final", "proyectofinal",
    "calificacion",                          # CalificacionesFBD20261.ods
    "fbd2026", "fbd_2026",                   # etiqueta de materia en nombre de archivo
    # Libros técnicos — formato "Autor A. Título Tecnología Año"
    "machine learning", "deep learning", "artificial intelligence",
    "aws certified", "aws lambda", "cloud computing",
    "devops", "systems thinking", "learning systems",
    "quantum computing", "quantum machine",
    "scalable", "pipelines", "mlops",
    "scikit-learn", "tensorflow", "pytorch",
    "raspberry pi", "raspberry_pi",
    "step-by-step journey", "beginners guide", "complete guide",
)


# ─── Dataclass ────────────────────────────────────────────────────────────────

@dataclass
class ClasificacionDoc:
    categoria: str      # personal | salud | trabajo | otro
    subcategoria: str   # identificaciones | certificados | recetas | estudios | ...
    confianza: str      # ruta | nombre | metadata | contenido | defecto
    año: str = ""       # solo para facturas y nóminas → subfolder YYYY


# ─── Helpers de extracción ────────────────────────────────────────────────────

def _metadata_pdf(ruta: Path) -> str:
    """Lee título + tema + autor del PDF sin abrir el contenido completo."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(ruta), strict=False)
        meta = reader.metadata or {}
        partes = [
            str(meta.get("/Title", "") or ""),
            str(meta.get("/Subject", "") or ""),
            str(meta.get("/Author", "") or ""),
        ]
        return _norm(" ".join(partes))
    except Exception:
        return ""


_MARKITDOWN_EXTS = frozenset({".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".html", ".htm", ".odt"})


def _texto_primera_pagina(ruta: Path) -> str:
    """
    Extracto de texto para clasificación (máx 600 chars).
    PDF: pdfplumber página 1 (rápido). DOCX/PPTX/XLSX/HTML: markitdown.
    """
    ext = ruta.suffix.lower()

    if ext == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(ruta) as pdf:
                if not pdf.pages:
                    return ""
                return _norm((pdf.pages[0].extract_text() or "")[:600])
        except Exception:
            return ""

    if ext in _MARKITDOWN_EXTS:
        try:
            from markitdown import MarkItDown
            texto = (MarkItDown().convert(str(ruta)).text_content or "").strip()
            return _norm(texto[:600])
        except Exception:
            pass

    return ""


def _detectar_año(texto: str) -> str:
    m = _RE_AÑO.search(texto)
    return m.group(1) if m else datetime.now().strftime("%Y")


# ─── Subcategorías ────────────────────────────────────────────────────────────

def _subcat_salud(nombre: str, texto: str) -> str:
    t = nombre + " " + texto
    if _contiene(t, *_SALUD_RECETAS):
        return "recetas"
    if _contiene(t, *_SALUD_ESTUDIOS):
        return "estudios"
    if _contiene(t, *_SALUD_SEGUROS):
        return "seguros"
    return "estudios"  # default salud → estudios


def _subcat_trabajo(nombre: str, texto: str) -> str:
    t = nombre + " " + texto
    if _contiene(t, *_TRABAJO_NOMINAS):
        return "nominas"
    if _contiene(t, *_TRABAJO_CONTRATOS):
        return "contratos"
    return "general"


def _subcat_personal(nombre: str, texto: str) -> tuple[str, str]:
    """Retorna (subcategoria, año). año solo para facturas."""
    t = nombre + " " + texto
    if _contiene(nombre, *_PERSONAL_FACTURAS):
        año = _detectar_año(nombre + " " + texto)
        return "facturas", año
    if _contiene(t, *_PERSONAL_IDENTIFICACIONES):
        return "identificaciones", ""
    if _contiene(t, *_PERSONAL_CERTIFICADOS):
        return "certificados", ""
    if _contiene(t, *_PERSONAL_COMPROBANTES):
        return "comprobantes", ""
    if _contiene(t, *_PERSONAL_CONTRATOS):
        return "contratos", ""
    return "general", ""


# ─── Clasificador principal ───────────────────────────────────────────────────

def clasificar_documento(ruta: Path) -> ClasificacionDoc:
    """
    Clasifica un documento en personal / salud / trabajo / otro.
    Usa solo heurísticas locales; no llama a ninguna API.
    """
    ruta_t  = _ruta_str(ruta)
    nombre  = _norm(ruta.stem)

    # ── 1. Por ruta ──────────────────────────────────────────────────────────
    if _contiene(ruta_t, *_IDIOMA_RUTA):
        return ClasificacionDoc("idioma", "ingles", "ruta")

    if _contiene(ruta_t, *_CURSO_RUTA):
        return ClasificacionDoc("curso", "general", "ruta")

    # Personal por ruta — va ANTES de salud para evitar que "issste" en "pensionissste"
    # o "fiel" en otro contexto disparen falsos positivos en salud/trabajo
    if _contiene(ruta_t, *_PERSONAL_RUTA_IDENTIF):
        return ClasificacionDoc("personal", "identificaciones", "ruta")

    if _contiene(ruta_t, *_PERSONAL_RUTA_COMPROBANTES):
        return ClasificacionDoc("personal", "comprobantes", "ruta")

    if _contiene(ruta_t, *_SALUD_RUTA):
        sub = _subcat_salud(nombre, "")
        return ClasificacionDoc("salud", sub, "ruta")

    if _contiene(ruta_t, *_TRABAJO_RUTA):
        sub = _subcat_trabajo(nombre, "")
        año = _detectar_año(nombre) if sub == "nominas" else ""
        return ClasificacionDoc("trabajo", sub, "ruta", año=año)

    # ── 2. Por nombre de archivo ──────────────────────────────────────────────
    if _contiene(nombre, *_IDIOMA_NOMBRE):
        return ClasificacionDoc("idioma", "ingles", "nombre")

    if _contiene(nombre, *_CURSO_NOMBRE):
        return ClasificacionDoc("curso", "general", "nombre")

    if _contiene(nombre, *_SALUD_NOMBRE):
        sub = _subcat_salud(nombre, "")
        return ClasificacionDoc("salud", sub, "nombre")

    if _contiene(nombre, *_TRABAJO_NOMBRE):
        sub = _subcat_trabajo(nombre, "")
        año = _detectar_año(nombre) if sub == "nominas" else ""
        return ClasificacionDoc("trabajo", sub, "nombre", año=año)

    if _contiene(nombre, *_PERSONAL_NOMBRE):
        sub, año = _subcat_personal(nombre, "")
        return ClasificacionDoc("personal", sub, "nombre", año=año)

    # ── 3. Por metadata PDF ───────────────────────────────────────────────────
    meta = _metadata_pdf(ruta)
    if meta:
        if _contiene(meta, *_SALUD_NOMBRE, *_SALUD_CONTENIDO):
            sub = _subcat_salud("", meta)
            return ClasificacionDoc("salud", sub, "metadata")

        if _contiene(meta, *_TRABAJO_NOMBRE, *_TRABAJO_CONTENIDO):
            sub = _subcat_trabajo("", meta)
            año = _detectar_año(meta) if sub == "nominas" else ""
            return ClasificacionDoc("trabajo", sub, "metadata", año=año)

        if _contiene(meta, *_PERSONAL_NOMBRE, *_PERSONAL_CONTENIDO):
            sub, año = _subcat_personal("", meta)
            return ClasificacionDoc("personal", sub, "metadata", año=año)

    # ── 4. Por texto primera página ───────────────────────────────────────────
    texto = _texto_primera_pagina(ruta)
    if texto:
        if _contiene(texto, *_SALUD_CONTENIDO):
            sub = _subcat_salud("", texto)
            return ClasificacionDoc("salud", sub, "contenido")

        if _contiene(texto, *_TRABAJO_CONTENIDO):
            sub = _subcat_trabajo("", texto)
            año = _detectar_año(texto) if sub == "nominas" else ""
            return ClasificacionDoc("trabajo", sub, "contenido", año=año)

        if _contiene(texto, *_PERSONAL_CONTENIDO):
            sub, año = _subcat_personal("", texto)
            return ClasificacionDoc("personal", sub, "contenido", año=año)

    # ── 5. Defecto ────────────────────────────────────────────────────────────
    return ClasificacionDoc("otro", "general", "defecto")


# ─── Destino ──────────────────────────────────────────────────────────────────

def destino_documento(clase: ClasificacionDoc, base_docs: Path) -> Path:
    """
    Devuelve el directorio destino dentro de base_docs (sin incluir el nombre del archivo).
    Para facturas incluye el subfolder del año: personal/facturas/YYYY/
    Para nóminas incluye el año: trabajo/nominas/YYYY/
    """
    if clase.año:
        return base_docs / clase.categoria / clase.subcategoria / clase.año
    return base_docs / clase.categoria / clase.subcategoria
