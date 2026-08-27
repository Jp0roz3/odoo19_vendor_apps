# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de ir.http
=====================================
Resuelve el Internal Server Error 500 que ocurre en Odoo 19 cuando el
navegador envía Accept-Language: es-419, es-ES o es.

CAUSA RAÍZ (confirmada por análisis del código fuente de Odoo 19):
──────────────────────────────────────────────────────────────────
La cadena de llamadas es:
  Request._serve_db
    → env['ir.http']._pre_dispatch(rule, args)
        → request.dispatcher.pre_dispatch(rule, args)   ← AQUÍ CRASHEA
            → website/HttpDispatcher detecta Accept-Language: es-419
            → babel.Locale.parse('es_419') lanza UnknownLocaleError
            → Odoo convierte a Internal Server Error 500

El código de región '419' (América Latina) es un código UN M.49 que
no es un subtag BCP-47 estándar y que ciertas versiones de babel no
pueden parsear, causando el crash.

SOLUCIÓN:
──────────────────────────────────────────────────────────────────
Sobrescribir ir.http._pre_dispatch para sanear el encabezado
HTTP_ACCEPT_LANGUAGE en el environ del request ANTES de llamar a
super() (que a su vez llama al módulo website que crashea).

También se mantiene _get_nearest_lang como red de seguridad.

Autor: JeanPerozo / Nubelco
"""
import re
import logging

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

# Códigos de región numéricos UN M.49 que babel NO puede parsear como locale
# 419 = América Latina, 001 = Mundo, 002 = África, 003 = América del Norte, etc.
_ES_NUMERIC_REGION_RE = re.compile(
    r'\bes-\d{3}(?:-[A-Za-z0-9]+)*\b',
    re.IGNORECASE,
)

# 'es' suelto (sin país) seguido de ; , o fin de string, con valor de calidad opcional
_ES_BARE_RE = re.compile(
    r'\bes\b(?=\s*(?:;[^,]*)?(?:,|$))',
    re.IGNORECASE,
)


def _fix_accept_language(al: str) -> str:
    """
    Normaliza el encabezado Accept-Language para que Odoo 19 lo acepte.

    Reglas:
    - es-419, es-419;q=0.9  → es-VE;q=<original>
    - es-ES                  → es-VE  (solo si es_ES no está activo en BD)
    - es (suelto)            → es-VE

    Si ya contiene 'es-VE' o 'es_VE', no se modifica.
    """
    if not al:
        return al

    al_lower = al.lower()
    # Si ya tiene es-VE no necesita modificación
    if 'es-ve' in al_lower or 'es_ve' in al_lower:
        return al

    # Si no contiene ninguna variante de español, no tocar
    if 'es' not in al_lower:
        return al

    # Paso 1: Reemplazar es-NNN (región numérica) por es-VE
    fixed = _ES_NUMERIC_REGION_RE.sub('es-VE', al)

    # Paso 2: Reemplazar es-ES (y cualquier otra variante es-XX de 2 letras)
    # SOLO si no quedó es-VE ya del paso anterior
    if 'es-VE' not in fixed and 'es_VE' not in fixed:
        fixed = re.sub(
            r'\bes-[A-Z]{2}\b',
            'es-VE',
            fixed,
            flags=re.IGNORECASE,
        )

    # Paso 3: Reemplazar 'es' suelto
    if 'es-VE' not in fixed and 'es_VE' not in fixed:
        fixed = _ES_BARE_RE.sub('es-VE', fixed)

    return fixed


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        """
        Sanea HTTP_ACCEPT_LANGUAGE ANTES de que el dispatcher del módulo
        website lo procese con babel, previniendo el crash con es-419.
        """
        try:
            environ = request.httprequest.environ
            al_original = environ.get('HTTP_ACCEPT_LANGUAGE', '')
            al_fixed = _fix_accept_language(al_original)
            if al_fixed != al_original:
                environ['HTTP_ACCEPT_LANGUAGE'] = al_fixed
                _logger.debug(
                    'Venezuela360: Accept-Language reescrito: %r → %r',
                    al_original, al_fixed,
                )
        except Exception as exc:
            # Nunca interrumpir el request por este fix
            _logger.warning(
                'Venezuela360: Error al sanear Accept-Language: %s', exc
            )

        return super()._pre_dispatch(rule, args)

    @classmethod
    def _get_nearest_lang(cls, lang_code):
        """
        Red de seguridad adicional: si el código de idioma no resuelve
        a ningún idioma activo en la BD, intentar con es_VE para cualquier
        variante de español.
        """
        try:
            res = super()._get_nearest_lang(lang_code)
        except Exception as exc:
            # babel puede lanzar UnknownLocaleError para es-419
            _logger.warning(
                'Venezuela360: _get_nearest_lang(%r) lanzó excepción: %s — '
                'usando fallback es_VE', lang_code, exc
            )
            res = None

        if not res and lang_code and str(lang_code).lower().startswith('es'):
            _logger.debug(
                'Venezuela360: Idioma %r no resuelto → usando es_VE como fallback.',
                lang_code,
            )
            return 'es_VE'

        return res
