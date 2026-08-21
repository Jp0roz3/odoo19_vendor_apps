# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de Productos (product.template & product.product)
==========================================================================
Añade visualización y cálculo de precios duales (Bs / USD), costo dual,
costo reposición, margen de ganancia bidireccional y pestaña de Retención ISLR según SENIAT.

Autor: JeanPerozo / Nubelco
"""
from odoo import models, fields, api, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    l10n_ve_list_price_usd = fields.Float(
        string='Precio de Venta ($)',
        compute='_compute_ve_product_prices',
        inverse='_inverse_ve_list_price_usd',
        digits=(18, 2),
        help='Precio de venta de referencia en Dólares (USD). Puedes editar este campo directamente.',
    )
    l10n_ve_list_price_bs = fields.Monetary(
        string='Precio de Venta (Bs)',
        currency_field='l10n_ve_currency_bs_id',
        compute='_compute_ve_product_prices',
        inverse='_inverse_ve_list_price_bs',
        help='Precio de venta en Bolívares (Bs). Puedes editar este campo directamente.',
    )
    l10n_ve_standard_price_bs = fields.Monetary(
        string='Costo (Bs)',
        currency_field='l10n_ve_currency_bs_id',
        compute='_compute_ve_product_prices',
        inverse='_inverse_ve_standard_price_bs',
        help='Costo en Bolívares (Bs). Puedes editar este campo directamente.',
    )
    l10n_ve_standard_price_usd = fields.Float(
        string='Costo ($)',
        compute='_compute_ve_product_prices',
        inverse='_inverse_ve_standard_price_usd',
        digits=(18, 2),
        help='Costo en Dólares (USD). Puedes editar este campo directamente.',
    )
    l10n_ve_replacement_cost_usd = fields.Float(
        string='Costo Reposición ($)',
        digits=(18, 2),
        default=0.0,
    )
    l10n_ve_profit_margin = fields.Float(
        string='Margen Ganancia (%)',
        compute='_compute_ve_profit_margin',
        inverse='_inverse_ve_profit_margin',
        digits=(18, 2),
        help='Porcentaje de ganancia sobre el costo. Puedes modificarlo directamente para recalcular el precio de venta.',
    )
    l10n_ve_islr_concept_id = fields.Many2one(
        comodel_name='account.wh.islr.concept',
        string='Concepto de Retención ISLR',
        help='Concepto de retención de ISLR según la normativa del SENIAT.',
    )
    l10n_ve_currency_bs_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda Bs',
        default=lambda self: self.env['res.currency'].search([('name', 'in', ['VES', 'VEF', 'VEB'])], limit=1),
    )

    @api.depends(
        'list_price', 'standard_price',
        'l10n_ve_list_price_usd', 'l10n_ve_list_price_bs',
        'l10n_ve_standard_price_usd', 'l10n_ve_standard_price_bs',
        'company_id', 'company_id.currency_id'
    )
    def _compute_ve_product_prices(self):
        for template in self:
            company = template.company_id or self.env.company
            rate = company.get_current_bcv_rate() if hasattr(company, 'get_current_bcv_rate') else 60.0
            if not rate:
                rate = 60.0

            bs_currency = company.l10n_ve_currency_bs_id if hasattr(company, 'l10n_ve_currency_bs_id') else None
            is_bs = (company.currency_id == bs_currency) if bs_currency else False

            if is_bs:
                template.l10n_ve_list_price_bs = template.list_price
                template.l10n_ve_list_price_usd = round(template.list_price / rate, 2) if rate else 0.0
                template.l10n_ve_standard_price_bs = template.standard_price
                template.l10n_ve_standard_price_usd = round(template.standard_price / rate, 2) if rate else 0.0
            else:
                template.l10n_ve_list_price_usd = template.list_price
                template.l10n_ve_list_price_bs = round(template.list_price * rate, 2)
                template.l10n_ve_standard_price_usd = template.standard_price
                template.l10n_ve_standard_price_bs = round(template.standard_price * rate, 2)

    def _inverse_ve_list_price_usd(self):
        for template in self:
            company = template.company_id or self.env.company
            rate = company.get_current_bcv_rate() if hasattr(company, 'get_current_bcv_rate') else 60.0
            if not rate:
                rate = 60.0
            bs_currency = company.l10n_ve_currency_bs_id if hasattr(company, 'l10n_ve_currency_bs_id') else None
            is_bs = (company.currency_id == bs_currency) if bs_currency else False

            if is_bs:
                template.list_price = round(template.l10n_ve_list_price_usd * rate, 2)
            else:
                template.list_price = template.l10n_ve_list_price_usd

    def _inverse_ve_list_price_bs(self):
        for template in self:
            company = template.company_id or self.env.company
            rate = company.get_current_bcv_rate() if hasattr(company, 'get_current_bcv_rate') else 60.0
            if not rate:
                rate = 60.0
            bs_currency = company.l10n_ve_currency_bs_id if hasattr(company, 'l10n_ve_currency_bs_id') else None
            is_bs = (company.currency_id == bs_currency) if bs_currency else False

            if is_bs:
                template.list_price = template.l10n_ve_list_price_bs
            else:
                template.list_price = round(template.l10n_ve_list_price_bs / rate, 2) if rate else 0.0

    def _inverse_ve_standard_price_usd(self):
        for template in self:
            company = template.company_id or self.env.company
            rate = company.get_current_bcv_rate() if hasattr(company, 'get_current_bcv_rate') else 60.0
            if not rate:
                rate = 60.0
            bs_currency = company.l10n_ve_currency_bs_id if hasattr(company, 'l10n_ve_currency_bs_id') else None
            is_bs = (company.currency_id == bs_currency) if bs_currency else False

            if is_bs:
                template.standard_price = round(template.l10n_ve_standard_price_usd * rate, 2)
            else:
                template.standard_price = template.l10n_ve_standard_price_usd

    def _inverse_ve_standard_price_bs(self):
        for template in self:
            company = template.company_id or self.env.company
            rate = company.get_current_bcv_rate() if hasattr(company, 'get_current_bcv_rate') else 60.0
            if not rate:
                rate = 60.0
            bs_currency = company.l10n_ve_currency_bs_id if hasattr(company, 'l10n_ve_currency_bs_id') else None
            is_bs = (company.currency_id == bs_currency) if bs_currency else False

            if is_bs:
                template.standard_price = template.l10n_ve_standard_price_bs
            else:
                template.standard_price = round(template.l10n_ve_standard_price_bs / rate, 2) if rate else 0.0

    @api.onchange('l10n_ve_list_price_usd')
    def _onchange_ve_list_price_usd(self):
        company = self.company_id or self.env.company
        rate = company.get_current_bcv_rate() if hasattr(company, 'get_current_bcv_rate') else 60.0
        if not rate:
            rate = 60.0
        bs_currency = company.l10n_ve_currency_bs_id if hasattr(company, 'l10n_ve_currency_bs_id') else None
        is_bs = (company.currency_id == bs_currency) if bs_currency else False

        self.l10n_ve_list_price_bs = round(self.l10n_ve_list_price_usd * rate, 2)
        if is_bs:
            self.list_price = round(self.l10n_ve_list_price_usd * rate, 2)
        else:
            self.list_price = self.l10n_ve_list_price_usd

    @api.onchange('l10n_ve_list_price_bs')
    def _onchange_ve_list_price_bs(self):
        company = self.company_id or self.env.company
        rate = company.get_current_bcv_rate() if hasattr(company, 'get_current_bcv_rate') else 60.0
        if not rate:
            rate = 60.0
        bs_currency = company.l10n_ve_currency_bs_id if hasattr(company, 'l10n_ve_currency_bs_id') else None
        is_bs = (company.currency_id == bs_currency) if bs_currency else False

        self.l10n_ve_list_price_usd = round(self.l10n_ve_list_price_bs / rate, 2) if rate else 0.0
        if is_bs:
            self.list_price = self.l10n_ve_list_price_bs
        else:
            self.list_price = round(self.l10n_ve_list_price_bs / rate, 2) if rate else 0.0

    @api.onchange('l10n_ve_standard_price_usd')
    def _onchange_ve_standard_price_usd(self):
        company = self.company_id or self.env.company
        rate = company.get_current_bcv_rate() if hasattr(company, 'get_current_bcv_rate') else 60.0
        if not rate:
            rate = 60.0
        bs_currency = company.l10n_ve_currency_bs_id if hasattr(company, 'l10n_ve_currency_bs_id') else None
        is_bs = (company.currency_id == bs_currency) if bs_currency else False

        self.l10n_ve_standard_price_bs = round(self.l10n_ve_standard_price_usd * rate, 2)
        if is_bs:
            self.standard_price = round(self.l10n_ve_standard_price_usd * rate, 2)
        else:
            self.standard_price = self.l10n_ve_standard_price_usd

    @api.onchange('l10n_ve_standard_price_bs')
    def _onchange_ve_standard_price_bs(self):
        company = self.company_id or self.env.company
        rate = company.get_current_bcv_rate() if hasattr(company, 'get_current_bcv_rate') else 60.0
        if not rate:
            rate = 60.0
        bs_currency = company.l10n_ve_currency_bs_id if hasattr(company, 'l10n_ve_currency_bs_id') else None
        is_bs = (company.currency_id == bs_currency) if bs_currency else False

        self.l10n_ve_standard_price_usd = round(self.l10n_ve_standard_price_bs / rate, 2) if rate else 0.0
        if is_bs:
            self.standard_price = self.l10n_ve_standard_price_bs
        else:
            self.standard_price = round(self.l10n_ve_standard_price_bs / rate, 2) if rate else 0.0

    @api.depends('list_price', 'standard_price', 'l10n_ve_list_price_usd', 'l10n_ve_standard_price_usd')
    def _compute_ve_profit_margin(self):
        for template in self:
            cost = template.l10n_ve_standard_price_usd or template.standard_price
            price = template.l10n_ve_list_price_usd or template.list_price
            if cost > 0:
                margin = ((price - cost) / cost) * 100.0
                template.l10n_ve_profit_margin = round(margin, 2)
            else:
                template.l10n_ve_profit_margin = 0.0

    def _inverse_ve_profit_margin(self):
        for template in self:
            cost_usd = template.l10n_ve_standard_price_usd or template.standard_price
            if cost_usd > 0:
                new_price_usd = round(cost_usd * (1.0 + (template.l10n_ve_profit_margin / 100.0)), 2)
                company = template.company_id or self.env.company
                rate = company.get_current_bcv_rate() if hasattr(company, 'get_current_bcv_rate') else 60.0
                bs_currency = company.l10n_ve_currency_bs_id if hasattr(company, 'l10n_ve_currency_bs_id') else None
                is_bs = (company.currency_id == bs_currency) if bs_currency else False

                if is_bs:
                    template.list_price = round(new_price_usd * rate, 2)
                else:
                    template.list_price = new_price_usd
