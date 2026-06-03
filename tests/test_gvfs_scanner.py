"""Tests para gvfs_scanner.py — Mejoras 1-3 (2026-05-18) + extensiones y duplicados (2026-05-19)."""
import os
from datetime import datetime
from pathlib import Path

import pytest

from src.organizador_hdd.gvfs_scanner import (
    clasificar_por_extension,
    clasificar_por_tamanio,
    escanear_gvfs,
    generar_reporte_md,
    resumir,
    GvfsEntrada,
    CATEGORIA_DOCUMENTO,
    CATEGORIA_GOOGLE_DOC,
    CATEGORIA_HOJA_CALCULO,
    CATEGORIA_IMAGEN,
    CATEGORIA_PRESENTACION,
    CATEGORIA_PROBABLE_DOCUMENTO,
    CATEGORIA_PROBABLE_IMAGEN_DOC,
    CATEGORIA_PROBABLE_VIDEO,
    CATEGORIA_PROBABLE_VIDEO_IMAGEN,
    CATEGORIA_CARPETA,
    CATEGORIA_VIDEO,
    _50_MB,
    _5_MB,
    _100_KB,
)


# ─── Mejora 3: clasificar_por_tamanio ────────────────────────────────────────

class TestClasificarPorTamanio:
    def test_archivo_grande_es_probable_video(self):
        assert clasificar_por_tamanio(_50_MB) == CATEGORIA_PROBABLE_VIDEO

    def test_archivo_muy_grande_es_probable_video(self):
        assert clasificar_por_tamanio(_50_MB + 1) == CATEGORIA_PROBABLE_VIDEO

    def test_limite_inferior_probable_video(self):
        # Exactamente 50 MB → probable_video
        assert clasificar_por_tamanio(50 * 1024 * 1024) == CATEGORIA_PROBABLE_VIDEO

    def test_archivo_5mb_50mb_es_video_o_imagen_grande(self):
        assert clasificar_por_tamanio(_5_MB) == CATEGORIA_PROBABLE_VIDEO_IMAGEN
        assert clasificar_por_tamanio(_50_MB - 1) == CATEGORIA_PROBABLE_VIDEO_IMAGEN

    def test_archivo_100kb_5mb_es_imagen_o_documento(self):
        assert clasificar_por_tamanio(_100_KB) == CATEGORIA_PROBABLE_IMAGEN_DOC
        assert clasificar_por_tamanio(_5_MB - 1) == CATEGORIA_PROBABLE_IMAGEN_DOC

    def test_archivo_pequeno_es_probable_documento(self):
        assert clasificar_por_tamanio(0) == CATEGORIA_PROBABLE_DOCUMENTO
        assert clasificar_por_tamanio(1024) == CATEGORIA_PROBABLE_DOCUMENTO
        assert clasificar_por_tamanio(_100_KB - 1) == CATEGORIA_PROBABLE_DOCUMENTO

    def test_todos_los_rangos_cubiertos(self):
        # Verificar que no hay gaps entre rangos
        rangos = [
            (0, CATEGORIA_PROBABLE_DOCUMENTO),
            (_100_KB - 1, CATEGORIA_PROBABLE_DOCUMENTO),
            (_100_KB, CATEGORIA_PROBABLE_IMAGEN_DOC),
            (_5_MB - 1, CATEGORIA_PROBABLE_IMAGEN_DOC),
            (_5_MB, CATEGORIA_PROBABLE_VIDEO_IMAGEN),
            (_50_MB - 1, CATEGORIA_PROBABLE_VIDEO_IMAGEN),
            (_50_MB, CATEGORIA_PROBABLE_VIDEO),
            (_50_MB + 1_000_000, CATEGORIA_PROBABLE_VIDEO),
        ]
        for tamanio, esperado in rangos:
            assert clasificar_por_tamanio(tamanio) == esperado, f"tamanio={tamanio}"


# ─── GvfsEntrada.categoria ────────────────────────────────────────────────────

