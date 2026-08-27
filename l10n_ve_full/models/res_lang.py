# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de res.lang
===================================
Redirige cualquier variante de español (es, es_ES, es-419, etc.) hacia el idioma
español instalado en la base de datos (es_VE) mediante el método nativo del ORM
_get_nearest_lang(), evitando errores HTTP 500 en navegadores en español.

Autor: JeanPerozo / Nubelco
"""
from odoo import models, api


class ResLang(models.Model):
    _inherit = 'res.lang'

    @api.model
    def _get_nearest_lang(self, lang_code):
        res = super()._get_nearest_lang(lang_code)
        if not res and lang_code and str(lang_code).startswith('es'):
            installed = dict(self.get_installed())
            if 'es_VE' in installed:
                return 'es_VE'
        return res
