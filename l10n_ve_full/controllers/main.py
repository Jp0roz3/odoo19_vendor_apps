# -*- coding: utf-8 -*-
"""
Venezuela360: Controlador de Enrutamiento de Idioma
===================================================
Redirige peticiones de navegadores en español hacia el idioma oficial instalado (/es_VE/*),
evitando fallos de traducción no encontrada en el backend web de Odoo 19.

Autor: JeanPerozo / Nubelco
"""
from odoo import http
from odoo.http import request


class SpanishRedirectController(http.Controller):

    @http.route(['/odoo', '/odoo/<path:subpath>'], type='http', auth='public', csrf=False)
    def redirect_odoo_spanish(self, subpath='', **kwargs):
        accept_lang = request.httprequest.headers.get('Accept-Language', '')
        if accept_lang and 'es' in accept_lang.lower():
            target = f'/es_VE/odoo/{subpath}' if subpath else '/es_VE/odoo'
            try:
                query = request.httprequest.query_string.decode('utf-8')
                if query:
                    target = f'{target}?{query}'
            except Exception:
                pass
            return request.redirect(target, code=302)
        target = f'/web/login?redirect={request.httprequest.full_path}'
        return request.redirect(target, code=302)

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
