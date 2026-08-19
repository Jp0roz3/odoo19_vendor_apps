# -*- coding: utf-8 -*-
"""
Venezuela360: post_init_hook
=============================
Se ejecuta UNA SOLA VEZ justo después de que el módulo es instalado.
Configura valores predeterminados seguros en la compañía activa.

Autor: JeanPerozo / Nubelco
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """
    Hook de post-instalación de Venezuela360.
    - Asigna las secuencias de retención a la compañía activa si aún no las tiene.
    - Registra un log de instalación exitosa.
    """
    company = env.company

    try:
        # Asignar secuencia de retención IVA
        if not company.l10n_ve_wh_iva_sequence_id:
            seq_iva = env.ref('l10n_ve_full.seq_wh_iva', raise_if_not_found=False)
            if seq_iva:
                company.l10n_ve_wh_iva_sequence_id = seq_iva
                _logger.info('Venezuela360: Secuencia IVA asignada a %s.', company.name)

        # Asignar secuencia de retención ISLR
        if not company.l10n_ve_wh_islr_sequence_id:
            seq_islr = env.ref('l10n_ve_full.seq_wh_islr', raise_if_not_found=False)
            if seq_islr:
                company.l10n_ve_wh_islr_sequence_id = seq_islr
                _logger.info('Venezuela360: Secuencia ISLR asignada a %s.', company.name)

        # Asignar secuencia de retención Municipal
        if not company.l10n_ve_wh_municipal_sequence_id:
            seq_mun = env.ref('l10n_ve_full.seq_wh_municipal', raise_if_not_found=False)
            if seq_mun:
                company.l10n_ve_wh_municipal_sequence_id = seq_mun
                _logger.info('Venezuela360: Secuencia Municipal asignada a %s.', company.name)

        _logger.info(
            '✅ Venezuela360 (l10n_ve_full) instalado correctamente en compañía: %s',
            company.name
        )

    except Exception as e:
        _logger.warning(
            'Venezuela360 post_init_hook: Error no crítico durante la configuración inicial: %s',
            str(e)
        )
