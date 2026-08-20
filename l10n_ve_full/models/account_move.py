# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de account.move
=========================================
Añade a todas las facturas, notas de crédito/débito y asientos:
- Tasa BCV histórica vinculada al documento
- Montos en Bs y en USD con equivalencia automática
- Referencia a la Unidad Tributaria vigente en la fecha
- Estado de retenciones (IVA, ISLR, Municipal)
- Número de documento fiscal venezolano
- Visibilidad completa de doble moneda en pantalla y reportes

Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ------------------------------------------------------------------
    # Indicador de localización
    # ------------------------------------------------------------------
    l10n_ve_localization = fields.Boolean(
        string='Localización Venezuela activa',
        related='company_id.l10n_ve_active',
        store=False,
    )

    # Medio de emisión fiscal
    l10n_ve_journal_emission_medium = fields.Selection([
        ('manual', 'Manual'),
        ('fiscal_printer', 'Impresora Fiscal'),
        ('free_format', 'Forma Libre'),
    ], string='Medio de Emisión', default='free_format', help='Medio de emisión del documento fiscal.')

    # ------------------------------------------------------------------
    # Tasa de cambio BCV
    # ------------------------------------------------------------------
    l10n_ve_exchange_rate_id = fields.Many2one(
        comodel_name='l10n_ve.exchange.rate',
        string='Tasa BCV del Documento',
        help=(
            'Tasa oficial BCV usada para la conversión BS/USD en este documento. '
            'Se asigna automáticamente desde el histórico de tasas al confirmar la fecha.'
        ),
        copy=False,
        tracking=True,
    )
    l10n_ve_rate = fields.Float(
        string='Tasa BCV (Bs/USD)',
        digits=(18, 6),
        compute='_compute_ve_rate',
        store=True,
        copy=False,
        help='Valor numérico de la tasa BCV usada. Calculado desde l10n_ve_exchange_rate_id.',
    )
    l10n_ve_rate_date = fields.Date(
        string='Fecha de Tasa BCV',
        compute='_compute_ve_rate',
        store=True,
        copy=False,
    )
    l10n_ve_rate_source = fields.Char(
        string='Fuente de Tasa',
        compute='_compute_ve_rate',
        store=True,
    )

    # ------------------------------------------------------------------
    # Montos duales BS / USD
    # ------------------------------------------------------------------
    l10n_ve_amount_untaxed_bs = fields.Monetary(
        string='Base Imponible (Bs)',
        currency_field='l10n_ve_currency_bs_id',
        compute='_compute_ve_amounts',
        store=True,
        copy=False,
        help='Base imponible (sin IVA) expresada en Bolívares.',
    )
    l10n_ve_amount_tax_bs = fields.Monetary(
        string='IVA Total (Bs)',
        currency_field='l10n_ve_currency_bs_id',
        compute='_compute_ve_amounts',
        store=True,
        copy=False,
    )
    l10n_ve_amount_total_bs = fields.Monetary(
        string='Total Factura (Bs)',
        currency_field='l10n_ve_currency_bs_id',
        compute='_compute_ve_amounts',
        store=True,
        copy=False,
    )
    l10n_ve_amount_untaxed_usd = fields.Float(
        string='Base Imponible (USD)',
        digits=(18, 4),
        compute='_compute_ve_amounts',
        store=True,
        copy=False,
    )
    l10n_ve_amount_tax_usd = fields.Float(
        string='IVA Total (USD)',
        digits=(18, 4),
        compute='_compute_ve_amounts',
        store=True,
        copy=False,
    )
    l10n_ve_amount_total_usd = fields.Float(
        string='Total Factura (USD)',
        digits=(18, 4),
        compute='_compute_ve_amounts',
        store=True,
        copy=False,
    )
    l10n_ve_currency_bs_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda Bs',
        related='company_id.l10n_ve_currency_bs_id',
        store=True,
    )

    # ------------------------------------------------------------------
    # Campos de Moneda Dual / Referencia (USD / Bs)
    # ------------------------------------------------------------------
    l10n_ve_is_bs_agreement = fields.Boolean(
        string='Acuerdo de Factura Bs.',
        help='Indica si el documento tiene acuerdo especial de factura en Bolívares.',
    )
    l10n_ve_dual_ref_currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda Dual Ref.',
        compute='_compute_ve_dual_header',
    )
    l10n_ve_dual_currency_name = fields.Char(
        string='Moneda Dual Ref.',
        compute='_compute_ve_dual_header',
        default='USD',
    )
    l10n_ve_ref_currency_label = fields.Char(
        string='Moneda de Referencia',
        compute='_compute_ve_dual_header',
        default='Dólares',
    )

    # Totales en Moneda de Referencia (USD) para pie de página
    l10n_ve_untaxed_ref = fields.Float(
        string='Base imponible Ref.',
        compute='_compute_ve_dual_totals',
        digits=(18, 2),
    )
    l10n_ve_tax_ref = fields.Float(
        string='Impuestos Ref.',
        compute='_compute_ve_dual_totals',
        digits=(18, 2),
    )
    l10n_ve_total_ref = fields.Float(
        string='Total Ref.',
        compute='_compute_ve_dual_totals',
        digits=(18, 2),
    )
    l10n_ve_paid_ref = fields.Float(
        string='Pagado Ref.',
        compute='_compute_ve_dual_totals',
        digits=(18, 2),
    )
    l10n_ve_residual_ref = fields.Float(
        string='Adeudado Ref.',
        compute='_compute_ve_dual_totals',
        digits=(18, 2),
    )

    # ------------------------------------------------------------------
    # Unidad Tributaria al momento del documento
    # ------------------------------------------------------------------
    l10n_ve_ut_id = fields.Many2one(
        comodel_name='account.ut.history',
        string='UT Vigente (en fecha del documento)',
        compute='_compute_ve_ut',
        store=True,
        copy=False,
        help='Valor de Unidad Tributaria vigente en la fecha de este documento.',
    )
    l10n_ve_ut_value = fields.Float(
        string='Valor UT (Bs)',
        digits=(18, 2),
        compute='_compute_ve_ut',
        store=True,
        copy=False,
    )

    # ------------------------------------------------------------------
    # Documento fiscal venezolano
    # ------------------------------------------------------------------
    l10n_ve_fiscal_number = fields.Char(
        string='Número Fiscal (SENIAT)',
        size=20,
        copy=False,
        help='Número de control o correlativo fiscal emitido por el SENIAT o la impresora fiscal.',
    )
    l10n_ve_control_number = fields.Char(
        string='Número de Control',
        size=14,
        copy=False,
        help='Número de control asignado al documento (ej: 00-12345678).',
    )

    # ------------------------------------------------------------------
    # Estado de retenciones
    # ------------------------------------------------------------------
    l10n_ve_wh_iva_ids = fields.One2many(
        comodel_name='account.wh.iva',
        inverse_name='move_id',
        string='Retenciones IVA',
        copy=False,
    )
    l10n_ve_wh_islr_ids = fields.One2many(
        comodel_name='account.wh.islr',
        inverse_name='move_id',
        string='Retenciones ISLR',
        copy=False,
    )
    l10n_ve_wh_municipal_ids = fields.One2many(
        comodel_name='account.wh.municipal',
        inverse_name='move_id',
        string='Retenciones Municipales',
        copy=False,
    )
    l10n_ve_wh_iva_count = fields.Integer(
        string='N° Ret. IVA',
        compute='_compute_wh_counts',
    )
    l10n_ve_wh_islr_count = fields.Integer(
        string='N° Ret. ISLR',
        compute='_compute_wh_counts',
    )
    l10n_ve_wh_municipal_count = fields.Integer(
        string='N° Ret. Municipal',
        compute='_compute_wh_counts',
    )

    # Montos totales de retención (en Bs y USD)
    l10n_ve_wh_iva_total_bs = fields.Monetary(
        string='Total Ret. IVA (Bs)',
        currency_field='l10n_ve_currency_bs_id',
        compute='_compute_wh_totals',
        store=True,
    )
    l10n_ve_wh_iva_total_usd = fields.Float(
        string='Total Ret. IVA (USD)',
        digits=(18, 4),
        compute='_compute_wh_totals',
        store=True,
    )
    l10n_ve_wh_islr_total_bs = fields.Monetary(
        string='Total Ret. ISLR (Bs)',
        currency_field='l10n_ve_currency_bs_id',
        compute='_compute_wh_totals',
        store=True,
    )
    l10n_ve_wh_municipal_total_bs = fields.Monetary(
        string='Total Ret. Municipal (Bs)',
        currency_field='l10n_ve_currency_bs_id',
        compute='_compute_wh_totals',
        store=True,
    )

    # ------------------------------------------------------------------
    # Compute: tasa de cambio desde registro histórico
    # ------------------------------------------------------------------
    @api.depends('l10n_ve_exchange_rate_id', 'l10n_ve_exchange_rate_id.rate',
                 'l10n_ve_exchange_rate_id.date', 'l10n_ve_exchange_rate_id.source')
    def _compute_ve_rate(self):
        for move in self:
            rate_rec = move.l10n_ve_exchange_rate_id
            move.l10n_ve_rate = rate_rec.rate if rate_rec else 0.0
            move.l10n_ve_rate_date = rate_rec.date if rate_rec else False
            move.l10n_ve_rate_source = dict(
                rate_rec._fields['source'].selection
            ).get(rate_rec.source, '') if rate_rec else ''

    # ------------------------------------------------------------------
    # Compute: montos duales BS/USD
    # ------------------------------------------------------------------
    @api.depends('amount_untaxed', 'amount_tax', 'amount_total',
                 'l10n_ve_rate', 'currency_id', 'company_id.l10n_ve_currency_bs_id')
    def _compute_ve_amounts(self):
        for move in self:
            rate = move.l10n_ve_rate
            bs_currency = move.company_id.l10n_ve_currency_bs_id
            # Si el documento ya está en Bs, no convertir
            if move.currency_id == bs_currency and bs_currency:
                move.l10n_ve_amount_untaxed_bs = move.amount_untaxed
                move.l10n_ve_amount_tax_bs = move.amount_tax
                move.l10n_ve_amount_total_bs = move.amount_total
                move.l10n_ve_amount_untaxed_usd = round(move.amount_untaxed / rate, 4) if rate else 0.0
                move.l10n_ve_amount_tax_usd = round(move.amount_tax / rate, 4) if rate else 0.0
                move.l10n_ve_amount_total_usd = round(move.amount_total / rate, 4) if rate else 0.0
            else:
                # Documento en USD → convertir a Bs
                move.l10n_ve_amount_untaxed_usd = move.amount_untaxed
                move.l10n_ve_amount_tax_usd = move.amount_tax
                move.l10n_ve_amount_total_usd = move.amount_total
                move.l10n_ve_amount_untaxed_bs = round(move.amount_untaxed * rate, 2)
                move.l10n_ve_amount_tax_bs = round(move.amount_tax * rate, 2)
                move.l10n_ve_amount_total_bs = round(move.amount_total * rate, 2)

    # ------------------------------------------------------------------
    # Compute: UT vigente en la fecha del documento
    # ------------------------------------------------------------------
    @api.depends('invoice_date', 'date', 'company_id')
    def _compute_ve_ut(self):
        for move in self:
            doc_date = move.invoice_date or move.date
            if doc_date and move.company_id.l10n_ve_active:
                ut = self.env['account.ut.history'].get_ut_for_date(
                    doc_date, company_id=move.company_id.id
                )
                move.l10n_ve_ut_id = ut.id if ut else False
                move.l10n_ve_ut_value = ut.value_bs if ut else 0.0
            else:
                move.l10n_ve_ut_id = False
                move.l10n_ve_ut_value = 0.0

    # ------------------------------------------------------------------
    # Compute: conteos de retención
    # ------------------------------------------------------------------
    def _compute_wh_counts(self):
        for move in self:
            move.l10n_ve_wh_iva_count = len(move.l10n_ve_wh_iva_ids)
            move.l10n_ve_wh_islr_count = len(move.l10n_ve_wh_islr_ids)
            move.l10n_ve_wh_municipal_count = len(move.l10n_ve_wh_municipal_ids)

    # ------------------------------------------------------------------
    # Compute: totales de retención en Bs y USD
    # ------------------------------------------------------------------
    @api.depends('l10n_ve_wh_iva_ids.amount_bs', 'l10n_ve_wh_iva_ids.state',
                 'l10n_ve_wh_islr_ids.amount_bs', 'l10n_ve_wh_municipal_ids.amount_bs')
    def _compute_wh_totals(self):
        for move in self:
            rate = move.l10n_ve_rate or 1.0
            wh_iva_bs = sum(
                wh.amount_bs for wh in move.l10n_ve_wh_iva_ids if wh.state != 'cancel'
            )
            move.l10n_ve_wh_iva_total_bs = wh_iva_bs
            move.l10n_ve_wh_iva_total_usd = round(wh_iva_bs / rate, 4) if rate else 0.0
            move.l10n_ve_wh_islr_total_bs = sum(
                wh.amount_bs for wh in move.l10n_ve_wh_islr_ids if wh.state != 'cancel'
            )
            move.l10n_ve_wh_municipal_total_bs = sum(
                wh.amount_bs for wh in move.l10n_ve_wh_municipal_ids if wh.state != 'cancel'
            )

    # ------------------------------------------------------------------
    # Override: al confirmar la factura, asignar tasa BCV si no está puesta
    # ------------------------------------------------------------------
    def action_post(self):
        for move in self:
            if move.company_id.l10n_ve_active and not move.l10n_ve_exchange_rate_id:
                doc_date = move.invoice_date or move.date
                if doc_date:
                    rate_rec = self.env['l10n_ve.exchange.rate'].get_rate_for_date(
                        doc_date, company_id=move.company_id.id
                    )
                    if rate_rec:
                        move.l10n_ve_exchange_rate_id = rate_rec.id
                    else:
                        _logger.warning(
                            'Venezuela360: No se encontró tasa BCV para fecha %s '
                            'en compañía %s. Asigne la tasa manualmente.',
                            doc_date, move.company_id.name
                        )
        return super().action_post()


    # ------------------------------------------------------------------
    # Acciones de botones stat
    # ------------------------------------------------------------------
    def action_view_wh_iva(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Retenciones IVA'),
            'res_model': 'account.wh.iva',
            'view_mode': 'list,form',
            'domain': [('move_id', '=', self.id)],
            'context': {'default_move_id': self.id},
        }

    def action_view_wh_islr(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Retenciones ISLR'),
            'res_model': 'account.wh.islr',
            'view_mode': 'list,form',
            'domain': [('move_id', '=', self.id)],
            'context': {'default_move_id': self.id},
        }

    def action_view_wh_municipal(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Retenciones Municipales'),
            'res_model': 'account.wh.municipal',
            'view_mode': 'list,form',
            'domain': [('move_id', '=', self.id)],
            'context': {'default_move_id': self.id},
        }

    # ------------------------------------------------------------------
    # Computos Duales (USD / Bs) de Cabecera y Totales
    # ------------------------------------------------------------------
    @api.depends('company_id')
    def _compute_ve_dual_header(self):
        usd = self.env.ref('base.USD', raise_if_not_found=False)
        for move in self:
            move.l10n_ve_dual_ref_currency_id = usd.id if usd else False
            move.l10n_ve_dual_currency_name = 'USD'
            move.l10n_ve_ref_currency_label = 'Dólares'

    @api.depends('amount_untaxed', 'amount_tax', 'amount_total', 'amount_residual', 'l10n_ve_rate', 'currency_id', 'company_id.l10n_ve_currency_bs_id')
    def _compute_ve_dual_totals(self):
        for move in self:
            rate = move.l10n_ve_rate or 1.0
            bs_currency = move.company_id.l10n_ve_currency_bs_id
            if move.currency_id == bs_currency and bs_currency:
                move.l10n_ve_untaxed_ref = round(move.amount_untaxed / rate, 2) if rate else 0.0
                move.l10n_ve_tax_ref = round(move.amount_tax / rate, 2) if rate else 0.0
                move.l10n_ve_total_ref = round(move.amount_total / rate, 2) if rate else 0.0
                move.l10n_ve_residual_ref = round(move.amount_residual / rate, 2) if rate else 0.0
                move.l10n_ve_paid_ref = round((move.amount_total - move.amount_residual) / rate, 2) if rate else 0.0
            else:
                move.l10n_ve_untaxed_ref = round(move.amount_untaxed, 2)
                move.l10n_ve_tax_ref = round(move.amount_tax, 2)
                move.l10n_ve_total_ref = round(move.amount_total, 2)
                move.l10n_ve_residual_ref = round(move.amount_residual, 2)
                move.l10n_ve_paid_ref = round(move.amount_total - move.amount_residual, 2)


