"""Tests para escuela_docs — procesamiento de documentos escolares sin tokens de IA."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.organizador_hdd.escuela_docs import (
    UMBRAL_LIBRO,
    ClasificacionImagen,
    ResultadoDoc,
    ResultadoSync,
    _extraer_cuerpo_editable,
    _markdown_a_tex_regex,
    _tex_a_markdown_regex,
    clasificar_imagen_escolar,
    obsidian_a_tex,
    pdf_a_obsidian,
    sincronizar_tex,
    tex_a_obsidian,
    txt_a_obsidian,
)


# ─── txt_a_obsidian ───────────────────────────────────────────────────────────

class TestTxtAObsidian:

    def test_crea_nota_nueva(self, tmp_path):
        txt = tmp_path / "apuntes.txt"
        txt.write_text("Contenido de mis apuntes", encoding="utf-8")
        vault = tmp_path / "vault"

        res = txt_a_obsidian(txt, vault, "Sem01", "Algoritmos")

        assert res.ok
        assert res.creado
        assert not res.sin_cambios
        nota = res.ruta_nota
        assert nota.exists()
        contenido = nota.read_text(encoding="utf-8")
        assert "Contenido de mis apuntes" in contenido
        assert "tags:" in contenido
        assert "fuente:" in contenido
        assert "<!-- fuente:inicio -->" in contenido
        assert "<!-- fuente:fin -->" in contenido

    def test_actualiza_cuerpo_preserva_frontmatter_manual(self, tmp_path):
        txt = tmp_path / "notas.txt"
        txt.write_text("Versión 1", encoding="utf-8")
        vault = tmp_path / "vault"

        res1 = txt_a_obsidian(txt, vault, "Sem02", "BD")
        nota = res1.ruta_nota

        # Agregar contenido manual fuera de los marcadores
        contenido_actual = nota.read_text(encoding="utf-8")
        nota.write_text(contenido_actual + "\n## Mis notas personales\nExtra manual.", encoding="utf-8")

        # Actualizar fuente
        txt.write_text("Versión 2 actualizada", encoding="utf-8")
        res2 = txt_a_obsidian(txt, vault, "Sem02", "BD")

        assert not res2.creado
        assert not res2.sin_cambios
        contenido_final = nota.read_text(encoding="utf-8")
        assert "Versión 2 actualizada" in contenido_final
        assert "Mis notas personales" in contenido_final  # se preservó

    def test_sin_cambios_si_mismo_contenido(self, tmp_path):
        txt = tmp_path / "igual.txt"
        txt.write_text("Mismo texto", encoding="utf-8")
        vault = tmp_path / "vault"

        txt_a_obsidian(txt, vault, "Sem01", "Mate")
        res2 = txt_a_obsidian(txt, vault, "Sem01", "Mate")

        assert res2.sin_cambios

    def test_maneja_codificacion_latin1(self, tmp_path):
        txt = tmp_path / "latin.txt"
        txt.write_bytes("Álgebra lineal ñoño".encode("latin-1"))
        vault = tmp_path / "vault"

        res = txt_a_obsidian(txt, vault, "Sem03", "Álgebra")
        assert res.ok

    def test_archivo_inexistente_devuelve_error(self, tmp_path):
        vault = tmp_path / "vault"
        res = txt_a_obsidian(tmp_path / "no_existe.txt", vault, "Sem01", "X")
        assert not res.ok
        assert "no se pudo leer" in res.error


# ─── pdf_a_obsidian ───────────────────────────────────────────────────────────

class TestPdfAObsidian:

    def test_pdf_mayor_umbral_devuelve_error(self, tmp_path):
        vault = tmp_path / "vault"
        with patch("src.organizador_hdd.escuela_docs._extraer_pdf") as mock_ext:
            mock_ext.return_value = (UMBRAL_LIBRO + 5, None)
            res = pdf_a_obsidian(tmp_path / "libro.pdf", vault, "Sem01", "SO")
        assert not res.ok
        assert "libro" in res.error.lower() or "Calibre" in res.error

    def test_pdf_menor_umbral_crea_nota(self, tmp_path):
        vault = tmp_path / "vault"
        with patch("src.organizador_hdd.escuela_docs._extraer_pdf") as mock_ext:
            mock_ext.return_value = (10, "Introducción a los sistemas operativos.\nProcesos y hilos.")
            res = pdf_a_obsidian(tmp_path / "apuntes_so.pdf", vault, "Sem04", "SO")
        assert res.ok
        assert res.creado
        contenido = res.ruta_nota.read_text(encoding="utf-8")
        assert "Introducción a los sistemas operativos" in contenido
        assert "paginas: 10" in contenido

    def test_pdf_sin_texto_extraible_crea_nota_con_aviso(self, tmp_path):
        vault = tmp_path / "vault"
        with patch("src.organizador_hdd.escuela_docs._extraer_pdf") as mock_ext:
            mock_ext.return_value = (5, None)
            res = pdf_a_obsidian(tmp_path / "escaneado.pdf", vault, "Sem01", "Calc")
        assert res.ok
        contenido = res.ruta_nota.read_text(encoding="utf-8")
        assert "pypdf" in contenido or "pdfplumber" in contenido

    def test_pdf_igual_contenido_sin_cambios(self, tmp_path):
        vault = tmp_path / "vault"
        with patch("src.organizador_hdd.escuela_docs._extraer_pdf") as mock_ext:
            mock_ext.return_value = (8, "Texto idéntico")
            pdf_a_obsidian(tmp_path / "rep.pdf", vault, "Sem01", "Prog")
            res2 = pdf_a_obsidian(tmp_path / "rep.pdf", vault, "Sem01", "Prog")
        assert res2.sin_cambios

    def test_pdf_exactamente_umbral_es_libro(self, tmp_path):
        vault = tmp_path / "vault"
        with patch("src.organizador_hdd.escuela_docs._extraer_pdf") as mock_ext:
            mock_ext.return_value = (UMBRAL_LIBRO, None)
            res = pdf_a_obsidian(tmp_path / "exacto.pdf", vault, "Sem01", "Mat")
        assert not res.ok


# ─── clasificar_imagen_escolar ────────────────────────────────────────────────

class TestClasificarImagenEscolar:

    def test_svg_es_diagrama(self, tmp_path):
        svg = tmp_path / "uml.svg"
        svg.write_text("<svg/>", encoding="utf-8")
        res = clasificar_imagen_escolar(svg)
        assert res.categoria == "diagrama"

    def test_nombre_camara_sin_pil_es_foto_escolar(self, tmp_path):
        img = tmp_path / "IMG_20230101_120000.jpg"
        img.write_bytes(b"\x00")
        with patch("src.organizador_hdd.escuela_docs._PIL_OK", False):
            res = clasificar_imagen_escolar(img)
        assert res.categoria == "foto_escolar"
        assert res.confianza == "heuristica"

    def test_sin_pil_nombre_normal_es_diagrama(self, tmp_path):
        img = tmp_path / "grafica_fuerza.png"
        img.write_bytes(b"\x00")
        with patch("src.organizador_hdd.escuela_docs._PIL_OK", False):
            res = clasificar_imagen_escolar(img)
        assert res.categoria == "diagrama"

    def test_con_exif_camara_es_foto_escolar(self, tmp_path):
        img = tmp_path / "laboratorio.jpg"
        img.write_bytes(b"\x00")
        mock_img = MagicMock()
        mock_img.__enter__ = lambda s: s
        mock_img.__exit__ = MagicMock(return_value=False)
        mock_img.size = (3024, 4032)
        mock_img.getexif.return_value = {271: "Canon", 272: "EOS 90D"}

        with patch("src.organizador_hdd.escuela_docs._PIL_OK", True), \
             patch("src.organizador_hdd.escuela_docs._PIL") as mock_pil:
            mock_pil.open.return_value = mock_img
            res = clasificar_imagen_escolar(img)

        assert res.categoria == "foto_escolar"
        assert res.tiene_camara_exif

    def test_resolucion_slide_sin_exif_camara_es_captura_clase(self, tmp_path):
        img = tmp_path / "diapositiva.png"
        img.write_bytes(b"\x00")
        mock_img = MagicMock()
        mock_img.__enter__ = lambda s: s
        mock_img.__exit__ = MagicMock(return_value=False)
        mock_img.size = (1920, 1080)
        mock_img.getexif.return_value = {}  # sin EXIF de cámara

        with patch("src.organizador_hdd.escuela_docs._PIL_OK", True), \
             patch("src.organizador_hdd.escuela_docs._PIL") as mock_pil:
            mock_pil.open.return_value = mock_img
            res = clasificar_imagen_escolar(img)

        assert res.categoria == "captura_clase"
        assert res.ancho == 1920

    def test_png_pequeno_sin_exif_es_diagrama(self, tmp_path):
        img = tmp_path / "grafica_datos.png"
        img.write_bytes(b"\x00")
        mock_img = MagicMock()
        mock_img.__enter__ = lambda s: s
        mock_img.__exit__ = MagicMock(return_value=False)
        mock_img.size = (640, 480)
        mock_img.getexif.return_value = {}

        with patch("src.organizador_hdd.escuela_docs._PIL_OK", True), \
             patch("src.organizador_hdd.escuela_docs._PIL") as mock_pil:
            mock_pil.open.return_value = mock_img
            res = clasificar_imagen_escolar(img)

        assert res.categoria == "diagrama"


# ─── tex_a_obsidian ───────────────────────────────────────────────────────────

class TestTexAObsidian:

    def _nota_desde_tex(self, tmp_path, contenido_tex):
        tex = tmp_path / "tarea.tex"
        tex.write_text(contenido_tex, encoding="utf-8")
        vault = tmp_path / "vault"
        with patch("src.organizador_hdd.escuela_docs._pandoc_disponible", return_value=False):
            return tex_a_obsidian(tex, vault, "Sem05", "Redes"), tex, vault

    def test_crea_nota_desde_tex(self, tmp_path):
        tex_content = r"\section{Introducción}\nEste es un documento de redes."
        res, tex, vault = self._nota_desde_tex(tmp_path, tex_content)
        assert res.ok
        assert res.creado
        contenido = res.ruta_nota.read_text(encoding="utf-8")
        assert "tipo: tex" in contenido

    def test_section_convierte_a_heading(self, tmp_path):
        tex_content = r"\section{Conceptos Básicos}" + "\nTexto de la sección."
        res, *_ = self._nota_desde_tex(tmp_path, tex_content)
        contenido = res.ruta_nota.read_text(encoding="utf-8")
        assert "## Conceptos Básicos" in contenido

    def test_textbf_convierte_a_bold(self, tmp_path):
        tex_content = r"La \textbf{red de área local} es importante."
        res, *_ = self._nota_desde_tex(tmp_path, tex_content)
        contenido = res.ruta_nota.read_text(encoding="utf-8")
        assert "**red de área local**" in contenido

    def test_archivo_inexistente_devuelve_error(self, tmp_path):
        vault = tmp_path / "vault"
        with patch("src.organizador_hdd.escuela_docs._pandoc_disponible", return_value=False):
            res = tex_a_obsidian(tmp_path / "no_existe.tex", vault, "Sem01", "X")
        assert not res.ok


# ─── obsidian_a_tex ───────────────────────────────────────────────────────────

class TestObsidianATex:

    def test_crea_tex_desde_md(self, tmp_path):
        md = tmp_path / "apuntes.md"
        md.write_text(
            "---\ntags: [test]\n---\n\n"
            "<!-- fuente:inicio -->\n## Redes\nContenido.\n<!-- fuente:fin -->\n",
            encoding="utf-8",
        )
        dest_tex = tmp_path / "output.tex"
        with patch("src.organizador_hdd.escuela_docs._pandoc_disponible", return_value=False):
            res = obsidian_a_tex(md, dest_tex)
        assert res.ok
        assert res.sincronizado
        assert dest_tex.exists()
        contenido = dest_tex.read_text(encoding="utf-8")
        assert "\\documentclass" in contenido
        assert "\\section{Redes}" in contenido

    def test_sin_cambios_si_mismo_contenido(self, tmp_path):
        md = tmp_path / "igual.md"
        md.write_text("# Título\nTexto.", encoding="utf-8")
        dest_tex = tmp_path / "igual.tex"
        with patch("src.organizador_hdd.escuela_docs._pandoc_disponible", return_value=False):
            obsidian_a_tex(md, dest_tex)
            res2 = obsidian_a_tex(md, dest_tex)
        assert not res2.sincronizado
        assert res2.direccion == "sin_cambios"


# ─── sincronizar_tex ──────────────────────────────────────────────────────────

class TestSincronizarTex:

    def test_crea_md_si_no_existe(self, tmp_path):
        tex = tmp_path / "apuntes.tex"
        tex.write_text(r"\section{Intro}" + "\nTexto inicial.", encoding="utf-8")
        md = tmp_path / "vault" / "Conocimiento" / "Universidad" / "Sem01" / "SO" / "apuntes.md"
        with patch("src.organizador_hdd.escuela_docs._pandoc_disponible", return_value=False):
            res = sincronizar_tex(tex, md, vault=tmp_path / "vault", semestre="Sem01", materia="SO")
        assert res.ok
        assert res.sincronizado
        assert res.direccion == "tex_a_md"

    def test_tex_mas_nuevo_actualiza_md(self, tmp_path):
        tex = tmp_path / "doc.tex"
        tex.write_text(r"\section{Original}", encoding="utf-8")
        md = tmp_path / "doc.md"

        # Crear md primero
        md.write_text("# Viejo\nContenido viejo.\n", encoding="utf-8")

        # tex más nuevo que md
        import time
        time.sleep(0.01)
        tex.touch()

        with patch("src.organizador_hdd.escuela_docs._pandoc_disponible", return_value=False):
            res = sincronizar_tex(tex, md)

        assert res.ok
        assert res.sincronizado
        assert res.direccion == "tex_a_md"

    def test_md_mas_nuevo_actualiza_tex(self, tmp_path):
        tex = tmp_path / "doc.tex"
        tex.write_text("\\documentclass{article}\n\\begin{document}\nViejo.\n\\end{document}\n",
                       encoding="utf-8")
        md = tmp_path / "doc.md"
        md.write_text("<!-- fuente:inicio -->\n## Nuevo\nContenido nuevo.\n<!-- fuente:fin -->\n",
                      encoding="utf-8")

        # md más nuevo que tex
        import time
        time.sleep(0.01)
        md.touch()

        with patch("src.organizador_hdd.escuela_docs._pandoc_disponible", return_value=False):
            res = sincronizar_tex(tex, md)

        assert res.ok
        assert res.sincronizado
        assert res.direccion == "md_a_tex"

    def test_sin_cambios_mismos_tiempos(self, tmp_path):
        tex = tmp_path / "doc.tex"
        md = tmp_path / "doc.md"
        tex.write_text("content", encoding="utf-8")
        md.write_text("# content", encoding="utf-8")

        # Forzar mismo mtime
        mtime = tex.stat().st_mtime
        import os
        os.utime(str(md), (mtime, mtime))
        os.utime(str(tex), (mtime, mtime))

        with patch("src.organizador_hdd.escuela_docs._pandoc_disponible", return_value=False):
            res = sincronizar_tex(tex, md)

        assert res.direccion == "sin_cambios"

    def test_tex_inexistente_devuelve_error(self, tmp_path):
        md = tmp_path / "doc.md"
        md.write_text("# Hola", encoding="utf-8")
        res = sincronizar_tex(tmp_path / "no_existe.tex", md)
        assert not res.ok


# ─── Conversión regex ─────────────────────────────────────────────────────────

class TestTexAMarkdownRegex:

    def test_section_a_h2(self):
        md = _tex_a_markdown_regex(r"\section{Título}")
        assert "## Título" in md

    def test_subsection_a_h3(self):
        md = _tex_a_markdown_regex(r"\subsection{Sub}")
        assert "### Sub" in md

    def test_textbf_a_bold(self):
        md = _tex_a_markdown_regex(r"texto \textbf{importante} aquí")
        assert "**importante**" in md

    def test_textit_a_cursiva(self):
        md = _tex_a_markdown_regex(r"\textit{énfasis}")
        assert "*énfasis*" in md

    def test_itemize_a_lista(self):
        tex = "\\begin{itemize}\n\\item Primero\n\\item Segundo\n\\end{itemize}"
        md = _tex_a_markdown_regex(tex)
        assert "- Primero" in md
        assert "- Segundo" in md

    def test_extrae_body_del_documento(self):
        tex = "\\documentclass{article}\n\\begin{document}\nContenido útil.\n\\end{document}"
        md = _tex_a_markdown_regex(tex)
        assert "Contenido útil" in md
        assert "documentclass" not in md

    def test_elimina_comentarios(self):
        md = _tex_a_markdown_regex("Texto real. % este es un comentario\nMás texto.")
        assert "comentario" not in md
        assert "Texto real" in md


class TestMarkdownATexRegex:

    def test_h2_a_section(self):
        tex = _markdown_a_tex_regex("## Mi sección")
        assert "\\section{Mi sección}" in tex

    def test_h3_a_subsection(self):
        tex = _markdown_a_tex_regex("### Sub")
        assert "\\subsection{Sub}" in tex

    def test_bold_a_textbf(self):
        tex = _markdown_a_tex_regex("texto **importante** aquí")
        assert "\\textbf{importante}" in tex

    def test_lista_a_itemize(self):
        tex = _markdown_a_tex_regex("- Item uno\n- Item dos")
        assert "\\begin{itemize}" in tex
        assert "\\item Item uno" in tex
        assert "\\end{itemize}" in tex

    def test_incluye_documentclass(self):
        tex = _markdown_a_tex_regex("# Título", titulo="Mi Doc")
        assert "\\documentclass{article}" in tex
        assert "\\begin{document}" in tex
        assert "\\end{document}" in tex


class TestExtraerCuerpoEditable:

    def test_extrae_entre_marcadores(self):
        md = "---\ntags: [x]\n---\n\n<!-- fuente:inicio -->\nContenido editable.\n<!-- fuente:fin -->\n## Extra"
        assert _extraer_cuerpo_editable(md) == "Contenido editable."

    def test_sin_marcadores_quita_frontmatter(self):
        md = "---\ntags: [x]\n---\n\n# Título\nCuerpo."
        cuerpo = _extraer_cuerpo_editable(md)
        assert "# Título" in cuerpo
        assert "tags:" not in cuerpo
