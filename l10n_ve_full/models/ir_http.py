# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de ir.http
==================================
Mapea de forma segura cualquier variante de español (es, es_ES, es-419, etc.)
hacia el idioma español venezolano instalado (es_VE) mediante _get_nearest_lang,
garantizando compatibilidad universal con todos los navegadores.

Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _get_nearest_lang(cls, lang_code):
        if lang_code and str(lang_code).lower().startswith('es'):
            try:
                if request and request.env:
                    installed = dict(request.env['res.lang'].sudo().get_installed())
                    if 'es_VE' in installed:
                        return 'es_VE'
            except Exception:
                return 'es_VE'
        return super()._get_nearest_lang(lang_code)
