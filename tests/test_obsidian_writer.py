"""Tests para obsidian_writer."""
from pathlib import Path

from src.organizador_hdd.obsidian_writer import (
    generar_indice_hdd,
    generar_notas_semestre,
    generar_indice_libros,
)
from src.organizador_hdd.paso8 import detectar_estructura_escolar


def _crear_hdd(tmp_path: Path) -> Path:
    hdd = tmp_path / "hdd"
    (hdd / "01_fotos" / "2024").mkdir(parents=True)
    (hdd / "01_fotos" / "2024" / "foto.jpg").write_bytes(b"\xff\xd8")
    (hdd / "03_musica" / "Artista A" / "Album").mkdir(parents=True)
    (hdd / "03_musica" / "Artista A" / "Album" / "cancion.mp3").write_bytes(b"\xff\xfb")
    (hdd / "04_libros").mkdir(parents=True)
    (hdd / "04_libros" / "libro.pdf").write_bytes(b"%PDF")
    return hdd


def _crear_universidad(tmp_path: Path) -> Path:
    uni = tmp_path / "Universidad"
    (uni / "Semestre 1" / "Estructuras").mkdir(parents=True)
    (uni / "Semestre 1" / "Estructuras" / "practica.py").write_text("x=1")
    (uni / "Semestre 2" / "Bases de Datos").mkdir(parents=True)
    (uni / "Semestre 2" / "Bases de Datos" / "tarea.docx").write_bytes(b"\x00" * 20)
    return uni


def test_indice_hdd_genera_archivo(tmp_path):
    hdd = _crear_hdd(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    nota = generar_indice_hdd(hdd, vault)
    assert nota.exists()
    contenido = nota.read_text(encoding="utf-8")
    assert "01_fotos" in contenido
    assert "03_musica" in contenido


def test_indice_hdd_frontmatter(tmp_path):
    hdd = _crear_hdd(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    nota = generar_indice_hdd(hdd, vault)
    contenido = nota.read_text(encoding="utf-8")
    assert "tags: [hdd" in contenido


def test_notas_semestre_crea_archivos(tmp_path):
    uni = _crear_universidad(tmp_path)
    resultado = detectar_estructura_escolar(uni)
    vault = tmp_path / "vault"
    (vault / "Conocimiento" / "Universidad").mkdir(parents=True)
    (vault / "Conocimiento" / "Universidad" / "_Indice_Universidad.md").write_text(
        "# Índice\n## Areas\n"
    )
    notas = generar_notas_semestre(resultado, vault)
    assert len(notas) == 2
    for nota in notas:
        assert nota.exists()


def test_nota_semestre_contiene_materias(tmp_path):
    uni = _crear_universidad(tmp_path)
    resultado = detectar_estructura_escolar(uni)
    vault = tmp_path / "vault"
    (vault / "Conocimiento" / "Universidad").mkdir(parents=True)
    (vault / "Conocimiento" / "Universidad" / "_Indice_Universidad.md").write_text("# Índice\n")
    notas = generar_notas_semestre(resultado, vault)
    sem1 = [n for n in notas if "Sem01" in n.name][0]
    contenido = sem1.read_text(encoding="utf-8")
    assert "Estructuras" in contenido
    assert "09_codigo" in contenido


def test_indice_universidad_actualizado(tmp_path):
    uni = _crear_universidad(tmp_path)
    resultado = detectar_estructura_escolar(uni)
    vault = tmp_path / "vault"
    (vault / "Conocimiento" / "Universidad").mkdir(parents=True)
    indice = vault / "Conocimiento" / "Universidad" / "_Indice_Universidad.md"
    indice.write_text("# Índice\n")
    generar_notas_semestre(resultado, vault)
    contenido = indice.read_text(encoding="utf-8")
    assert "Semestres documentados" in contenido
    assert "Sem01" in contenido


def test_indice_libros_genera_archivo(tmp_path):
    hdd = _crear_hdd(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    nota = generar_indice_libros(hdd, vault)
    assert nota.exists()
    contenido = nota.read_text(encoding="utf-8")
    assert "libro.pdf" in contenido
