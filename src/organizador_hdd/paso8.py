"""
Paso 8 — Datos escolares.

Detecta la estructura de semestres y materias en un directorio universitario:
  Semestre N/
    Materia/
      practica1.py, notas.pdf, libro.pdf ...

Clasifica y mueve:
  código/prácticas  → 09_codigo/escolar/<semestre>/<materia>/
  PDFs > 30 págs    → 04_libros/escolar/
  documentos/PDFs   → 08_documentos/escolar/<semestre>/<materia>/
  comprimidos       → _pendientes/checar/

Genera notas Obsidian por semestre si se provee --vault.
"""
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .utils import contar_paginas_pdf, resolver_destino, sanitizar_nombre

# ─── Mapa canónico UNAM FC — Ciencias de la Computación Plan 1994 ─────────────

MAPA_SEMESTRES_UNAM: dict[str, str] = {
    "Sem01": "S01_2011-1",
    "Sem02": "S02_2011-2",
    "Sem03": "S03_2012-1",
    "Sem04": "S04_2012-2",
    "Sem05": "S05_2013-1",
    "Sem06": "S06_2013-2",
    "Sem07": "S07_2014-1",
    "Sem08": "S08_2014-2",
    "Sem09": "S09_2015-1",
    "Sem10": "S10_2015-2",
}

# HDD folder name → clave_NombreOficial  (insensible a mayúsculas)
MAPA_MATERIAS_UNAM: dict[str, str] = {
    # S02
    "icc1": "0224_ICC_I",
    # S03
    "icc2": "0339_ICC_II",
    # S04
    "analisis logico": "0415_Analisis_Logico",
    "calculo 2": "0092_Calculo_II",
    "calculo 3": "0093_Calculo_III",
    "diseños": "0574_Disenio_Sistemas_Digitales",
    "diseños de sistemas digitales": "0574_Disenio_Sistemas_Digitales",
    "lineal": "0005_Algebra_Lineal_I",
    # S05
    "analisis log": "0415_Analisis_Logico",
    "calculo iii": "0093_Calculo_III",
    "calculo iv": "0094_Calculo_IV",
    "lineal ii": "0006_Algebra_Lineal_II",
    # S06
    "bases de datos": "0606_Sistemas_Bases_Datos",
    "lenguajes": "0607_Lenguajes_Paradigmas",
    "sistemas operativos": "0713_Sistemas_Operativos",
    "teoria de la computacion": "0576_Teoria_Computacion",
    # S07
    "aa": "0414_Analisis_Algoritmos_I",
    "gbd": "0824_Grandes_Bases_Datos",
    "redes": "0714_Redes_Computadoras",
    "smbd": "0826_SMBD",
    "teoria de redes": "0077_Analisis_Redes",
    # S08
    "arquitectura": "0605_Arquitectura_Computadoras",
    "criptografia": "0014_Seguridad_Informatica",
    "ingenieria de software": "0575_Ingenieria_Software",
    "inteligencia artificial": "0608_Inteligencia_Artificial",
    "lineal 2": "0006_Algebra_Lineal_II",
    "smdbdd": "0826_SMBD",
    # S09
    "ia": "0608_Inteligencia_Artificial",
    "is2": "0429_Temas_Selectos_IS_A",
    "numerico": "0036_Analisis_Numerico_I",
    "reconocimiento de patrones": "0285_Reconocimiento_Patrones",
    # S10
    "admon de proyectos": "0429_Admon_Proyectos",
    "declarativo": "0813_Prog_Funcional_Logica",
    "interfaces": "0822_Disenio_Interfaces",
}


def _normalizar_materia(nombre: str) -> str:
    """Devuelve el nombre canónico de la materia si existe en el mapa, o el nombre sanitizado."""
    canonico = MAPA_MATERIAS_UNAM.get(nombre.lower().strip())
    return canonico if canonico else sanitizar_nombre(nombre)


# ─── Detección de semestres ───────────────────────────────────────────────────

_PATRON_SEMESTRE = re.compile(
    r"(?i)(?:semestre?|sem)[\s._\-]?(\d{1,2})|^(\d{1,2})(?:er?|do?|ro?|to?)?[\s._\-]?(?:semestre?)?$"
)

