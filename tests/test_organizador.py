import json
import shutil
from pathlib import Path
import pytest
from src.analizador.organizador import (
    ReglaMovimiento,
    construir_plan,
    ejecutar_plan,
    deshacer_movimiento,
)


def _archivos_prueba(tmp_path: Path) -> list[dict]:
    (tmp_path / "fotos").mkdir()
    (tmp_path / "docs").mkdir()
    for nombre, contenido in [
        ("foto1.jpg", b"img1"), ("foto2.jpg", b"img2"), ("doc1.pdf", b"pdf1")
    ]:
        carpeta = "fotos" if nombre.endswith(".jpg") else "docs"
        p = tmp_path / carpeta / nombre
        p.write_bytes(contenido)

    return [
        {"ruta": str(tmp_path / "fotos" / "foto1.jpg"), "nombre": "foto1.jpg", "tipo": "imagen", "tamanio": 4},
        {"ruta": str(tmp_path / "fotos" / "foto2.jpg"), "nombre": "foto2.jpg", "tipo": "imagen", "tamanio": 4},
        {"ruta": str(tmp_path / "docs" / "doc1.pdf"),   "nombre": "doc1.pdf",  "tipo": "documento", "tamanio": 4},
    ]


class TestConstruirPlan:
    def test_plan_tiene_todos_los_archivos(self, tmp_path):
        archivos = _archivos_prueba(tmp_path)
        regla = ReglaMovimiento(destino=str(tmp_path / "destino"))
        plan = construir_plan(archivos, regla)
        assert len(plan) == 3

    def test_excluir_evita_archivos(self, tmp_path):
        archivos = _archivos_prueba(tmp_path)
        regla = ReglaMovimiento(destino=str(tmp_path / "destino"))
        excluir = [str(tmp_path / "fotos")]
        plan = construir_plan(archivos, regla, excluir=excluir)
        assert len(plan) == 1
        assert plan[0].nombre == "doc1.pdf"

    def test_destino_en_plan(self, tmp_path):
        archivos = _archivos_prueba(tmp_path)
        destino = str(tmp_path / "destino")
        regla = ReglaMovimiento(destino=destino)
        plan = construir_plan(archivos, regla)
        assert all(m.destino.startswith(destino) for m in plan)

    def test_plan_vacio_si_todo_excluido(self, tmp_path):
        archivos = _archivos_prueba(tmp_path)
        regla = ReglaMovimiento(destino=str(tmp_path / "destino"))
        excluir = [str(tmp_path)]
        plan = construir_plan(archivos, regla, excluir=excluir)
        assert plan == []


class TestEjecutarPlanDryRun:
    def test_dry_run_no_mueve_archivos(self, tmp_path):
        archivos = _archivos_prueba(tmp_path)
        regla = ReglaMovimiento(destino=str(tmp_path / "destino"))
        plan = construir_plan(archivos, regla)

        resultado = ejecutar_plan(plan, log_path=str(tmp_path / "log.json"), dry_run=True)

        assert len(resultado.movidos) == 3
        assert not (tmp_path / "destino").exists()

    def test_dry_run_no_escribe_log(self, tmp_path):
        archivos = _archivos_prueba(tmp_path)
        regla = ReglaMovimiento(destino=str(tmp_path / "destino"))
        plan = construir_plan(archivos, regla)
        log_path = str(tmp_path / "log.json")

        ejecutar_plan(plan, log_path=log_path, dry_run=True)

        assert not Path(log_path).exists()


class TestEjecutarPlanReal:
    def test_mueve_archivos(self, tmp_path):
        archivos = _archivos_prueba(tmp_path)
        destino = tmp_path / "destino"
        regla = ReglaMovimiento(destino=str(destino))
        plan = construir_plan(archivos, regla)

        resultado = ejecutar_plan(plan, log_path=str(tmp_path / "log.json"), dry_run=False)

        assert len(resultado.movidos) == 3
        assert len(resultado.errores) == 0
        assert (destino / "foto1.jpg").exists()
        assert (destino / "doc1.pdf").exists()

    def test_escribe_log_reversion(self, tmp_path):
        archivos = _archivos_prueba(tmp_path)
        destino = tmp_path / "destino"
        regla = ReglaMovimiento(destino=str(destino))
        plan = construir_plan(archivos, regla)
        log_path = str(tmp_path / "log.json")

        ejecutar_plan(plan, log_path=log_path, dry_run=False)

        assert Path(log_path).exists()
        datos = json.loads(Path(log_path).read_text())
        assert "movimientos" in datos
        assert len(datos["movimientos"]) == 3

    def test_archivos_originales_ya_no_existen(self, tmp_path):
        archivos = _archivos_prueba(tmp_path)
        destino = tmp_path / "destino"
        regla = ReglaMovimiento(destino=str(destino))
        plan = construir_plan(archivos, regla)

        ejecutar_plan(plan, log_path=str(tmp_path / "log.json"), dry_run=False)

        assert not (tmp_path / "fotos" / "foto1.jpg").exists()


class TestDeshacerMovimiento:
    def test_deshacer_devuelve_archivos(self, tmp_path):
        archivos = _archivos_prueba(tmp_path)
        destino = tmp_path / "destino"
        regla = ReglaMovimiento(destino=str(destino))
        plan = construir_plan(archivos, regla)
        log_path = str(tmp_path / "log.json")

        ejecutar_plan(plan, log_path=log_path, dry_run=False)
        deshacer_movimiento(log_path, dry_run=False)

        assert (tmp_path / "fotos" / "foto1.jpg").exists()
        assert (tmp_path / "fotos" / "foto2.jpg").exists()
        assert (tmp_path / "docs" / "doc1.pdf").exists()

    def test_deshacer_dry_run_no_mueve(self, tmp_path):
        archivos = _archivos_prueba(tmp_path)
        destino = tmp_path / "destino"
        regla = ReglaMovimiento(destino=str(destino))
        plan = construir_plan(archivos, regla)
        log_path = str(tmp_path / "log.json")

        ejecutar_plan(plan, log_path=log_path, dry_run=False)
        deshacer_movimiento(log_path, dry_run=True)

        # Dry-run: archivos siguen en destino
        assert (destino / "foto1.jpg").exists()

    def test_deshacer_log_inexistente_lanza_error(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            deshacer_movimiento(str(tmp_path / "no_existe.json"))
