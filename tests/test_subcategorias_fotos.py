"""Tests para organizador_hdd.fotos.subcategorias."""
import pytest
from pathlib import Path
from organizador_hdd.fotos.subcategorias import detectar_subcategoria


class TestDetectarSubcategoria:

    def _ruta(self, nombre: str, carpeta: str = "descargas") -> Path:
        return Path("/media/HDD") / carpeta / nombre

    # ── Wallpapers ────────────────────────────────────────────────────────────

    def test_wallpaper_por_nombre(self) -> None:
        assert detectar_subcategoria(self._ruta("wallpaper_ciudad.jpg")) == "wallpapers"

    def test_wallpaper_por_carpeta(self) -> None:
        assert detectar_subcategoria(Path("/media/HDD/wallpapers/ciudad.jpg")) == "wallpapers"

    def test_wallpaper_por_resolucion_1080p(self) -> None:
        assert detectar_subcategoria(self._ruta("fondo.jpg"), ancho=1920, alto=1080) == "wallpapers"

    def test_wallpaper_por_resolucion_4k(self) -> None:
        assert detectar_subcategoria(self._ruta("fondo.jpg"), ancho=3840, alto=2160) == "wallpapers"

    def test_wallpaper_fondo_keyword(self) -> None:
        assert detectar_subcategoria(self._ruta("fondo_pantalla_nature.jpg")) == "wallpapers"

    # ── Superhéroes ───────────────────────────────────────────────────────────

    def test_superheroes_marvel(self) -> None:
        assert detectar_subcategoria(self._ruta("marvel_avengers.jpg")) == "superheroes"

    def test_superheroes_dragonball(self) -> None:
        assert detectar_subcategoria(self._ruta("dragonball_goku.jpg")) == "superheroes"

    def test_superheroes_batman(self) -> None:
        assert detectar_subcategoria(self._ruta("batman_dark.jpg")) == "superheroes"

    def test_superheroes_naruto(self) -> None:
        assert detectar_subcategoria(self._ruta("naruto_uzumaki.jpg")) == "superheroes"

    # ── Arte digital ──────────────────────────────────────────────────────────

    def test_arte_anime_keyword(self) -> None:
        assert detectar_subcategoria(self._ruta("anime_girl.jpg")) == "arte"

    def test_arte_illustration(self) -> None:
        assert detectar_subcategoria(self._ruta("illustration_forest.jpg")) == "arte"

    def test_arte_fanart(self) -> None:
        assert detectar_subcategoria(self._ruta("zelda_fanart.png")) == "arte"

    # ── Autos ─────────────────────────────────────────────────────────────────

    def test_autos_ferrari(self) -> None:
        assert detectar_subcategoria(self._ruta("ferrari_458.jpg")) == "autos"

    def test_autos_supercar_keyword(self) -> None:
        assert detectar_subcategoria(self._ruta("supercar_rojo.jpg")) == "autos"

    def test_autos_carpeta(self) -> None:
        assert detectar_subcategoria(Path("/media/HDD/autos/bmw_m3.jpg")) == "autos"

    # ── Memes ─────────────────────────────────────────────────────────────────

    def test_memes_keyword(self) -> None:
        assert detectar_subcategoria(self._ruta("meme_gato.jpg")) == "memes"

    def test_memes_funny(self) -> None:
        assert detectar_subcategoria(self._ruta("funny_cat.jpg")) == "memes"

    # ── Default ───────────────────────────────────────────────────────────────

    def test_sin_categoria_generico(self) -> None:
        assert detectar_subcategoria(self._ruta("imagen_random.jpg")) == "_sin_categoria"

    def test_sin_categoria_extension_no_afecta(self) -> None:
        assert detectar_subcategoria(self._ruta("descarga_123.png")) == "_sin_categoria"

    # ── Prioridad: wallpaper antes que anime ──────────────────────────────────

    def test_wallpaper_tiene_prioridad_sobre_anime(self) -> None:
        # Resolución de pantalla y keyword anime — wallpaper gana
        assert detectar_subcategoria(
            self._ruta("anime_wallpaper.jpg"), ancho=1920, alto=1080
        ) == "wallpapers"
