import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.organizador_hdd.paso3 import (
    ArchivoMusica,
    ResultadoPaso3,
    detectar_musica,
    construir_plan,
    ejecutar_plan,
    _es_compilacion,
    _nombre_album_carpeta,
)
from src.organizador_hdd.utils import transliterar, sanitizar_nombre


# ─── utils ────────────────────────────────────────────────────────────────────

class TestUtils:
    def test_transliterar_cirilico(self):
        assert transliterar("Москва") == "Moskva"
        assert transliterar("Иванов") == "Ivanov"

    def test_transliterar_sin_cirilico(self):
        assert transliterar("Beatles") == "Beatles"

    def test_transliterar_mixto(self):
        resultado = transliterar("AC/DC и Иванов")
        assert "Ivanov" in resultado
        assert "AC/DC" in resultado

    def test_sanitizar_elimina_invalidos(self):
        assert "/" not in sanitizar_nombre("AC/DC")
        assert ":" not in sanitizar_nombre("01:02")

    def test_sanitizar_cirílico(self):
        resultado = sanitizar_nombre("Иванов Иван")
        assert resultado == "Ivanov Ivan"

    def test_sanitizar_vacio_devuelve_placeholder(self):
        assert sanitizar_nombre("") == "_sin_nombre"
        assert sanitizar_nombre("   ") == "_sin_nombre"

    def test_sanitizar_max_len(self):
        largo = "A" * 300
        assert len(sanitizar_nombre(largo)) <= 200


# ─── lógica de dominio ────────────────────────────────────────────────────────

class TestLogicaPaso3:
    def test_es_compilacion_various_artists(self):
        assert _es_compilacion("Various Artists") is True
        assert _es_compilacion("various artists") is True
        assert _es_compilacion("VA") is True
        assert _es_compilacion("V.A.") is True
        assert _es_compilacion("Varios Artistas") is True

    def test_no_es_compilacion_artista_normal(self):
        assert _es_compilacion("The Beatles") is False
        assert _es_compilacion("Metallica") is False

    def test_nombre_album_carpeta_con_anio(self):
        assert _nombre_album_carpeta("Abbey Road", "1969") == "Abbey Road (1969)"

    def test_nombre_album_carpeta_sin_anio(self):
        assert _nombre_album_carpeta("Abbey Road", "") == "Abbey Road"

    def test_nombre_album_carpeta_anio_no_numerico(self):
        assert _nombre_album_carpeta("Album", "s/d") == "Album"

    def test_nombre_album_carpeta_vacio(self):
        assert _nombre_album_carpeta("", "") == "_sin_album"


# ─── ResultadoPaso3 ───────────────────────────────────────────────────────────

class TestResultadoPaso3:
    def _make(self, artista="", es_compilacion=False, tiene_tags=True):
        return ArchivoMusica(
            ruta=Path("f.mp3"), artista=artista, album="", titulo="",
            anio="", tamanio=100, tiene_tags=tiene_tags,
            es_compilacion=es_compilacion,
        )

    def test_total_correcto(self):
        r = ResultadoPaso3(archivos=[self._make("A"), self._make("B")])
        assert r.total == 2

    def test_con_tags(self):
        r = ResultadoPaso3(archivos=[self._make("A", tiene_tags=True), self._make("", tiene_tags=False)])
        assert r.con_tags == 1
        assert r.sin_tags == 1

    def test_compilaciones(self):
        r = ResultadoPaso3(archivos=[self._make("Various Artists", es_compilacion=True), self._make("Beatles")])
        assert r.compilaciones == 1

    def test_total_bytes(self):
        r = ResultadoPaso3(archivos=[self._make("A"), self._make("B")])
        assert r.total_bytes == 200

    def test_por_artista(self):
        r = ResultadoPaso3(archivos=[
            self._make("Beatles"), self._make("Beatles"), self._make(""),
        ])
        pa = r.por_artista()
        assert pa["Beatles"] == 2
        assert pa["_sin_artista"] == 1


# ─── Detección ────────────────────────────────────────────────────────────────