_EXT_CODIGO: frozenset[str] = frozenset({
    ".py", ".java", ".c", ".cpp", ".h", ".cs", ".js", ".ts", ".go",
    ".rs", ".php", ".rb", ".sh", ".bat", ".sql", ".r", ".m", ".pl",
})

_EXT_DOCUMENTO: frozenset[str] = frozenset({
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt",
    ".rtf", ".odt", ".ods", ".odp",
})

_EXT_COMPRIMIDO: frozenset[str] = frozenset({
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2",
})

_UMBRAL_LIBRO = 30


def _normalizar_semestre(nombre: str) -> str | None:
    """Extrae el número de semestre del nombre de carpeta. Devuelve 'Sem01' o None."""
    m = _PATRON_SEMESTRE.match(nombre.strip())
    if m:
        num = m.group(1) or m.group(2)
        return f"Sem{int(num):02d}"
    return None


def _clasificar_archivo(ruta: Path) -> str:
    """Devuelve: 'codigo' | 'libro' | 'documento' | 'comprimido' | 'otro'."""
    ext = ruta.suffix.lower()
    if ext in _EXT_CODIGO:
        return "codigo"
    if ext in _EXT_COMPRIMIDO:
        return "comprimido"
    if ext == ".pdf":
        paginas = contar_paginas_pdf(ruta)
        return "libro" if (paginas is not None and paginas > _UMBRAL_LIBRO) else "documento"
    if ext in {".epub", ".mobi"}:
        return "libro"
    if ext in _EXT_DOCUMENTO:
        return "documento"
    return "otro"


# ─── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class ArchivoEscolar:
    ruta: Path
    semestre: str      # ej. "Sem01"
    materia: str       # nombre de la carpeta de materia
    categoria: str     # codigo | libro | documento | comprimido | otro
    tamanio: int = 0


@dataclass
class ResultadoPaso8:
    archivos: list[ArchivoEscolar] = field(default_factory=list)
    semestres_detectados: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.archivos)

    @property
    def total_bytes(self) -> int:
        return sum(a.tamanio for a in self.archivos)

    def por_semestre(self) -> dict[str, list[ArchivoEscolar]]:
        grupos: dict[str, list[ArchivoEscolar]] = {}
        for a in self.archivos:
            grupos.setdefault(a.semestre, []).append(a)
        return dict(sorted(grupos.items()))

    def por_categoria(self) -> dict[str, int]:
        conteo: dict[str, int] = {}
        for a in self.archivos:
            conteo[a.categoria] = conteo.get(a.categoria, 0) + 1
        return dict(sorted(conteo.items(), key=lambda x: -x[1]))


@dataclass
class MovimientoEscolar:
    origen: Path
    destino: Path
    semestre: str
    materia: str
    categoria: str
    tamanio: int


@dataclass
class PlanPaso8:
    movimientos: list[MovimientoEscolar] = field(default_factory=list)
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


# ─── Detección ───────────────────────────────────────────────────────────────

def detectar_estructura_escolar(directorio: str | Path) -> ResultadoPaso8:
    """
    Escanea buscando la estructura Semestre N / Materia / archivos.
    Si no encuentra semestres, trata el nivel raíz como materias de un semestre genérico.
    """
    directorio = Path(directorio)
    resultado = ResultadoPaso8()
    semestres_vistos: set[str] = set()

    for carpeta_sem in sorted(directorio.iterdir()):
        if not carpeta_sem.is_dir():
            continue

        sem_id = _normalizar_semestre(carpeta_sem.name)

        if sem_id:
            semestres_vistos.add(sem_id)
            # Nivel 2: materias
            for carpeta_mat in sorted(carpeta_sem.iterdir()):
                if not carpeta_mat.is_dir():
                    # Archivo suelto en la raíz del semestre
                    _agregar_archivo(resultado, carpeta_mat, sem_id, "_general")
                    continue
                materia = sanitizar_nombre(carpeta_mat.name)
                for raiz, _, archivos in os.walk(str(carpeta_mat)):
                    for nombre in archivos:
                        _agregar_archivo(resultado, Path(raiz) / nombre, sem_id, materia)
        else:
            # Carpeta no reconocida como semestre → omitir (no es estructura escolar)
            continue

    resultado.semestres_detectados = sorted(semestres_vistos)
    return resultado


