import json
from pathlib import Path

import pytest

from src.organizador_hdd.paso2 import (
    ResultadoPaso2,
    detectar_calibre,
    construir_plan,
    ejecutar_plan,
)


def _crear_calibre(tmp_path: Path, n_libros: int = 5) -> Path:
    """Crea una estructura de biblioteca Calibre mínima."""
    biblioteca = tmp_path / "MiBiblioteca"
    for i in range(n_libros):
        libro = biblioteca / f"Autor {i}" / f"Titulo {i} (2020)"
        libro.mkdir(parents=True)
        (libro / "metadata.opf").write_text(f"<opf>{i}</opf>")
        (libro / f"libro{i}.epub").write_bytes(b"PK")
    return biblioteca


class TestDetectarCalibre:
    def test_detecta_biblioteca_simple(self, tmp_path):
        biblioteca = _crear_calibre(tmp_path)
        resultado = detectar_calibre(tmp_path)
        assert resultado.encontrada
        assert resultado.biblioteca == biblioteca

    def test_cuenta_libros(self, tmp_path):
        _crear_calibre(tmp_path, n_libros=4)
        resultado = detectar_calibre(tmp_path)
        assert resultado.total_libros == 4

    def test_no_detecta_sin_libros_suficientes(self, tmp_path):
        # Solo 2 libros — debajo del umbral de 3
        biblioteca = tmp_path / "Lib"
        for i in range(2):
            libro = biblioteca / f"Autor" / f"Titulo {i}"
            libro.mkdir(parents=True)
            (libro / "metadata.opf").write_text("<opf/>")
        resultado = detectar_calibre(tmp_path)
        assert not resultado.encontrada

    def test_no_detecta_sin_opf(self, tmp_path):
        directorio = tmp_path / "musica"
        (directorio / "artista" / "album").mkdir(parents=True)
        (directorio / "artista" / "album" / "song.mp3").write_bytes(b"\xff\xfb")
        resultado = detectar_calibre(tmp_path)
        assert not resultado.encontrada

    def test_total_bytes_no_cero(self, tmp_path):
        _crear_calibre(tmp_path, n_libros=3)
        resultado = detectar_calibre(tmp_path)
        assert resultado.total_bytes > 0


class TestConstruirPlanPaso2:
    def test_plan_con_biblioteca(self, tmp_path):
        _crear_calibre(tmp_path)
        resultado = detectar_calibre(tmp_path)
        plan = construir_plan(resultado, tmp_path / "04_libros")
        assert plan
        assert plan.destino == tmp_path / "04_libros" / "calibre"

    def test_plan_vacio_sin_biblioteca(self, tmp_path):
        resultado = ResultadoPaso2()  # sin biblioteca
        plan = construir_plan(resultado, tmp_path / "04_libros")
        assert not plan


class TestEjecutarPlanPaso2:
    def test_dry_run_no_mueve(self, tmp_path):
        _crear_calibre(tmp_path)
        resultado = detectar_calibre(tmp_path)
        plan = construir_plan(resultado, tmp_path / "libros")
        origen_original = plan.origen
        ejec = ejecutar_plan(plan, tmp_path / "log.json", dry_run=True)
        assert ejec.exito
        assert origen_original.exists()

    def test_real_mueve_biblioteca(self, tmp_path):
        biblioteca = _crear_calibre(tmp_path)
        resultado = detectar_calibre(tmp_path)
        plan = construir_plan(resultado, tmp_path / "libros")
        ejec = ejecutar_plan(plan, tmp_path / "log.json", dry_run=False)
        assert ejec.exito
        assert not biblioteca.exists()
        assert plan.destino.exists()

    def test_real_escribe_log(self, tmp_path):
        _crear_calibre(tmp_path)
        resultado = detectar_calibre(tmp_path)
        plan = construir_plan(resultado, tmp_path / "libros")
        log = tmp_path / "log.json"
        ejecutar_plan(plan, log, dry_run=False)
        assert log.exists()
        datos = json.loads(log.read_text())
        assert datos["paso"] == 2
        assert len(datos["movimientos"]) == 1
