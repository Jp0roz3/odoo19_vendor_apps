# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de res.config.settings
================================================
Expone todos los campos de res.company relativos a la localización venezolana
en la pantalla de Configuración de Odoo (Ajustes > Contabilidad > Venezuela360).

Patrón Odoo 19: cada campo en res.config.settings que corresponde
a un campo de la compañía usa el helper config_parameter o related.

Autor: JeanPerozo / Nubelco
"""
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Activación ──────────────────────────────────────────────────
    l10n_ve_active = fields.Boolean(
        string='Activar Localización Venezuela360',
        related='company_id.l10n_ve_active',
        readonly=False,
    )

    # ── Dual moneda ─────────────────────────────────────────────────
    l10n_ve_dual_currency = fields.Boolean(
        string='Contabilidad Dual BS/USD',
        related='company_id.l10n_ve_dual_currency',
        readonly=False,
    )

    # ── Identificación SENIAT ────────────────────────────────────────
    l10n_ve_rif = fields.Char(
        string='RIF de la Empresa',
        related='company_id.l10n_ve_rif',
        readonly=False,
    )
    l10n_ve_contributor_type = fields.Selection(
        related='company_id.l10n_ve_contributor_type',
        readonly=False,
        string='Tipo de Contribuyente IVA',
    )
    l10n_ve_retention_agent = fields.Boolean(
        string='Agente de Retención IVA',
        related='company_id.l10n_ve_retention_agent',
        readonly=False,
    )
    l10n_ve_retention_islr_agent = fields.Boolean(
        string='Agente de Retención ISLR',
        related='company_id.l10n_ve_retention_islr_agent',
        readonly=False,
    )
    l10n_ve_retention_municipal_agent = fields.Boolean(
        string='Agente de Retención Municipal',
        related='company_id.l10n_ve_retention_municipal_agent',
        readonly=False,
    )

    # ── Tasa de cambio ──────────────────────────────────────────────
    l10n_ve_rate_source = fields.Selection(
        related='company_id.l10n_ve_rate_source',
        readonly=False,
        string='Fuente de Tasa BCV',
    )

    # ── Tasas IVA ───────────────────────────────────────────────────
    l10n_ve_iva_rate = fields.Float(
        string='IVA General (%)',
        related='company_id.l10n_ve_iva_rate',
        readonly=False,
    )
    l10n_ve_iva_reduced_rate = fields.Float(
        string='IVA Reducida (%)',
        related='company_id.l10n_ve_iva_reduced_rate',
        readonly=False,
    )
    l10n_ve_wh_iva_rate_general = fields.Float(
        string='Ret. IVA Contribuyente Ordinario (%)',
        related='company_id.l10n_ve_wh_iva_rate_general',
        readonly=False,
    )
    l10n_ve_wh_iva_rate_special = fields.Float(
        string='Ret. IVA Contribuyente Especial (%)',
        related='company_id.l10n_ve_wh_iva_rate_special',
        readonly=False,
    )

    # ── Diarios ─────────────────────────────────────────────────────
    l10n_ve_wh_iva_journal_id = fields.Many2one(
        string='Diario Ret. IVA',
        related='company_id.l10n_ve_wh_iva_journal_id',
        readonly=False,
    )
    l10n_ve_wh_islr_journal_id = fields.Many2one(
        string='Diario Ret. ISLR',
        related='company_id.l10n_ve_wh_islr_journal_id',
        readonly=False,
    )
    l10n_ve_wh_municipal_journal_id = fields.Many2one(
        string='Diario Ret. Municipal',
        related='company_id.l10n_ve_wh_municipal_journal_id',
        readonly=False,
    )

    # ── Cuentas Contables ────────────────────────────────────────────
    l10n_ve_wh_iva_account_id = fields.Many2one(
        string='Cuenta IVA Retenido (emitido)',
        related='company_id.l10n_ve_wh_iva_account_id',
        readonly=False,
    )
    l10n_ve_wh_iva_received_account_id = fields.Many2one(
        string='Cuenta IVA Retenido (recibido)',
        related='company_id.l10n_ve_wh_iva_received_account_id',
        readonly=False,
    )
    l10n_ve_wh_islr_account_id = fields.Many2one(
        string='Cuenta ISLR Retenido',
        related='company_id.l10n_ve_wh_islr_account_id',
        readonly=False,
    )
    l10n_ve_wh_municipal_account_id = fields.Many2one(
        string='Cuenta Ret. Municipal',
        related='company_id.l10n_ve_wh_municipal_account_id',
        readonly=False,
    )
