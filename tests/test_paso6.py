import json
from pathlib import Path
import pytest
from unittest.mock import patch
from src.organizador_hdd.paso6 import (
    clasificar, detectar_pendientes, construir_plan, ejecutar_plan,
    _EXT_A_CATEGORIA, _DESTINO_POR_CATEGORIA, _destino_privado,
    es_proyecto_programacion, _detectar_lenguaje, _destino_proyecto,
    _es_carpeta_codigo_bloque,
    _es_carpeta_curso, _destino_carpeta_curso,
    _normalizar_nombre_archivo, _calcular_renombres_curso, _revisar_archivos_curso,
    _en_carpeta_audiolibro,
)

_VERIFICAR_OK = patch("src.organizador_hdd.paso6.verificar_archivo", return_value=(True, ""))


class TestClasificar:
    def test_jpg_es_imagen(self, tmp_path):
        ruta = tmp_path / "foto.jpg"
        assert clasificar(ruta) == ("imagen", "extension")

    def test_mp4_es_video(self, tmp_path):
        ruta = tmp_path / "video.mp4"
        assert clasificar(ruta) == ("video", "extension")

    def test_mp3_es_audio(self, tmp_path):
        ruta = tmp_path / "cancion.mp3"
        assert clasificar(ruta) == ("audio", "extension")

    def test_pdf_es_documento(self, tmp_path):
        ruta = tmp_path / "doc.pdf"
        assert clasificar(ruta) == ("documento", "extension")

    def test_py_es_codigo(self, tmp_path):
        ruta = tmp_path / "script.py"
        assert clasificar(ruta) == ("codigo", "extension")

    def test_zip_es_comprimido(self, tmp_path):
        ruta = tmp_path / "archivo.zip"
        assert clasificar(ruta) == ("comprimido", "extension")

    def test_ext_desconocida(self, tmp_path):
        ruta = tmp_path / "archivo.xyz123"
        cat, metodo = clasificar(ruta)
        assert cat == "desconocido"

    def test_cbr_es_comic(self, tmp_path):
        ruta = tmp_path / "comic.cbr"
        assert clasificar(ruta) == ("comic", "extension")

    def test_cbz_es_comic(self, tmp_path):
        ruta = tmp_path / "manga.cbz"
        assert clasificar(ruta) == ("comic", "extension")

    def test_tcx_es_fitness(self, tmp_path):
        ruta = tmp_path / "actividad.tcx"
        assert clasificar(ruta) == ("fitness", "extension")

    def test_srt_es_subtitulo(self, tmp_path):
        ruta = tmp_path / "sub.srt"
        assert clasificar(ruta) == ("subtitulo", "extension")

    def test_todas_categorias_tienen_destino(self):
        categorias = set(_EXT_A_CATEGORIA.values()) | {"desconocido", "dañado"}
        for cat in categorias:
            assert cat in _DESTINO_POR_CATEGORIA, f"Sin destino para: {cat}"

    def test_mp3_en_carpeta_audiolibros_es_audiolibro(self, tmp_path):
        audiolibros = tmp_path / "audiolibros"
        audiolibros.mkdir()
        ruta = audiolibros / "capitulo1.mp3"
        assert clasificar(ruta) == ("audiolibro", "ruta_audiolibro")

    def test_mp3_sin_carpeta_audiolibros_es_audio(self, tmp_path):
        ruta = tmp_path / "cancion.mp3"
        assert clasificar(ruta) == ("audio", "extension")

    def test_en_carpeta_audiolibro_detecta_keyword(self, tmp_path):
        carpeta = tmp_path / "Audio libros" / "libro1"
        carpeta.mkdir(parents=True)
        ruta = carpeta / "cap01.mp3"
        assert _en_carpeta_audiolibro(ruta) is True

    def test_audiolibro_destino_es_04_libros(self):
        assert "04_libros" in _DESTINO_POR_CATEGORIA.get("audiolibro", "")


