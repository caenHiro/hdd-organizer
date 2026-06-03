import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.organizador_hdd.paso4 import (
    ArchivoImagen,
    ResultadoPaso4,
    detectar_imagenes,
    construir_plan,
    ejecutar_plan,
    _puntaje_foto,
    _fecha_desde_json_companion,
    _nombre_estandarizado,
    MESES_ES,
)


# ─── Scoring ──────────────────────────────────────────────────────────────────

class TestPuntajeFoto:
    def _exif(self, tiene_camara=False, tiene_gps=False, fecha=None,
              es_screenshot=False, es_resolucion_pantalla=False):
        mock = MagicMock()
        mock.tiene_camara = tiene_camara
        mock.tiene_gps = tiene_gps
        mock.fecha = fecha
        mock.es_screenshot_nombre = es_screenshot
        mock.es_resolucion_pantalla = es_resolucion_pantalla
        return mock

    def test_exif_camara_da_score_positivo(self, tmp_path):
        ruta = tmp_path / "IMG_1234.jpg"
        exif = self._exif(tiene_camara=True)
        with patch("src.organizador_hdd.paso4._PIL_DISPONIBLE", True):
            score = _puntaje_foto(ruta, exif, 2_000_000)
        assert score > 0

    def test_screenshot_da_score_negativo(self, tmp_path):
        ruta = tmp_path / "screenshot_001.png"
        exif = self._exif(es_screenshot=True)
        with patch("src.organizador_hdd.paso4._PIL_DISPONIBLE", True):
            score = _puntaje_foto(ruta, exif, 100_000)
        assert score < 0

    def test_resolucion_pantalla_da_score_negativo(self, tmp_path):
        ruta = tmp_path / "fondo.jpg"
        exif = self._exif(es_resolucion_pantalla=True)
        with patch("src.organizador_hdd.paso4._PIL_DISPONIBLE", True):
            score = _puntaje_foto(ruta, exif, 500_000)
        assert score < 0

    def test_nombre_camara_da_score_positivo(self, tmp_path):
        ruta = tmp_path / "IMG_20240601_123456.jpg"
        with patch("src.organizador_hdd.paso4._PIL_DISPONIBLE", False):
            score = _puntaje_foto(ruta, None, 1_600_000)
        assert score > 0

    def test_png_pequeno_da_score_negativo(self, tmp_path):
        ruta = tmp_path / "icono.png"
        with patch("src.organizador_hdd.paso4._PIL_DISPONIBLE", False):
            score = _puntaje_foto(ruta, None, 20_000)
        assert score < 0

    def test_carpeta_dcim_da_score_positivo(self, tmp_path):
        dcim = tmp_path / "DCIM" / "foto.jpg"
        dcim.parent.mkdir(parents=True, exist_ok=True)
        with patch("src.organizador_hdd.paso4._PIL_DISPONIBLE", False):
            score = _puntaje_foto(dcim, None, 500_000)
        assert score > 0

    def test_carpeta_downloads_da_score_negativo(self, tmp_path):
        dl = tmp_path / "downloads" / "imagen.jpg"
        dl.parent.mkdir(parents=True, exist_ok=True)
        with patch("src.organizador_hdd.paso4._PIL_DISPONIBLE", False):
            score = _puntaje_foto(dl, None, 100_000)
        assert score < 0


# ─── JSON companion ───────────────────────────────────────────────────────────