class TestGvfsEntradaCategoria:
    def _entrada(self, es_symlink=False, es_dir=False, tamanio=0):
        return GvfsEntrada(
            ruta=Path("/fake/path"),
            es_symlink=es_symlink,
            es_directorio=es_dir,
            tamanio=tamanio,
            mtime="2026-01-01",
        )

    def test_symlink_es_google_doc(self):
        e = self._entrada(es_symlink=True)
        assert e.categoria == CATEGORIA_GOOGLE_DOC

    def test_directorio_es_carpeta(self):
        e = self._entrada(es_dir=True)
        assert e.categoria == CATEGORIA_CARPETA

    def test_archivo_grande_es_probable_video(self):
        e = self._entrada(tamanio=_50_MB + 1)
        assert e.categoria == CATEGORIA_PROBABLE_VIDEO

    def test_archivo_pequeno_es_probable_documento(self):
        e = self._entrada(tamanio=50_000)
        assert e.categoria == CATEGORIA_PROBABLE_DOCUMENTO

    def test_symlink_tiene_prioridad_sobre_directorio(self):
        # Un symlink no debería ser ambos, pero si lo fuera, symlink tiene prioridad
        e = self._entrada(es_symlink=True, tamanio=_50_MB + 1)
        assert e.categoria == CATEGORIA_GOOGLE_DOC

    def test_tamanio_legible_kb(self):
        e = self._entrada(tamanio=5 * 1024)
        assert "KB" in e.tamanio_legible

    def test_tamanio_legible_mb(self):
        e = self._entrada(tamanio=_5_MB)
        assert "MB" in e.tamanio_legible

    def test_tamanio_legible_gb(self):
        e = self._entrada(tamanio=2 * 1024 * 1024 * 1024)
        assert "GB" in e.tamanio_legible


# ─── Mejora 2: resumir — columna google_doc ──────────────────────────────────

class TestResumir:
    def _entradas(self):
        return [
            GvfsEntrada(Path("/gvfs/gdoc1"), es_symlink=True,  es_directorio=False, tamanio=0,         mtime="2026-01-01"),
            GvfsEntrada(Path("/gvfs/gdoc2"), es_symlink=True,  es_directorio=False, tamanio=0,         mtime="2026-01-01"),
            GvfsEntrada(Path("/gvfs/video"), es_symlink=False, es_directorio=False, tamanio=_50_MB+1,  mtime="2026-01-01"),
            GvfsEntrada(Path("/gvfs/doc"),   es_symlink=False, es_directorio=False, tamanio=50_000,    mtime="2026-01-01"),
            GvfsEntrada(Path("/gvfs/dir"),   es_symlink=False, es_directorio=True,  tamanio=0,         mtime="2026-01-01"),
        ]

    def test_cuenta_google_docs(self):
        r = resumir(self._entradas())
        assert r.google_docs == 2

    def test_cuenta_archivos_regulares(self):
        r = resumir(self._entradas())
        assert r.archivos_regulares == 2

    def test_cuenta_carpetas(self):
        r = resumir(self._entradas())
        assert r.carpetas == 1

    def test_total_entradas(self):
        r = resumir(self._entradas())
        assert r.total_entradas == 5

    def test_tamanio_excluye_directorios(self):
        r = resumir(self._entradas())
        # Solo archivos regulares: video (_50MB+1) + doc (50_000) + 0 para gdocs
        assert r.tamanio_total == _50_MB + 1 + 50_000

    def test_por_categoria_incluye_google_doc(self):
        r = resumir(self._entradas())
        assert r.por_categoria.get(CATEGORIA_GOOGLE_DOC, 0) == 2

    def test_por_categoria_incluye_probable_video(self):
        r = resumir(self._entradas())
        assert r.por_categoria.get(CATEGORIA_PROBABLE_VIDEO, 0) == 1

    def test_por_categoria_incluye_probable_documento(self):
        r = resumir(self._entradas())
        assert r.por_categoria.get(CATEGORIA_PROBABLE_DOCUMENTO, 0) == 1

    def test_tamanio_legible_no_vacio(self):
        r = resumir(self._entradas())
        assert r.tamanio_legible  # no vacío

    def test_sin_entradas_no_falla(self):
        # Debe manejar lista vacía sin lanzar excepción
        entradas = [GvfsEntrada(Path("/x"), False, False, 0, "2026-01-01")]
        r = resumir(entradas)
        assert r.total_entradas == 1