class TestDetectarPendientes:
    def test_detecta_archivos_mixtos(self, tmp_path):
        (tmp_path / "foto.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "doc.pdf").write_bytes(b"%PDF")
        (tmp_path / "song.mp3").write_bytes(b"\xff\xfb")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        assert resultado.total == 3

    def test_clasifica_correctamente(self, tmp_path):
        (tmp_path / "foto.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "code.py").write_text("pass")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        cats = {a.categoria for a in resultado.archivos}
        assert "imagen" in cats
        assert "codigo" in cats

    def test_por_categoria(self, tmp_path):
        for i in range(3):
            (tmp_path / f"img{i}.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "doc.pdf").write_bytes(b"%PDF")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        por_cat = resultado.por_categoria()
        assert por_cat["imagen"] == 3
        assert por_cat["documento"] == 1


class TestPlan:
    def test_imagen_va_a_01b_imagenes(self, tmp_path):
        (tmp_path / "img.jpg").write_bytes(b"\xff\xd8")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        plan = construir_plan(resultado, tmp_path / "org")
        assert "01b_imagenes" in plan.movimientos[0]["destino"]

    def test_video_va_a_02_videos(self, tmp_path):
        (tmp_path / "v.mp4").write_bytes(b"\x00\x00\x00\x20")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        plan = construir_plan(resultado, tmp_path / "org")
        assert "02_videos" in plan.movimientos[0]["destino"]

    def test_desconocido_va_a_sin_clasificar(self, tmp_path):
        (tmp_path / "raro.xyz123").write_bytes(b"\x00")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        plan = construir_plan(resultado, tmp_path / "org")
        assert "sin_clasificar" in plan.movimientos[0]["destino"]


class TestEjecucion:
    def test_dry_run_no_mueve(self, tmp_path):
        orig = tmp_path / "archivo.jpg"
        orig.write_bytes(b"\xff\xd8")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        plan = construir_plan(resultado, tmp_path / "org")
        ejec = ejecutar_plan(plan, tmp_path / "log.json", dry_run=True)
        assert orig.exists()
        assert len(ejec.movidos) == 1

    def test_real_mueve_y_escribe_log(self, tmp_path):
        orig = tmp_path / "pendiente" / "f.mp3"
        orig.parent.mkdir()
        orig.write_bytes(b"\xff\xfb")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path / "pendiente")
        plan = construir_plan(resultado, tmp_path / "org")
        log = tmp_path / "log.json"
        ejec = ejecutar_plan(plan, log, dry_run=False)
        assert not orig.exists()
        assert log.exists()
        datos = json.loads(log.read_text())
        assert datos["paso"] == 6


def test_idempotente_paso6_omite_identico(tmp_path):
    """Paso 6: archivo ya en destino con mismo contenido → se omite."""
    pendiente = tmp_path / "pendiente"
    pendiente.mkdir()
    contenido = b"\xff\xfb" * 50
    origen = pendiente / "cancion.mp3"
    origen.write_bytes(contenido)

    org = tmp_path / "org"
    (org / "03_musica/_sin_artista").mkdir(parents=True)
    (org / "03_musica/_sin_artista" / "cancion.mp3").write_bytes(contenido)

    with _VERIFICAR_OK:
        resultado = detectar_pendientes(pendiente)
    plan = construir_plan(resultado, org)

    assert len(plan.movimientos) == 0
    assert len(plan.omitidos_identicos) == 1


# ─── Carpetas privadas ────────────────────────────────────────────────────────

class TestCarpetasPrivadas:
    def test_archivo_en_privado_categorizado_como_privado(self, tmp_path):
        carpeta = tmp_path / "_privado"
        carpeta.mkdir()
        archivo = carpeta / "datos.xlsx"
        archivo.write_bytes(b"PK\x03\x04")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        archivos_privados = [a for a in resultado.archivos if a.categoria == "privado"]
        assert len(archivos_privados) == 1
        assert archivos_privados[0].es_privado is True

    def test_archivo_privado_va_a_punto_privado(self, tmp_path):
        carpeta = tmp_path / "privados"
        carpeta.mkdir()
        archivo = carpeta / "contrato.pdf"
        archivo.write_bytes(b"%PDF")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        plan = construir_plan(resultado, tmp_path / "org")
        destinos = [m["destino"] for m in plan.movimientos]
        assert any(".privado" in d for d in destinos)

    def test_archivo_normal_no_es_privado(self, tmp_path):
        (tmp_path / "imagen.jpg").write_bytes(b"\xff\xd8")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        assert all(not a.es_privado for a in resultado.archivos)

    def test_privado_metodo_es_carpeta_privada(self, tmp_path):
        carpeta = tmp_path / "_privado"
        carpeta.mkdir()
        (carpeta / "doc.doc").write_bytes(b"\xd0\xcf\x11\xe0")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        privado = resultado.archivos[0]
        assert privado.metodo == "carpeta_privada"


# ─── Modo --privado (forzar_privado) ─────────────────────────────────────────

class TestForzarPrivado:
    def test_forzar_privado_clasifica_como_privado(self, tmp_path):
        (tmp_path / "foto.jpg").write_bytes(b"\xff\xd8")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path, forzar_privado=True)
        assert all(a.categoria == "privado" for a in resultado.archivos)

    def test_imagen_privada_va_a_privado_fotos(self, tmp_path):
        (tmp_path / "IMG_20240101.jpg").write_bytes(b"\xff\xd8")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path, forzar_privado=True)
        plan = construir_plan(resultado, tmp_path / "org")
        destino = plan.movimientos[0]["destino"]
        assert ".privado" in destino
        assert "fotos" in destino

    def test_video_privado_va_a_privado_videos(self, tmp_path):
        (tmp_path / "pelicula.mp4").write_bytes(b"\x00\x00\x00\x20ftyp")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path, forzar_privado=True)
        plan = construir_plan(resultado, tmp_path / "org")
        destino = plan.movimientos[0]["destino"]
        assert ".privado" in destino
        assert "videos" in destino

    def test_audio_privado_va_a_privado_audio(self, tmp_path):
        (tmp_path / "cancion.mp3").write_bytes(b"\xff\xfb")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path, forzar_privado=True)
        plan = construir_plan(resultado, tmp_path / "org")
        destino = plan.movimientos[0]["destino"]
        assert ".privado" in destino
        assert "audio" in destino

    def test_archivo_desconocido_privado_va_a_privado_varios(self, tmp_path):
        (tmp_path / "datos.xyz").write_bytes(b"\x00\x01")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path, forzar_privado=True)
        plan = construir_plan(resultado, tmp_path / "org")
        destino = plan.movimientos[0]["destino"]
        assert ".privado" in destino
        assert "varios" in destino

    def test_destino_privado_helper_foto(self, tmp_path):
        ruta = tmp_path / "VID_20220315.jpg"
        dest = _destino_privado(ruta, tmp_path / "respaldo")
        assert ".privado" in str(dest)
        assert "fotos" in str(dest)
        assert "2022" in str(dest)

    def test_destino_privado_helper_audio(self, tmp_path):
        ruta = tmp_path / "track.mp3"
        dest = _destino_privado(ruta, tmp_path / "respaldo")
        assert ".privado/audio" in str(dest)