class TestFechaJsonCompanion:
    def test_lee_timestamp_google_photos(self, tmp_path):
        foto = tmp_path / "foto.jpg"
        foto.write_bytes(b"\xff\xd8")
        companion = tmp_path / "foto.jpg.json"
        companion.write_text(json.dumps({
            "photoTakenTime": {"timestamp": "1654041600", "formatted": "Jun 1, 2022"}
        }))
        fecha = _fecha_desde_json_companion(foto)
        assert fecha is not None
        assert fecha.year == 2022

    def test_retorna_none_sin_companion(self, tmp_path):
        foto = tmp_path / "foto.jpg"
        foto.write_bytes(b"\xff\xd8")
        assert _fecha_desde_json_companion(foto) is None

    def test_retorna_none_con_json_malformado(self, tmp_path):
        foto = tmp_path / "foto.jpg"
        foto.write_bytes(b"\xff\xd8")
        (tmp_path / "foto.jpg.json").write_text("no es json")
        assert _fecha_desde_json_companion(foto) is None


# ─── ResultadoPaso4 ───────────────────────────────────────────────────────────

class TestResultadoPaso4:
    def _make(self, tipo="foto", score=3):
        return ArchivoImagen(
            ruta=Path("f.jpg"), tamanio=100, tipo=tipo, score=score,
            fecha=None, fuente_fecha="ninguna",
            tiene_camara=False, tiene_gps=False,
        )

    def test_fotos_e_imagenes(self):
        r = ResultadoPaso4(archivos=[self._make("foto"), self._make("imagen"), self._make("foto")])
        assert r.fotos == 2
        assert r.imagenes == 1

    def test_total_bytes(self):
        r = ResultadoPaso4(archivos=[self._make() for _ in range(3)])
        assert r.total_bytes == 300


# ─── Detección ────────────────────────────────────────────────────────────────

class TestDetectarImagenes:
    def test_detecta_jpg(self, tmp_path):
        (tmp_path / "foto.jpg").write_bytes(b"\xff\xd8")
        with patch("src.organizador_hdd.paso4._PIL_DISPONIBLE", False):
            resultado = detectar_imagenes(tmp_path)
        assert resultado.total == 1

    def test_ignora_no_imagen(self, tmp_path):
        (tmp_path / "doc.pdf").write_bytes(b"%PDF")
        (tmp_path / "cancion.mp3").write_bytes(b"\xff\xfb")
        with patch("src.organizador_hdd.paso4._PIL_DISPONIBLE", False):
            resultado = detectar_imagenes(tmp_path)
        assert resultado.total == 0

    def test_no_desciende_en_destino(self, tmp_path):
        hdd = tmp_path / "hdd"
        (hdd / "foto.jpg").parent.mkdir(parents=True, exist_ok=True)
        (hdd / "foto.jpg").write_bytes(b"\xff\xd8")
        # Simular destino ya organizado
        (hdd / "01_fotos" / "2024" / "01_enero").mkdir(parents=True, exist_ok=True)
        (hdd / "01_fotos" / "2024" / "01_enero" / "otra.jpg").write_bytes(b"\xff\xd8")
        with patch("src.organizador_hdd.paso4._PIL_DISPONIBLE", False):
            resultado = detectar_imagenes(hdd)
        assert resultado.total == 1

    def test_screenshot_clasificado_como_imagen(self, tmp_path):
        (tmp_path / "screenshot_001.png").write_bytes(b"\x89PNG")
        with patch("src.organizador_hdd.paso4._PIL_DISPONIBLE", False):
            resultado = detectar_imagenes(tmp_path)
        assert resultado.archivos[0].tipo == "imagen"

    def test_img_nombre_camara_clasificado_como_foto(self, tmp_path):
        (tmp_path / "IMG_20240601_123456.jpg").write_bytes(b"\xff\xd8")
        with patch("src.organizador_hdd.paso4._PIL_DISPONIBLE", False):
            resultado = detectar_imagenes(tmp_path)
        assert resultado.archivos[0].tipo == "foto"


# ─── Plan ─────────────────────────────────────────────────────────────────────

_VERIFICAR_OK_P4 = patch("src.organizador_hdd.paso4.verificar_archivo", return_value=(True, ""))