def _agregar_archivo(resultado: ResultadoPaso8, ruta: Path, semestre: str, materia: str) -> None:
    if not ruta.is_file():
        return
    try:
        tamanio = ruta.stat().st_size
    except OSError:
        tamanio = 0
    categoria = _clasificar_archivo(ruta)
    resultado.archivos.append(ArchivoEscolar(
        ruta=ruta,
        semestre=semestre,
        materia=materia,
        categoria=categoria,
        tamanio=tamanio,
    ))


# ─── Plan ────────────────────────────────────────────────────────────────────

def construir_plan(
    resultado: ResultadoPaso8,
    destino: str | Path,
    mapa_semestres: dict[str, str] | None = None,
    mapa_materias: dict[str, str] | None = None,
) -> PlanPaso8:
    """
    Construye el plan de movimientos.
    destino = base del HDD organizado (la misma que usan los demás pasos).
    mapa_semestres: opcional — mapea 'Sem01' → 'S01_2011-1'. Por defecto usa MAPA_SEMESTRES_UNAM.
    mapa_materias: opcional — mapea nombre HDD → nombre canónico. Por defecto usa MAPA_MATERIAS_UNAM.
    """
    destino = Path(destino)
    plan = PlanPaso8()
    _mapa_sem = mapa_semestres if mapa_semestres is not None else MAPA_SEMESTRES_UNAM
    _mapa_mat = mapa_materias if mapa_materias is not None else MAPA_MATERIAS_UNAM

    for archivo in resultado.archivos:
        sem_raw = archivo.semestre
        sem = _mapa_sem.get(sem_raw, sem_raw)
        mat_raw = sanitizar_nombre(archivo.materia)
        mat = _mapa_mat.get(archivo.materia.lower().strip(), mat_raw)

        if archivo.categoria == "codigo":
            dest_base = destino / "09_codigo" / "escolar" / sem / mat / archivo.ruta.name
        elif archivo.categoria == "libro":
            dest_base = destino / "04_libros" / "escolar" / archivo.ruta.name
        elif archivo.categoria == "documento":
            dest_base = destino / "07_escuela" / sem / mat / archivo.ruta.name
        elif archivo.categoria == "comprimido":
            dest_base = destino / "_pendientes" / "checar" / sem / mat / archivo.ruta.name
        else:
            dest_base = destino / "_pendientes" / "sin_clasificar" / sem / mat / archivo.ruta.name

        ruta_dest = resolver_destino(archivo.ruta, dest_base)
        if ruta_dest is None:
            plan.omitidos_identicos.append(str(archivo.ruta))
            continue

        plan.movimientos.append(MovimientoEscolar(
            origen=archivo.ruta,
            destino=ruta_dest,
            semestre=sem,
            materia=mat,
            categoria=archivo.categoria,
            tamanio=archivo.tamanio,
        ))
        plan.total_bytes += archivo.tamanio

    return plan


# ─── Ejecución ───────────────────────────────────────────────────────────────

def ejecutar_plan(
    plan: PlanPaso8,
    log_path: str | Path,
    dry_run: bool = True,
) -> ResultadoEjecucion:
    log_path = Path(log_path)
    resultado = ResultadoEjecucion(
        log_path=str(log_path),
        omitidos_identicos=list(plan.omitidos_identicos),
    )

    if dry_run:
        for mov in plan.movimientos:
            resultado.movidos.append({
                "origen": str(mov.origen),
                "destino": str(mov.destino),
                "semestre": mov.semestre,
                "materia": mov.materia,
                "categoria": mov.categoria,
            })
        return resultado

    reversion = {
        "timestamp": datetime.now().isoformat(),
        "paso": 8,
        "movimientos": [
            {"origen": str(m.destino), "destino": str(m.origen)}
            for m in plan.movimientos
        ],
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(reversion, ensure_ascii=False, indent=2), encoding="utf-8")

    for mov in plan.movimientos:
        try:
            mov.destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(mov.origen), str(mov.destino))
            resultado.movidos.append({
                "origen": str(mov.origen),
                "destino": str(mov.destino),
                "semestre": mov.semestre,
                "materia": mov.materia,
                "categoria": mov.categoria,
            })
        except (OSError, shutil.Error) as e:
            resultado.errores.append({"origen": str(mov.origen), "error": str(e)})

    return resultado