# ─── Archivos dañados en paso6 ────────────────────────────────────────────────

class TestArchivosDanadosPaso6:
    def test_archivo_danado_categorizado_como_danado(self, tmp_path):
        pendiente = tmp_path / "checar"
        pendiente.mkdir()
        rota = pendiente / "rota.jpg"
        rota.write_bytes(b"\xff\xd8")
        from unittest.mock import patch
        with patch("src.organizador_hdd.paso6.verificar_archivo", return_value=(False, "truncado")):
            resultado = detectar_pendientes(pendiente, base_hdd=tmp_path)
        danados = [a for a in resultado.archivos if a.categoria == "dañado"]
        assert len(danados) == 1
        assert danados[0].error_integridad == "truncado"
        assert danados[0].ruta_danado is not None

    def test_archivo_danado_va_a_pendientes_danados_en_plan(self, tmp_path):
        pendiente = tmp_path / "checar"
        pendiente.mkdir()
        rota = pendiente / "rota.mp3"
        rota.write_bytes(b"\xff\xfb")
        from unittest.mock import patch
        with patch("src.organizador_hdd.paso6.verificar_archivo", return_value=(False, "error io")):
            resultado = detectar_pendientes(pendiente, base_hdd=tmp_path)
        plan = construir_plan(resultado, tmp_path / "org")
        assert any("dañados" in m["destino"] for m in plan.movimientos)

    def test_archivo_sano_no_va_a_danados(self, tmp_path):
        pendiente = tmp_path / "checar"
        pendiente.mkdir()
        buena = pendiente / "buena.mp3"
        buena.write_bytes(b"\xff\xfb")
        from unittest.mock import patch
        with patch("src.organizador_hdd.paso6.verificar_archivo", return_value=(True, "")):
            resultado = detectar_pendientes(pendiente, base_hdd=tmp_path)
        assert all(a.categoria != "dañado" for a in resultado.archivos)