class TestConstruirPlanPaso4:
    def _archivo(self, tipo="foto", fecha=None, nombre="foto.jpg"):
        return ArchivoImagen(
            ruta=Path(f"/hdd/{nombre}"), tamanio=500_000, tipo=tipo,
            score=3 if tipo == "foto" else -2,
            fecha=fecha, fuente_fecha="exif" if fecha else "ninguna",
            tiene_camara=tipo == "foto", tiene_gps=False,
        )

    def test_foto_con_fecha_va_a_anio_mes(self, tmp_path):
        fecha = datetime(2024, 6, 15)
        resultado = ResultadoPaso4(archivos=[self._archivo("foto", fecha)])
        with _VERIFICAR_OK_P4:
            plan = construir_plan(resultado, tmp_path)
        destino = Path(plan.movimientos[0]["destino"])
        assert "01_fotos" in destino.parts
        assert "2024" in destino.parts
        assert "06_junio" in destino.parts

    def test_foto_sin_fecha_va_a_sin_fecha(self, tmp_path):
        resultado = ResultadoPaso4(archivos=[self._archivo("foto", None)])
        with _VERIFICAR_OK_P4:
            plan = construir_plan(resultado, tmp_path)
        destino = Path(plan.movimientos[0]["destino"])
        assert "_sin_fecha" in destino.parts

    def test_imagen_va_a_sin_categoria(self, tmp_path):
        resultado = ResultadoPaso4(archivos=[self._archivo("imagen")])
        with _VERIFICAR_OK_P4:
            plan = construir_plan(resultado, tmp_path)
        destino = Path(plan.movimientos[0]["destino"])
        assert "01b_imagenes" in destino.parts
        assert "_sin_categoria" in destino.parts

    def test_meses_es_todos_presentes(self):
        assert len(MESES_ES) == 12
        assert MESES_ES[1] == "01_enero"
        assert MESES_ES[12] == "12_diciembre"


# ─── Ejecución ────────────────────────────────────────────────────────────────

class TestEjecutarPlanPaso4:
    def test_dry_run_no_mueve(self, tmp_path):
        origen = tmp_path / "foto.jpg"
        origen.write_bytes(b"\xff\xd8")
        resultado = ResultadoPaso4(archivos=[
            ArchivoImagen(
                ruta=origen, tamanio=100, tipo="foto", score=5,
                fecha=datetime(2024, 1, 1), fuente_fecha="exif",
                tiene_camara=True, tiene_gps=False,
            )
        ])
        with _VERIFICAR_OK_P4:
            plan = construir_plan(resultado, tmp_path / "organizado")
        ejec = ejecutar_plan(plan, tmp_path / "log.json", dry_run=True)
        assert origen.exists()
        assert len(ejec.movidos) == 1

    def test_real_mueve_y_crea_estructura(self, tmp_path):
        hdd = tmp_path / "hdd"
        hdd.mkdir()
        origen = hdd / "IMG_20240615.jpg"
        origen.write_bytes(b"\xff\xd8")
        resultado = ResultadoPaso4(archivos=[
            ArchivoImagen(
                ruta=origen, tamanio=100, tipo="foto", score=5,
                fecha=datetime(2024, 6, 15), fuente_fecha="exif",
                tiene_camara=True, tiene_gps=False,
            )
        ])
        destino_base = tmp_path / "organizado"
        with _VERIFICAR_OK_P4:
            plan = construir_plan(resultado, destino_base)
        ejec = ejecutar_plan(plan, tmp_path / "log.json", dry_run=False)
        assert not origen.exists()
        destino = Path(ejec.movidos[0]["destino"])
        assert destino.exists()
        assert "2024" in str(destino)
        assert "06_junio" in str(destino)

    def test_escribe_log_paso4(self, tmp_path):
        origen = tmp_path / "f.jpg"
        origen.write_bytes(b"\xff\xd8")
        resultado = ResultadoPaso4(archivos=[
            ArchivoImagen(
                ruta=origen, tamanio=10, tipo="foto", score=5,
                fecha=None, fuente_fecha="ninguna",
                tiene_camara=False, tiene_gps=False,
            )
        ])
        with _VERIFICAR_OK_P4:
            plan = construir_plan(resultado, tmp_path / "org")
        log = tmp_path / "log.json"
        ejecutar_plan(plan, log, dry_run=False)
        datos = json.loads(log.read_text())
        assert datos["paso"] == 4