# ─── Mejora 1: escanear_gvfs ─────────────────────────────────────────────────

class TestEscanearGvfs:
    def test_archivos_regulares_detectados(self, tmp_path):
        (tmp_path / "archivo.txt").write_text("hola")
        entradas = escanear_gvfs(tmp_path)
        nombres = [e.ruta.name for e in entradas]
        assert "archivo.txt" in nombres

    def test_directorios_detectados(self, tmp_path):
        (tmp_path / "subcarpeta").mkdir()
        entradas = escanear_gvfs(tmp_path)
        dirs = [e for e in entradas if e.es_directorio]
        assert any(e.ruta.name == "subcarpeta" for e in dirs)

    def test_directorio_tiene_categoria_carpeta(self, tmp_path):
        (tmp_path / "sub").mkdir()
        entradas = escanear_gvfs(tmp_path)
        sub = next(e for e in entradas if e.ruta.name == "sub")
        assert sub.categoria == CATEGORIA_CARPETA

    def test_archivo_sin_extension_clasifica_por_tamanio(self, tmp_path):
        # Simula un archivo con ID de Drive (sin extensión) — pequeño → probable_documento
        archivo = tmp_path / "1BTM61ddnPwvXkCdr7Cb3sWtdDjm1uqbS"
        archivo.write_bytes(b"x" * 1024)
        entradas = escanear_gvfs(tmp_path)
        e = next(x for x in entradas if x.ruta.name == "1BTM61ddnPwvXkCdr7Cb3sWtdDjm1uqbS")
        assert e.categoria == CATEGORIA_PROBABLE_DOCUMENTO

    def test_archivo_grande_sin_extension_clasifica_como_video(self, tmp_path):
        archivo = tmp_path / "1y36NYioZu3zF_j_kMrWF7Xrm0RTKVIVSjAwKm_Q5g6Q"
        archivo.write_bytes(b"v" * (_50_MB + 1))
        entradas = escanear_gvfs(tmp_path)
        e = next(x for x in entradas if x.ruta.name == "1y36NYioZu3zF_j_kMrWF7Xrm0RTKVIVSjAwKm_Q5g6Q")
        assert e.categoria == CATEGORIA_PROBABLE_VIDEO

    def test_profundidad_limita_recursion(self, tmp_path):
        # Crea estructura: tmp/a/b/c/archivo.txt
        (tmp_path / "a" / "b" / "c").mkdir(parents=True)
        (tmp_path / "a" / "b" / "c" / "deep.txt").write_text("x")
        # Con profundidad 1 solo llega a a/
        entradas = escanear_gvfs(tmp_path, max_prof=1)
        nombres = [e.ruta.name for e in entradas]
        assert "deep.txt" not in nombres

    def test_profundidad_2_llega_a_subcarpeta(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "archivo.txt").write_text("x")
        entradas = escanear_gvfs(tmp_path, max_prof=2)
        nombres = [e.ruta.name for e in entradas]
        assert "archivo.txt" in nombres

    def test_directorio_vacio_no_falla(self, tmp_path):
        entradas = escanear_gvfs(tmp_path)
        assert entradas == []

    def test_mtime_formato_iso(self, tmp_path):
        (tmp_path / "f.txt").write_text("x")
        entradas = escanear_gvfs(tmp_path)
        e = entradas[0]
        # Debe tener formato YYYY-MM-DD
        partes = e.mtime.split("-")
        assert len(partes) == 3
        assert len(partes[0]) == 4  # año

    def test_symlink_detectado(self, tmp_path):
        target = tmp_path / "real.txt"
        target.write_text("x")
        link = tmp_path / "enlace"
        link.symlink_to(target)
        entradas = escanear_gvfs(tmp_path)
        sym = next((e for e in entradas if e.ruta.name == "enlace"), None)
        assert sym is not None
        assert sym.es_symlink is True
        assert sym.categoria == CATEGORIA_GOOGLE_DOC

    def test_symlink_roto_detectado_como_google_doc(self, tmp_path):
        link = tmp_path / "broken_symlink"
        link.symlink_to(tmp_path / "no_existe")
        entradas = escanear_gvfs(tmp_path)
        sym = next((e for e in entradas if e.ruta.name == "broken_symlink"), None)
        assert sym is not None
        assert sym.es_symlink is True
        assert sym.categoria == CATEGORIA_GOOGLE_DOC