# ─── Proyectos de programación (unidades atómicas) ───────────────────────────

class TestProyectosProgramacion:
    def test_detecta_requirements_txt(self, tmp_path):
        proyecto = tmp_path / "mi_lambda"
        proyecto.mkdir()
        (proyecto / "requirements.txt").write_text("boto3")
        assert es_proyecto_programacion(proyecto)

    def test_detecta_pom_xml(self, tmp_path):
        proyecto = tmp_path / "proyecto_java"
        proyecto.mkdir()
        (proyecto / "pom.xml").write_text("<project/>")
        assert es_proyecto_programacion(proyecto)

    def test_detecta_git(self, tmp_path):
        proyecto = tmp_path / "repo"
        proyecto.mkdir()
        (proyecto / ".git").mkdir()
        assert es_proyecto_programacion(proyecto)

    def test_detecta_package_json(self, tmp_path):
        proyecto = tmp_path / "web_app"
        proyecto.mkdir()
        (proyecto / "package.json").write_text("{}")
        assert es_proyecto_programacion(proyecto)

    def test_no_detecta_carpeta_normal(self, tmp_path):
        carpeta = tmp_path / "documentos"
        carpeta.mkdir()
        (carpeta / "doc.pdf").write_bytes(b"%PDF")
        assert not es_proyecto_programacion(carpeta)

    def test_detecta_lenguaje_python(self, tmp_path):
        proyecto = tmp_path / "lambda"
        proyecto.mkdir()
        (proyecto / "requirements.txt").write_text("boto3")
        assert _detectar_lenguaje(proyecto) == "python"

    def test_detecta_lenguaje_java(self, tmp_path):
        proyecto = tmp_path / "app"
        proyecto.mkdir()
        (proyecto / "pom.xml").write_text("<project/>")
        assert _detectar_lenguaje(proyecto) == "java"

    def test_detecta_lenguaje_varios_sin_indicador(self, tmp_path):
        carpeta = tmp_path / "misc"
        carpeta.mkdir()
        assert _detectar_lenguaje(carpeta) == "varios"

    def test_proyecto_se_mueve_como_unidad(self, tmp_path):
        """Proyecto detectado aparece como UNA entrada, no sus archivos individuales."""
        carpeta = tmp_path / "mi_lambda"
        carpeta.mkdir()
        (carpeta / "requirements.txt").write_text("boto3")
        (carpeta / "lambda_function.py").write_text("def handler(): pass")
        (carpeta / "utils.py").write_text("pass")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        proyectos = [a for a in resultado.archivos if a.categoria == "proyecto"]
        assert len(proyectos) == 1
        assert proyectos[0].ruta == carpeta
        # Archivos internos NO deben aparecer por separado
        nombres_no_proyecto = [a.ruta.name for a in resultado.archivos if a.categoria != "proyecto"]
        assert "lambda_function.py" not in nombres_no_proyecto
        assert "requirements.txt" not in nombres_no_proyecto

    def test_proyecto_trabajo_va_a_codigo_trabajo(self, tmp_path):
        carpeta = tmp_path / "mi_lambda"
        carpeta.mkdir()
        (carpeta / "requirements.txt").write_text("boto3")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path, contexto="trabajo")
        plan = construir_plan(resultado, tmp_path / "org")
        assert len(plan.movimientos) == 1
        destino = plan.movimientos[0]["destino"]
        assert "09_codigo" in destino
        assert "_trabajo" in destino
        assert "python" in destino

    def test_proyecto_escuela_va_a_escuela(self, tmp_path):
        carpeta = tmp_path / "practica_poo"
        carpeta.mkdir()
        (carpeta / "pom.xml").write_text("<project/>")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path, contexto="escuela")
        plan = construir_plan(resultado, tmp_path / "org")
        assert "07_escuela" in plan.movimientos[0]["destino"]

    def test_proyecto_personal_va_a_personales(self, tmp_path):
        carpeta = tmp_path / "mi_app"
        carpeta.mkdir()
        (carpeta / "package.json").write_text("{}")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path, contexto="personal")
        plan = construir_plan(resultado, tmp_path / "org")
        assert "personales" in plan.movimientos[0]["destino"]

    def test_proyecto_sin_contexto_va_a_pendientes(self, tmp_path):
        carpeta = tmp_path / "proyecto"
        carpeta.mkdir()
        (carpeta / "Cargo.toml").write_text("[package]")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        plan = construir_plan(resultado, tmp_path / "org")
        destino = plan.movimientos[0]["destino"]
        assert "09_codigo" in destino
        assert "_pendientes" in destino

    def test_archivos_fuera_de_proyecto_se_clasifican_normal(self, tmp_path):
        """Archivos sueltos junto a un proyecto se clasifican individualmente."""
        proyecto = tmp_path / "mi_lambda"
        proyecto.mkdir()
        (proyecto / "requirements.txt").write_text("boto3")
        (tmp_path / "documento.pdf").write_bytes(b"%PDF")
        (tmp_path / "cancion.mp3").write_bytes(b"\xff\xfb")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        categorias = {a.categoria for a in resultado.archivos}
        assert "proyecto" in categorias
        assert "documento" in categorias
        assert "audio" in categorias

    def test_destino_proyecto_helper(self, tmp_path):
        proyecto = tmp_path / "lambda_func"
        proyecto.mkdir()
        (proyecto / "requirements.txt").write_text("boto3")
        dest_trabajo = _destino_proyecto(proyecto, tmp_path / "respaldo", "trabajo")
        assert "09_codigo" in str(dest_trabajo)
        assert "_trabajo" in str(dest_trabajo)
        dest_escuela = _destino_proyecto(proyecto, tmp_path / "respaldo", "escuela")
        assert "07_escuela" in str(dest_escuela)
        dest_personal = _destino_proyecto(proyecto, tmp_path / "respaldo", "personal")
        assert "personales" in str(dest_personal)


