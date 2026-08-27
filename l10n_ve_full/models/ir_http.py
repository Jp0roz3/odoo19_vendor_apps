# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de ir.http
===================================
Garantiza que cualquier petición de navegador en español (es, es-419, es-ES)
resuelva automáticamente al idioma instalado 'es_VE' (Español Venezuela),
evitando excepciones 500 en la ruta raíz /odoo en Odoo.sh.

Autor: JeanPerozo / Nubelco
"""
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _get_nearest_lang(cls, lang_code):
        res = super()._get_nearest_lang(lang_code)
        if not res and lang_code and str(lang_code).lower().startswith('es'):
            return 'es_VE'
        return res