# ─── Nombre estandarizado ─────────────────────────────────────────────────────

class TestNombreEstandarizado:
    def _archivo(self, nombre, fuente="exif", fecha=None):
        return ArchivoImagen(
            ruta=Path(f"/hdd/{nombre}"), tamanio=100, tipo="foto", score=5,
            fecha=fecha, fuente_fecha=fuente,
            tiene_camara=True, tiene_gps=False,
        )

    def test_exif_genera_nombre_timestamp(self):
        a = self._archivo("IMG_1234.jpg", fuente="exif", fecha=datetime(2024, 6, 15, 10, 30, 45))
        assert _nombre_estandarizado(a) == "2024-06-15_103045.jpg"

    def test_json_companion_genera_nombre_timestamp(self):
        a = self._archivo("foto.JPG", fuente="json_companion", fecha=datetime(2023, 1, 1, 0, 0, 0))
        assert _nombre_estandarizado(a) == "2023-01-01_000000.jpg"

    def test_mtime_conserva_nombre_original(self):
        a = self._archivo("foto_vieja.jpg", fuente="mtime", fecha=datetime(2020, 1, 1))
        assert _nombre_estandarizado(a) == "foto_vieja.jpg"

    def test_sin_fecha_conserva_nombre_original(self):
        a = self._archivo("descarga.jpg", fuente="ninguna", fecha=None)
        assert _nombre_estandarizado(a) == "descarga.jpg"

    def test_extension_queda_minuscula(self):
        a = self._archivo("IMG.JPEG", fuente="exif", fecha=datetime(2024, 3, 5, 8, 0, 0))
        assert _nombre_estandarizado(a).endswith(".jpeg")


# ─── Archivos dañados en el plan ──────────────────────────────────────────────

class TestArchivosDanadosPlan:
    def test_archivo_danado_va_a_danados(self, tmp_path):
        origen = tmp_path / "rota.jpg"
        origen.write_bytes(b"\xff\xd8")  # bytes mínimos pero Pillow no está en tests
        resultado = ResultadoPaso4(archivos=[
            ArchivoImagen(
                ruta=origen, tamanio=2, tipo="foto", score=5,
                fecha=datetime(2024, 1, 1), fuente_fecha="exif",
                tiene_camara=True, tiene_gps=False,
            )
        ])
        # Simular que verificar_archivo devuelve error
        with patch("src.organizador_hdd.paso4.verificar_archivo", return_value=(False, "truncado")):
            plan = construir_plan(resultado, tmp_path / "org", base_hdd=tmp_path / "org")
        assert len(plan.movimientos) == 1
        mov = plan.movimientos[0]
        assert "dañados" in mov["destino"]
        assert mov["tipo"] == "dañado"
        assert mov["error_integridad"] == "truncado"

    def test_archivo_sano_no_va_a_danados(self, tmp_path):
        origen = tmp_path / "buena.jpg"
        origen.write_bytes(b"\xff\xd8")
        resultado = ResultadoPaso4(archivos=[
            ArchivoImagen(
                ruta=origen, tamanio=2, tipo="foto", score=5,
                fecha=datetime(2024, 1, 1), fuente_fecha="exif",
                tiene_camara=True, tiene_gps=False,
            )
        ])
        with patch("src.organizador_hdd.paso4.verificar_archivo", return_value=(True, "")):
            plan = construir_plan(resultado, tmp_path / "org", base_hdd=tmp_path / "org")
        assert len(plan.movimientos) == 1
        assert plan.movimientos[0].get("tipo") != "dañado"
