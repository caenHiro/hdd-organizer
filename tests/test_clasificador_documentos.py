"""Tests para clasificador_documentos — heurísticas locales sin tokens."""
from pathlib import Path
from unittest.mock import patch

import pytest

from src.organizador_hdd.clasificador_documentos import (
    ClasificacionDoc,
    clasificar_documento,
    destino_documento,
    _norm,
    _detectar_año,
    _subcat_salud,
    _subcat_trabajo,
    _subcat_personal,
)


# ─── Utilidades ───────────────────────────────────────────────────────────────

class TestNorm:
    def test_elimina_acentos(self):
        assert _norm("diagnóstico") == "diagnostico"
        assert _norm("Médico") == "medico"
        assert _norm("nómina") == "nomina"

    def test_convierte_minusculas(self):
        assert _norm("CURP") == "curp"


class TestDetectarAño:
    def test_detecta_año_en_nombre(self):
        assert _detectar_año("nomina_enero_2026") == "2026"

    def test_año_no_encontrado_usa_actual(self):
        from datetime import datetime
        actual = datetime.now().strftime("%Y")
        assert _detectar_año("archivo_sin_fecha") == actual


# ─── Subcategorías ────────────────────────────────────────────────────────────

class TestSubcatSalud:
    def test_receta(self):
        assert _subcat_salud("receta_medica", "") == "recetas"

    def test_laboratorio(self):
        assert _subcat_salud("resultado_laboratorio", "") == "estudios"

    def test_poliza(self):
        assert _subcat_salud("poliza_gm", "") == "seguros"

    def test_defecto_salud(self):
        assert _subcat_salud("consulta_general", "") == "estudios"


class TestSubcatTrabajo:
    def test_nomina(self):
        assert _subcat_trabajo("nomina_enero", "") == "nominas"

    def test_contrato(self):
        assert _subcat_trabajo("contrato_laboral", "") == "contratos"

    def test_finiquito(self):
        assert _subcat_trabajo("finiquito_2025", "") == "contratos"

    def test_defecto_trabajo(self):
        assert _subcat_trabajo("informe_reunion", "") == "general"


class TestSubcatPersonal:
    def test_factura(self):
        sub, año = _subcat_personal("factura_amazon_2026", "")
        assert sub == "facturas"
        assert año == "2026"

    def test_curp(self):
        sub, año = _subcat_personal("curp_caen", "")
        assert sub == "identificaciones"
        assert año == ""

    def test_titulo(self):
        sub, año = _subcat_personal("titulo_ing_sistemas", "")
        assert sub == "certificados"

    def test_comprobante_domicilio(self):
        sub, _ = _subcat_personal("comprobante_domicilio_cfe", "")
        assert sub == "comprobantes"

    def test_contrato_arrendamiento(self):
        sub, _ = _subcat_personal("contrato_arrendamiento_depto", "")
        assert sub == "contratos"


# ─── clasificar_documento — por ruta ─────────────────────────────────────────

class TestClasificarPorRuta:
    def test_carpeta_salud(self, tmp_path):
        f = (tmp_path / "salud" / "doc.pdf")
        f.parent.mkdir()
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "salud"
        assert result.confianza == "ruta"

    def test_carpeta_hospital(self, tmp_path):
        f = tmp_path / "hospital" / "historial.pdf"
        f.parent.mkdir()
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "salud"

    def test_carpeta_trabajo_ine(self, tmp_path):
        f = tmp_path / "trabajo" / "ine" / "doc.pdf"
        f.parent.mkdir(parents=True)
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "trabajo"
        assert result.confianza == "ruta"

    def test_carpeta_accenture(self, tmp_path):
        f = tmp_path / "accenture" / "contrato.pdf"
        f.parent.mkdir()
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "trabajo"


# ─── clasificar_documento — por nombre ───────────────────────────────────────

