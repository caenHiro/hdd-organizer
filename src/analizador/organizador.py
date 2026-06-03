"""
Organizador de archivos — mover-en-bloque con log de reversión.

Principio: toda operación destructiva requiere --confirmar explícito.
Sin --confirmar, siempre es dry-run y solo muestra el plan.
"""
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ReglaMovimiento:
    destino: str
    tipo: str | None = None
    extension: str | None = None
    directorio_origen: str | None = None


@dataclass
class MovimientoPlan:
    origen: str
    destino: str
    nombre: str
    tamanio: int
    tipo: str


@dataclass
class ResultadoMovimiento:
    movidos: list[dict] = field(default_factory=list)
    errores: list[dict] = field(default_factory=list)
    omitidos: list[dict] = field(default_factory=list)
    log_path: str = ""


def construir_plan(
    archivos: list[dict],
    regla: ReglaMovimiento,
    excluir: list[str] | None = None,
) -> list[MovimientoPlan]:
    """
    Dado un listado de archivos (dicts con 'ruta', 'nombre', 'tamanio', 'tipo'),
    construye el plan de movimiento aplicando la regla y excluyendo rutas prohibidas.
    """
    rutas_excluidas = [Path(e).resolve() for e in (excluir or [])]
    plan: list[MovimientoPlan] = []
    destino_base = Path(regla.destino)

    for arch in archivos:
        ruta_origen = Path(arch["ruta"])

        # Verificar exclusiones
        excluido = any(
            str(ruta_origen).startswith(str(ex))
            for ex in rutas_excluidas
        )
        if excluido:
            continue

        ruta_destino = destino_base / arch["nombre"]
        # Evitar colisiones: añadir sufijo numérico si ya existe el nombre
        if ruta_destino.exists():
            stem = ruta_destino.stem
            suffix = ruta_destino.suffix
            i = 1
            while ruta_destino.exists():
                ruta_destino = destino_base / f"{stem}_{i}{suffix}"
                i += 1

        plan.append(MovimientoPlan(
            origen=str(ruta_origen),
            destino=str(ruta_destino),
            nombre=arch["nombre"],
            tamanio=arch.get("tamanio", 0),
            tipo=arch.get("tipo", "otro"),
        ))

    return plan


def ejecutar_plan(
    plan: list[MovimientoPlan],
    log_path: str,
    dry_run: bool = True,
) -> ResultadoMovimiento:
    """
    Ejecuta el plan de movimiento.
    - dry_run=True (default): no mueve nada, solo reporta.
    - dry_run=False: escribe log de reversión ANTES de mover, luego mueve.
    """
    resultado = ResultadoMovimiento(log_path=log_path)

    if dry_run:
        for mov in plan:
            resultado.movidos.append({
                "origen": mov.origen,
                "destino": mov.destino,
                "nombre": mov.nombre,
                "tamanio": mov.tamanio,
            })
        return resultado

    # Escribir log de reversión antes de mover nada
    reversion = {
        "timestamp": datetime.now().isoformat(),
        "movimientos": [
            {"origen": m.destino, "destino": m.origen}  # invertido para deshacer
            for m in plan
        ],
    }
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    Path(log_path).write_text(json.dumps(reversion, indent=2, ensure_ascii=False), encoding="utf-8")

    for mov in plan:
        try:
            destino_path = Path(mov.destino)
            destino_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(mov.origen, mov.destino)
            resultado.movidos.append({
                "origen": mov.origen,
                "destino": mov.destino,
                "nombre": mov.nombre,
                "tamanio": mov.tamanio,
            })
        except (OSError, shutil.Error) as e:
            resultado.errores.append({
                "origen": mov.origen,
                "destino": mov.destino,
                "error": str(e),
            })

    return resultado


def deshacer_movimiento(log_path: str, dry_run: bool = True) -> ResultadoMovimiento:
    """
    Lee el log de reversión y deshace los movimientos.
    - dry_run=True: solo muestra qué haría.
    - dry_run=False: mueve los archivos de vuelta a su posición original.
    """
    resultado = ResultadoMovimiento(log_path=log_path)
    ruta_log = Path(log_path)

    if not ruta_log.exists():
        raise FileNotFoundError(f"Log de reversión no encontrado: {log_path}")

    datos = json.loads(ruta_log.read_text(encoding="utf-8"))
    movimientos = datos.get("movimientos", [])

    for mov in movimientos:
        origen = mov["origen"]   # destino original (archivo está aquí)
        destino = mov["destino"] # ruta original (a donde volver)

        if not Path(origen).exists():
            resultado.errores.append({"origen": origen, "destino": destino, "error": "archivo no encontrado"})
            continue

        if dry_run:
            resultado.movidos.append({"origen": origen, "destino": destino})
            continue

        try:
            Path(destino).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(origen, destino)
            resultado.movidos.append({"origen": origen, "destino": destino})
        except (OSError, shutil.Error) as e:
            resultado.errores.append({"origen": origen, "destino": destino, "error": str(e)})

    return resultado
