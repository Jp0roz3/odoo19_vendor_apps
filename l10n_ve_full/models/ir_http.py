# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de ir.http
==================================
Normaliza variantes de español no instaladas (ej: es, es_ES, es-419) hacia el
idioma español instalado en la base de datos (es_VE) antes del dispatch,
evitando errores HTTP 500 al navegar con navegadores configurados en español.

Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

_ES_VARIANTS = frozenset([
    'es', 'es_ES', 'es_419',
    'es_MX', 'es_CO', 'es_AR', 'es_PE', 'es_CL',
    'es_EC', 'es_BO', 'es_PY', 'es_UY', 'es_CR',
    'es_PA', 'es_DO', 'es_GT', 'es_HN', 'es_SV', 'es_NI',
    'es_US', 'es_PH', 'es_GQ', 'es_IC', 'es_EA',
])

_ES_FALLBACK_ORDER = ('es_VE', 'es_ES', 'es_MX', 'en_US')


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        try:
            ctx_lang = request.env.context.get('lang') or ''
            if ctx_lang in _ES_VARIANTS:
                installed = frozenset(
                    code for code, _name in request.env['res.lang'].sudo().get_installed()
                )
                if ctx_lang not in installed:
                    target = next((c for c in _ES_FALLBACK_ORDER if c in installed), 'es_VE')
                    request.update_context(lang=target)
        except Exception as exc:
            _logger.warning('Venezuela360 ir_http lang normalization warning: %s', exc)
        return super()._pre_dispatch(rule, args)
