"""Tests para readme_carpetas.py — generador de _README.md por carpeta."""
import pytest
from pathlib import Path
from collections import Counter

from organizador_hdd.readme_carpetas import (
    generar_readme_carpeta,
    generar_readme_raiz,
    generar_todos,
    _stats_carpeta,
    _CARPETAS,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def hdd_raiz(tmp_path: Path) -> Path:
    return tmp_path / "HDD_organizado"


# ─── Tests: generar_readme_carpeta ───────────────────────────────────────────

class TestGenerarReadmeCarpeta:

    def test_crea_archivo(self, hdd_raiz: Path) -> None:
        carpeta = hdd_raiz / "02_videos"
        resultado = generar_readme_carpeta(carpeta, con_stats=False)
        assert resultado == carpeta / "_README.md"
        assert resultado.exists()

    def test_crea_carpeta_si_no_existe(self, hdd_raiz: Path) -> None:
        carpeta = hdd_raiz / "03_musica"
        assert not carpeta.exists()
        generar_readme_carpeta(carpeta, con_stats=False)
        assert carpeta.exists()

    def test_contiene_titulo(self, hdd_raiz: Path) -> None:
        carpeta = hdd_raiz / "01_fotos"
        generar_readme_carpeta(carpeta, con_stats=False)
        contenido = (carpeta / "_README.md").read_text(encoding="utf-8")
        assert "Fotos Personales" in contenido

    def test_contiene_reglas(self, hdd_raiz: Path) -> None:
        carpeta = hdd_raiz / "04_libros"
        generar_readme_carpeta(carpeta, con_stats=False)
        contenido = (carpeta / "_README.md").read_text(encoding="utf-8")
        assert "## Reglas del organizador" in contenido

    def test_contiene_subcarpetas(self, hdd_raiz: Path) -> None:
        carpeta = hdd_raiz / "02_videos"
        generar_readme_carpeta(carpeta, con_stats=False)
        contenido = (carpeta / "_README.md").read_text(encoding="utf-8")
        assert "## Subcarpetas" in contenido
        assert "series/" in contenido

    def test_contiene_encaja_si(self, hdd_raiz: Path) -> None:
        carpeta = hdd_raiz / "08_documentos"
        generar_readme_carpeta(carpeta, con_stats=False)
        contenido = (carpeta / "_README.md").read_text(encoding="utf-8")
        assert "¿Este contenido va aquí?" in contenido
        assert "Sí encaja si:" in contenido

    def test_carpeta_desconocida_usa_defaults(self, hdd_raiz: Path) -> None:
        carpeta = hdd_raiz / "99_desconocida"
        generar_readme_carpeta(carpeta, con_stats=False)
        contenido = (carpeta / "_README.md").read_text(encoding="utf-8")
        assert "99_desconocida" in contenido

    def test_stats_vacias_cuando_sin_stats(self, hdd_raiz: Path) -> None:
        carpeta = hdd_raiz / "03_musica"
        generar_readme_carpeta(carpeta, con_stats=False)
        contenido = (carpeta / "_README.md").read_text(encoding="utf-8")
        assert "Carpeta vacía" in contenido

    def test_stats_con_archivos(self, hdd_raiz: Path) -> None:
        carpeta = hdd_raiz / "03_musica"
        carpeta.mkdir(parents=True)
        (carpeta / "cancion.mp3").write_bytes(b"x")
        (carpeta / "album.flac").write_bytes(b"x")
        generar_readme_carpeta(carpeta, con_stats=True)
        contenido = (carpeta / "_README.md").read_text(encoding="utf-8")
        assert "audio" in contenido
        assert "2" in contenido

    def test_frontmatter_presente(self, hdd_raiz: Path) -> None:
        carpeta = hdd_raiz / "09_codigo"
        generar_readme_carpeta(carpeta, con_stats=False)
        contenido = (carpeta / "_README.md").read_text(encoding="utf-8")
        assert "tipo: hdd-readme" in contenido
        assert "carpeta: 09_codigo" in contenido


# ─── Tests: generar_readme_raiz ──────────────────────────────────────────────

class TestGenerarReadmeRaiz:

    def test_crea_archivo_en_raiz(self, hdd_raiz: Path) -> None:
        resultado = generar_readme_raiz(hdd_raiz, con_stats=False)
        assert resultado == hdd_raiz / "_README.md"
        assert resultado.exists()

    def test_contiene_todas_las_carpetas(self, hdd_raiz: Path) -> None:
        generar_readme_raiz(hdd_raiz, con_stats=False)
        contenido = (hdd_raiz / "_README.md").read_text(encoding="utf-8")
        for nombre in _CARPETAS:
            assert nombre in contenido

    def test_contiene_flujo_organizacion(self, hdd_raiz: Path) -> None:
        generar_readme_raiz(hdd_raiz, con_stats=False)
        contenido = (hdd_raiz / "_README.md").read_text(encoding="utf-8")
        assert "Flujo de organización" in contenido
        assert "paso6" in contenido

    def test_contiene_comandos_uso(self, hdd_raiz: Path) -> None:
        generar_readme_raiz(hdd_raiz, con_stats=False)
        contenido = (hdd_raiz / "_README.md").read_text(encoding="utf-8")
        assert "generar-readme" in contenido
        assert "hdd-organizar" in contenido


# ─── Tests: generar_todos ────────────────────────────────────────────────────

class TestGenerarTodos:

    def test_genera_readme_raiz_y_subcarpetas(self, hdd_raiz: Path) -> None:
        archivos = generar_todos(hdd_raiz, con_stats=False)
        # 1 raíz + N subcarpetas conocidas
        assert len(archivos) == 1 + len(_CARPETAS)

    def test_todos_los_archivos_existen(self, hdd_raiz: Path) -> None:
        archivos = generar_todos(hdd_raiz, con_stats=False)
        for arch in archivos:
            assert arch.exists(), f"No existe: {arch}"

    def test_todos_son_readme(self, hdd_raiz: Path) -> None:
        archivos = generar_todos(hdd_raiz, con_stats=False)
        for arch in archivos:
            assert arch.name == "_README.md"


# ─── Tests: _stats_carpeta ───────────────────────────────────────────────────

class TestStatsCarpeta:

    def test_carpeta_vacia(self, tmp_path: Path) -> None:
        assert _stats_carpeta(tmp_path) == Counter()

    def test_carpeta_inexistente(self, tmp_path: Path) -> None:
        assert _stats_carpeta(tmp_path / "noexiste") == Counter()

    def test_clasifica_audio(self, tmp_path: Path) -> None:
        (tmp_path / "a.mp3").write_bytes(b"x")
        (tmp_path / "b.flac").write_bytes(b"x")
        stats = _stats_carpeta(tmp_path)
        assert stats["audio"] == 2

    def test_clasifica_video(self, tmp_path: Path) -> None:
        (tmp_path / "video.mkv").write_bytes(b"x")
        stats = _stats_carpeta(tmp_path)
        assert stats["video"] == 1

    def test_clasifica_desconocido_como_otro(self, tmp_path: Path) -> None:
        (tmp_path / "archivo.xyz").write_bytes(b"x")
        stats = _stats_carpeta(tmp_path)
        assert stats["otro"] == 1

    def test_recursivo(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "foto.jpg").write_bytes(b"x")
        (tmp_path / "musica.mp3").write_bytes(b"x")
        stats = _stats_carpeta(tmp_path)
        assert stats["imagen"] == 1
        assert stats["audio"] == 1