# ─── Carpeta código bloque ───────────────────────────────────────────────────

class TestCodigoBloque:
    def test_carpeta_mayoria_codigo_es_bloque(self, tmp_path):
        carpeta = tmp_path / "apuntes_bd"
        carpeta.mkdir()
        for i in range(8):
            (carpeta / f"consulta_{i}.sql").write_text("SELECT 1")
        (carpeta / "notas.txt").write_text("notas")
        (carpeta / "imagen.png").write_bytes(b"\x89PNG")
        assert _es_carpeta_codigo_bloque(carpeta) is True

    def test_carpeta_mayoria_media_no_es_bloque(self, tmp_path):
        carpeta = tmp_path / "fotos_viaje"
        carpeta.mkdir()
        for i in range(8):
            (carpeta / f"foto_{i}.jpg").write_bytes(b"\xff\xd8")
        (carpeta / "notas.py").write_text("x=1")
        assert _es_carpeta_codigo_bloque(carpeta) is False

    def test_carpeta_exactamente_70_pct_es_bloque(self, tmp_path):
        carpeta = tmp_path / "scripts"
        carpeta.mkdir()
        for i in range(7):
            (carpeta / f"script_{i}.py").write_text("pass")
        for i in range(3):
            (carpeta / f"doc_{i}.pdf").write_bytes(b"%PDF")
        assert _es_carpeta_codigo_bloque(carpeta) is True

    def test_carpeta_un_archivo_no_es_bloque(self, tmp_path):
        carpeta = tmp_path / "solo_uno"
        carpeta.mkdir()
        (carpeta / "script.py").write_text("pass")
        assert _es_carpeta_codigo_bloque(carpeta) is False

    def test_carpeta_vacia_no_es_bloque(self, tmp_path):
        carpeta = tmp_path / "vacia"
        carpeta.mkdir()
        assert _es_carpeta_codigo_bloque(carpeta) is False

    def test_carpeta_python_mixto_es_bloque(self, tmp_path):
        carpeta = tmp_path / "practica_fbd"
        carpeta.mkdir()
        for ext in [".py", ".sql", ".md", ".txt", ".json"]:
            (carpeta / f"archivo{ext}").write_text("contenido")
        assert _es_carpeta_codigo_bloque(carpeta) is True

    def test_detectar_pendientes_trata_bloque_como_proyecto(self, tmp_path):
        carpeta = tmp_path / "scripts_bash"
        carpeta.mkdir()
        for i in range(8):
            (carpeta / f"deploy_{i}.sh").write_text("#!/bin/bash")
        (carpeta / "readme.md").write_text("# docs")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        categorias_metodos = {a.metodo for a in resultado.archivos if a.ruta == carpeta}
        assert "codigo_bloque" in categorias_metodos

    def test_detectar_pendientes_bloque_no_recursiona(self, tmp_path):
        carpeta = tmp_path / "proyecto_sql"
        carpeta.mkdir()
        for i in range(5):
            (carpeta / f"q{i}.sql").write_text("SELECT 1")
        (carpeta / "datos.csv").write_text("a,b")
        subcarpeta = carpeta / "sub"
        subcarpeta.mkdir()
        (subcarpeta / "otro.sql").write_text("SELECT 2")
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        rutas = [a.ruta for a in resultado.archivos]
        assert carpeta in rutas
        assert subcarpeta not in rutas


