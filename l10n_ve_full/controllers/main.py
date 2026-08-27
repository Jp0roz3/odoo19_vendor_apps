# -*- coding: utf-8 -*-
"""
Venezuela360: Controlador de Enrutamiento de Idioma
===================================================
Intercepta peticiones dirigidas a variantes de español no instaladas (/es/*, /es_ES/*)
y las redirige limpiamente hacia el idioma español oficial instalado (/es_VE/*),
garantizando navegación fluida y sin errores 500 en todos los navegadores.

Autor: JeanPerozo / Nubelco
"""
from odoo import http
from odoo.http import request


class SpanishRedirectController(http.Controller):

    @http.route(['/es', '/es/<path:subpath>'], type='http', auth='public', csrf=False)
    def redirect_es_to_es_ve(self, subpath='', **kwargs):
        target = f'/es_VE/{subpath}' if subpath else '/es_VE'
        try:
            query = request.httprequest.query_string.decode('utf-8')
            if query:
                target = f'{target}?{query}'
        except Exception:
            pass
        return request.redirect(target, code=302)

    @http.route(['/es_ES', '/es_ES/<path:subpath>'], type='http', auth='public', csrf=False)
    def redirect_es_es_to_es_ve(self, subpath='', **kwargs):
        target = f'/es_VE/{subpath}' if subpath else '/es_VE'
        try:
            query = request.httprequest.query_string.decode('utf-8')
            if query:
                target = f'{target}?{query}'
        except Exception:
            pass
        return request.redirect(target, code=302)