class TestClasificarPorNombre:
    def test_receta_medica(self, tmp_path):
        f = tmp_path / "receta_medica.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "salud"
        assert result.subcategoria == "recetas"
        assert result.confianza == "nombre"

    def test_analisis_laboratorio(self, tmp_path):
        f = tmp_path / "analisis_sangre_2026.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "salud"
        assert result.subcategoria == "estudios"

    def test_nomina(self, tmp_path):
        f = tmp_path / "nomina_enero_2026.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "trabajo"
        assert result.subcategoria == "nominas"
        assert result.año == "2026"

    def test_cfdi_nomina(self, tmp_path):
        f = tmp_path / "cfdi_nomina_02_2026.xml"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "trabajo"
        assert result.subcategoria == "nominas"

    def test_curp(self, tmp_path):
        f = tmp_path / "CURP_carlos_escalona.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "personal"
        assert result.subcategoria == "identificaciones"

    def test_titulo_universitario(self, tmp_path):
        f = tmp_path / "titulo_ingenieria_sistemas.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "personal"
        assert result.subcategoria == "certificados"

    def test_factura_con_año(self, tmp_path):
        f = tmp_path / "factura_amazon_2025.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "personal"
        assert result.subcategoria == "facturas"
        assert result.año == "2025"

    def test_comprobante_domicilio(self, tmp_path):
        f = tmp_path / "comprobante_domicilio_cfe.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "personal"
        assert result.subcategoria == "comprobantes"

    def test_contrato_arrendamiento(self, tmp_path):
        f = tmp_path / "contrato_arrendamiento_2024.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "personal"
        assert result.subcategoria == "contratos"


# ─── clasificar_documento — defecto ──────────────────────────────────────────

class TestClasificarDefecto:
    def test_archivo_desconocido(self, tmp_path):
        f = tmp_path / "documento_random.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "otro"
        assert result.subcategoria == "general"
        assert result.confianza == "defecto"

    def test_docx_sin_pistas(self, tmp_path):
        f = tmp_path / "notas.docx"
        f.touch()
        result = clasificar_documento(f)
        assert result.confianza == "defecto"


# ─── destino_documento ────────────────────────────────────────────────────────

class TestDestinoDocumento:
    def test_personal_identificaciones(self, tmp_path):
        clase = ClasificacionDoc("personal", "identificaciones", "nombre")
        dest = destino_documento(clase, tmp_path / "08_documentos")
        assert dest == tmp_path / "08_documentos" / "personal" / "identificaciones"

    def test_salud_estudios(self, tmp_path):
        clase = ClasificacionDoc("salud", "estudios", "nombre")
        dest = destino_documento(clase, tmp_path / "08_documentos")
        assert dest == tmp_path / "08_documentos" / "salud" / "estudios"

    def test_personal_facturas_con_año(self, tmp_path):
        clase = ClasificacionDoc("personal", "facturas", "nombre", año="2026")
        dest = destino_documento(clase, tmp_path / "08_documentos")
        assert dest == tmp_path / "08_documentos" / "personal" / "facturas" / "2026"

    def test_trabajo_nominas_con_año(self, tmp_path):
        clase = ClasificacionDoc("trabajo", "nominas", "nombre", año="2025")
        dest = destino_documento(clase, tmp_path / "08_documentos")
        assert dest == tmp_path / "08_documentos" / "trabajo" / "nominas" / "2025"

    def test_otro_general(self, tmp_path):
        clase = ClasificacionDoc("otro", "general", "defecto")
        dest = destino_documento(clase, tmp_path / "08_documentos")
        assert dest == tmp_path / "08_documentos" / "otro" / "general"


# ─── Cursos ───────────────────────────────────────────────────────────────────