# ─── Carpeta de curso ────────────────────────────────────────────────────────

class TestCarpetaCurso:
    # ── Detección ───────────────────────────────────────────────────────────
    def test_padre_udemy_es_curso(self, tmp_path):
        udemy = tmp_path / "udemy"
        udemy.mkdir()
        curso = udemy / "python_bootcamp"
        curso.mkdir()
        (curso / "001_intro.mp4").write_bytes(b"\x00")
        assert _es_carpeta_curso(curso) is True

    def test_nombre_combina_plataforma_es_curso(self, tmp_path):
        carpeta = tmp_path / "udemy_aws_developer"
        carpeta.mkdir()
        (carpeta / "video.mp4").write_bytes(b"\x00")
        assert _es_carpeta_curso(carpeta) is True

    def test_nombre_solo_plataforma_no_es_curso(self, tmp_path):
        # "udemy" solo es un contenedor — no se trata como curso individual
        carpeta = tmp_path / "udemy"
        carpeta.mkdir()
        (carpeta / "video.mp4").write_bytes(b"\x00")
        assert _es_carpeta_curso(carpeta) is False

    def test_nombre_cursos_es_curso(self, tmp_path):
        carpeta = tmp_path / "cursos_aws"
        carpeta.mkdir()
        (carpeta / "001_intro.mp4").write_bytes(b"\x00")
        assert _es_carpeta_curso(carpeta) is True

    def test_lecciones_numeradas_es_curso(self, tmp_path):
        carpeta = tmp_path / "mi_bootcamp"
        carpeta.mkdir()
        for i in range(1, 7):
            (carpeta / f"{i:03d}_leccion.mp4").write_bytes(b"\x00")
        (carpeta / "recursos.pdf").write_bytes(b"%PDF")
        assert _es_carpeta_curso(carpeta) is True

    def test_pocos_archivos_no_es_curso(self, tmp_path):
        carpeta = tmp_path / "random_folder"
        carpeta.mkdir()
        (carpeta / "001_tema.mp4").write_bytes(b"\x00")
        (carpeta / "002_tema.mp4").write_bytes(b"\x00")
        # Solo 2 archivos (mínimo es 3)
        assert _es_carpeta_curso(carpeta) is False

    def test_archivos_sin_numero_no_es_curso(self, tmp_path):
        carpeta = tmp_path / "random_folder"
        carpeta.mkdir()
        for i in range(5):
            (carpeta / f"video_{i}.mp4").write_bytes(b"\x00")
        assert _es_carpeta_curso(carpeta) is False

    def test_proyecto_programacion_no_es_curso(self, tmp_path):
        carpeta = tmp_path / "udemy_python"
        carpeta.mkdir()
        (carpeta / "requirements.txt").write_text("flask")
        (carpeta / "app.py").write_text("pass")
        # es_proyecto_programacion tiene prioridad sobre es_curso
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        entry = next((a for a in resultado.archivos if a.ruta == carpeta), None)
        assert entry is not None
        assert entry.categoria == "proyecto"

    # ── Destino ─────────────────────────────────────────────────────────────
    def test_destino_mayoria_video_va_a_02_videos(self, tmp_path):
        carpeta = tmp_path / "aws_course"
        carpeta.mkdir()
        for i in range(7):
            (carpeta / f"{i:03d}_clase.mp4").write_bytes(b"\x00")
        (carpeta / "slides.pdf").write_bytes(b"%PDF")
        base = tmp_path / "hdd"
        dest = _destino_carpeta_curso(carpeta, base)
        assert "02_videos" in str(dest)
        assert "cursos" in str(dest)

    def test_destino_mayoria_docs_va_a_04_libros(self, tmp_path):
        carpeta = tmp_path / "curso_bd"
        carpeta.mkdir()
        for i in range(8):
            (carpeta / f"practica_{i}.pdf").write_bytes(b"%PDF")
        (carpeta / "demo.mp4").write_bytes(b"\x00")
        base = tmp_path / "hdd"
        dest = _destino_carpeta_curso(carpeta, base)
        assert "04_libros" in str(dest)
        assert "cursos" in str(dest)

    # ── Normalización de nombres ─────────────────────────────────────────────
    def test_normalizar_espacios(self):
        assert _normalizar_nombre_archivo("001 Introduction to AWS.mp4") == "001_Introduction_to_AWS.mp4"

    def test_normalizar_acentos(self):
        assert _normalizar_nombre_archivo("001 Introducción al Curso.mp4") == "001_Introduccion_al_Curso.mp4"

    def test_normalizar_caracteres_raros(self):
        resultado = _normalizar_nombre_archivo("001 ¡Hola! Mundo?.mp4")
        assert "¡" not in resultado
        assert "?" not in resultado

    def test_normalizar_sin_cambios_necesarios(self):
        assert _normalizar_nombre_archivo("001_Clean_Name.mp4") == "001_Clean_Name.mp4"

    def test_normalizar_preserva_extension(self):
        resultado = _normalizar_nombre_archivo("clase con acentos.mkv")
        assert resultado.endswith(".mkv")

    def test_calcular_renombres_detecta_archivos_a_renombrar(self, tmp_path):
        curso = tmp_path / "mi_curso"
        curso.mkdir()
        (curso / "001 Introduction.mp4").write_bytes(b"\x00")
        (curso / "002_Already_Clean.mp4").write_bytes(b"\x00")
        (curso / "003 Configuración básica.mp4").write_bytes(b"\x00")
        renombres = _calcular_renombres_curso(curso)
        nombres_nuevos = [r["nombre_nuevo"] for r in renombres]
        assert "001_Introduction.mp4" in nombres_nuevos
        assert "003_Configuracion_basica.mp4" in nombres_nuevos
        assert "002_Already_Clean.mp4" not in nombres_nuevos

    # ── Revisión de archivos problemáticos ────────────────────────────────────
    def test_revisar_detecta_archivo_vacio(self, tmp_path):
        curso = tmp_path / "curso_test"
        curso.mkdir()
        (curso / "001_intro.mp4").write_bytes(b"\x00" * 100)
        (curso / "002_vacio.mp4").write_bytes(b"")
        problemas = _revisar_archivos_curso(curso)
        motivos = [p["motivo"] for p in problemas]
        assert "vacio" in motivos

    def test_revisar_detecta_descarga_incompleta(self, tmp_path):
        curso = tmp_path / "curso_test"
        curso.mkdir()
        (curso / "001_intro.mp4").write_bytes(b"\x00" * 100)
        (curso / "002_incompleto.mp4.crdownload").write_bytes(b"\x00" * 50)
        problemas = _revisar_archivos_curso(curso)
        motivos = [p["motivo"] for p in problemas]
        assert "descarga_incompleta" in motivos

    def test_revisar_carpeta_limpia_sin_problemas(self, tmp_path):
        curso = tmp_path / "curso_ok"
        curso.mkdir()
        (curso / "001_intro.mp4").write_bytes(b"\x00" * 100)
        (curso / "002_topic.mp4").write_bytes(b"\x00" * 200)
        assert _revisar_archivos_curso(curso) == []

    # ── Integración con detectar_pendientes ────────────────────────────────
    def test_detectar_pendientes_trata_curso_como_unidad(self, tmp_path):
        curso = tmp_path / "udemy_python_course"
        curso.mkdir()
        for i in range(5):
            (curso / f"{i:03d}_clase.mp4").write_bytes(b"\x00" * 100)
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        entry = next((a for a in resultado.archivos if a.ruta == curso), None)
        assert entry is not None
        assert entry.categoria == "curso"
        assert entry.metodo == "carpeta_curso"

    def test_detectar_pendientes_curso_no_recursiona(self, tmp_path):
        curso = tmp_path / "udemy_aws"
        curso.mkdir()
        sub = curso / "seccion1"
        sub.mkdir()
        (sub / "001_intro.mp4").write_bytes(b"\x00" * 100)
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path)
        rutas = [a.ruta for a in resultado.archivos]
        assert curso in rutas
        assert sub not in rutas

    # ── Integración con construir_plan ────────────────────────────────────
    def test_construir_plan_curso_video_tiene_destino_02_videos(self, tmp_path):
        curso = tmp_path / "pendientes" / "udemy_aws_video"
        curso.mkdir(parents=True)
        for i in range(5):
            (curso / f"{i:03d}_clase.mp4").write_bytes(b"\x00" * 100)
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path / "pendientes")
        plan = construir_plan(resultado, tmp_path / "hdd")
        mov = next((m for m in plan.movimientos if "udemy_aws_video" in m["origen"]), None)
        assert mov is not None
        assert "02_videos" in mov["destino"]
        assert "cursos" in mov["destino"]

    def test_construir_plan_curso_incluye_renombres(self, tmp_path):
        curso = tmp_path / "pendientes" / "udemy_python"
        curso.mkdir(parents=True)
        (curso / "001 Intro al curso.mp4").write_bytes(b"\x00" * 100)
        (curso / "002_Clean.mp4").write_bytes(b"\x00" * 100)
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path / "pendientes")
        plan = construir_plan(resultado, tmp_path / "hdd")
        mov = next((m for m in plan.movimientos if "udemy_python" in m["origen"]), None)
        assert mov is not None
        assert "renombres_internos" in mov
        nombres_nuevos = [r["nombre_nuevo"] for r in mov["renombres_internos"]]
        assert "001_Intro_al_curso.mp4" in nombres_nuevos

    def test_ejecutar_plan_curso_renombra_archivos_internos(self, tmp_path):
        curso = tmp_path / "pendientes" / "mi_curso"
        curso.mkdir(parents=True)
        (curso / "001 Introduction.mp4").write_bytes(b"\x00" * 100)
        (curso / "002_Clean.mp4").write_bytes(b"\x00" * 100)
        with _VERIFICAR_OK:
            resultado = detectar_pendientes(tmp_path / "pendientes")
        hdd = tmp_path / "hdd"
        plan = construir_plan(resultado, hdd)
        log = tmp_path / "log.json"
        ejecutar_plan(plan, log, dry_run=False)
        # El archivo con espacio debe haber sido renombrado
        dest_curso = hdd / "02_videos" / "cursos" / "mi_curso"
        assert (dest_curso / "001_Introduction.mp4").exists()
        assert (dest_curso / "002_Clean.mp4").exists()


