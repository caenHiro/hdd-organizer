"""Tests para paso8 — datos escolares."""
import shutil
from pathlib import Path

import pytest

from src.organizador_hdd.paso8 import (
    _normalizar_semestre,
    _clasificar_archivo,
    detectar_estructura_escolar,
    construir_plan,
    ejecutar_plan,
)


# ─── _normalizar_semestre ─────────────────────────────────────────────────────

@pytest.mark.parametrize("nombre,esperado", [
    ("Semestre 1",  "Sem01"),
    ("semestre 12", "Sem12"),
    ("Sem 3",       "Sem03"),
    ("Sem3",        "Sem03"),
    ("1er semestre","Sem01"),
    ("2",           "Sem02"),
    ("Trabajo",     None),
    ("Downloads",   None),
])
def test_normalizar_semestre(nombre, esperado):
    assert _normalizar_semestre(nombre) == esperado


# ─── _clasificar_archivo ──────────────────────────────────────────────────────

def test_clasifica_codigo(tmp_path):
    f = tmp_path / "practica.py"
    f.write_text("print('hola')")
    assert _clasificar_archivo(f) == "codigo"


def test_clasifica_comprimido(tmp_path):
    f = tmp_path / "entrega.zip"
    f.write_bytes(b"PK\x03\x04")
    assert _clasificar_archivo(f) == "comprimido"


def test_clasifica_documento_word(tmp_path):
    f = tmp_path / "reporte.docx"
    f.write_bytes(b"\x00" * 100)
    assert _clasificar_archivo(f) == "documento"


def test_clasifica_epub_libro(tmp_path):
    f = tmp_path / "libro.epub"
    f.write_bytes(b"\x00" * 100)
    assert _clasificar_archivo(f) == "libro"


# ─── detectar_estructura_escolar ──────────────────────────────────────────────

def _crear_universidad(tmp_path: Path) -> Path:
    uni = tmp_path / "Universidad"
    (uni / "Semestre 1" / "Estructuras de Datos").mkdir(parents=True)
    (uni / "Semestre 1" / "Estructuras de Datos" / "practica1.py").write_text("x=1")
    (uni / "Semestre 1" / "Estructuras de Datos" / "apuntes.docx").write_bytes(b"\x00" * 50)
    (uni / "Semestre 2" / "Bases de Datos").mkdir(parents=True)
    (uni / "Semestre 2" / "Bases de Datos" / "consultas.sql").write_text("SELECT 1")
    (uni / "Semestre 2" / "Bases de Datos" / "notas.txt").write_text("nota")
    return uni


def test_detecta_semestres(tmp_path):
    uni = _crear_universidad(tmp_path)
    resultado = detectar_estructura_escolar(uni)
    assert "Sem01" in resultado.semestres_detectados
    assert "Sem02" in resultado.semestres_detectados


def test_detecta_archivos_en_materias(tmp_path):
    uni = _crear_universidad(tmp_path)
    resultado = detectar_estructura_escolar(uni)
    assert resultado.total == 4


def test_clasifica_codigo_en_resultado(tmp_path):
    uni = _crear_universidad(tmp_path)
    resultado = detectar_estructura_escolar(uni)
    codigos = [a for a in resultado.archivos if a.categoria == "codigo"]
    assert len(codigos) == 2  # practica1.py + consultas.sql


def test_materia_asignada(tmp_path):
    uni = _crear_universidad(tmp_path)
    resultado = detectar_estructura_escolar(uni)
    ed = [a for a in resultado.archivos if "Datos" in a.materia]
    assert len(ed) > 0
    assert ed[0].semestre == "Sem01"


def test_carpetas_no_semestre_ignoradas(tmp_path):
    uni = tmp_path / "Universidad"
    (uni / "Semestre 1" / "Materia").mkdir(parents=True)
    (uni / "Semestre 1" / "Materia" / "archivo.py").write_text("x")
    (uni / "Downloads").mkdir()
    (uni / "Downloads" / "algo.txt").write_text("algo")
    resultado = detectar_estructura_escolar(uni)
    assert resultado.total == 1  # solo archivo.py


# ─── construir_plan ───────────────────────────────────────────────────────────

def test_plan_codigo_va_a_09(tmp_path):
    uni = _crear_universidad(tmp_path)
    resultado = detectar_estructura_escolar(uni)
    plan = construir_plan(resultado, tmp_path / "org")
    codigos = [m for m in plan.movimientos if m.categoria == "codigo"]
    for mov in codigos:
        assert "09_codigo" in str(mov.destino)
        assert "escolar" in str(mov.destino)


def test_plan_documento_escolar_va_a_07(tmp_path):
    uni = _crear_universidad(tmp_path)
    resultado = detectar_estructura_escolar(uni)
    plan = construir_plan(resultado, tmp_path / "org")
    docs = [m for m in plan.movimientos if m.categoria == "documento"]
    for mov in docs:
        assert "07_escuela" in str(mov.destino)


def test_plan_semestre_en_ruta(tmp_path):
    uni = _crear_universidad(tmp_path)
    resultado = detectar_estructura_escolar(uni)
    plan = construir_plan(resultado, tmp_path / "org")
    for mov in plan.movimientos:
        if mov.categoria != "libro":
            assert mov.semestre in str(mov.destino)


def test_plan_idempotente(tmp_path):
    uni = _crear_universidad(tmp_path)
    resultado = detectar_estructura_escolar(uni)
    org = tmp_path / "org"
    # Construir plan una vez para saber la ruta real del destino
    plan_inicial = construir_plan(resultado, org)
    mov_practica = next(m for m in plan_inicial.movimientos if "practica1" in m.origen.name)
    # Pre-crear destino con mismo contenido
    mov_practica.destino.parent.mkdir(parents=True)
    mov_practica.destino.write_text("x=1")
    # Reconstruir plan — ahora debe omitir el archivo
    plan = construir_plan(resultado, org)
    omitidos = [m for m in plan.omitidos_identicos if "practica1" in m]
    assert len(omitidos) == 1


# ─── ejecutar_plan ────────────────────────────────────────────────────────────

def test_ejecutar_mueve_archivos(tmp_path):
    uni = _crear_universidad(tmp_path)
    resultado = detectar_estructura_escolar(uni)
    plan = construir_plan(resultado, tmp_path / "org")
    ejec = ejecutar_plan(plan, tmp_path / "log.json", dry_run=False)
    assert len(ejec.movidos) == resultado.total
    assert (tmp_path / "log.json").exists()


def test_ejecutar_dry_run_no_mueve(tmp_path):
    uni = _crear_universidad(tmp_path)
    resultado = detectar_estructura_escolar(uni)
    plan = construir_plan(resultado, tmp_path / "org")
    ejec = ejecutar_plan(plan, tmp_path / "log.json", dry_run=True)
    assert len(ejec.movidos) > 0
    # Los archivos originales deben seguir en su lugar
    assert (uni / "Semestre 1" / "Estructuras de Datos" / "practica1.py").exists()
