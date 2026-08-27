# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de ir.http
=====================================
Resuelve Internal Server Error 500 para navegadores con
Accept-Language: es-419, es-ES o es en Odoo 19.

CAUSA RAÍZ:
  babel.Locale.parse('es_419') lanza UnknownLocaleError porque 419
  es un código de región numérico UN M.49, no un subtag BCP-47 estándar.

SOLUCIÓN:
  Sobrescribir _get_nearest_lang con try/except que captura la excepción
  de babel y retorna 'es_VE' como fallback para cualquier variante de español.

Autor: JeanPerozo / Nubelco
"""
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _get_nearest_lang(cls, lang_code):
        """
        Red de seguridad: captura UnknownLocaleError de babel para es-419
        y retorna es_VE como fallback para cualquier variante de español.
        """
        try:
            res = super()._get_nearest_lang(lang_code)
        except Exception:
            # babel no puede parsear es-419 (UN M.49 region code)
            res = None

        if not res and lang_code and str(lang_code).lower().startswith('es'):
            _logger.debug(
                'Venezuela360: lang %r no resuelto → fallback es_VE', lang_code
            )
            return 'es_VE'

        return res
