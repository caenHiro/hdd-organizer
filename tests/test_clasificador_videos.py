"""Tests para clasificador_videos — heurísticas locales sin tokens."""
from pathlib import Path
from unittest.mock import patch

import pytest

from src.organizador_hdd.clasificador_videos import (
    ClasificacionVideo,
    clasificar_video,
    destino_video,
    _extraer_fecha,
    _extraer_nombre_serie,
    _limpiar_nombre_serie,
    MESES_ES,
)


# ─── Clasificación por ruta ────────────────────────────────────────────────────

class TestClasificacionPorRuta:
    def test_ruta_dcim_es_personal(self):
        ruta = Path("/sdcard/DCIM/Camera/VID_20240101_120000.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "personal"
        assert c.confianza in ("ruta", "nombre")  # VID_ pattern detectado por nombre

    def test_ruta_whatsapp_es_personal(self):
        ruta = Path("/storage/WhatsApp/Media/WA0001.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "personal"
        assert c.confianza in ("ruta", "nombre")  # WA pattern detectado por nombre

    def test_ruta_camera_es_personal(self):
        ruta = Path("/Pictures/camera/video_familia.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "personal"
        assert c.confianza == "ruta"

    def test_ruta_series_es_serie(self):
        ruta = Path("/media/series/BreakingBad/S01E01.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "serie"
        assert c.confianza == "ruta"

    def test_ruta_movies_es_pelicula(self):
        ruta = Path("/media/movies/Inception.2010.BluRay.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "pelicula"
        assert c.confianza == "ruta"

    def test_ruta_peliculas_es_pelicula(self):
        ruta = Path("/HDD/peliculas/El_Padrino.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "pelicula"
        assert c.confianza == "ruta"

    def test_ruta_musicales_es_musical(self):
        ruta = Path("/videos/musicales/BTS - Dynamite.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "musical"
        assert c.confianza == "ruta"

    def test_ruta_documentales_es_documental(self):
        ruta = Path("/videos/documentales/Planet.Earth.S01E01.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "documental"
        assert c.confianza == "ruta"


# ─── Clasificación por nombre ─────────────────────────────────────────────────

class TestClasificacionPorNombre:
    def test_vid_prefijo_es_personal(self):
        ruta = Path("/random/VID_20240315_103045.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "personal"
        assert c.confianza == "nombre"

    def test_mov_prefijo_es_personal(self):
        ruta = Path("/random/MOV_0012.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "personal"
        assert c.confianza == "nombre"

    def test_gopr_prefijo_es_personal(self):
        ruta = Path("/downloads/GOPR1234.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "personal"
        assert c.confianza == "nombre"

    def test_fecha_hhmmss_es_personal(self):
        ruta = Path("/descargas/20230810_142233.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "personal"
        assert c.confianza == "nombre"

    def test_whatsapp_wa_es_personal(self):
        ruta = Path("/backup/WA0025.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "personal"
        assert c.confianza == "nombre"

    def test_sxxexx_es_serie(self):
        ruta = Path("/downloads/Chernobyl.S01E02.720p.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "serie"
        assert c.confianza == "nombre"

    def test_temporada_es_serie(self):
        ruta = Path("/descargas/The.Office.Temporada.3.Ep5.avi")
        c = clasificar_video(ruta)
        assert c.tipo == "serie"
        assert c.confianza == "nombre"

    def test_bluray_es_pelicula(self):
        ruta = Path("/downloads/Interstellar.2014.BluRay.1080p.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "pelicula"
        assert c.confianza == "nombre"

    def test_1080p_es_pelicula(self):
        ruta = Path("/downloads/Avengers.2012.1080p.x264.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "pelicula"
        assert c.confianza == "nombre"

    def test_music_video_es_musical(self):
        ruta = Path("/descargas/Taylor Swift - Shake It Off [Official Music Video].mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "musical"
        assert c.confianza == "nombre"

    def test_official_video_es_musical(self):
        ruta = Path("/descargas/Adele - Hello official video.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "musical"
        assert c.confianza == "nombre"

    def test_documental_nombre_es_documental(self):
        ruta = Path("/downloads/BBC.Earth.Documental.Naturaleza.2020.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "documental"
        assert c.confianza == "nombre"

    def test_sin_patron_es_otro(self):
        ruta = Path("/descargas/reunion_equipo_final.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "otro"
        assert c.confianza == "defecto"


# ─── Extracción de fecha ──────────────────────────────────────────────────────

class TestExtraerFecha:
    def test_fecha_en_nombre_vid(self):
        ruta = Path("/DCIM/VID_20230815_100000.mp4")
        año, mes = _extraer_fecha(ruta)
        assert año == "2023"
        assert mes == 8

    def test_fecha_en_nombre_yyyymmdd(self):
        ruta = Path("/20240310_154500.mp4")
        año, mes = _extraer_fecha(ruta)
        assert año == "2024"
        assert mes == 3

    def test_fecha_sin_patron_usa_mtime(self, tmp_path):
        archivo = tmp_path / "video_sin_fecha.mp4"
        archivo.write_bytes(b"")
        año, mes = _extraer_fecha(archivo)
        assert año.isdigit() and int(año) >= 2020
        assert 1 <= mes <= 12


# ─── Destino ─────────────────────────────────────────────────────────────────

class TestDestinoVideo:
    def test_personal_con_fecha(self, tmp_path):
        clase = ClasificacionVideo("personal", "ruta", año="2024", mes=3)
        dest = destino_video(clase, tmp_path)
        assert str(dest).endswith("01_fotos/2024/03_marzo")

    def test_personal_sin_fecha(self, tmp_path):
        clase = ClasificacionVideo("personal", "defecto")
        dest = destino_video(clase, tmp_path)
        assert "_sin_fecha" in str(dest)

    def test_pelicula(self, tmp_path):
        clase = ClasificacionVideo("pelicula", "nombre")
        dest = destino_video(clase, tmp_path)
        assert str(dest).endswith("02_videos/peliculas")

    def test_serie(self, tmp_path):
        clase = ClasificacionVideo("serie", "nombre")
        dest = destino_video(clase, tmp_path)
        assert str(dest).endswith("02_videos/series")

    def test_musical(self, tmp_path):
        clase = ClasificacionVideo("musical", "ruta")
        dest = destino_video(clase, tmp_path)
        assert str(dest).endswith("02_videos/musicales")

    def test_documental(self, tmp_path):
        clase = ClasificacionVideo("documental", "ruta")
        dest = destino_video(clase, tmp_path)
        assert str(dest).endswith("02_videos/documentales")

    def test_otro(self, tmp_path):
        clase = ClasificacionVideo("otro", "defecto")
        dest = destino_video(clase, tmp_path)
        assert str(dest).endswith("02_videos/otros")

    def test_carpeta_mes(self):
        clase = ClasificacionVideo("personal", "ruta", año="2023", mes=12)
        assert clase.carpeta_mes == "12_diciembre"

    def test_carpeta_mes_sin_fecha(self):
        clase = ClasificacionVideo("personal", "defecto")
        assert clase.carpeta_mes == "_sin_fecha"


# ─── MESES_ES ────────────────────────────────────────────────────────────────

class TestMesesEs:
    def test_todos_los_meses_presentes(self):
        assert len(MESES_ES) == 12

    def test_formato_correcto(self):
        assert MESES_ES[1] == "01_enero"
        assert MESES_ES[6] == "06_junio"
        assert MESES_ES[12] == "12_diciembre"


# ─── Cursos ───────────────────────────────────────────────────────────────────

class TestClasificacionCursos:
    def test_ruta_cursos_es_curso(self):
        ruta = Path("/respaldo/cursos/aws/001 Introduction.mp4")
        assert clasificar_video(ruta).tipo == "curso"

    def test_ruta_udemy_es_curso(self):
        ruta = Path("/Downloads/udemy/python_bootcamp/32. Lists.mp4")
        assert clasificar_video(ruta).tipo == "curso"

    def test_ruta_linkedin_learning_es_curso(self):
        ruta = Path("/Downloads/linkedin learning/Running Jenkins on AWS/001 intro.mp4")
        assert clasificar_video(ruta).tipo == "curso"

    def test_nombre_numerado_tres_digitos_es_curso(self):
        ruta = Path("/videos/001 Step Functions - Introduction.mp4")
        assert clasificar_video(ruta).tipo == "curso"

    def test_nombre_numerado_con_punto_es_curso(self):
        ruta = Path("/videos/32. API Gateway Basics Hands On.mp4")
        assert clasificar_video(ruta).tipo == "curso"

    def test_nombre_numerado_cuatro_digitos_es_curso(self):
        ruta = Path("/videos/0308 Making An AMI.mp4")
        assert clasificar_video(ruta).tipo == "curso"

    def test_curso_destino_correcto(self, tmp_path):
        clase = ClasificacionVideo("curso", "ruta")
        dest = destino_video(clase, tmp_path)
        assert str(dest).endswith("02_videos/cursos")

    def test_personal_no_confunde_con_curso(self):
        # VID_ siempre es personal, aunque esté en carpeta de cursos
        ruta = Path("/cursos/VID_20240101_120000.mp4")
        clase = clasificar_video(ruta)
        assert clase.tipo == "personal"

    def test_serie_no_confunde_con_curso(self):
        ruta = Path("/series/Friends/Friends.S01E01.mp4")
        assert clasificar_video(ruta).tipo == "serie"


# ─── Regresión: _ruta_str solo debe mirar directorios padre ──────────────────

class TestRutaSoloPadre:
    def test_phone_en_titulo_no_es_personal(self):
        # "phone" en el nombre del archivo no debe disparar la regla de cámara personal
        ruta = Path("/media/series/Friends/Friends S09E09 The One With Rachel's Phone Number.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "serie", f"Esperado serie, got {c.tipo} — 'phone' en título no debe matchear ruta"

    def test_camera_en_titulo_no_es_personal(self):
        # "camera" en el título no debe marcar como personal
        ruta = Path("/videos/documentales/Hidden Camera Documentary.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "documental", f"Esperado documental, got {c.tipo}"

    def test_dcim_en_carpeta_si_es_personal(self):
        # "dcim" en la CARPETA sí debe ser personal
        ruta = Path("/sdcard/DCIM/Camera/clip.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "personal"

    def test_whatsapp_en_titulo_no_es_personal(self):
        # "whatsapp" en el título de un archivo no debe marcar como personal
        ruta = Path("/videos/tutoriales/How to use WhatsApp.mp4")
        c = clasificar_video(ruta)
        assert c.tipo in ("curso", "otro"), f"Esperado curso u otro, got {c.tipo}"


# ─── Zoom recordings (GMT prefix) ───────────────────────────────────────────

class TestZoomRecordings:
    def test_gmt_recording_es_personal(self):
        ruta = Path("/downloads/GMT20250129-032316_Recording_2160x1334.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "personal"
        assert c.confianza == "nombre"

    def test_gmt_recording_sin_resolucion_es_personal(self):
        ruta = Path("/downloads/GMT20250131-032223_Recording.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "personal"

    def test_gmt_extrae_fecha_correctamente(self):
        ruta = Path("/downloads/GMT20250205-032206_Recording_2160x1368.mp4")
        c = clasificar_video(ruta)
        assert c.año == "2025"
        assert c.mes == 2


# ─── Season en carpeta (Friends Season N) ───────────────────────────────────

class TestSeasonEnCarpeta:
    def test_season_singular_en_carpeta_es_serie(self):
        ruta = Path("/Revisar/Friends Season 1  (1080p BD x265)/Friends.S01E01.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "serie"

    def test_season_en_carpeta_sin_sxxexx_es_serie(self):
        ruta = Path("/Revisar/Friends Season 3  (1080p)/Friends.309.The.One.With.The.Football.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "serie"


# ─── Extracción de nombre y temporada ────────────────────────────────────────

class TestSerieNombreTemporada:
    def test_extrae_nombre_y_temporada_sxxexx(self):
        ruta = Path("/downloads/Chernobyl.S01E02.720p.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "serie"
        assert c.serie_nombre == "Chernobyl"
        assert c.temporada == 1

    def test_extrae_nombre_con_puntos(self):
        ruta = Path("/downloads/Breaking.Bad.S03E07.720p.mkv")
        c = clasificar_video(ruta)
        assert c.serie_nombre == "Breaking Bad"
        assert c.temporada == 3

    def test_extrae_nombre_con_guiones(self):
        ruta = Path("/downloads/The-Office-S02E05.avi")
        c = clasificar_video(ruta)
        assert c.serie_nombre == "The Office"
        assert c.temporada == 2

    def test_extrae_nombre_multipalabra(self):
        ruta = Path("/downloads/Game.of.Thrones.S08E06.mkv")
        c = clasificar_video(ruta)
        assert c.serie_nombre == "Game Of Thrones"
        assert c.temporada == 8

    def test_extrae_season_desde_carpeta(self):
        ruta = Path("/Revisar/Friends Season 1  (1080p)/Friends.S01E01.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "serie"
        assert c.serie_nombre == "Friends"
        assert c.temporada == 1

    def test_extrae_temporada_desde_carpeta(self):
        ruta = Path("/media/Breaking Bad Temporada 2/Breaking.Bad.S02E03.mkv")
        c = clasificar_video(ruta)
        assert c.tipo == "serie"
        assert c.temporada == 2

    def test_limpiar_nombre_serie_puntos(self):
        assert _limpiar_nombre_serie("Breaking.Bad") == "Breaking Bad"

    def test_limpiar_nombre_serie_guiones_bajos(self):
        assert _limpiar_nombre_serie("The_Office") == "The Office"

    def test_limpiar_nombre_serie_title_case(self):
        assert _limpiar_nombre_serie("game.of.thrones") == "Game Of Thrones"

    def test_destino_serie_con_nombre_y_temporada(self, tmp_path):
        clase = ClasificacionVideo("serie", "nombre", serie_nombre="Friends", temporada=1)
        dest = destino_video(clase, tmp_path)
        assert dest == tmp_path / "02_videos" / "series" / "Friends" / "Temporada 01"

    def test_destino_serie_con_nombre_sin_temporada(self, tmp_path):
        clase = ClasificacionVideo("serie", "nombre", serie_nombre="Chernobyl", temporada=0)
        dest = destino_video(clase, tmp_path)
        assert dest == tmp_path / "02_videos" / "series" / "Chernobyl"

    def test_destino_serie_sin_nombre(self, tmp_path):
        clase = ClasificacionVideo("serie", "nombre")
        dest = destino_video(clase, tmp_path)
        assert dest == tmp_path / "02_videos" / "series"

    def test_temporada_formateada_dos_digitos(self, tmp_path):
        clase = ClasificacionVideo("serie", "nombre", serie_nombre="Dark", temporada=3)
        dest = destino_video(clase, tmp_path)
        assert str(dest).endswith("Dark/Temporada 03")


# ─── Fitness ─────────────────────────────────────────────────────────────────

class TestFitness:
    def test_ruta_yoga_es_fitness(self):
        ruta = Path("/media/ddp_yoga_combo_pack/clase1.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "fitness"
        assert c.confianza == "ruta"

    def test_ruta_tapout_es_fitness(self):
        ruta = Path("/videos/tapout_xt/workout1.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "fitness"

    def test_ruta_crossfit_es_fitness(self):
        ruta = Path("/downloads/crossfit_training/dia1.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "fitness"

    def test_nombre_yoga_es_fitness(self):
        ruta = Path("/descargas/yoga_flow_morning.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "fitness"
        assert c.confianza == "nombre"

    def test_destino_fitness(self, tmp_path):
        clase = ClasificacionVideo("fitness", "ruta")
        dest = destino_video(clase, tmp_path)
        assert str(dest).endswith("02_videos/fitness")


# ─── Idioma en video ──────────────────────────────────────────────────────────

class TestIdiomaVideo:
    def test_ruta_bbc_learning_es_idioma(self):
        ruta = Path("/Revisar/BBC_Learning_English_Series/London Life/smoking.rm")
        c = clasificar_video(ruta)
        assert c.tipo == "idioma"
        assert c.confianza == "ruta"

    def test_ruta_learning_english_es_idioma(self):
        ruta = Path("/downloads/learning english/lesson01.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "idioma"

    def test_ruta_graded_readers_es_idioma(self):
        ruta = Path("/media/English Graded Readers/level_b1.mp4")
        c = clasificar_video(ruta)
        assert c.tipo == "idioma"

    def test_destino_idioma_va_a_libros(self, tmp_path):
        clase = ClasificacionVideo("idioma", "ruta")
        dest = destino_video(clase, tmp_path)
        assert dest == tmp_path / "04_libros" / "idiomas"

    def test_idioma_no_confunde_con_serie(self):
        # Un .rm de BBC Learning no debe clasificarse como serie
        ruta = Path("/Revisar/BBC_Learning_English_Series/FunkyPhrasals/ep01.rm")
        c = clasificar_video(ruta)
        assert c.tipo == "idioma"
        assert c.tipo != "serie"


# ─── Fecha ISO (Dropbox "Cargas de cámara") ──────────────────────────────────

class TestFechaISO:
    def test_fecha_iso_guiones_extrae_año_mes(self, tmp_path):
        # Dropbox camera uploads: "2026-04-13 22.14.15.jpg"
        ruta = tmp_path / "2026-04-13 22.14.15.jpg"
        ruta.touch()
        año, mes = _extraer_fecha(ruta)
        assert año == "2026"
        assert mes == 4

    def test_fecha_iso_enero(self, tmp_path):
        ruta = tmp_path / "2025-01-05 10.30.00.jpg"
        ruta.touch()
        año, mes = _extraer_fecha(ruta)
        assert año == "2025"
        assert mes == 1

    def test_fecha_iso_diciembre(self, tmp_path):
        ruta = tmp_path / "2024-12-31 23.59.59.png"
        ruta.touch()
        año, mes = _extraer_fecha(ruta)
        assert año == "2024"
        assert mes == 12

    def test_cargas_camara_clasifica_personal_con_fecha(self, tmp_path):
        # Ruta "Cargas de cámara" → personal, fecha extraída del nombre
        ruta = tmp_path / "Cargas de camara" / "2026-04-13 22.14.15.jpg"
        ruta.parent.mkdir()
        ruta.touch()
        c = clasificar_video(ruta)
        assert c.tipo == "personal"
        assert c.año == "2026"
        assert c.mes == 4

    def test_fecha_compacta_sigue_funcionando(self, tmp_path):
        # El formato original YYYYMMDD no debe romperse
        ruta = tmp_path / "VID_20240315_120000.mp4"
        ruta.touch()
        año, mes = _extraer_fecha(ruta)
        assert año == "2024"
        assert mes == 3