class TestClasificacionCursos:
    def test_ruta_cursos_es_curso(self):
        ruta = Path("/respaldo/cursos/aws/normalizacion.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "curso"

    def test_ruta_udemy_es_curso(self):
        ruta = Path("/Downloads/udemy/python_bootcamp/lecture.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "curso"

    def test_ruta_universidad_es_curso(self):
        ruta = Path("/Downloads/universidad/semestre5/apuntes.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "curso"

    def test_nombre_practica_es_curso(self):
        ruta = Path("/tmp/practica_normalizacion.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "curso"

    def test_nombre_reporte_es_curso(self):
        ruta = Path("/tmp/reporte_funciones_procedimientos.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "curso"

    def test_titulo_universitario_sigue_siendo_personal(self, tmp_path):
        f = tmp_path / "titulo_ingenieria_sistemas.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "personal"
        assert result.subcategoria == "certificados"

    def test_ruta_bbc_learning_es_idioma(self):
        ruta = Path("/Revisar/BBC_Learning_English_Series/FunkyPhrasals/doc.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "idioma"
        assert result.confianza == "ruta"

    def test_ruta_learning_english_es_idioma(self):
        ruta = Path("/Downloads/learning english/lesson1/vocabulary.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "idioma"

    def test_nombre_calificacion_es_curso(self):
        ruta = Path("/tmp/CalificacionesFBD20261.ods")
        result = clasificar_documento(ruta)
        assert result.categoria == "curso"
        assert result.confianza == "nombre"

    def test_nombre_fbd2026_es_curso(self):
        ruta = Path("/tmp/cronogramafbd2026.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "curso"


# ─── Personal — documentos nuevos México ─────────────────────────────────────

class TestPersonalDocumentosMX:
    def test_boleta_agua_es_personal_comprobante(self, tmp_path):
        f = tmp_path / "boleta_agua_3236255025010000.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "personal"
        assert result.subcategoria == "comprobantes"

    def test_comprobante_auto_es_personal_comprobante(self, tmp_path):
        f = tmp_path / "ComprobanteBYD2026.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "personal"
        assert result.subcategoria == "comprobantes"

    def test_comprobante_predio_es_personal_comprobante(self, tmp_path):
        f = tmp_path / "Comprobante_predio_cerro_2026.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "personal"
        assert result.subcategoria == "comprobantes"

    def test_poliza_seguro_auto_es_personal_comprobante(self, tmp_path):
        f = tmp_path / "Poliza_685421166_BYD_2025.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "personal"
        assert result.subcategoria == "comprobantes"

    def test_estado_de_cuenta_con_espacio_es_personal(self, tmp_path):
        f = tmp_path / "Estado de Cuenta-10.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "personal"
        assert result.subcategoria == "comprobantes"

    def test_statement_bancario_es_personal_comprobante(self, tmp_path):
        f = tmp_path / "statement2025_07.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "personal"
        assert result.subcategoria == "comprobantes"

    def test_cotizacion_es_personal_comprobante(self, tmp_path):
        f = tmp_path / "Cotizacion BYD 2025.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "personal"
        assert result.subcategoria == "comprobantes"

    def test_predial_es_personal_comprobante(self, tmp_path):
        f = tmp_path / "Comprobante_predio_vicente_2026.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "personal"
        assert result.subcategoria == "comprobantes"


# ─── Idioma ───────────────────────────────────────────────────────────────────

class TestIdioma:
    def test_ruta_idiomas_es_idioma(self):
        ruta = Path("/respaldo/idiomas/grammar_book.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "idioma"
        assert result.confianza == "ruta"

    def test_ruta_learning_english_es_idioma(self):
        ruta = Path("/Downloads/learning english/lesson1/vocabulary.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "idioma"

    def test_ruta_bbc_learning_es_idioma(self):
        ruta = Path("/Revisar/BBC_Learning_English_Series/FunkyPhrasals/doc.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "idioma"
        assert result.confianza == "ruta"

    def test_ruta_language_learning_es_idioma(self):
        ruta = Path("/media/language_learning/french/lesson.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "idioma"

    def test_nombre_grammar_es_idioma(self, tmp_path):
        f = tmp_path / "english_grammar_advanced.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "idioma"
        assert result.confianza == "nombre"

    def test_nombre_phrasal_verbs_es_idioma(self, tmp_path):
        f = tmp_path / "phrasal_verbs_in_use.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "idioma"

    def test_nombre_vocabulary_es_idioma(self, tmp_path):
        f = tmp_path / "vocabulary_b2_level.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "idioma"

    def test_nombre_fluent_english_es_idioma(self, tmp_path):
        f = tmp_path / "fluent_english_speaking.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "idioma"

    def test_idioma_no_confunde_con_curso(self, tmp_path):
        # Un PDF de gramática va a idioma, no a curso
        f = tmp_path / "english_grammar_book.pdf"
        f.touch()
        result = clasificar_documento(f)
        assert result.categoria == "idioma"
        assert result.categoria != "curso"

    def test_ruta_language_pack_es_idioma(self):
        ruta = Path("/downloads/Language Learning Packs Vol.2/chinese_book.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "idioma"

    def test_ruta_graded_readers_es_idioma(self):
        ruta = Path("/media/English Graded Readers/level_b1.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "idioma"

    def test_ruta_chinese_language_es_idioma(self):
        ruta = Path("/downloads/Chinese Language Learning/lesson1.pdf")
        result = clasificar_documento(ruta)
        assert result.categoria == "idioma"


# ─── Libros técnicos → curso ──────────────────────────────────────────────────

class TestLibrosTecnicos:
    def test_machine_learning_es_curso(self, tmp_path):
        f = tmp_path / "Python Machine Learning Step-by-Step.pdf"
        f.touch()
        r = clasificar_documento(f)
        assert r.categoria == "curso"

    def test_deep_learning_es_curso(self, tmp_path):
        f = tmp_path / "AI Deep Learning in Image Processing 2026.pdf"
        f.touch()
        r = clasificar_documento(f)
        assert r.categoria == "curso"

    def test_aws_certified_es_curso(self, tmp_path):
        f = tmp_path / "Cabianca D. AWS Certified Machine Learning Engineer.pdf"
        f.touch()
        r = clasificar_documento(f)
        assert r.categoria == "curso"

    def test_devops_es_curso(self, tmp_path):
        f = tmp_path / "Learning DevOps Continuously Deliver Better Software.pdf"
        f.touch()
        r = clasificar_documento(f)
        assert r.categoria == "curso"

    def test_quantum_es_curso(self, tmp_path):
        f = tmp_path / "Van Griensven T. Quantum Computing and Quantum Machine Learning 2025.pdf"
        f.touch()
        r = clasificar_documento(f)
        assert r.categoria == "curso"


# ─── SAT / acuse → personal comprobantes ─────────────────────────────────────

class TestSATDocumentos:
    def test_acuse_es_personal_comprobante(self, tmp_path):
        f = tmp_path / "Acuse.EANC920224TL4.6.2025.pdf"
        f.touch()
        r = clasificar_documento(f)
        assert r.categoria == "personal"
        assert r.subcategoria == "comprobantes"

    def test_pago_sat_es_personal_comprobante(self, tmp_path):
        f = tmp_path / "Pago SAT 2025.pdf"
        f.touch()
        r = clasificar_documento(f)
        assert r.categoria == "personal"
        assert r.subcategoria == "comprobantes"


# ─── FIEL SAT → personal identificaciones ────────────────────────────────────

class TestFIELDocumentos:
    def test_fiel_carpeta_es_identificaciones(self, tmp_path):
        carpeta = tmp_path / "FIEL_EANC920224TL4_20170214172252"
        carpeta.mkdir()
        f = carpeta / "eanc920224tl4.cer"
        f.touch()
        r = clasificar_documento(f)
        assert r.categoria == "personal"
        assert r.subcategoria == "identificaciones"

    def test_claveprivada_fiel_es_identificaciones(self, tmp_path):
        f = tmp_path / "Claveprivada_FIEL_EANC920224TL4_20220726_133129.key"
        f.touch()
        r = clasificar_documento(f)
        assert r.categoria == "personal"
        assert r.subcategoria == "identificaciones"

    def test_estado_cuenta_pension_es_comprobante(self, tmp_path):
        # "pensionissste" en la ruta — no debe disparar salud por "issste" como substring
        carpeta = tmp_path / "personal" / "pensionissste"
        carpeta.mkdir(parents=True)
        f = carpeta / "EstadodeCuenta.pdf"
        f.touch()
        r = clasificar_documento(f)
        assert r.categoria == "personal"
        assert r.subcategoria == "comprobantes"


# ─── Ayudantías → curso ───────────────────────────────────────────────────────

class TestAyudantias:
    def test_ruta_ayudantias_es_curso(self, tmp_path):
        carpeta = tmp_path / "Ayudantias" / "2026-1" / "lineamientos"
        carpeta.mkdir(parents=True)
        f = carpeta / "lineamientos.pdf"
        f.touch()
        r = clasificar_documento(f)
        assert r.categoria == "curso"

    def test_ruta_ayudantia_singular_es_curso(self, tmp_path):
        carpeta = tmp_path / "ayudantia" / "2022-1"
        carpeta.mkdir(parents=True)
        f = carpeta / "practica1.pdf"
        f.touch()
        r = clasificar_documento(f)
        assert r.categoria == "curso"
