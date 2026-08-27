# -*- coding: utf-8 -*-
"""Venezuela360 migration 19.0.2.3.0: activate Spanish languages.

Runs AUTOMATICALLY when the module is updated to this version.
Activates 'es' (Spanish) and 'es_VE' (Spanish Venezuela) in res.lang
so that browsers sending Accept-Language: es-419 / es-ES / es
do not get Internal Server Error 500.
"""
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Activate es and es_VE in res_lang on module update."""
    import odoo.api
    from odoo import SUPERUSER_ID
    try:
        env = odoo.api.Environment(cr, SUPERUSER_ID, {})
        for code in ('es', 'es_VE'):
            try:
                lang = env['res.lang'].with_context(active_test=False).search(
                    [('code', '=', code)], limit=1
                )
                if lang and not lang.active:
                    lang.write({'active': True})
                    _logger.info('Venezuela360 migrate: lang %s activated.', code)
                elif lang:
                    _logger.info('Venezuela360 migrate: lang %s already active.', code)
                else:
                    env['res.lang']._activate_lang(code)
                    _logger.info('Venezuela360 migrate: lang %s installed.', code)
            except Exception as exc:
                _logger.warning('Venezuela360 migrate: error with %s: %s', code, exc)
    except Exception as exc:
        _logger.warning('Venezuela360 migrate: general error: %s', exc)