# ─── generar_reporte_md ───────────────────────────────────────────────────────

class TestGenerarReporteMd:
    def _entradas_muestra(self, ruta_base: Path) -> list[GvfsEntrada]:
        return [
            GvfsEntrada(ruta_base / "gdoc1", es_symlink=True,  es_directorio=False, tamanio=0,        mtime="2026-01-01"),
            GvfsEntrada(ruta_base / "video", es_symlink=False, es_directorio=False, tamanio=_50_MB+1, mtime="2026-01-01"),
            GvfsEntrada(ruta_base / "doc",   es_symlink=False, es_directorio=False, tamanio=50_000,   mtime="2026-01-01"),
            GvfsEntrada(ruta_base / "sub",   es_symlink=False, es_directorio=True,  tamanio=0,        mtime="2026-01-01"),
        ]

    def test_reporte_contiene_seccion_resumen(self, tmp_path):
        entradas = self._entradas_muestra(tmp_path)
        reporte = generar_reporte_md("Test Drive", entradas, tmp_path)
        assert "## Resumen" in reporte

    def test_reporte_muestra_google_docs(self, tmp_path):
        entradas = self._entradas_muestra(tmp_path)
        reporte = generar_reporte_md("Test", entradas, tmp_path)
        assert "google_doc" in reporte

    def test_reporte_muestra_advertencia_google_docs(self, tmp_path):
        entradas = self._entradas_muestra(tmp_path)
        reporte = generar_reporte_md("Test", entradas, tmp_path)
        assert "Takeout" in reporte

    def test_reporte_contiene_tabla_distribucion(self, tmp_path):
        entradas = self._entradas_muestra(tmp_path)
        reporte = generar_reporte_md("Test", entradas, tmp_path)
        assert "## Distribución por categoría" in reporte

    def test_reporte_contiene_detalle_archivos(self, tmp_path):
        entradas = self._entradas_muestra(tmp_path)
        reporte = generar_reporte_md("Test", entradas, tmp_path)
        assert "## Detalle de archivos" in reporte

    def test_reporte_contiene_frontmatter(self, tmp_path):
        entradas = self._entradas_muestra(tmp_path)
        reporte = generar_reporte_md("Test", entradas, tmp_path)
        assert reporte.startswith("---")
        assert "tipo: mapa-gvfs" in reporte

    def test_reporte_contiene_nota_clasificacion_tamanio(self, tmp_path):
        entradas = self._entradas_muestra(tmp_path)
        reporte = generar_reporte_md("Test", entradas, tmp_path)
        assert "50 MB" in reporte
        assert "100 KB" in reporte

    def test_sin_google_docs_no_muestra_advertencia(self, tmp_path):
        entradas = [
            GvfsEntrada(tmp_path / "doc", es_symlink=False, es_directorio=False, tamanio=50_000, mtime="2026-01-01"),
        ]
        reporte = generar_reporte_md("Test", entradas, tmp_path)
        # No debe mostrar el bloque de advertencia Takeout cuando no hay google_docs
        assert "no son descargables" not in reporte

    def test_reporte_es_string_no_vacio(self, tmp_path):
        entradas = self._entradas_muestra(tmp_path)
        reporte = generar_reporte_md("Test", entradas, tmp_path)
        assert len(reporte) > 100


