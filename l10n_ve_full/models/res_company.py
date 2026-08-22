# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de res.company
========================================
Añade a res.company todos los parámetros de configuración fiscal
y contable venezolana, incluyendo configuración dual BS/USD,
parámetros de retención y la UT activa.

Autor: JeanPerozo / Nubelco
"""
from odoo import models, fields, api, _
import re


class ResCompany(models.Model):
    _inherit = 'res.company'

    # ------------------------------------------------------------------
    # Indicador de localización activa
    # ------------------------------------------------------------------
    l10n_ve_active = fields.Boolean(
        string='Localización Venezuela360 Activa',
        default=False,
        help='Activa la localización fiscal venezolana completa para esta compañía.',
    )

    # ------------------------------------------------------------------
    # Territorialidad
    # ------------------------------------------------------------------
    l10n_ve_state_id = fields.Many2one(
        comodel_name='l10n_ve.state',
        string='Estado (Venezuela)',
        help='Estado venezolano donde está registrada la compañía ante el SENIAT.',
    )
    l10n_ve_municipality_id = fields.Many2one(
        comodel_name='l10n_ve.municipality',
        string='Municipio (Venezuela)',
        domain="[('state_id', '=', l10n_ve_state_id)]",
    )
    l10n_ve_parish_id = fields.Many2one(
        comodel_name='l10n_ve.parish',
        string='Parroquia (Venezuela)',
        domain="[('municipality_id', '=', l10n_ve_municipality_id)]",
    )

    # ------------------------------------------------------------------
    # Identificación SENIAT
    # ------------------------------------------------------------------
    l10n_ve_rif = fields.Char(
        string='RIF',
        size=15,
        help='Registro de Información Fiscal. Ej: J-12345678-9',
    )
    l10n_ve_rif_clean = fields.Char(
        string='RIF (sin formato)',
        compute='_compute_rif_clean',
        store=True,
    )
    l10n_ve_contributor_type = fields.Selection([
        ('ordinary',    'Contribuyente Ordinario'),
        ('formal',      'Contribuyente Formal'),
        ('special',     'Contribuyente Especial'),
        ('exonerated',  'Exonerado'),
    ], string='Tipo de Contribuyente IVA',
       default='ordinary',
       help='Clasificación del contribuyente ante el SENIAT para efectos de IVA.',
    )
    l10n_ve_retention_agent = fields.Boolean(
        string='Agente de Retención IVA',
        default=False,
        help='Indica que esta empresa está designada como Agente de Retención de IVA por el SENIAT.',
    )
    l10n_ve_retention_islr_agent = fields.Boolean(
        string='Agente de Retención ISLR',
        default=False,
        help='Indica que esta empresa es Agente de Retención del ISLR.',
    )

    # ------------------------------------------------------------------
    # Monedas: configuración dual BS / USD
    # ------------------------------------------------------------------
    l10n_ve_currency_bs_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda Bs (Bolívar)',
        default=lambda self: self.env['res.currency'].search(
            [('name', 'in', ['VES', 'VEF', 'VEB'])], limit=1
        ),
        help='Moneda venezolana activa (Bolívar Soberano / Digital).',
    )
    l10n_ve_currency_usd_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda USD',
        default=lambda self: self.env.ref('base.USD', raise_if_not_found=False),
    )
    l10n_ve_dual_currency = fields.Boolean(
        string='Contabilidad Dual BS/USD',
        default=True,
        help=(
            'Activa el registro de montos en BS y USD de forma simultánea '
            'en todos los documentos, asientos y reportes.'
        ),
    )

    # ------------------------------------------------------------------
    # Fuente de tasa de cambio
    # ------------------------------------------------------------------
    l10n_ve_rate_source = fields.Selection([
        ('bcv',    'BCV — Banco Central de Venezuela'),
        ('seniat', 'SENIAT — Tabla Oficial'),
        ('manual', 'Manual (usuario)'),
    ], string='Fuente de Tasa BCV',
       default='bcv',
       help='Fuente utilizada para registrar y consultar la tasa de cambio oficial.',
    )

    # ------------------------------------------------------------------
    # Diarios contables de localización
    # ------------------------------------------------------------------
    l10n_ve_wh_iva_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario Retenciones IVA',
        help='Diario contable donde se registran los asientos de retención de IVA.',
    )
    l10n_ve_wh_islr_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario Retenciones ISLR',
    )
    l10n_ve_wh_municipal_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario Retenciones Municipales',
    )

    # ------------------------------------------------------------------
    # Cuentas contables de retenciones
    # ------------------------------------------------------------------
    l10n_ve_wh_iva_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta IVA Retenido (Emitido)',
        help='Cuenta donde se registra el IVA retenido al proveedor.',
    )
    l10n_ve_wh_iva_received_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta IVA Retenido (Recibido)',
        help='Cuenta donde se registra el IVA que nos han retenido como proveedores.',
    )
    l10n_ve_wh_islr_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta ISLR Retenido (Emitido)',
    )
    l10n_ve_wh_islr_received_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta ISLR Retenido (Recibido)',
    )
    l10n_ve_wh_municipal_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta Ret. Municipal (Emitido)',
    )

    # ------------------------------------------------------------------
    # Parámetros de IVA
    # ------------------------------------------------------------------
    l10n_ve_iva_rate = fields.Float(
        string='Tasa IVA General (%)',
        default=16.0,
        digits=(5, 2),
        help='Porcentaje de IVA general aplicable. Ej: 16%.',
    )
    l10n_ve_iva_reduced_rate = fields.Float(
        string='Tasa IVA Reducida (%)',
        default=8.0,
        digits=(5, 2),
    )
    l10n_ve_iva_additional_rate = fields.Float(
        string='Tasa IVA Adicional (%)',
        default=15.0,
        digits=(5, 2),
    )

    # ------------------------------------------------------------------
    # Parámetros de Retención IVA (porcentaje sobre el IVA facturado)
    # ------------------------------------------------------------------
    l10n_ve_wh_iva_rate_general = fields.Float(
        string='Ret. IVA — Contribuyente Ordinario (%)',
        default=75.0,
        digits=(5, 2),
        help='Porcentaje de retención sobre el IVA para contribuyentes ordinarios (default 75%).',
    )
    l10n_ve_wh_iva_rate_special = fields.Float(
        string='Ret. IVA — Contribuyente Especial (%)',
        default=100.0,
        digits=(5, 2),
        help='Porcentaje de retención sobre el IVA para contribuyentes especiales (default 100%).',
    )

    # ------------------------------------------------------------------
    # Numeración de comprobantes
    # ------------------------------------------------------------------
    l10n_ve_wh_iva_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Secuencia Comprobante Ret. IVA',
    )
    l10n_ve_wh_islr_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Secuencia Comprobante Ret. ISLR',
    )
    l10n_ve_wh_municipal_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Secuencia Comprobante Ret. Municipal',
    )

    # ------------------------------------------------------------------
    # UT activa (computed)
    # ------------------------------------------------------------------
    l10n_ve_current_ut_id = fields.Many2one(
        comodel_name='account.ut.history',
        string='UT Vigente',
        compute='_compute_current_ut',
        help='Valor de Unidad Tributaria actualmente vigente para esta compañía.',
    )
    l10n_ve_current_ut_value = fields.Float(
        string='Valor UT Vigente (Bs)',
        compute='_compute_current_ut',
        digits=(18, 2),
    )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('l10n_ve_rif', 'partner_id.vat', 'partner_id.l10n_ve_rif')
    def _compute_rif_clean(self):
        for company in self:
            rif = company.l10n_ve_rif or company.partner_id.l10n_ve_rif or company.partner_id.vat or company.vat or ''
            company.l10n_ve_rif_clean = re.sub(r'[^A-Za-z0-9]', '', rif).upper()

    def _compute_current_ut(self):
        today = fields.Date.context_today(self)
        for company in self:
            ut = self.env['account.ut.history'].get_ut_for_date(today, company_id=company.id)
            company.l10n_ve_current_ut_id = ut.id if ut else False
            company.l10n_ve_current_ut_value = ut.value_bs if ut else 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def get_current_bcv_rate(self):
        """Retorna el valor float de la tasa BCV más reciente para esta compañía."""
        self.ensure_one()
        rate_rec = self.env['l10n_ve.exchange.rate'].get_latest_rate(company_id=self.id)
        return rate_rec.rate if rate_rec else 0.0
