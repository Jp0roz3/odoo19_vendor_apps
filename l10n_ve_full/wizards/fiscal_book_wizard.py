# -*- coding: utf-8 -*-
"""
Venezuela360: Wizard — Generación e Impresión de Libro Fiscal (PDF / XLSX)
==========================================================================
Modal interactivo para imprimir el Libro Fiscal en formato PDF o Excel (.xlsx).
Coincidencia visual exacta con la Imagen 3 de referencia.

Autor: JeanPerozo / Nubelco
"""
import base64
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class FiscalBookWizard(models.TransientModel):
    _name = 'account.fiscal.book.wizard'
    _description = 'Wizard Libro Fiscal (Impresión PDF / XLSX)'

    book_id = fields.Many2one(
        comodel_name='account.fiscal.book',
        string='Libro Fiscal',
    )
    date_from = fields.Date(
        string='Fecha de Inicio',
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    book_type = fields.Selection([
        ('purchase', 'Compra'),
        ('sale',     'Venta'),
    ], string='Tipo', required=True, default='purchase')

    date_to = fields.Date(
        string='Fecha Fin',
        required=True,
        default=fields.Date.context_today,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )

    xlsx_file = fields.Binary(
        string='Archivo Excel',
        readonly=True,
    )
    xlsx_filename = fields.Char(
        string='Nombre del Archivo',
        readonly=True,
    )

    def _get_or_create_book(self):
        """Busca o crea el libro fiscal correspondiente al rango seleccionado."""
        if self.book_id:
            if not self.book_id.line_ids:
                self.book_id.action_generate_lines()
            return self.book_id

        book = self.env['account.fiscal.book'].search([
            ('book_type', '=', self.book_type),
            ('date_from', '=', self.date_from),
            ('date_to', '=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('state', '!=', 'cancel'),
        ], limit=1)

        if not book:
            bname = f"{'COMPRA' if self.book_type == 'purchase' else 'VENTA'} {self.date_from.strftime('%d/%m/%Y')} AL {self.date_to.strftime('%d/%m/%Y')}"
            book = self.env['account.fiscal.book'].create({
                'name': bname,
                'book_type': self.book_type,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'company_id': self.company_id.id,
            })
            book.action_generate_lines()
        elif not book.line_ids:
            book.action_generate_lines()

        return book

    def action_print_pdf(self):
        """Imprime y descarga el reporte PDF oficial del Libro Fiscal."""
        self.ensure_one()
        book = self._get_or_create_book()
        return self.env.ref('l10n_ve_full.action_report_fiscal_book').report_action(book)

    def action_print_xlsx(self):
        """Genera y descarga el archivo Excel .xlsx del Libro Fiscal."""
        self.ensure_one()
        book = self._get_or_create_book()
        xlsx_bytes = book.get_fiscal_book_xlsx_bytes()
        
        btype_name = "Compras" if self.book_type == 'purchase' else "Ventas"
        filename = f"Libro_de_{btype_name}_{self.date_from.strftime('%Y%m%d')}_{self.date_to.strftime('%Y%m%d')}.xlsx"
        
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(xlsx_bytes),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self.id,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