# ─── Exclusiones _es_carpeta_curso ───────────────────────────────────────────

class TestExclusionesCurso:
    def test_documentacion_personal_no_es_curso(self, tmp_path):
        d = tmp_path / "DocumentacionCarlosEscalona"
        d.mkdir()
        for i, name in enumerate(["1.- IMSS.pdf", "2.- curp.pdf", "3.- CSF.pdf", "4.- domicilio.pdf"]):
            (d / name).write_bytes(b"x")
        assert not _es_carpeta_curso(d)

    def test_profesional_numerado_no_es_curso(self, tmp_path):
        d = tmp_path / "Profesional en Desarrollo Senior"
        d.mkdir()
        for i in range(5):
            (d / f"0{i+1}_ficha.pdf").write_bytes(b"x")
        assert not _es_carpeta_curso(d)

    def test_curriculum_no_es_curso(self, tmp_path):
        d = tmp_path / "curriculum vitae 2026"
        d.mkdir()
        for i in range(4):
            (d / f"{i+1}_doc.pdf").write_bytes(b"x")
        assert not _es_carpeta_curso(d)

    def test_curso_real_sigue_siendo_detectado(self, tmp_path):
        d = tmp_path / "python bootcamp"
        d.mkdir()
        for i in range(6):
            (d / f"{i+1:03d}_lesson.mp4").write_bytes(b"\x00")
        assert _es_carpeta_curso(d)
