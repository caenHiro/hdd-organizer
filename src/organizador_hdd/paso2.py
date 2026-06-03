"""
Paso 2 — Biblioteca Calibre.

Detecta la raíz de una biblioteca Calibre buscando directorios que contienen
subdirectorios con archivos 'metadata.opf' (un archivo por libro).
Mueve la biblioteca completa a 04_libros/calibre/.

Calibre organiza los libros como:
    <Biblioteca>/
        <Autor>/
            <Titulo> (<anio>)/
                metadata.opf
                libro.epub
                cover.jpg
"""
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


_MIN_LIBROS_PARA_DETECTAR = 3  # mínimo de libros para considerar una carpeta como Calibre


@dataclass
class ResultadoPaso2:
    biblioteca: Path | None = None    # ruta raíz de la biblioteca Calibre
    total_libros: int = 0
    total_bytes: int = 0

    @property
    def encontrada(self) -> bool:
        return self.biblioteca is not None


@dataclass
class PlanPaso2:
    origen: Path | None = None
    destino: Path | None = None
    total_bytes: int = 0

    def __bool__(self) -> bool:
        return self.origen is not None


@dataclass
class ResultadoEjecucion:
    exito: bool = False
    error: str = ""
    log_path: str = ""


def _contar_libros(directorio: Path) -> tuple[int, int]:
    """Cuenta libros (dirs con metadata.opf) y suma bytes bajo un directorio."""
    total_libros = 0
    total_bytes = 0
    for raiz, _, archivos in os.walk(str(directorio)):
        if "metadata.opf" in archivos:
            total_libros += 1
        for a in archivos:
            try:
                total_bytes += (Path(raiz) / a).stat().st_size
            except OSError:
                pass
    return total_libros, total_bytes


def detectar_calibre(directorio: str | Path) -> ResultadoPaso2:
    """
    Busca la raíz de una biblioteca Calibre en directorio.
    Una carpeta es Calibre si contiene >= _MIN_LIBROS_PARA_DETECTAR subdirs con metadata.opf.
    Retorna el primer candidato encontrado.
    """
    directorio = Path(directorio)
    resultado = ResultadoPaso2()

    for raiz, dirs, _ in os.walk(str(directorio)):
        raiz_path = Path(raiz)
        libros_directos = 0

        for d in dirs:
            subdir = raiz_path / d
            # Un libro Calibre tiene metadata.opf dentro del directorio del título
            for subsubdir in subdir.iterdir() if subdir.is_dir() else []:
                if subsubdir.is_dir() and (subsubdir / "metadata.opf").exists():
                    libros_directos += 1
                    break
            # También puede estar directamente en el primer nivel (autor como carpeta raíz)
            if (subdir / "metadata.opf").exists():
                libros_directos += 1

        if libros_directos >= _MIN_LIBROS_PARA_DETECTAR:
            libros, bytes_total = _contar_libros(raiz_path)
            resultado.biblioteca = raiz_path
            resultado.total_libros = libros
            resultado.total_bytes = bytes_total
            return resultado

    return resultado


def construir_plan(resultado: ResultadoPaso2, destino: str | Path) -> PlanPaso2:
    """Construye el plan para mover la biblioteca Calibre a destino/calibre/."""
    if not resultado.encontrada:
        return PlanPaso2()
    destino_final = Path(destino) / "calibre"
    return PlanPaso2(
        origen=resultado.biblioteca,
        destino=destino_final,
        total_bytes=resultado.total_bytes,
    )


def ejecutar_plan(
    plan: PlanPaso2,
    log_path: str | Path,
    dry_run: bool = True,
) -> ResultadoEjecucion:
    """Mueve la biblioteca Calibre al destino. dry_run=True solo reporta."""
    log_path = Path(log_path)
    if not plan:
        return ResultadoEjecucion(exito=True, log_path=str(log_path))

    if dry_run:
        return ResultadoEjecucion(exito=True, log_path=str(log_path))

    # Escribir log de reversión antes de mover
    reversion = {
        "timestamp": datetime.now().isoformat(),
        "paso": 2,
        "movimientos": [{"origen": str(plan.destino), "destino": str(plan.origen)}],
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps(reversion, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    try:
        plan.destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(plan.origen), str(plan.destino))
        return ResultadoEjecucion(exito=True, log_path=str(log_path))
    except (OSError, shutil.Error) as e:
        return ResultadoEjecucion(exito=False, error=str(e), log_path=str(log_path))