def _crear_mp3_fake(ruta: Path) -> None:
    """Crea un .mp3 vacío (sin tags reales — mutagen devolverá tags vacías)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"\xff\xfb\x90\x00")  # cabecera MP3 mínima


class TestDetectarMusica:
    def test_detecta_mp3(self, tmp_path):
        _crear_mp3_fake(tmp_path / "cancion.mp3")
        resultado = detectar_musica(tmp_path)
        assert resultado.total == 1

    def test_ignora_no_audio(self, tmp_path):
        (tmp_path / "imagen.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "doc.pdf").write_bytes(b"%PDF")
        resultado = detectar_musica(tmp_path)
        assert resultado.total == 0

    def test_detecta_multiples_extensiones(self, tmp_path):
        for ext in [".mp3", ".flac", ".ogg", ".m4a"]:
            _crear_mp3_fake(tmp_path / f"cancion{ext}")
        resultado = detectar_musica(tmp_path)
        assert resultado.total == 4

    def test_no_desciende_en_destino(self, tmp_path):
        """No debe iterar dentro de por_artista/ si ya existe."""
        hdd = tmp_path / "hdd"
        _crear_mp3_fake(hdd / "cancion.mp3")
        # Simular que ya existe el destino con música organizada
        _crear_mp3_fake(hdd / "por_artista" / "Beatles" / "Abbey.mp3")
        resultado = detectar_musica(hdd)
        # Solo debe encontrar la cancion.mp3, no la de por_artista/
        assert resultado.total == 1

    def test_tags_con_mock(self, tmp_path):
        """Verifica que los tags se leen y clasifican correctamente."""
        _crear_mp3_fake(tmp_path / "cancion.mp3")
        tags_mock = MagicMock()
        tags_mock.artista = "The Beatles"
        tags_mock.album = "Abbey Road"
        tags_mock.titulo = "Come Together"
        tags_mock.anio = "1969"
        tags_mock.disponible = True

        with patch("src.organizador_hdd.paso3.leer_tags", return_value=tags_mock):
            with patch("src.organizador_hdd.paso3._MUTAGEN_DISPONIBLE", True):
                resultado = detectar_musica(tmp_path)

        assert resultado.total == 1
        arch = resultado.archivos[0]
        assert arch.artista == "The Beatles"
        assert arch.album == "Abbey Road"
        assert arch.tiene_tags is True
        assert arch.es_compilacion is False

    def test_compilacion_con_mock(self, tmp_path):
        _crear_mp3_fake(tmp_path / "comp.mp3")
        tags_mock = MagicMock()
        tags_mock.artista = "Various Artists"
        tags_mock.album = "Greatest Hits"
        tags_mock.titulo = ""
        tags_mock.anio = "2000"
        tags_mock.disponible = True

        with patch("src.organizador_hdd.paso3.leer_tags", return_value=tags_mock):
            with patch("src.organizador_hdd.paso3._MUTAGEN_DISPONIBLE", True):
                resultado = detectar_musica(tmp_path)

        assert resultado.compilaciones == 1
        assert resultado.archivos[0].es_compilacion is True


# ─── Plan ─────────────────────────────────────────────────────────────────────

class TestConstruirPlanPaso3:
    def _resultado_simple(self, artista="Beatles", album="Abbey Road", compilacion=False) -> ResultadoPaso3:
        return ResultadoPaso3(archivos=[
            ArchivoMusica(
                ruta=Path("/hdd/cancion.mp3"),
                artista=artista, album=album, titulo="Come Together",
                anio="1969", tamanio=500_000, tiene_tags=True,
                es_compilacion=compilacion,
            )
        ])

    def test_destino_normal_tiene_artista_y_album(self, tmp_path):
        resultado = self._resultado_simple("Beatles", "Abbey Road")
        plan = construir_plan(resultado, tmp_path / "03_musica")
        mov = plan.movimientos[0]
        assert "por_artista" in mov.destino.parts
        assert "Beatles" in mov.destino.parts

    def test_destino_compilacion(self, tmp_path):
        resultado = self._resultado_simple("Various Artists", "Greatest Hits", compilacion=True)
        plan = construir_plan(resultado, tmp_path / "03_musica")
        mov = plan.movimientos[0]
        assert "compilaciones" in mov.destino.parts

    def test_destino_sin_artista(self, tmp_path):
        resultado = self._resultado_simple(artista="")
        plan = construir_plan(resultado, tmp_path / "03_musica")
        mov = plan.movimientos[0]
        assert "_sin_artista" in mov.destino.parts

    def test_cirilico_en_artista(self, tmp_path):
        resultado = self._resultado_simple(artista="Иванов Иван")
        plan = construir_plan(resultado, tmp_path / "03_musica")
        mov = plan.movimientos[0]
        assert "Ivanov Ivan" in str(mov.destino)

    def test_total_bytes(self, tmp_path):
        resultado = self._resultado_simple()
        plan = construir_plan(resultado, tmp_path)
        assert plan.total_bytes == 500_000


# ─── Ejecución ────────────────────────────────────────────────────────────────

class TestEjecutarPlanPaso3:
    def test_dry_run_no_mueve(self, tmp_path):
        origen = tmp_path / "cancion.mp3"
        origen.write_bytes(b"\xff\xfb")
        resultado = ResultadoPaso3(archivos=[
            ArchivoMusica(
                ruta=origen, artista="Beatles", album="Abbey", titulo="",
                anio="", tamanio=100, tiene_tags=True, es_compilacion=False,
            )
        ])
        plan = construir_plan(resultado, tmp_path / "musica")
        ejec = ejecutar_plan(plan, tmp_path / "log.json", dry_run=True)
        assert len(ejec.movidos) == 1
        assert origen.exists()

    def test_real_mueve_archivo(self, tmp_path):
        origen = tmp_path / "hdd" / "cancion.mp3"
        origen.parent.mkdir()
        origen.write_bytes(b"\xff\xfb")
        resultado = ResultadoPaso3(archivos=[
            ArchivoMusica(
                ruta=origen, artista="Beatles", album="Abbey Road", titulo="",
                anio="1969", tamanio=100, tiene_tags=True, es_compilacion=False,
            )
        ])
        plan = construir_plan(resultado, tmp_path / "03_musica")
        ejec = ejecutar_plan(plan, tmp_path / "log.json", dry_run=False)
        assert not origen.exists()
        assert len(ejec.movidos) == 1
        destino = Path(ejec.movidos[0]["destino"])
        assert destino.exists()

    def test_escribe_log_reversion(self, tmp_path):
        origen = tmp_path / "f.mp3"
        origen.write_bytes(b"\xff\xfb")
        resultado = ResultadoPaso3(archivos=[
            ArchivoMusica(
                ruta=origen, artista="A", album="B", titulo="",
                anio="", tamanio=10, tiene_tags=True, es_compilacion=False,
            )
        ])
        plan = construir_plan(resultado, tmp_path / "musica")
        log = tmp_path / "log.json"
        ejecutar_plan(plan, log, dry_run=False)
        datos = json.loads(log.read_text())
        assert datos["paso"] == 3
        assert len(datos["movimientos"]) == 1
