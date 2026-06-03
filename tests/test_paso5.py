import json
from pathlib import Path
import pytest
from src.organizador_hdd.paso5 import (
    ResultadoPaso5, detectar_takeout, construir_plan, ejecutar_plan,
    _es_paquete_takeout, _categoria_desde_carpeta,
)


def _crear_takeout(tmp_path: Path) -> Path:
    """
    Crea estructura Takeout mínima:
    Takeout/
      Google Fotos/2022/foto.jpg + foto.jpg.json
      Meet Recordings/reunion.mp4
      Classroom/material.pdf
    """
    t = tmp_path / "Takeout"
    # Google Fotos con companion JSON
    fotos = t / "Google Fotos" / "2022"
    fotos.mkdir(parents=True)
    (fotos / "foto.jpg").write_bytes(b"\xff\xd8")
    (fotos / "foto.jpg.json").write_text(json.dumps({
        "photoTakenTime": {"timestamp": "1640995200"}  # 2022-01-01
    }))
    # Meet Recordings
    meet = t / "Meet Recordings"
    meet.mkdir()
    (meet / "reunion.mp4").write_bytes(b"\x00\x00\x00\x1c")
    # Classroom
    cls = t / "Classroom"
    cls.mkdir()
    (cls / "material.pdf").write_bytes(b"%PDF")
    return t


class TestDeteccion:
    def test_es_paquete_takeout(self, tmp_path):
        t = tmp_path / "Takeout"
        (t / "Google Fotos").mkdir(parents=True)
        assert _es_paquete_takeout(t)

    def test_no_es_paquete_sin_carpetas_conocidas(self, tmp_path):
        t = tmp_path / "carpeta"
        (t / "musica").mkdir(parents=True)
        assert not _es_paquete_takeout(t)

    def test_categoria_google_fotos(self):
        assert _categoria_desde_carpeta("Google Fotos") == "01_fotos"
        assert _categoria_desde_carpeta("google fotos") == "01_fotos"

    def test_categoria_meet(self):
        assert _categoria_desde_carpeta("Meet Recordings") == "02_videos"

    def test_categoria_classroom(self):
        assert _categoria_desde_carpeta("Classroom") == "05_cursos"

    def test_categoria_desconocida(self):
        assert _categoria_desde_carpeta("AlgoRaro") == "_pendientes/checar"

    def test_detecta_paquete(self, tmp_path):
        _crear_takeout(tmp_path)
        resultado = detectar_takeout(tmp_path)
        assert len(resultado.paquetes_detectados) == 1

    def test_cuenta_archivos(self, tmp_path):
        _crear_takeout(tmp_path)
        resultado = detectar_takeout(tmp_path)
        # 3 archivos: foto.jpg, reunion.mp4, material.pdf (JSON se omite)
        assert resultado.total == 3

    def test_omite_json_companions(self, tmp_path):
        _crear_takeout(tmp_path)
        resultado = detectar_takeout(tmp_path)
        rutas = [str(a.ruta) for a in resultado.archivos]
        assert not any(r.endswith(".json") for r in rutas)

    def test_foto_tiene_fecha_json(self, tmp_path):
        _crear_takeout(tmp_path)
        resultado = detectar_takeout(tmp_path)
        fotos = [a for a in resultado.archivos if "foto.jpg" in str(a.ruta)]
        assert fotos
        assert fotos[0].fecha is not None
        assert fotos[0].fecha.year == 2022
        assert fotos[0].fuente_fecha == "json_companion"

    def test_sin_takeout_resultado_vacio(self, tmp_path):
        (tmp_path / "musica").mkdir()
        (tmp_path / "musica" / "song.mp3").write_bytes(b"\xff\xfb")
        resultado = detectar_takeout(tmp_path)
        assert resultado.total == 0


class TestPlan:
    def test_foto_va_a_01_fotos_con_fecha(self, tmp_path):
        _crear_takeout(tmp_path)
        resultado = detectar_takeout(tmp_path)
        plan = construir_plan(resultado, tmp_path / "organizado")
        fotos = [m for m in plan.movimientos if "foto.jpg" in m["destino"]]
        assert fotos
        assert "01_fotos" in fotos[0]["destino"]
        assert "2022" in fotos[0]["destino"]

    def test_video_va_a_02_videos(self, tmp_path):
        _crear_takeout(tmp_path)
        resultado = detectar_takeout(tmp_path)
        plan = construir_plan(resultado, tmp_path / "org")
        videos = [m for m in plan.movimientos if "reunion.mp4" in m["destino"]]
        assert videos
        assert "02_videos" in videos[0]["destino"]

    def test_pdf_va_a_05_cursos(self, tmp_path):
        _crear_takeout(tmp_path)
        resultado = detectar_takeout(tmp_path)
        plan = construir_plan(resultado, tmp_path / "org")
        pdfs = [m for m in plan.movimientos if "material.pdf" in m["destino"]]
        assert pdfs
        assert "05_cursos" in pdfs[0]["destino"]


class TestEjecucion:
    def test_dry_run_no_mueve(self, tmp_path):
        t = _crear_takeout(tmp_path)
        resultado = detectar_takeout(tmp_path)
        plan = construir_plan(resultado, tmp_path / "org")
        ejec = ejecutar_plan(plan, tmp_path / "log.json", dry_run=True)
        assert len(ejec.movidos) == 3
        assert (t / "Meet Recordings" / "reunion.mp4").exists()

    def test_real_mueve_y_escribe_log(self, tmp_path):
        _crear_takeout(tmp_path)
        resultado = detectar_takeout(tmp_path)
        plan = construir_plan(resultado, tmp_path / "organizado")
        log = tmp_path / "log.json"
        ejec = ejecutar_plan(plan, log, dry_run=False)
        assert len(ejec.movidos) == 3
        assert log.exists()
        datos = json.loads(log.read_text())
        assert datos["paso"] == 5