# ─── clasificar_por_extension ─────────────────────────────────────────────────

class TestClasificarPorExtension:
    def test_pdf_es_documento(self):
        assert clasificar_por_extension("libro.pdf") == CATEGORIA_DOCUMENTO

    def test_docx_es_documento(self):
        assert clasificar_por_extension("carta.docx") == CATEGORIA_DOCUMENTO

    def test_html_es_documento(self):
        assert clasificar_por_extension("index.html") == CATEGORIA_DOCUMENTO

    def test_xlsx_es_hoja_calculo(self):
        assert clasificar_por_extension("datos.xlsx") == CATEGORIA_HOJA_CALCULO

    def test_csv_es_hoja_calculo(self):
        assert clasificar_por_extension("datos.csv") == CATEGORIA_HOJA_CALCULO

    def test_pptx_es_presentacion(self):
        assert clasificar_por_extension("slides.pptx") == CATEGORIA_PRESENTACION

    def test_jpg_es_imagen(self):
        assert clasificar_por_extension("foto.jpg") == CATEGORIA_IMAGEN

    def test_jpeg_es_imagen(self):
        assert clasificar_por_extension("foto.JPEG") == CATEGORIA_IMAGEN  # mayúsculas

    def test_png_es_imagen(self):
        assert clasificar_por_extension("captura.png") == CATEGORIA_IMAGEN

    def test_mp4_es_video(self):
        assert clasificar_por_extension("video.mp4") == CATEGORIA_VIDEO

    def test_sin_extension_retorna_none(self):
        assert clasificar_por_extension("1BTM61ddnPwv") is None

    def test_extension_desconocida_retorna_none(self):
        assert clasificar_por_extension("archivo.xyz") is None

    def test_mayusculas_normalizadas(self):
        assert clasificar_por_extension("DOC.PDF") == CATEGORIA_DOCUMENTO


# ─── GvfsEntrada — extensión y duplicados ─────────────────────────────────────

class TestGvfsEntradaExtension:
    def _entrada(self, nombre: str, tamanio: int = 0) -> GvfsEntrada:
        return GvfsEntrada(
            ruta=Path(f"/fake/{nombre}"),
            es_symlink=False,
            es_directorio=False,
            tamanio=tamanio,
            mtime="2026-01-01",
        )

    def test_pdf_categoria_documento(self):
        assert self._entrada("libro.pdf").categoria == CATEGORIA_DOCUMENTO

    def test_xlsx_categoria_hoja_calculo(self):
        assert self._entrada("datos.xlsx").categoria == CATEGORIA_HOJA_CALCULO

    def test_jpg_categoria_imagen(self):
        assert self._entrada("foto.jpg").categoria == CATEGORIA_IMAGEN

    def test_mp4_categoria_video(self):
        assert self._entrada("clip.mp4").categoria == CATEGORIA_VIDEO

    def test_pptx_categoria_presentacion(self):
        assert self._entrada("slides.pptx").categoria == CATEGORIA_PRESENTACION

    def test_sin_extension_usa_tamanio_grande(self):
        e = self._entrada("1BTM61dd", tamanio=_50_MB + 1)
        assert e.categoria == CATEGORIA_PROBABLE_VIDEO

    def test_sin_extension_usa_tamanio_pequeno(self):
        e = self._entrada("1BTM61dd", tamanio=1024)
        assert e.categoria == CATEGORIA_PROBABLE_DOCUMENTO

    def test_extension_tiene_prioridad_sobre_tamanio(self):
        # Un PDF pequeño (<100KB) debe ser documento, no probable_documento
        e = self._entrada("micro.pdf", tamanio=1024)
        assert e.categoria == CATEGORIA_DOCUMENTO

    def test_duplicado_drive_con_numero(self):
        e = self._entrada("Biomecanica (1).pdf")
        assert e.es_duplicado_drive is True

    def test_duplicado_drive_con_numero_alto(self):
        e = self._entrada("archivo (12).docx")
        assert e.es_duplicado_drive is True

    def test_no_duplicado_nombre_normal(self):
        e = self._entrada("Biomecanica.pdf")
        assert e.es_duplicado_drive is False

    def test_no_duplicado_con_parentesis_no_numero(self):
        # "archivo (abc).pdf" no es un duplicado de Drive
        e = self._entrada("Carrera (5,10)k.pdf")
        assert e.es_duplicado_drive is False


