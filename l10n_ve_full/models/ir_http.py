# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de ir.http
Fallback seguro para Accept-Language: es-419, es-ES, es → es_VE.
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
        Captura excepciones de babel para es-419 (código región UN M.49)
        y retorna es_VE como fallback para cualquier variante de español.
        """
        try:
            res = super()._get_nearest_lang(lang_code)
        except Exception:
            res = None
        if not res and lang_code and str(lang_code).lower().startswith('es'):
            return 'es_VE'
        return res
