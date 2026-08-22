# -*- coding: utf-8 -*-
"""
Venezuela360: Libros Fiscales de Compra y Venta (SENIAT)
=========================================================
Estructura oficial y reglamentaria para Libros Fiscales de Compra y Venta:
- Generación de líneas a partir de facturas y retenciones publicadas.
- Soporte para exportación en PDF de alta fidelidad y Excel (.xlsx) nativo.
- Cumplimiento estricto con las Providencias Administrativas del SENIAT.

Autor: JeanPerozo / Nubelco
"""
import io
import base64
import zipfile
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountFiscalBook(models.Model):
    _name = 'account.fiscal.book'
    _description = 'Libro Fiscal SENIAT (Compras / Ventas)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, book_type, id desc'
    _rec_name = 'display_name'

    name = fields.Char(
        string='Descripción',
        required=True,
        copy=False,
        default=lambda self: _('Nuevo Libro Fiscal'),
        tracking=True,
    )
    book_type = fields.Selection([
        ('purchase', 'Libro de Compra'),
        ('sale',     'Libro de Venta'),
    ], string='Tipo de libro', required=True, default='purchase', tracking=True)

    period_type = fields.Selection([
        ('custom',     'Personalizado'),
        ('month',      'Mensual'),
        ('fortnight',  'Quincenal'),
    ], string='Período', default='custom', required=True)

    state = fields.Selection([
        ('draft',    'Preparándose'),
        ('approved', 'Aprobado por el Responsable'),
        ('done',     'Enviado al Seniat'),
        ('cancel',   'Anulado'),
    ], string='Estado', default='draft', required=True, copy=False, tracking=True)

    date_from = fields.Date(
        string='Fecha de Inicio',
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
        tracking=True,
    )
    date_to = fields.Date(
        string='Fecha Fin',
        required=True,
        default=fields.Date.context_today,
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
        string='Moneda Bs',
        related='company_id.l10n_ve_currency_bs_id',
        store=True,
    )
    journal_ids = fields.Many2many(
        comodel_name='account.journal',
        string='Diarios',
        domain="[('type', 'in', ['sale', 'purchase']), ('company_id', '=', company_id)]",
    )

    # ------------------------------------------------------------------
    # Líneas y pestañas del libro fiscal
    # ------------------------------------------------------------------
    line_ids = fields.One2many(
        comodel_name='account.fiscal.book.line',
        inverse_name='book_id',
        string='Líneas de Libro Fiscal',
        copy=False,
    )
    line_count = fields.Integer(
        string='N° Documentos',
        compute='_compute_totals',
        store=True,
    )

    # Totales monetarios en Bolívares
    total_amount_bs = fields.Monetary(
        string='Total con IVA (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_totals',
        store=True,
    )
    total_sdcf_bs = fields.Monetary(
        string='Total SDCF / No Sujeto (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_totals',
        store=True,
    )
    total_exempt_bs = fields.Monetary(
        string='Total Exento (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_totals',
        store=True,
    )
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
        string='Total IVA Retenido (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_totals',
        store=True,
    )
    total_igtf_bs = fields.Monetary(
        string='Total IGTF 3% (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_totals',
        store=True,
    )

    @api.depends('name', 'book_type', 'date_from', 'date_to')
    def _compute_display_name(self):
        for book in self:
            btype = 'COMPRA' if book.book_type == 'purchase' else 'VENTA'
            book.display_name = f"LIBRO FISCAL DE {btype} ({book.name or ''})"

    @api.depends('line_ids', 'line_ids.total_amount_bs', 'line_ids.base_general_bs',
                 'line_ids.iva_general_bs', 'line_ids.wh_amount_bs', 'line_ids.exempt_bs', 'line_ids.sdcf_bs')
    def _compute_totals(self):
        for book in self:
            book.line_count = len(book.line_ids)
            book.total_amount_bs = sum(book.line_ids.mapped('total_amount_bs'))
            book.total_sdcf_bs = sum(book.line_ids.mapped('sdcf_bs'))
            book.total_exempt_bs = sum(book.line_ids.mapped('exempt_bs'))
            book.total_base_bs = sum(book.line_ids.mapped('base_general_bs')) + sum(book.line_ids.mapped('base_reduced_bs')) + sum(book.line_ids.mapped('base_additional_bs'))
            book.total_iva_bs = sum(book.line_ids.mapped('iva_general_bs')) + sum(book.line_ids.mapped('iva_reduced_bs')) + sum(book.line_ids.mapped('iva_additional_bs'))
            book.total_wh_iva_bs = sum(book.line_ids.mapped('wh_amount_bs'))
            book.total_igtf_bs = sum(book.line_ids.mapped('igtf_amount_bs'))

    # ------------------------------------------------------------------
    # Acciones principales del formulario
    # ------------------------------------------------------------------
    def action_generate_lines(self):
        """Genera o actualiza las líneas del libro fiscal a partir de facturas y notas registradas."""
        self.ensure_one()
        self.line_ids.unlink()

        move_types = ('in_invoice', 'in_refund') if self.book_type == 'purchase' else ('out_invoice', 'out_refund')
        domain = [
            ('move_type', 'in', move_types),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]
        if self.journal_ids:
            domain.append(('journal_id', 'in', self.journal_ids.ids))

        moves = self.env['account.move'].search(domain, order='invoice_date asc, l10n_ve_control_number asc, name asc')

        line_vals = []
        op_no = 1

        for move in moves:
            partner = move.partner_id
            rif = getattr(partner, 'l10n_ve_rif', False) or partner.vat or ''
            
            # Clasificación fiscal del proveedor / cliente
            ptype = 'pjdo'
            if partner.company_type == 'person':
                ptype = 'pnre'
            elif rif.upper().startswith('E') or rif.upper().startswith('J-N'):
                ptype = 'pjnd'

            # Tipo de documento
            if move.move_type in ('out_invoice', 'in_invoice'):
                doc_type = 'FACT'
                trans_type = '01-REG'
            elif move.move_type in ('out_refund', 'in_refund'):
                doc_type = 'NC'
                trans_type = '02-COMP'
            else:
                doc_type = 'ND'
                trans_type = '01-REG'

            # Tasa del documento
            rate = move.l10n_ve_rate_applied or move.l10n_ve_rate or move.company_id.get_current_bcv_rate() or 779.9522
            is_bs = move.currency_id and move.currency_id.name in ['VES', 'VEF', 'VEB']
            sign = -1.0 if move.move_type in ('out_refund', 'in_refund') else 1.0

            # Desglose de importes
            total_bs = (move.amount_total if is_bs else round(move.amount_total * rate, 2)) * sign
            tax_bs = (move.amount_tax if is_bs else round(move.amount_tax * rate, 2)) * sign
            untaxed_bs = (move.amount_untaxed if is_bs else round(move.amount_untaxed * rate, 2)) * sign

            exempt_bs = 0.0
            base_gen_bs = 0.0
            iva_gen_bs = 0.0
            base_red_bs = 0.0
            iva_red_bs = 0.0
            base_add_bs = 0.0
            iva_add_bs = 0.0

            # Analizar líneas de impuestos
            for line in move.invoice_line_ids:
                l_untaxed_bs = (line.price_subtotal if is_bs else round(line.price_subtotal * rate, 2)) * sign
                taxes = line.tax_ids
                if not taxes or any(t.amount == 0 for t in taxes):
                    exempt_bs += l_untaxed_bs
                else:
                    tax = taxes[0]
                    if abs(tax.amount - 16.0) < 0.1:
                        base_gen_bs += l_untaxed_bs
                        iva_gen_bs += round(l_untaxed_bs * 0.16, 2)
                    elif abs(tax.amount - 8.0) < 0.1:
                        base_red_bs += l_untaxed_bs
                        iva_red_bs += round(l_untaxed_bs * 0.08, 2)
                    elif abs(tax.amount - 31.0) < 0.1:
                        base_add_bs += l_untaxed_bs
                        iva_add_bs += round(l_untaxed_bs * 0.31, 2)
                    else:
                        base_gen_bs += l_untaxed_bs
                        iva_gen_bs += round(l_untaxed_bs * (tax.amount / 100.0), 2)

            if not base_gen_bs and untaxed_bs and not exempt_bs:
                base_gen_bs = untaxed_bs
                iva_gen_bs = tax_bs

            # Retención de IVA
            wh_amount_bs = 0.0
            wh_voucher = ''
            if hasattr(move, 'l10n_ve_wh_iva_ids') and move.l10n_ve_wh_iva_ids:
                wh_rec = move.l10n_ve_wh_iva_ids[0]
                wh_amount_bs = wh_rec.amount_bs or (wh_rec.amount * rate if not is_bs else wh_rec.amount)
                wh_voucher = wh_rec.name or ''

            line_vals.append({
                'book_id': self.id,
                'line_no': op_no,
                'doc_type': doc_type,
                'date': move.invoice_date or move.date,
                'control_number': move.l10n_ve_control_number or '',
                'invoice_number': move.name or '',
                'affected_invoice': move.reversed_entry_id.name if move.reversed_entry_id else '',
                'partner_id': partner.id,
                'partner_name': partner.name or '',
                'rif': rif,
                'partner_type': ptype,
                'transaction_type': trans_type,
                'total_amount_bs': total_bs,
                'sdcf_bs': 0.0,
                'exempt_bs': exempt_bs,
                'base_general_bs': base_gen_bs,
                'aliquot_general': 16.0 if base_gen_bs else 0.0,
                'iva_general_bs': iva_gen_bs,
                'base_reduced_bs': base_red_bs,
                'aliquot_reduced': 8.0 if base_red_bs else 0.0,
                'iva_reduced_bs': iva_red_bs,
                'base_additional_bs': base_add_bs,
                'aliquot_additional': 31.0 if base_add_bs else 0.0,
                'iva_additional_bs': iva_add_bs,
                'wh_voucher_number': wh_voucher,
                'wh_amount_bs': wh_amount_bs,
                'move_id': move.id,
            })
            op_no += 1

        if line_vals:
            self.env['account.fiscal.book.line'].create(line_vals)

        return True

    def action_clear_book(self):
        """Borra todas las líneas generadas."""
        self.ensure_one()
        self.line_ids.unlink()
        return True

    def action_print_book_wizard(self):
        """Abre el modal interactivo de impresión (PDF / XLSX) idéntico a la Imagen 3."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Libro Fiscal'),
            'res_model': 'account.fiscal.book.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_book_id': self.id,
                'default_book_type': self.book_type,
                'default_date_from': self.date_from,
                'default_date_to': self.date_to,
                'default_company_id': self.company_id.id,
            },
        }

    def action_confirm(self):
        """Confirma el libro fiscal."""
        self.ensure_one()
        if not self.line_ids:
            self.action_generate_lines()
        self.state = 'approved'

    def action_send_seniat(self):
        """Marca el libro como enviado al SENIAT."""
        self.ensure_one()
        self.state = 'done'

    def action_set_draft(self):
        """Regresa el libro a estado Preparándose."""
        self.ensure_one()
        self.state = 'draft'

    def action_print_summary(self):
        """Abre el asistente de impresión para formato resumido."""
        return self.action_print_book_wizard()

    # ------------------------------------------------------------------
    # Generador de archivo Excel (.xlsx) idéntico a la muestra del cliente
    # ------------------------------------------------------------------
    def get_fiscal_book_xlsx_bytes(self):
        """Genera el contenido binario del archivo Excel .xlsx del libro fiscal."""
        self.ensure_one()
        company = self.company_id
        rif = getattr(company, 'l10n_ve_rif', False) or company.vat or 'J-00000000-0'
        is_purchase = (self.book_type == 'purchase')

        title = f"{company.name or 'EMPRESA'} - RIF: {rif}"
        book_title = "Libro de Compras" if is_purchase else "Libro de Venta"
        period_str = f"Desde: {self.date_from.strftime('%d/%m/%Y')}   Hasta: {self.date_to.strftime('%d/%m/%Y')}"

        if is_purchase:
            headers = [
                "Nro. Op", "Fecha Emisión Doc.", "Nro. de RIF", "Nombre / Razón Social", "Tipo Prov.",
                "Nro. de Factura", "Nro. de Control", "Nro. Nota de Crédito", "Nro. Nota de Débito",
                "Tipo de Trans", "Nro. Factura Afectada", "Total Compras con IVA", "Compras sin Derecho a Crédito",
                "Base Imponible Alícuota General", "% Alícuota General", "Impuesto (I.V.A) Alícuota General",
                "Base Imponible Alícuota Reducida", "% Alícuota Reducida", "Impuesto (I.V.A) Alícuota Reducida",
                "Base Imponible Alícuota Adicional", "% Alícuota Adicional", "Impuesto (I.V.A) Alícuota Adicional",
                "Nro. Planilla Importación", "Nro. Expediente Importación", "Nro. de Comprobante", "IVA Ret (Vend.)"
            ]
        else:
            headers = [
                "Nro. Op", "Fecha Documento", "RIF", "Nombre / Razón Social", "Tipo Prov.",
                "Nro. De Factura", "Nro. De Control", "Nro. Factura Afectada", "Nro. Nota de Débito",
                "Nro. Nota de Crédito", "Tipo de Trans.", "Ventas Incluyendo IVA", "Ventas sin Derecho a Débito",
                "Base Imponible Alícuota General", "% Alícuota General", "Impuesto (I.V.A) Alícuota General",
                "Base Imponible Alícuota Reducida", "% Alícuota Reducida", "Impuesto (I.V.A) Alícuota Reducida",
                "Base Imponible Alícuota Adicional", "% Alícuota Adicional", "Impuesto (I.V.A) Alícuota Adicional",
                "Nro. de Comprobante", "IVA Retenido"
            ]

        data_rows = []
        for l in self.line_ids:
            if is_purchase:
                data_rows.append([
                    l.line_no,
                    l.date.strftime('%d/%m/%Y') if l.date else '',
                    l.rif or '',
                    l.partner_name or '',
                    l.partner_type or 'pjdo',
                    l.invoice_number if l.doc_type == 'FACT' else '',
                    l.control_number or '',
                    l.invoice_number if l.doc_type == 'NC' else '',
                    l.invoice_number if l.doc_type == 'ND' else '',
                    l.transaction_type or '01-REG',
                    l.affected_invoice or '',
                    round(l.total_amount_bs, 2),
                    round(l.exempt_bs + l.sdcf_bs, 2),
                    round(l.base_general_bs, 2),
                    16 if l.base_general_bs else 0,
                    round(l.iva_general_bs, 2),
                    round(l.base_reduced_bs, 2),
                    8 if l.base_reduced_bs else 0,
                    round(l.iva_reduced_bs, 2),
                    round(l.base_additional_bs, 2),
                    31 if l.base_additional_bs else 0,
                    round(l.iva_additional_bs, 2),
                    l.import_form_no or '',
                    l.import_file_no or '',
                    l.wh_voucher_number or '',
                    round(l.wh_amount_bs, 2),
                ])
            else:
                data_rows.append([
                    l.line_no,
                    l.date.strftime('%d/%m/%Y') if l.date else '',
                    l.rif or '',
                    l.partner_name or '',
                    l.partner_type or 'pjdo',
                    l.invoice_number if l.doc_type == 'FACT' else '',
                    l.control_number or '',
                    l.affected_invoice or '',
                    l.invoice_number if l.doc_type == 'ND' else '',
                    l.invoice_number if l.doc_type == 'NC' else '',
                    l.transaction_type or '01-REG',
                    round(l.total_amount_bs, 2),
                    round(l.exempt_bs + l.sdcf_bs, 2),
                    round(l.base_general_bs, 2),
                    16 if l.base_general_bs else 0,
                    round(l.iva_general_bs, 2),
                    round(l.base_reduced_bs, 2),
                    8 if l.base_reduced_bs else 0,
                    round(l.iva_reduced_bs, 2),
                    round(l.base_additional_bs, 2),
                    31 if l.base_additional_bs else 0,
                    round(l.iva_additional_bs, 2),
                    l.wh_voucher_number or '',
                    round(l.wh_amount_bs, 2),
                ])

        # Construir paquete .xlsx nativo
        output = io.BytesIO()
        unique_strings = []
        string_map = {}

        def get_string_id(s):
            s = str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if s not in string_map:
                string_map[s] = len(unique_strings)
                unique_strings.append(s)
            return string_map[s]

        sheet_data_xml = []
        sheet_data_xml.append(f'<row r="1"><c r="A1" t="s"><v>{get_string_id(title)}</v></c></row>')
        sheet_data_xml.append(f'<row r="2"><c r="A2" t="s"><v>{get_string_id(book_title)}</v></c><c r="C2" t="s"><v>{get_string_id(period_str)}</v></c></row>')

        # Fila de Encabezados
        header_cells = []
        for col_idx, h in enumerate(headers, 1):
            col_letter = chr(64 + col_idx) if col_idx <= 26 else f"A{chr(64 + col_idx - 26)}"
            header_cells.append(f'<c r="{col_letter}4" t="s"><v>{get_string_id(h)}</v></c>')
        sheet_data_xml.append(f'<row r="4">{"".join(header_cells)}</row>')

        # Filas de Datos
        for r_idx, row in enumerate(data_rows, 5):
            row_cells = []
            for col_idx, val in enumerate(row, 1):
                col_letter = chr(64 + col_idx) if col_idx <= 26 else f"A{chr(64 + col_idx - 26)}"
                if isinstance(val, (int, float)):
                    row_cells.append(f'<c r="{col_letter}{r_idx}"><v>{val}</v></c>')
                else:
                    row_cells.append(f'<c r="{col_letter}{r_idx}" t="s"><v>{get_string_id(val)}</v></c>')
            sheet_data_xml.append(f'<row r="{r_idx}">{"".join(row_cells)}</row>')

        shared_strings_xml = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(unique_strings)}" uniqueCount="{len(unique_strings)}">' + "".join([f'<si><t>{s}</t></si>' for s in unique_strings]) + '</sst>'
        sheet_xml = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_data_xml)}</sheetData></worksheet>'

        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/></Types>')
            z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
            z.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/></Relationships>')
            z.writestr('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Libro Fiscal" sheetId="1" r:id="rId1"/></sheets></workbook>')
            z.writestr('xl/worksheets/sheet1.xml', sheet_xml)
            z.writestr('xl/sharedStrings.xml', shared_strings_xml)

        output.seek(0)
        return output.read()


class AccountFiscalBookLine(models.Model):
    _name = 'account.fiscal.book.line'
    _description = 'Línea de Libro Fiscal SENIAT'
    _order = 'line_no asc, date asc, id asc'

    book_id = fields.Many2one('account.fiscal.book', string='Libro Fiscal', ondelete='cascade', required=True)
    line_no = fields.Integer(string='Line', default=1)
    doc_type = fields.Char(string='Tipo de Doc', size=10, default='FACT')
    date = fields.Date(string='Fecha de Emisión')
    control_number = fields.Char(string='Nro de Control')
    invoice_number = fields.Char(string='Nro de Factura')
    affected_invoice = fields.Char(string='Factura Afectada')
    z_report_number = fields.Char(string='Nro Reporte Z')
    last_invoice_number = fields.Char(string='Nro Última Factura')
    imex_date = fields.Date(string='Fecha Imex')
    import_form_no = fields.Char(string='Nro Planilla Imex')
    import_file_no = fields.Char(string='Nro Exp Imex')
    partner_id = fields.Many2one('res.partner', string='Contacto')
    partner_name = fields.Char(string='Nombre de la Razón Social')
    rif = fields.Char(string='Nro. RIF')
    partner_type = fields.Char(string='Tipo de Persona', default='pjdo')
    transaction_type = fields.Char(string='Tipo de Trans', default='01-REG')

    # Columnas de importes en Bolívares
    currency_bs_id = fields.Many2one('res.currency', related='book_id.currency_bs_id')
    total_amount_bs = fields.Monetary(string='Total con IVA', currency_field='currency_bs_id')
    sdcf_bs = fields.Monetary(string='SDCF', currency_field='currency_bs_id', default=0.0)
    exempt_bs = fields.Monetary(string='Exento', currency_field='currency_bs_id', default=0.0)
    base_general_bs = fields.Monetary(string='Base General (16%)', currency_field='currency_bs_id', default=0.0)
    aliquot_general = fields.Float(string='% Alic. General', default=16.0)
    iva_general_bs = fields.Monetary(string='IVA General (16%)', currency_field='currency_bs_id', default=0.0)
    base_reduced_bs = fields.Monetary(string='Base Reducida (8%)', currency_field='currency_bs_id', default=0.0)
    aliquot_reduced = fields.Float(string='% Alic. Reducida', default=8.0)
    iva_reduced_bs = fields.Monetary(string='IVA Reducida (8%)', currency_field='currency_bs_id', default=0.0)
    base_additional_bs = fields.Monetary(string='Base Adicional (31%)', currency_field='currency_bs_id', default=0.0)
    aliquot_additional = fields.Float(string='% Alic. Adicional', default=31.0)
    iva_additional_bs = fields.Monetary(string='IVA Adicional (31%)', currency_field='currency_bs_id', default=0.0)
    wh_voucher_number = fields.Char(string='Nro. Comprobante')
    wh_amount_bs = fields.Monetary(string='IVA Retenido', currency_field='currency_bs_id', default=0.0)
    igtf_amount_bs = fields.Monetary(string='IGTF 3%', currency_field='currency_bs_id', default=0.0)
    move_id = fields.Many2one('account.move', string='Factura')
