# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de res.lang
===================================
Asegura la resolución segura de cualquier variante de español (es, es_ES, es-419, etc.)
hacia el idioma español instalado (es_VE) en los métodos de búsqueda del ORM:
- _lang_get(code)
- _lang_get_code(code)
- _get_nearest_lang(lang_code)

Evita que _lang_get devuelva None y cause AttributeError (500) en el router de Odoo.

Autor: JeanPerozo / Nubelco
"""
from odoo import models, api, tools


class ResLang(models.Model):
    _inherit = 'res.lang'

    @api.model
    @tools.ormcache('code')
    def _lang_get_code(self, code):
        res = super()._lang_get_code(code)
        if not res and code and str(code).startswith('es'):
            installed = dict(self.get_installed())
            if 'es_VE' in installed:
                return 'es_VE'
        return res

    @api.model
    @tools.ormcache('code')
    def _lang_get(self, code):
        res = super()._lang_get(code)
        if not res and code and str(code).startswith('es'):
            res = super()._lang_get('es_VE')
        return res

    @api.model
    def _get_nearest_lang(self, lang_code):
        res = super()._get_nearest_lang(lang_code)
        if not res and lang_code and str(lang_code).startswith('es'):
            installed = dict(self.get_installed())
            if 'es_VE' in installed:
                return 'es_VE'
        return res