class AccountMoveLine(models.Model):
    """Extensión de líneas de asiento para montos en moneda dual (USD)."""
    _inherit = 'account.move.line'

    l10n_ve_price_unit_usd = fields.Float(
        string='Precio $ Moneda Ref.',
        compute='_compute_ve_line_usd',
        digits=(18, 2),
    )
    l10n_ve_price_subtotal_usd = fields.Float(
        string='Subtotal Ref.',
        compute='_compute_ve_line_usd',
        digits=(18, 2),
    )

    @api.depends('price_unit', 'price_subtotal', 'move_id.l10n_ve_rate', 'move_id.currency_id', 'move_id.company_id.l10n_ve_currency_bs_id')
    def _compute_ve_line_usd(self):
        for line in self:
            move = line.move_id
            rate = move.l10n_ve_rate or 1.0
            bs_currency = move.company_id.l10n_ve_currency_bs_id
            if move.currency_id == bs_currency and bs_currency:
                line.l10n_ve_price_unit_usd = round(line.price_unit / rate, 2) if rate else 0.0
                line.l10n_ve_price_subtotal_usd = round(line.price_subtotal / rate, 2) if rate else 0.0
            else:
                line.l10n_ve_price_unit_usd = round(line.price_unit, 2)
                line.l10n_ve_price_subtotal_usd = round(line.price_subtotal, 2)

