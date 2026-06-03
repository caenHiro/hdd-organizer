"""
Paso 1 — Artefactos técnicos.

Detecta archivos y carpetas que son residuos de compilación, builds o
sistemas de control de versiones: bytecode Java, caché Maven, SVN, node_modules, etc.

Solo lectura por defecto. El movimiento requiere llamar a ejecutar_plan con dry_run=False.
"""
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .utils import resolver_destino

_CONFIG_PATH = Path(__file__).parent / "config.json"


def _cargar_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)["paso1"]


@dataclass
class Artefacto:
    ruta: Path
    razon: str   # "extension", "nombre_exacto", "carpeta"
    tamanio: int = 0


@dataclass
class ResultadoPaso1:
    archivos: list[Artefacto] = field(default_factory=list)
    carpetas: list[Path] = field(default_factory=list)

    @property
    def total_archivos(self) -> int:
        return len(self.archivos)

    @property
    def total_bytes(self) -> int:
        return sum(a.tamanio for a in self.archivos)

    def por_extension(self) -> dict[str, int]:
        conteo: dict[str, int] = {}
        for a in self.archivos:
            ext = a.ruta.suffix.lower() or a.ruta.name
            conteo[ext] = conteo.get(ext, 0) + 1
        return dict(sorted(conteo.items(), key=lambda x: -x[1]))


@dataclass
class PlanPaso1:
    movimientos: list[dict] = field(default_factory=list)  # {origen, destino, tipo}
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


def _carpeta_tiene_clases(carpeta: Path) -> bool:
    """Verdadero si la carpeta contiene al menos un .class (confirma build Maven/Gradle)."""
    try:
        return next(carpeta.rglob("*.class"), None) is not None
    except (PermissionError, OSError):
        return False


def detectar_artefactos(
    directorio: str | Path,
    config: dict | None = None,
) -> ResultadoPaso1:
    """
    Escanea directorio buscando artefactos técnicos. Solo lectura.

    Usa os.walk para no descender dentro de carpetas ya marcadas como artefacto,
    evitando iterar los millones de archivos dentro de node_modules/.m2/target/etc.
    """
    directorio = Path(directorio)
    cfg = config or _cargar_config()
    resultado = ResultadoPaso1()

    extensiones = frozenset(cfg.get("extensiones", []))
    nombres_exactos = frozenset(cfg.get("nombres_exactos", []))
    carpetas_siempre = frozenset(cfg.get("carpetas_siempre", []))
    carpetas_condicionales = frozenset(cfg.get("carpetas_si_contienen_class", []))
    detectar_m2 = cfg.get("carpetas_maven_m2", True)

    carpetas_excluidas: set[str] = set()

    for raiz_str, dirs, archivos in os.walk(str(directorio)):
        raiz = Path(raiz_str)

        # Marcar carpetas artefacto y evitar descender en ellas
        dirs_excluir: list[str] = []
        for d in dirs:
            ruta_d = raiz / d
            es_artefacto = False

            if d in carpetas_siempre:
                es_artefacto = True
            elif d in carpetas_condicionales and _carpeta_tiene_clases(ruta_d):
                es_artefacto = True
            elif detectar_m2 and d == "repository" and raiz.name == ".m2":
                es_artefacto = True

            if es_artefacto:
                resultado.carpetas.append(ruta_d)
                carpetas_excluidas.add(str(ruta_d.resolve()))
                dirs_excluir.append(d)

        for d in dirs_excluir:
            dirs.remove(d)

        # Archivos sueltos no dentro de carpetas ya marcadas
        for nombre in archivos:
            ruta_archivo = raiz / nombre

            razon: str | None = None
            if nombre in nombres_exactos:
                razon = "nombre_exacto"
            elif Path(nombre).suffix.lower() in extensiones:
                razon = "extension"

            if razon:
                try:
                    tamanio = ruta_archivo.stat().st_size
                except OSError:
                    tamanio = 0
                resultado.archivos.append(Artefacto(
                    ruta=ruta_archivo,
                    razon=razon,
                    tamanio=tamanio,
                ))

    return resultado


def construir_plan(
    resultado: ResultadoPaso1,
    destino: str | Path,
) -> PlanPaso1:
    """Construye el plan de movimientos a partir de lo detectado en Paso 1."""
    destino = Path(destino)
    plan = PlanPaso1()

    for artefacto in resultado.archivos:
        ruta_dest = resolver_destino(artefacto.ruta, destino / "archivos" / artefacto.ruta.name)
        if ruta_dest is None:
            plan.omitidos_identicos.append(str(artefacto.ruta))
            continue
        plan.movimientos.append({
            "origen": str(artefacto.ruta),
            "destino": str(ruta_dest),
            "tipo": "archivo",
            "tamanio": artefacto.tamanio,
        })
        plan.total_bytes += artefacto.tamanio

    for carpeta in resultado.carpetas:
        ruta_dest = destino / "carpetas" / carpeta.name
        if ruta_dest.exists():
            i = 2
            while ruta_dest.exists():
                ruta_dest = ruta_dest.parent / f"{carpeta.name}_{i}"
                i += 1
        plan.movimientos.append({
            "origen": str(carpeta),
            "destino": str(ruta_dest),
            "tipo": "carpeta",
            "tamanio": 0,
        })

    return plan


def ejecutar_plan(
    plan: PlanPaso1,
    log_path: str | Path,
    dry_run: bool = True,
) -> ResultadoEjecucion:
    """
    Ejecuta el plan de Paso 1.
    - dry_run=True (default): solo reporta, no mueve.
    - dry_run=False: escribe log de reversión ANTES de mover.
    """
    log_path = Path(log_path)
    resultado = ResultadoEjecucion(
        log_path=str(log_path),
        omitidos_identicos=list(plan.omitidos_identicos),
    )

    if dry_run:
        for mov in plan.movimientos:
            resultado.movidos.append(mov)
        return resultado

    # Escribir log de reversión antes de mover nada
    reversion = {
        "timestamp": datetime.now().isoformat(),
        "paso": 1,
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
        except (OSError, shutil.Error) as e:
            resultado.errores.append({**mov, "error": str(e)})

    return resultado
