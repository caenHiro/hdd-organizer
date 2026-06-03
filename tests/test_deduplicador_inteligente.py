"""Tests para deduplicador_inteligente."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.organizador_hdd.deduplicador_inteligente import (
    GrupoDuplicados,
    DecisionDuplicado,
    agrupar_por_hash,
    decidir,
    planificar,
    construir_plan,
    ejecutar_plan,
    puntaje_archivo,
    _puntaje_ruta,
    _puntaje_nombre,
    resumen_texto,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _archivo(ruta: str, tamanio: int = 1_000_000, fecha: str = "2026-01-01") -> dict:
    return {"ruta": ruta, "tamanio": tamanio, "fecha_modificacion": fecha, "hash_sha256": "abc123"}


def _grupo(*rutas_y_sizes) -> GrupoDuplicados:
    """Crea un grupo con archivos dados como (ruta, tamanio, fecha)."""
    archivos = [
        {"ruta": r, "tamanio": t, "fecha_modificacion": f, "hash_sha256": "hash1"}
        for r, t, f in rutas_y_sizes
    ]
    return GrupoDuplicados("hash1", archivos)


# ─── Scoring: puntaje_ruta ────────────────────────────────────────────────────

class TestPuntajeRuta:
    def test_carpeta_organizada_score_5(self):
        assert _puntaje_ruta(Path("/hdd/01_fotos/2024/foto.jpg")) == 5

    def test_carpeta_musica_score_5(self):
        assert _puntaje_ruta(Path("/hdd/03_musica/artista/cancion.mp3")) == 5

    def test_carpeta_escuela_score_5(self):
        assert _puntaje_ruta(Path("/hdd/07_escuela/Sem01/tarea.pdf")) == 5

    def test_carpeta_pendientes_score_0(self):
        assert _puntaje_ruta(Path("/hdd/_pendientes/checar/foto.jpg")) == 0

    def test_carpeta_sin_clasificar_score_2(self):
        assert _puntaje_ruta(Path("/home/usuario/Descargas/foto.jpg")) == 2


# ─── Scoring: puntaje_nombre ─────────────────────────────────────────────────

class TestPuntajeNombre:
    def test_nombre_camara_score_0(self):
        assert _puntaje_nombre(Path("IMG_20240101.jpg")) == 0

    def test_nombre_dsc_score_0(self):
        assert _puntaje_nombre(Path("DSC_1234.jpg")) == 0

    def test_nombre_timestamp_score_0(self):
        assert _puntaje_nombre(Path("20240101_123456.jpg")) == 0

    def test_nombre_significativo_score_2(self):
        assert _puntaje_nombre(Path("cumpleanos_mamá_2024.jpg")) == 2

    def test_nombre_cancion_score_2(self):
        assert _puntaje_nombre(Path("Bohemian_Rhapsody.mp3")) == 2


# ─── agrupar_por_hash ────────────────────────────────────────────────────────

class TestAgruparPorHash:
    def test_agrupa_mismo_hash(self):
        archivos = [
            {"ruta": "/a/foto.jpg", "tamanio": 100, "hash_sha256": "abc", "fecha_modificacion": "2026-01-01"},
            {"ruta": "/b/foto.jpg", "tamanio": 100, "hash_sha256": "abc", "fecha_modificacion": "2026-01-02"},
            {"ruta": "/c/otro.jpg", "tamanio": 200, "hash_sha256": "def", "fecha_modificacion": "2026-01-01"},
        ]
        grupos = agrupar_por_hash(archivos)
        assert len(grupos) == 1
        assert grupos[0].hash_sha256 == "abc"
        assert grupos[0].total == 2

    def test_hash_unico_no_incluido(self):
        archivos = [
            {"ruta": "/a/foto.jpg", "tamanio": 100, "hash_sha256": "solo", "fecha_modificacion": "2026-01-01"},
        ]
        grupos = agrupar_por_hash(archivos)
        assert len(grupos) == 0

    def test_hash_vacio_ignorado(self):
        archivos = [
            {"ruta": "/a/foto.jpg", "tamanio": 100, "hash_sha256": "", "fecha_modificacion": "2026-01-01"},
            {"ruta": "/b/foto.jpg", "tamanio": 100, "hash_sha256": "", "fecha_modificacion": "2026-01-01"},
        ]
        grupos = agrupar_por_hash(archivos)
        assert len(grupos) == 0


# ─── decidir ────────────────────────────────────────────────────────────────

class TestDecidir:
    def test_conserva_carpeta_organizada(self):
        g = _grupo(
            ("/hdd/01_fotos/foto.jpg",   1_000_000, "2026-01-01"),
            ("/Downloads/foto.jpg",      1_000_000, "2026-01-01"),
        )
        dec = decidir(g)
        assert "01_fotos" in dec.conservar["ruta"]
        assert len(dec.descartar) == 1

    def test_conserva_mas_antiguo_en_empate(self):
        g = _grupo(
            ("/hdd/01_fotos/a.jpg", 1_000_000, "2026-03-01"),
            ("/hdd/01_fotos/b.jpg", 1_000_000, "2024-01-01"),  # más antiguo
        )
        dec = decidir(g)
        assert dec.conservar["ruta"].endswith("b.jpg")

    def test_conserva_el_mas_grande_en_empate_tamanio(self):
        g = _grupo(
            ("/Downloads/a.jpg", 500_000, "2026-01-01"),
            ("/Downloads/b.jpg", 2_000_000, "2026-01-01"),   # más grande
        )
        dec = decidir(g)
        assert dec.conservar["ruta"].endswith("b.jpg")

    def test_espacio_recuperable(self):
        g = _grupo(
            ("/hdd/01_fotos/a.jpg", 3_000_000, "2026-01-01"),
            ("/Downloads/a.jpg",    3_000_000, "2026-01-02"),
        )
        assert g.espacio_recuperable == 3_000_000

    def test_razon_incluida(self):
        g = _grupo(
            ("/hdd/01_fotos/foto.jpg", 1_000_000, "2026-01-01"),
            ("/Downloads/foto.jpg",    1_000_000, "2026-01-01"),
        )
        dec = decidir(g)
        assert dec.razon != ""

    def test_tres_copias_descarta_dos(self):
        g = _grupo(
            ("/hdd/01_fotos/x.jpg", 1_000_000, "2024-01-01"),
            ("/Downloads/x.jpg",    1_000_000, "2025-01-01"),
            ("/Backup/x.jpg",       1_000_000, "2026-01-01"),
        )
        dec = decidir(g)
        assert len(dec.descartar) == 2


# ─── construir_plan ─────────────────────────────────────────────────────────

class TestConstruirPlan:
    def test_destino_en_pendientes_duplicados(self, tmp_path):
        dec = DecisionDuplicado(
            hash_sha256="abc",
            conservar={"ruta": str(tmp_path / "01_fotos" / "a.jpg"), "tamanio": 1000, "fecha_modificacion": ""},
            descartar=[{"ruta": str(tmp_path / "Downloads" / "a.jpg"), "tamanio": 1000, "fecha_modificacion": ""}],
            razon="score mayor",
            espacio_recuperable=1000,
        )
        plan = construir_plan([dec], tmp_path)
        assert len(plan) == 1
        destino = str(plan[0].destino)
        assert "_pendientes" in destino
        assert "duplicados" in destino
        # La ruta codificada del directorio origen debe estar en la ruta destino
        assert "Downloads" in destino

    def test_tipo_imagen_en_ruta(self, tmp_path):
        dec = DecisionDuplicado(
            hash_sha256="abc",
            conservar={"ruta": "/keep/a.jpg", "tamanio": 1000, "fecha_modificacion": ""},
            descartar=[{"ruta": "/discard/a.jpg", "tamanio": 1000, "fecha_modificacion": ""}],
            razon="test",
            espacio_recuperable=1000,
        )
        plan = construir_plan([dec], tmp_path)
        assert plan[0].tipo == "imagen"

    def test_tipo_audio_en_ruta(self, tmp_path):
        dec = DecisionDuplicado(
            hash_sha256="abc",
            conservar={"ruta": "/keep/cancion.mp3", "tamanio": 1000, "fecha_modificacion": ""},
            descartar=[{"ruta": "/discard/cancion.mp3", "tamanio": 1000, "fecha_modificacion": ""}],
            razon="test",
            espacio_recuperable=1000,
        )
        plan = construir_plan([dec], tmp_path)
        assert plan[0].tipo == "audio"


# ─── ejecutar_plan ───────────────────────────────────────────────────────────

class TestEjecutarPlan:
    def test_dry_run_no_mueve_archivos(self, tmp_path):
        origen = tmp_path / "foto.jpg"
        origen.write_bytes(b"fake_image")

        from src.organizador_hdd.deduplicador_inteligente import MovimientoDuplicado
        mov = MovimientoDuplicado(
            origen=origen,
            destino=tmp_path / "_pendientes" / "duplicados" / "imagen" / "_raiz" / "foto.jpg",
            hash_sha256="abc",
            tipo="imagen",
        )
        resultado = ejecutar_plan([mov], tmp_path / "log.json", dry_run=True)
        assert len(resultado.movidos) == 1
        assert origen.exists()   # no se movió
        assert not (tmp_path / "log.json").exists()

    def test_ejecucion_real_mueve_y_escribe_log(self, tmp_path):
        origen = tmp_path / "foto.jpg"
        origen.write_bytes(b"fake_image")

        from src.organizador_hdd.deduplicador_inteligente import MovimientoDuplicado
        mov = MovimientoDuplicado(
            origen=origen,
            destino=tmp_path / "_pendientes" / "duplicados" / "imagen" / "_raiz" / "foto.jpg",
            hash_sha256="abc",
            tipo="imagen",
        )
        resultado = ejecutar_plan([mov], tmp_path / "log.json", dry_run=False)
        assert len(resultado.movidos) == 1
        assert not origen.exists()
        assert mov.destino.exists()
        assert (tmp_path / "log.json").exists()

    def test_archivo_faltante_va_a_omitidos(self, tmp_path):
        from src.organizador_hdd.deduplicador_inteligente import MovimientoDuplicado
        mov = MovimientoDuplicado(
            origen=tmp_path / "no_existe.jpg",
            destino=tmp_path / "_pendientes" / "duplicados" / "imagen" / "_raiz" / "no_existe.jpg",
            hash_sha256="abc",
            tipo="imagen",
        )
        resultado = ejecutar_plan([mov], tmp_path / "log.json", dry_run=False)
        assert len(resultado.movidos) == 0
        assert len(resultado.omitidos) == 1


# ─── resumen_texto ───────────────────────────────────────────────────────────

class TestResumenTexto:
    def test_incluye_totales(self):
        g = _grupo(
            ("/hdd/01_fotos/a.jpg", 5_000_000, "2024-01-01"),
            ("/Downloads/a.jpg",    5_000_000, "2025-01-01"),
        )
        decisiones = planificar([g])
        texto = resumen_texto(decisiones)
        assert "Grupos duplicados: 1" in texto
        assert "Archivos a descartar: 1" in texto