# ─── resumir — duplicados ─────────────────────────────────────────────────────

class TestResumirDuplicados:
    def test_cuenta_duplicados_drive(self):
        entradas = [
            GvfsEntrada(Path("/x/libro.pdf"),       False, False, 50_000, "2026-01-01"),
            GvfsEntrada(Path("/x/libro (1).pdf"),   False, False, 50_000, "2026-01-01"),
            GvfsEntrada(Path("/x/libro (2).pdf"),   False, False, 50_000, "2026-01-01"),
            GvfsEntrada(Path("/x/otro.docx"),       False, False, 10_000, "2026-01-01"),
        ]
        r = resumir(entradas)
        assert r.duplicados_drive == 2

    def test_sin_duplicados(self):
        entradas = [
            GvfsEntrada(Path("/x/a.pdf"),  False, False, 50_000, "2026-01-01"),
            GvfsEntrada(Path("/x/b.docx"), False, False, 10_000, "2026-01-01"),
        ]
        r = resumir(entradas)
        assert r.duplicados_drive == 0

    def test_directorios_no_cuentan_como_duplicados(self):
        entradas = [
            GvfsEntrada(Path("/x/sub (1)"), False, True, 0, "2026-01-01"),
        ]
        r = resumir(entradas)
        assert r.duplicados_drive == 0


# ─── generar_reporte_md — modo local ─────────────────────────────────────────

class TestGenerarReporteMdLocal:
    def _entradas(self, tmp_path: Path) -> list[GvfsEntrada]:
        return [
            GvfsEntrada(tmp_path / "Personal" / "doc.pdf",        False, False, 50_000, "2026-01-01"),
            GvfsEntrada(tmp_path / "Personal" / "doc (1).pdf",    False, False, 50_000, "2026-01-01"),
            GvfsEntrada(tmp_path / "Fotos" / "foto.jpg",          False, False, 200_000, "2026-01-01"),
            GvfsEntrada(tmp_path / "Fotos",                       False, True,  0,       "2026-01-01"),
            GvfsEntrada(tmp_path / "Personal",                    False, True,  0,       "2026-01-01"),
        ]

    def test_titulo_es_mapa_local(self, tmp_path):
        r = generar_reporte_md("Test", self._entradas(tmp_path), tmp_path, is_local=True)
        assert "Mapa Local" in r

    def test_tipo_frontmatter_es_mapa_local(self, tmp_path):
        r = generar_reporte_md("Test", self._entradas(tmp_path), tmp_path, is_local=True)
        assert "tipo: mapa-local" in r

    def test_contiene_seccion_por_carpeta(self, tmp_path):
        r = generar_reporte_md("Test", self._entradas(tmp_path), tmp_path, is_local=True)
        assert "Por carpeta" in r

    def test_contiene_seccion_duplicados(self, tmp_path):
        r = generar_reporte_md("Test", self._entradas(tmp_path), tmp_path, is_local=True)
        assert "Duplicados probables" in r

    def test_contiene_notas_extension(self, tmp_path):
        r = generar_reporte_md("Test", self._entradas(tmp_path), tmp_path, is_local=True)
        assert "clasificación por extensión" in r.lower() or "Clasificación por extensión" in r

    def test_modo_gvfs_no_muestra_por_carpeta(self, tmp_path):
        r = generar_reporte_md("Test", self._entradas(tmp_path), tmp_path, is_local=False)
        assert "Por carpeta" not in r

    def test_muestra_duplicados_drive_en_frontmatter(self, tmp_path):
        r = generar_reporte_md("Test", self._entradas(tmp_path), tmp_path, is_local=True)
        assert "duplicados_drive: 1" in r
