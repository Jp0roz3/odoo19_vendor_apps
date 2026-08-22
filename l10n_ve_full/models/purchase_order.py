# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de purchase.order
==========================================
Permite configurar el tipo de tasa de cambio (BCV, Personalizada, Acuerdo Comercial)
en pedidos de compra, calcular totales referenciales en Bolívares (Bs.) o Dólares ($)
y propagar la tasa automáticamente a la factura de proveedor (account.move).

Autor: JeanPerozo / Nubelco
"""
from odoo import models, fields, api, _


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # ------------------------------------------------------------------
    # Tipo de Tasa y Tasa Aplicada (Requerimientos 1 y 2)
    # ------------------------------------------------------------------
    l10n_ve_rate_type = fields.Selection([
        ('bcv', 'Tasa Oficial BCV'),
        ('commercial', 'Acuerdo Comercial'),
    ], string='Tipo de Tasa de Cambio', default='bcv', copy=True, tracking=True,
       help='Selecciona si el pedido de compra usará la tasa oficial BCV del día o un acuerdo comercial.')

    l10n_ve_rate_applied = fields.Float(
        string='Tasa Aplicada (Bs/USD)',
        digits=(18, 6),
        compute='_compute_ve_purchase_dual',
        inverse='_inverse_ve_purchase_rate_applied',
        store=True,
        copy=True,
        tracking=True,
        help='Tasa de cambio efectiva para las conversiones de la orden de compra.',
    )

    l10n_ve_rate = fields.Float(
        string='Tasa BCV (Bs/USD)',
        compute='_compute_ve_purchase_dual',
        store=True,
        digits=(18, 6),
    )
    l10n_ve_untaxed_bs = fields.Float(
        string='Base imponible Bs.',
        compute='_compute_ve_purchase_dual',
        store=True,
        digits=(18, 2),
    )
    l10n_ve_tax_bs = fields.Float(
        string='Impuestos Bs.',
        compute='_compute_ve_purchase_dual',
        store=True,
        digits=(18, 2),
    )
    l10n_ve_total_bs = fields.Float(
        string='Total Pedido Bs.',
        compute='_compute_ve_purchase_dual',
        store=True,
        digits=(18, 2),
    )
    l10n_ve_is_usd_order = fields.Boolean(
        string='Pedido en USD',
        compute='_compute_ve_purchase_dual',
        store=True,
    )

    @api.depends('amount_untaxed', 'amount_tax', 'amount_total', 'currency_id',
                 'date_order', 'company_id', 'l10n_ve_rate_type', 'l10n_ve_rate_applied')
    def _compute_ve_purchase_dual(self):
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

    def _inverse_ve_purchase_rate_applied(self):
        for order in self:
            if order.l10n_ve_rate_type == 'bcv' and order.l10n_ve_rate_applied != order.l10n_ve_rate:
                order.l10n_ve_rate_type = 'commercial'

    # ------------------------------------------------------------------
    # Propagación de tasa de cambio a la factura de proveedor (Requerimiento 1)
    # ------------------------------------------------------------------
    def action_create_invoice(self, *args, **kwargs):
        res = super().action_create_invoice(*args, **kwargs)
        # Actualizar las facturas creadas con la tasa de la orden de compra
        for order in self:
            for invoice in order.invoice_ids.filtered(lambda inv: inv.state == 'draft'):
                invoice.write({
                    'l10n_ve_rate_type': order.l10n_ve_rate_type or 'bcv',
                    'l10n_ve_rate_applied': order.l10n_ve_rate_applied or order.l10n_ve_rate,
                })
        return res


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    l10n_ve_price_unit_usd = fields.Float(
        string='Costo Ref. ($)',
        compute='_compute_ve_purchase_line_duals',
        digits=(18, 2),
    )
    l10n_ve_price_subtotal_bs = fields.Float(
        string='Subtotal (Bs)',
        compute='_compute_ve_purchase_line_duals',
        digits=(18, 2),
    )

    @api.depends('price_unit', 'price_subtotal', 'order_id.currency_id', 'order_id.l10n_ve_rate_applied')
    def _compute_ve_purchase_line_duals(self):
        for line in self:
            rate = line.order_id.l10n_ve_rate_applied or line.order_id.l10n_ve_rate or 1.0
            is_bs = line.order_id.currency_id and line.order_id.currency_id.name in ['VES', 'VEF', 'VEB']
            if is_bs:
                line.l10n_ve_price_unit_usd = round(line.price_unit / rate, 2) if rate else 0.0
                line.l10n_ve_price_subtotal_bs = line.price_subtotal
            else:
                line.l10n_ve_price_unit_usd = line.price_unit
                line.l10n_ve_price_subtotal_bs = round(line.price_subtotal * rate, 2)

    @api.onchange('product_id')
    def _onchange_product_id_ve_purchase_price(self):
        """Asigna de inmediato el costo unitario correcto al seleccionar el producto en compras."""
        for line in self:
            if not line.product_id:
                continue
            order = line.order_id
            is_usd = order.currency_id and order.currency_id.name in ['USD', '$']
            is_bs = order.currency_id and order.currency_id.name in ['VES', 'VEF', 'VEB']

            if is_usd:
                cost_usd = getattr(line.product_id, 'l10n_ve_standard_price_usd', 0.0) or line.product_id.standard_price
                if cost_usd > 0:
                    line.price_unit = cost_usd
            elif is_bs:
                rate = order.l10n_ve_rate_applied or order.l10n_ve_rate or order.company_id.get_current_bcv_rate() or 779.9522
                cost_usd = getattr(line.product_id, 'l10n_ve_standard_price_usd', 0.0) or line.product_id.standard_price
                if cost_usd > 0:
                    line.price_unit = round(cost_usd * rate, 2)

