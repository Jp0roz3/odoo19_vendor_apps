# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de sale.order
======================================
Permite configurar el tipo de tasa de cambio (BCV, Personalizada, Acuerdo Comercial),
calcular totales referenciales en Bolívares (Bs.) o Dólares ($) y propagar
la tasa elegida automáticamente a la factura de venta (account.move).

Autor: JeanPerozo / Nubelco
"""
from odoo import models, fields, api, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------------
    # Tipo de Tasa y Tasa Aplicada (Requerimiento 1 y 2)
    # ------------------------------------------------------------------
    l10n_ve_rate_type = fields.Selection([
        ('bcv', 'Tasa Oficial BCV'),
        ('commercial', 'Acuerdo Comercial'),
    ], string='Tipo de Tasa de Cambio', default='bcv', copy=True, tracking=True,
       help='Selecciona si la cotización usará la tasa oficial BCV del día o un acuerdo comercial.')

    l10n_ve_rate_applied = fields.Float(
        string='Tasa Aplicada (Bs/USD)',
        digits=(18, 6),
        compute='_compute_ve_sale_dual',
        inverse='_inverse_ve_sale_rate_applied',
        store=True,
        copy=True,
        tracking=True,
        help='Tasa de cambio efectiva para las conversiones de la orden.',
    )

    l10n_ve_rate = fields.Float(
        string='Tasa BCV (Bs/USD)',
        compute='_compute_ve_sale_dual',
        store=True,
        digits=(18, 6),
    )
    l10n_ve_untaxed_bs = fields.Float(
        string='Base imponible Bs.',
        compute='_compute_ve_sale_dual',
        store=True,
        digits=(18, 2),
    )
    l10n_ve_tax_bs = fields.Float(
        string='Impuestos Bs.',
        compute='_compute_ve_sale_dual',
        store=True,
        digits=(18, 2),
    )
    l10n_ve_total_bs = fields.Float(
        string='Total Order Bs.',
        compute='_compute_ve_sale_dual',
        store=True,
        digits=(18, 2),
    )
    l10n_ve_is_usd_order = fields.Boolean(
        string='Cotización en USD',
        compute='_compute_ve_sale_dual',
        store=True,
    )

    @api.depends('amount_untaxed', 'amount_tax', 'amount_total', 'currency_id',
                 'date_order', 'company_id', 'l10n_ve_rate_type', 'l10n_ve_rate_applied')
    def _compute_ve_sale_dual(self):
        for order in self:
            date = order.date_order or fields.Date.context_today(order)
            rate_rec = self.env['l10n_ve.exchange.rate'].get_rate_for_date(date, company_id=order.company_id.id)
            if not rate_rec or not rate_rec.rate:
                rate_rec = self.env['l10n_ve.exchange.rate'].get_latest_rate(company_id=order.company_id.id)
            rate_val = rate_rec.rate if rate_rec and rate_rec.rate > 0 else (order.company_id.get_current_bcv_rate() or 779.9522)

            order.l10n_ve_rate = rate_val

            # Determinar tasa aplicada
            if order.l10n_ve_rate_type == 'bcv' or not order.l10n_ve_rate_applied:
                active_rate = rate_val
                order.l10n_ve_rate_applied = active_rate
            else:
                active_rate = order.l10n_ve_rate_applied

            bs_currency = order.company_id.l10n_ve_currency_bs_id
            is_bs = (order.currency_id == bs_currency) or (order.currency_id.name in ['VES', 'VEF', 'VEB'])
            order.l10n_ve_is_usd_order = not is_bs

            if is_bs:
                order.l10n_ve_untaxed_bs = order.amount_untaxed
                order.l10n_ve_tax_bs = order.amount_tax
                order.l10n_ve_total_bs = order.amount_total
            else:
                order.l10n_ve_untaxed_bs = round(order.amount_untaxed * active_rate, 2)
                order.l10n_ve_tax_bs = round(order.amount_tax * active_rate, 2)
                order.l10n_ve_total_bs = round(order.amount_total * active_rate, 2)

    def _inverse_ve_sale_rate_applied(self):
        for order in self:
            if order.l10n_ve_rate_type == 'bcv' and order.l10n_ve_rate_applied != order.l10n_ve_rate:
                order.l10n_ve_rate_type = 'commercial'

    @api.onchange('date_order', 'company_id')
    def _onchange_date_order_ve_rate(self):
        for order in self:
            date = order.date_order or fields.Date.context_today(order)
            rate_rec = self.env['l10n_ve.exchange.rate'].get_rate_for_date(date, company_id=order.company_id.id)
            if not rate_rec or rate_rec.rate <= 0:
                rate_rec = self.env['l10n_ve.exchange.rate'].get_latest_rate(company_id=order.company_id.id)
            if rate_rec:
                order.l10n_ve_rate = rate_rec.rate
                if order.l10n_ve_rate_type == 'bcv':
                    order.l10n_ve_rate_applied = rate_rec.rate

    # ------------------------------------------------------------------
    # Propagación de tasa de cambio a la factura (Requerimiento 1)
    # ------------------------------------------------------------------
    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        if self.company_id.l10n_ve_active:
            invoice_vals.update({
                'l10n_ve_rate_type': self.l10n_ve_rate_type or 'bcv',
                'l10n_ve_rate_applied': self.l10n_ve_rate_applied or self.l10n_ve_rate,
            })
        return invoice_vals


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    l10n_ve_price_unit_usd = fields.Float(
        string='Precio Ref. ($)',
        compute='_compute_ve_sale_line_duals',
        digits=(18, 2),
    )
    l10n_ve_price_subtotal_bs = fields.Float(
        string='Subtotal (Bs)',
        compute='_compute_ve_sale_line_duals',
        digits=(18, 2),
    )

    @api.depends('price_unit', 'price_subtotal', 'order_id.currency_id', 'order_id.l10n_ve_rate_applied')
    def _compute_ve_sale_line_duals(self):
        for line in self:
            rate = line.order_id.l10n_ve_rate_applied or line.order_id.l10n_ve_rate or 1.0
            is_bs = line.order_id.currency_id and line.order_id.currency_id.name in ['VES', 'VEF', 'VEB']
            if is_bs:
                line.l10n_ve_price_unit_usd = round(line.price_unit / rate, 2) if rate else 0.0
                line.l10n_ve_price_subtotal_bs = line.price_subtotal
            else:
                line.l10n_ve_price_unit_usd = line.price_unit
                line.l10n_ve_price_subtotal_bs = round(line.price_subtotal * rate, 2)

    def _get_display_price(self):
        """Garantiza que al seleccionar un producto en cotizaciones en USD, use el precio en USD sin dividir por la tasa."""
        order = self.order_id
        is_usd = order.currency_id and order.currency_id.name in ['USD', '$']
        if is_usd and self.product_id:
            usd_price = getattr(self.product_id, 'l10n_ve_list_price_usd', 0.0) or self.product_id.lst_price
            if usd_price > 0:
                return usd_price
        return super()._get_display_price()

    @api.onchange('product_id')
    def _onchange_product_id_ve_sale_price(self):
        """Asigna de inmediato el precio unitario correcto al seleccionar el producto en la cotización."""
        for line in self:
            if not line.product_id:
                continue
            order = line.order_id
            is_usd = order.currency_id and order.currency_id.name in ['USD', '$']
            is_bs = order.currency_id and order.currency_id.name in ['VES', 'VEF', 'VEB']

            if is_usd:
                usd_price = getattr(line.product_id, 'l10n_ve_list_price_usd', 0.0) or line.product_id.lst_price
                if usd_price > 0:
                    line.price_unit = usd_price
            elif is_bs:
                rate = order.l10n_ve_rate_applied or order.l10n_ve_rate or order.company_id.get_current_bcv_rate() or 779.9522
                usd_price = getattr(line.product_id, 'l10n_ve_list_price_usd', 0.0) or line.product_id.lst_price
                if usd_price > 0:
                    line.price_unit = round(usd_price * rate, 2)

