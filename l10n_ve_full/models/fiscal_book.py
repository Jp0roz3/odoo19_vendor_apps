# -*- coding: utf-8 -*-
"""
Venezuela360: Libros Fiscales (account.fiscal.book)
====================================================
Libro de Compras y Ventas según lo exige el SENIAT de Venezuela.

Permite:
- Consolidar todas las facturas del período por tipo (compras/ventas)
- Mostrar tasa BCV, montos BS/USD, base imponible, IVA y retenciones
- Exportar en PDF, Excel, TXT y XML (formatos SENIAT)

Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountFiscalBook(models.Model):
    _name = 'account.fiscal.book'
    _description = 'Libro Fiscal (Compras/Ventas) — SENIAT Venezuela'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, book_type, id desc'
    _rec_name = 'display_name'

    # ------------------------------------------------------------------
    # Campos principales
    # ------------------------------------------------------------------
    name = fields.Char(
        string='Referencia del Libro',
        required=True,
        copy=False,
        default='/',
        tracking=True,
    )
    book_type = fields.Selection([
        ('purchase', 'Libro de Compras'),
        ('sale',     'Libro de Ventas'),
    ], string='Tipo de Libro', required=True, default='purchase', tracking=True,
    )
    state = fields.Selection([
        ('draft',  'Borrador'),
        ('done',   'Cerrado / Presentado'),
        ('cancel', 'Anulado'),
    ], string='Estado', default='draft', required=True, copy=False, tracking=True,
    )
    date_from = fields.Date(
        string='Período Desde',
        required=True,
        tracking=True,
    )
    date_to = fields.Date(
        string='Período Hasta',
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_bs_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.l10n_ve_currency_bs_id',
        store=True,
    )

    # ------------------------------------------------------------------
    # Líneas del libro
    # ------------------------------------------------------------------
    line_ids = fields.One2many(
        comodel_name='account.fiscal.book.line',
        inverse_name='book_id',
        string='Líneas del Libro',
        copy=False,
    )
    line_count = fields.Integer(
        string='N° de Documentos',
        compute='_compute_totals',
        store=True,
    )

    # ------------------------------------------------------------------
    # Totales del período
    # ------------------------------------------------------------------
    total_base_bs = fields.Monetary(
        string='Total Base Imponible (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_totals',
        store=True,
    )
    total_iva_bs = fields.Monetary(
        string='Total IVA (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_totals',
        store=True,
    )
    total_wh_iva_bs = fields.Monetary(
        string='Total Ret. IVA (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_totals',
        store=True,
    )
    total_wh_islr_bs = fields.Monetary(
        string='Total Ret. ISLR (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_totals',
        store=True,
    )
    total_amount_bs = fields.Monetary(
        string='Total General (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_totals',
        store=True,
    )
    total_base_usd = fields.Float(
        string='Total Base Imponible (USD)',
        digits=(18, 4),
        compute='_compute_totals',
        store=True,
    )
    total_amount_usd = fields.Float(
        string='Total General (USD)',
        digits=(18, 4),
        compute='_compute_totals',
        store=True,
    )

    display_name = fields.Char(
        string='Descripción',
        compute='_compute_display_name_field',
        store=True,
    )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('line_ids.base_bs', 'line_ids.iva_bs', 'line_ids.wh_iva_bs',
                 'line_ids.wh_islr_bs', 'line_ids.total_bs', 'line_ids.total_usd',
                 'line_ids.base_usd')
    def _compute_totals(self):
        for book in self:
            lines = book.line_ids
            book.line_count = len(lines)
            book.total_base_bs = sum(lines.mapped('base_bs'))
            book.total_iva_bs = sum(lines.mapped('iva_bs'))
            book.total_wh_iva_bs = sum(lines.mapped('wh_iva_bs'))
            book.total_wh_islr_bs = sum(lines.mapped('wh_islr_bs'))
            book.total_amount_bs = sum(lines.mapped('total_bs'))
            book.total_base_usd = sum(lines.mapped('base_usd'))
            book.total_amount_usd = sum(lines.mapped('total_usd'))

    @api.depends('book_type', 'date_from', 'date_to')
    def _compute_display_name_field(self):
        type_labels = {'purchase': 'Compras', 'sale': 'Ventas'}
        for book in self:
            tipo = type_labels.get(book.book_type, '?')
            d_from = str(book.date_from) if book.date_from else '?'
            d_to = str(book.date_to) if book.date_to else '?'
            book.display_name = f'Libro de {tipo} | {d_from} al {d_to}'

    # ------------------------------------------------------------------
    # Acción principal: generar líneas del libro
    # ------------------------------------------------------------------
    def action_generate_lines(self):
        """
        Carga automáticamente las facturas del período en las líneas del libro.
        """
        for book in self:
            if book.state != 'draft':
                raise UserError(_('Solo se pueden regenerar libros en estado Borrador.'))

            # Determinar tipos de movimiento según tipo de libro
            if book.book_type == 'purchase':
                move_types = ['in_invoice', 'in_refund']
            else:
                move_types = ['out_invoice', 'out_refund']

            moves = self.env['account.move'].search([
                ('company_id', '=', book.company_id.id),
                ('move_type', 'in', move_types),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', book.date_from),
                ('invoice_date', '<=', book.date_to),
            ], order='invoice_date asc, name asc')

            # Eliminar líneas previas y recrear
            book.line_ids.unlink()
            line_vals = []
            for move in moves:
                line_vals.append({
                    'book_id': book.id,
                    'move_id': move.id,
                    'date': move.invoice_date or move.date,
                    'partner_id': move.partner_id.id,
                    'rif': move.partner_id.l10n_ve_rif or '',
                    'base_bs': move.l10n_ve_amount_untaxed_bs,
                    'iva_bs': move.l10n_ve_amount_tax_bs,
                    'total_bs': move.l10n_ve_amount_total_bs,
                    'base_usd': move.l10n_ve_amount_untaxed_usd,
                    'total_usd': move.l10n_ve_amount_total_usd,
                    'rate': move.l10n_ve_rate,
                    'wh_iva_bs': move.l10n_ve_wh_iva_total_bs,
                    'wh_islr_bs': move.l10n_ve_wh_islr_total_bs,
                    'fiscal_number': move.l10n_ve_fiscal_number or '',
                    'control_number': move.l10n_ve_control_number or '',
                })
            self.env['account.fiscal.book.line'].create(line_vals)

            _logger.info(
                'Venezuela360 FiscalBook: Generadas %d líneas para libro %s.',
                len(line_vals), book.name
            )
        return True

    def action_close_book(self):
        for book in self:
            book.state = 'done'

    def action_cancel(self):
        for book in self:
            book.state = 'cancel'


class AccountFiscalBookLine(models.Model):
    """Línea individual del libro fiscal (1 por factura)."""
    _name = 'account.fiscal.book.line'
    _description = 'Línea de Libro Fiscal — Venezuela'
    _order = 'date asc, id asc'

    book_id = fields.Many2one(
        comodel_name='account.fiscal.book',
        string='Libro Fiscal',
        required=True,
        ondelete='cascade',
        index=True,
    )
    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura',
        required=True,
        ondelete='restrict',
    )
    date = fields.Date(string='Fecha', required=True)
    partner_id = fields.Many2one(comodel_name='res.partner', string='Proveedor / Cliente')
    rif = fields.Char(string='RIF', size=15)
    fiscal_number = fields.Char(string='N° Fiscal', size=20)
    control_number = fields.Char(string='N° Control', size=14)
    rate = fields.Float(string='Tasa BCV (Bs/USD)', digits=(18, 6))

    # ------------------------------------------------------------------
    # Montos (Bs y USD)
    # ------------------------------------------------------------------
    currency_bs_id = fields.Many2one(
        comodel_name='res.currency',
        related='book_id.currency_bs_id',
        store=True,
    )
    base_bs = fields.Monetary(string='Base Imponible (Bs)', currency_field='currency_bs_id')
    iva_bs = fields.Monetary(string='IVA (Bs)', currency_field='currency_bs_id')
    wh_iva_bs = fields.Monetary(string='Ret. IVA (Bs)', currency_field='currency_bs_id')
    wh_islr_bs = fields.Monetary(string='Ret. ISLR (Bs)', currency_field='currency_bs_id')
    total_bs = fields.Monetary(string='Total (Bs)', currency_field='currency_bs_id')
    base_usd = fields.Float(string='Base Imponible (USD)', digits=(18, 4))
    total_usd = fields.Float(string='Total (USD)', digits=(18, 4))
