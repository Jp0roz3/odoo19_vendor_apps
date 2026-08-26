# -*- coding: utf-8 -*-
"""
Venezuela360: Retención de IVA (account.wh.iva)
=================================================
Modelo principal de retención de IVA según la normativa del SENIAT Venezuela.

Soporta:
- 75% para contribuyentes ordinarios
- 100% para contribuyentes especiales
- Tasas personalizables por documento
- Comprobante PDF numerado
- Asiento contable automático
- Doble moneda BS/USD con tasa histórica BCV
- Trazabilidad completa con factura origen

Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountWhIva(models.Model):
    """
    Comprobante de Retención de IVA.
    Cada registro representa un comprobante de retención emitido
    (o recibido) vinculado a una factura de proveedor o cliente.
    """
    _name = 'account.wh.iva'
    _description = 'Retención de IVA — Venezuela'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'
    _rec_name = 'name'

    # ------------------------------------------------------------------
    # Campos principales
    # ------------------------------------------------------------------
    name = fields.Char(
        string='Número de Comprobante',
        required=True,
        copy=False,
        default='/',
        tracking=True,
        help='Correlativo del comprobante de retención IVA. Ej: RET-IVA/2024/00001.',
    )
    state = fields.Selection([
        ('draft',     'Borrador'),
        ('confirmed', 'Confirmado'),
        ('posted',    'Contabilizado'),
        ('cancel',    'Cancelado'),
    ], string='Estado', default='draft', required=True,
       copy=False, tracking=True,
    )
    wh_type = fields.Selection([
        ('customer', 'Retención a Cliente (IVA Cobrado)'),
        ('supplier', 'Retención a Proveedor (IVA Pagado)'),
    ], string='Tipo de Retención', required=True, default='supplier',
       help='Indica si se retiene IVA cobrado (cliente) o pagado (proveedor).',
    )

    # ------------------------------------------------------------------
    # Relación con factura
    # ------------------------------------------------------------------
    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura Origen',
        required=True,
        ondelete='restrict',
        index=True,
        domain="[('move_type', 'in', ['in_invoice','in_refund','out_invoice','out_refund'])]",
        tracking=True,
    )
    move_type = fields.Selection(
        related='move_id.move_type',
        store=True,
        string='Tipo de Factura',
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Proveedor / Cliente',
        related='move_id.partner_id',
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        related='move_id.company_id',
        store=True,
    )

    # ------------------------------------------------------------------
    # Fechas
    # ------------------------------------------------------------------
    date = fields.Date(
        string='Fecha de Retención',
        required=True,
        default=fields.Date.context_today,
        copy=False,
        tracking=True,
    )
    invoice_date = fields.Date(
        string='Fecha de Factura',
        related='move_id.invoice_date',
        store=True,
    )

    # ------------------------------------------------------------------
    # Tasa BCV
    # ------------------------------------------------------------------
    exchange_rate_id = fields.Many2one(
        comodel_name='l10n_ve.exchange.rate',
        string='Tasa BCV',
        related='move_id.l10n_ve_exchange_rate_id',
        store=True,
        help='Tasa BCV histórica heredada de la factura origen.',
    )
    rate = fields.Float(
        string='Tasa Bs/USD',
        related='move_id.l10n_ve_rate',
        store=True,
        digits=(18, 6),
    )

    # ------------------------------------------------------------------
    # Montos de la factura (base de cálculo)
    # ------------------------------------------------------------------
    invoice_amount_untaxed_bs = fields.Monetary(
        string='Base Imponible Factura (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_invoice_amounts',
        store=True,
    )
    invoice_amount_tax_bs = fields.Monetary(
        string='IVA Factura (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_invoice_amounts',
        store=True,
        help='Monto de IVA sobre el que se calcula la retención.',
    )
    invoice_amount_total_bs = fields.Monetary(
        string='Total Factura (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_invoice_amounts',
        store=True,
    )

    # ------------------------------------------------------------------
    # Porcentaje y monto de retención
    # ------------------------------------------------------------------
    wh_rate = fields.Float(
        string='% Retención sobre IVA',
        required=True,
        digits=(5, 2),
        default=75.0,
        help=(
            'Porcentaje de retención aplicado sobre el IVA de la factura. '
            '75% para contribuyentes ordinarios, 100% para especiales.'
        ),
    )
    amount_bs = fields.Monetary(
        string='Monto Retenido (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_wh_amount',
        store=True,
        copy=False,
        help='Monto de IVA efectivamente retenido en Bolívares.',
    )
    amount_usd = fields.Float(
        string='Monto Retenido (USD)',
        digits=(18, 4),
        compute='_compute_wh_amount',
        store=True,
        copy=False,
    )

    # ------------------------------------------------------------------
    # Monedas
    # ------------------------------------------------------------------
    currency_bs_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda Bs',
        related='company_id.l10n_ve_currency_bs_id',
        store=True,
    )

    # ------------------------------------------------------------------
    # Asiento contable generado
    # ------------------------------------------------------------------
    journal_entry_id = fields.Many2one(
        comodel_name='account.move',
        string='Asiento Contable',
        copy=False,
        readonly=True,
        help='Asiento generado al contabilizar esta retención.',
    )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('move_id.l10n_ve_amount_untaxed_bs', 'move_id.l10n_ve_amount_tax_bs',
                 'move_id.l10n_ve_amount_total_bs')
    def _compute_invoice_amounts(self):
        for rec in self:
            rec.invoice_amount_untaxed_bs = rec.move_id.l10n_ve_amount_untaxed_bs
            rec.invoice_amount_tax_bs = rec.move_id.l10n_ve_amount_tax_bs
            rec.invoice_amount_total_bs = rec.move_id.l10n_ve_amount_total_bs

    @api.depends('invoice_amount_tax_bs', 'wh_rate', 'rate', 'move_id.amount_tax', 'move_id.currency_id')
    def _compute_wh_amount(self):
        for rec in self:
            doc_rate = rec.move_id.l10n_ve_rate or rec.move_id.l10n_ve_rate_applied or rec.rate or (rec.company_id.get_current_bcv_rate() if hasattr(rec.company_id, 'get_current_bcv_rate') else 779.9522) or 779.9522
            rec.rate = doc_rate
            rate_pct = rec.wh_rate or 0.0

            is_inv_bs = rec.move_id.currency_id and rec.move_id.currency_id.name in ['VES', 'VEF', 'VEB']
            if is_inv_bs:
                tax_bs = rec.invoice_amount_tax_bs or rec.move_id.amount_tax or 0.0
                rec.amount_bs = round(tax_bs * rate_pct / 100.0, 2)
                rec.amount_usd = round(rec.amount_bs / doc_rate, 2) if doc_rate else 0.0
            else:
                tax_usd = rec.move_id.amount_tax or 0.0
                rec.amount_usd = round(tax_usd * rate_pct / 100.0, 2)
                rec.amount_bs = round(rec.amount_usd * doc_rate, 2)

    # ------------------------------------------------------------------
    # Onchange: sugerir % retención según tipo de contribuyente
    # ------------------------------------------------------------------
    @api.onchange('move_id')
    def _onchange_move_id(self):
        if self.move_id and self.move_id.partner_id:
            self.wh_rate = self.move_id.partner_id.get_wh_iva_rate(
                company=self.move_id.company_id
            )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains('wh_rate')
    def _check_wh_rate(self):
        for rec in self:
            if not (0.0 <= rec.wh_rate <= 100.0):
                raise ValidationError(
                    _('El porcentaje de retención de IVA debe estar entre 0% y 100%.')
                )

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_confirm(self):
        """Confirmar el comprobante de retención."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Solo se pueden confirmar retenciones en borrador.'))
            if rec.name == '/':
                sequence = rec.company_id.l10n_ve_wh_iva_sequence_id
                if sequence:
                    rec.name = sequence.next_by_id()
                else:
                    rec.name = self.env['ir.sequence'].next_by_code('account.wh.iva') or '/'
            rec.state = 'confirmed'
        return True

    def action_post(self):
        """Contabilizar la retención: genera el asiento contable."""
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError(_('Debe confirmar la retención antes de contabilizarla.'))
            if not rec.company_id.l10n_ve_wh_iva_journal_id:
                raise UserError(
                    _('Configure el "Diario Retenciones IVA" en la configuración de la compañía.')
                )
            if not rec.company_id.l10n_ve_wh_iva_account_id:
                raise UserError(
                    _('Configure la "Cuenta IVA Retenido" en la configuración de la compañía.')
                )
            entry = rec._create_journal_entry()
            rec.journal_entry_id = entry.id
            rec.state = 'posted'
            _logger.info('Venezuela360 IVA: Retención %s contabilizada → Asiento %s', rec.name, entry.name)
        return True

    def _create_journal_entry(self):
        """
        Genera el asiento contable de la retención de IVA.
        Débito: Cuenta IVA por Pagar / Débito Fiscal
        Crédito: Cuenta IVA Retenido (pasivo frente al proveedor o activo si es cliente)
        """
        self.ensure_one()
        journal = self.company_id.l10n_ve_wh_iva_journal_id
        account_wh = self.company_id.l10n_ve_wh_iva_account_id

        # Buscar la cuenta de IVA de la factura
        tax_lines = self.move_id.line_ids.filtered(
            lambda l: l.tax_line_id and not l.reconciled
        )
        iva_account = tax_lines[:1].account_id if tax_lines else account_wh

        comp_currency = self.company_id.currency_id
        comp_is_usd = bool(comp_currency and comp_currency.name in ['USD', '$'])
        doc_rate = self.move_id.l10n_ve_rate or self.move_id.l10n_ve_rate_applied or self.rate or (self.company_id.get_current_bcv_rate() if hasattr(self.company_id, 'get_current_bcv_rate') else 779.9522) or 779.9522

        if comp_is_usd:
            # En base USD: debit y credit son en USD
            debit_usd = round(self.amount_usd or (self.amount_bs / doc_rate if doc_rate else 0.0), 2)
            credit_usd = debit_usd
        else:
            # En base VES: debit y credit son en Bs
            debit_usd = self.amount_bs
            credit_usd = self.amount_bs

        move_vals = {
            'move_type': 'entry',
            'date': self.date,
            'journal_id': journal.id,
            'ref': f'Ret. IVA {self.name} — Factura {self.move_id.name}',
            'company_id': self.company_id.id,
            'l10n_ve_rate': doc_rate,
            'l10n_ve_rate_applied': doc_rate,
            'l10n_ve_rate_type': self.move_id.l10n_ve_rate_type or 'bcv',
            'line_ids': [
                # Débito: reduce el IVA a pagar en la cuenta de IVA de la factura
                (0, 0, {
                    'account_id': iva_account.id,
                    'name': f'Ret. IVA {self.wh_rate:.0f}% — {self.partner_id.name}',
                    'debit': debit_usd,
                    'credit': 0.0,
                    'partner_id': self.partner_id.id,
                }),
                # Crédito: cuenta de IVA retenido (pasivo frente al contribuyente)
                (0, 0, {
                    'account_id': account_wh.id,
                    'name': f'IVA Retenido — {self.name}',
                    'debit': 0.0,
                    'credit': credit_usd,
                    'partner_id': self.partner_id.id,
                }),
            ],
        }
        entry = self.env['account.move'].create(move_vals)
        entry.action_post()
        return entry

    def action_cancel(self):
        """Cancelar la retención y revertir el asiento si existe."""
        for rec in self:
            if rec.state == 'posted' and rec.journal_entry_id:
                rec.journal_entry_id.button_cancel()
            rec.state = 'cancel'

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state != 'cancel':
                raise UserError(_('Solo se pueden reiniciar retenciones canceladas.'))
            rec.state = 'draft'
