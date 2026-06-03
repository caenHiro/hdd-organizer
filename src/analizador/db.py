import csv
from datetime import datetime
from pathlib import Path

from commons.db.base import BaseDatosSQL
from .scanner import ArchivoInfo

_SCHEMA = """
CREATE TABLE IF NOT EXISTS archivos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ruta                TEXT UNIQUE NOT NULL,
    nombre              TEXT NOT NULL,
    extension           TEXT,
    tipo                TEXT,
    tamanio             INTEGER,
    fecha_modificacion  TEXT,
    hash_sha256         TEXT,
    fecha_escaneo       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_hash     ON archivos (hash_sha256);
CREATE INDEX IF NOT EXISTS idx_tipo     ON archivos (tipo);
CREATE INDEX IF NOT EXISTS idx_tamanio  ON archivos (tamanio);
"""


class BaseDatos(BaseDatosSQL):
    _SCHEMA = _SCHEMA

    def __init__(self, ruta_db: str = "inventario.db"):
        super().__init__(ruta_db)

    def insertar_o_actualizar(self, info: ArchivoInfo) -> None:
        sql = """
        INSERT INTO archivos (ruta, nombre, extension, tipo, tamanio,
                              fecha_modificacion, hash_sha256)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ruta) DO UPDATE SET
            tamanio           = excluded.tamanio,
            fecha_modificacion = excluded.fecha_modificacion,
            hash_sha256       = excluded.hash_sha256,
            fecha_escaneo     = datetime('now')
        """
        self._execute(sql, (
            info.ruta, info.nombre, info.extension, info.tipo,
            info.tamanio, info.fecha_modificacion.isoformat(), info.hash_sha256,
        ))

    def insertar_lote(self, lote: list[ArchivoInfo]) -> None:
        sql = """
        INSERT INTO archivos (ruta, nombre, extension, tipo, tamanio,
                              fecha_modificacion, hash_sha256)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ruta) DO UPDATE SET
            tamanio           = excluded.tamanio,
            fecha_modificacion = excluded.fecha_modificacion,
            hash_sha256       = excluded.hash_sha256,
            fecha_escaneo     = datetime('now')
        """
        datos = [
            (i.ruta, i.nombre, i.extension, i.tipo,
             i.tamanio, i.fecha_modificacion.isoformat(), i.hash_sha256)
            for i in lote
        ]
        self._executemany(sql, datos)

    def archivos_duplicados(self, min_bytes: int = 0) -> list[dict]:
        """Devuelve todos los registros individuales de archivos que tienen duplicados."""
        sql = """
        SELECT a.ruta, a.nombre, a.tamanio, a.fecha_modificacion,
               a.hash_sha256, a.tipo
        FROM   archivos a
        INNER JOIN (
            SELECT hash_sha256
            FROM   archivos
            WHERE  hash_sha256 != '' AND tamanio >= ?
            GROUP  BY hash_sha256
            HAVING COUNT(*) > 1
        ) d ON a.hash_sha256 = d.hash_sha256
        ORDER  BY a.hash_sha256, a.tamanio DESC
        """
        return self._fetchall(sql, (min_bytes,))

    def duplicados(self, min_bytes: int = 1024 * 1024) -> list[dict]:
        sql = """
        SELECT hash_sha256,
               COUNT(*)            AS copias,
               SUM(tamanio)        AS espacio_total,
               GROUP_CONCAT(ruta, '|||') AS rutas
        FROM   archivos
        WHERE  hash_sha256 != ''
          AND  tamanio >= ?
        GROUP  BY hash_sha256
        HAVING COUNT(*) > 1
        ORDER  BY espacio_total DESC
        """
        return self._fetchall(sql, (min_bytes,))

    def estadisticas(self) -> dict:
        resumen_sql = """
        SELECT COUNT(*)       AS total_archivos,
               SUM(tamanio)   AS espacio_total
        FROM   archivos
        """
        tipo_sql = """
        SELECT tipo, COUNT(*) AS cantidad, SUM(tamanio) AS espacio
        FROM   archivos
        GROUP  BY tipo
        ORDER  BY espacio DESC
        """
        with self._conn() as conn:
            stats = dict(conn.execute(resumen_sql).fetchone())
            stats["por_tipo"] = [dict(r) for r in conn.execute(tipo_sql).fetchall()]
        return stats

    def archivos_por_carpeta(self) -> list[dict]:
        sql = """
        SELECT
            substr(ruta, 1, length(ruta) - length(nombre) - 1) AS carpeta,
            nombre, ruta, tamanio, tipo
        FROM  archivos
        ORDER BY carpeta, nombre
        """
        return self._fetchall(sql)

    def archivos_grandes(self, top: int = 50, min_bytes: int = 100 * 1024 * 1024) -> list[dict]:
        sql = """
        SELECT nombre, ruta, tipo, tamanio
        FROM   archivos
        WHERE  tamanio >= ?
        ORDER  BY tamanio DESC
        LIMIT  ?
        """
        return self._fetchall(sql, (min_bytes, top))

    def archivos_viejos(
        self,
        directorio: str,
        dias: int = 180,
        min_bytes: int = 0,
    ) -> list[dict]:
        sql = """
        SELECT nombre, ruta, tipo, tamanio, fecha_modificacion
        FROM   archivos
        WHERE  ruta LIKE ?
          AND  tamanio >= ?
          AND  fecha_modificacion <= datetime('now', ? || ' days')
        ORDER  BY fecha_modificacion ASC
        """
        prefijo = directorio.rstrip("/") + "/%"
        return self._fetchall(sql, (prefijo, min_bytes, f"-{dias}"))

    def archivos_por_fecha(
        self,
        desde: str | None = None,
        hasta: str | None = None,
    ) -> list[dict]:
        condiciones = []
        params: list = []
        if desde:
            condiciones.append("fecha_modificacion >= ?")
            params.append(desde)
        if hasta:
            condiciones.append("fecha_modificacion <= ?")
            params.append(hasta)
        where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
        sql = f"SELECT nombre, ruta, tipo, tamanio, fecha_modificacion FROM archivos {where} ORDER BY fecha_modificacion DESC"
        return self._fetchall(sql, tuple(params))

    def buscar_por_tipo(self, tipo: str, min_bytes: int = 0) -> list[dict]:
        sql = """
        SELECT nombre, ruta, tipo, tamanio, fecha_modificacion
        FROM   archivos
        WHERE  tipo = ? AND tamanio >= ?
        ORDER  BY tamanio DESC
        """
        return self._fetchall(sql, (tipo, min_bytes))

    def buscar_por_extension(self, extension: str) -> list[dict]:
        ext = extension if extension.startswith(".") else "." + extension
        sql = """
        SELECT nombre, ruta, tipo, tamanio, fecha_modificacion
        FROM   archivos
        WHERE  lower(extension) = lower(?)
        ORDER  BY tamanio DESC
        """
        return self._fetchall(sql, (ext,))

    def exportar_csv(
        self,
        ruta_csv: str,
        desde: str | None = None,
        hasta: str | None = None,
    ) -> int:
        filas = self.archivos_por_fecha(desde=desde, hasta=hasta)
        if not filas:
            sql = "SELECT nombre, ruta, tipo, tamanio, fecha_modificacion, hash_sha256 FROM archivos ORDER BY ruta"
            filas = self._fetchall(sql)

        columnas = ["nombre", "ruta", "tipo", "tamanio", "fecha_modificacion", "hash_sha256"]
        with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(filas)
        return len(filas)
