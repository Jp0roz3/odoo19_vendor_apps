# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de res.lang
===================================
Asegura que los idiomas español estándar (es_ES, es_VE) estén activos en la base
de datos para evitar errores HTTP 500 cuando los navegadores envían cabeceras
Accept-Language en español.

Autor: JeanPerozo / Nubelco
"""
from odoo import models, api


class ResLang(models.Model):
    _inherit = 'res.lang'

    @api.model
    def _auto_init(self):
        super()._auto_init()
        try:
            self.env.cr.execute("""
                UPDATE res_lang
                SET active = TRUE
                WHERE code IN ('es_ES', 'es_VE') AND (active IS NULL OR active = FALSE);
            """)
        except Exception:
            pass
