# -*- coding: utf-8 -*-
"""
Venezuela360: Wizard — Generación de Libro Fiscal
===================================================
Permite configurar y generar un Libro de Compras o Ventas
para un período seleccionado.
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class FiscalBookWizard(models.TransientModel):
    _name = 'account.fiscal.book.wizard'
    _description = 'Wizard Generación de Libro Fiscal'

    book_type = fields.Selection([
        ('purchase', 'Libro de Compras'),
        ('sale',     'Libro de Ventas'),
    ], string='Tipo de Libro', required=True, default='purchase')

    date_from = fields.Date(
        string='Período Desde',
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string='Período Hasta',
        required=True,
        default=fields.Date.context_today,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    check_existing = fields.Boolean(
        string='Verificar si ya existe un libro para este período',
        default=True,
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_to < rec.date_from:
                raise UserError(_('La fecha "Hasta" no puede ser anterior a la fecha "Desde".'))

    def action_generate_book(self):
        """Crea un nuevo libro fiscal y genera sus líneas automáticamente."""
        self.ensure_one()

        if self.check_existing:
            existing = self.env['account.fiscal.book'].search([
                ('book_type',  '=', self.book_type),
                ('date_from',  '=', self.date_from),
                ('date_to',    '=', self.date_to),
                ('company_id', '=', self.company_id.id),
                ('state',      '!=', 'cancel'),
            ], limit=1)
            if existing:
                raise UserError(_(
                    'Ya existe el libro "%s" para el período %s al %s.\n'
                    'Si deseas regenerarlo, ábrelo y usa el botón "Generar / Actualizar Líneas".'
                ) % (existing.name, self.date_from, self.date_to))

        # Obtener siguiente correlativo
        book_type_labels = {'purchase': 'Compras', 'sale': 'Ventas'}
        seq_code = f'account.fiscal.book.{self.book_type}'
        name = self.env['ir.sequence'].next_by_code(seq_code) or '/'

        book = self.env['account.fiscal.book'].create({
            'name':       name,
            'book_type':  self.book_type,
            'date_from':  self.date_from,
            'date_to':    self.date_to,
            'company_id': self.company_id.id,
        })
        book.action_generate_lines()

        _logger.info(
            'Venezuela360: Libro %s generado con %d líneas.',
            book.name, book.line_count
        )

        # Abrir el libro recién creado
        return {
            'type':      'ir.actions.act_window',
            'res_model': 'account.fiscal.book',
            'res_id':    book.id,
            'view_mode': 'form',
            'target':    'current',
        }
