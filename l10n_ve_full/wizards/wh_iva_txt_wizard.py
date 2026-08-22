# -*- coding: utf-8 -*-
"""
Venezuela360: Generador de Archivo TXT de Retenciones de IVA (SENIAT)
=====================================================================
Genera el archivo plano (.txt) con la estructura oficial de 14 campos
exigida por el portal fiscal del SENIAT para la declaración de retenciones de IVA:

Campos del archivo plano (separados por tabulación o estructura posicional):
 1. RIF del Agente de Retención (ej: J123456789)
 2. Período Impositivo (AAAAMM)
 3. Fecha de la Factura (AAAA-MM-DD)
 4. Tipo de Operación ('C' = Compras)
 5. Tipo de Documento ('01' = Factura, '02' = Débito, '03' = Crédito)
 6. RIF del Proveedor Retenido
 7. Número de la Factura
 8. Número de Control de la Factura
 9. Monto Total de la Factura (con IVA)
10. Base Imponible
11. Monto del IVA Retenido
12. Número del Documento Afectado (para NC / ND)
13. Número de Comprobante de Retención (AAAAMMSSSSSSSS)
14. Monto Exento de la Factura
15. Alícuota de IVA aplicada (ej: 16.00)
16. Número de Expediente (opcional o '0')

Autor: JeanPerozo / Nubelco
"""
import base64
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class WhIvaTxtWizard(models.TransientModel):
    _name = 'l10n_ve.wh.iva.txt.wizard'
    _description = 'Generador de Archivo TXT de Retenciones IVA SENIAT'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )
    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        default=fields.Date.context_today,
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        default=fields.Date.context_today,
    )
    fortnight = fields.Selection([
        ('first', 'Primera Quincena (1 al 15)'),
        ('second', 'Segunda Quincena (16 a fin de mes)'),
        ('full_month', 'Mes Completo'),
    ], string='Período Quincenal', default='full_month')

    txt_file = fields.Binary(
        string='Archivo TXT SENIAT',
        readonly=True,
    )
    txt_filename = fields.Char(
        string='Nombre del Archivo',
        readonly=True,
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Generado'),
    ], default='draft')

    @api.onchange('fortnight', 'date_from')
    def _onchange_fortnight(self):
        if self.date_from:
            year = self.date_from.year
            month = self.date_from.month
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            if self.fortnight == 'first':
                self.date_from = fields.Date.from_string(f'{year}-{month:02d}-01')
                self.date_to = fields.Date.from_string(f'{year}-{month:02d}-15')
            elif self.fortnight == 'second':
                self.date_from = fields.Date.from_string(f'{year}-{month:02d}-16')
                self.date_to = fields.Date.from_string(f'{year}-{month:02d}-{last_day:02d}')
            elif self.fortnight == 'full_month':
                self.date_from = fields.Date.from_string(f'{year}-{month:02d}-01')
                self.date_to = fields.Date.from_string(f'{year}-{month:02d}-{last_day:02d}')

    def action_generate_txt(self):
        """Genera el archivo plano TXT con los 14 campos reglamentarios del SENIAT."""
        self.ensure_one()
        company = self.company_id
        agent_rif = (company.l10n_ve_rif_clean or company.vat or '').replace('-', '').strip().upper()
        if not agent_rif:
            raise UserError(_('La compañía no tiene configurado un RIF válido para el SENIAT.'))

        retentions = self.env['account.wh.iva'].search([
            ('company_id', '=', company.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', '=', 'posted'),
        ])

        if not retentions:
            raise UserError(
                _('No se encontraron comprobantes de retención de IVA confirmados '
                  'entre %s y %s.') % (self.date_from, self.date_to)
            )

        period = self.date_from.strftime('%Y%m')
        lines = []

        for ret in retentions:
            move = ret.move_id
            supplier_rif = (ret.partner_id.l10n_ve_rif_clean or ret.partner_id.vat or '').replace('-', '').strip().upper()
            invoice_date = (move.invoice_date or ret.date).strftime('%Y-%m-%d')
            op_type = 'C'  # Compras

            # Tipo de documento SENIAT: 01=Factura, 02=Nota Débito, 03=Nota Crédito
            doc_type = '01'
            if move.move_type == 'in_refund':
                doc_type = '03'
            elif hasattr(move, 'debit_origin_id') and move.debit_origin_id:
                doc_type = '02'

            inv_number = (move.name or '').replace('/', '').replace('-', '')[-10:] or '00000001'
            ctrl_number = (move.l10n_ve_control_number or '').replace('-', '').strip() or '00000001'
            doc_affected = (move.reversed_entry_id.name or '0').replace('/', '').replace('-', '')[-10:] if move.move_type == 'in_refund' else '0'

            total_amount = f"{abs(ret.amount_total_bs):.2f}"
            base_amount = f"{abs(ret.amount_untaxed_bs):.2f}"
            retained_amount = f"{abs(ret.amount_bs):.2f}"
            exempt_amount = "0.00"
            tax_rate = f"{ret.tax_id.amount:.2f}" if ret.tax_id else "16.00"
            voucher_number = (ret.number or '').replace('-', '') or f"{period}{ret.id:08d}"

            # Estructura de 14 campos reglamentaria SENIAT
            line_txt = (
                f"{agent_rif}\t"
                f"{period}\t"
                f"{invoice_date}\t"
                f"{op_type}\t"
                f"{doc_type}\t"
                f"{supplier_rif}\t"
                f"{inv_number}\t"
                f"{ctrl_number}\t"
                f"{total_amount}\t"
                f"{base_amount}\t"
                f"{retained_amount}\t"
                f"{doc_affected}\t"
                f"{voucher_number}\t"
                f"{exempt_amount}\t"
                f"{tax_rate}\t"
                f"0"
            )
            lines.append(line_txt)

        txt_content = "\r\n".join(lines)
        txt_base64 = base64.b64encode(txt_content.encode('latin1', errors='replace'))
        filename = f"IVA_{agent_rif}_{period}.txt"

        self.write({
            'txt_file': txt_base64,
            'txt_filename': filename,
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Generador TXT Retenciones IVA'),
            'res_model': 'l10n_ve.wh.iva.txt.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
