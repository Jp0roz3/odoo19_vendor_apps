# -*- coding: utf-8 -*-
"""
Venezuela360: Generador de Archivo XML de Retenciones de ISLR (SENIAT)
======================================================================
Genera el archivo XML oficial según el esquema XSD y especificaciones
técnicas del SENIAT para la declaración de retenciones de ISLR:

Estructura XML SENIAT:
<RelacionRetencionesISLR RifAgente="J123456789" Periodo="AAAAMM">
  <DetalleRetencion>
    <RifRetenido>J987654321</RifRetenido>
    <NumeroFactura>00012345</NumeroFactura>
    <NumeroControl>00-00012345</NumeroControl>
    <FechaOperacion>DD/MM/AAAA</FechaOperacion>
    <CodigoConcepto>001</CodigoConcepto>
    <MontoOperacion>1000.00</MontoOperacion>
    <PorcentajeRetencion>5.00</PorcentajeRetencion>
  </DetalleRetencion>
</RelacionRetencionesISLR>

Autor: JeanPerozo / Nubelco
"""
import base64
import logging
from xml.sax.saxutils import escape
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class WhIslrXmlWizard(models.TransientModel):
    _name = 'l10n_ve.wh.islr.xml.wizard'
    _description = 'Generador de Archivo XML de Retenciones ISLR SENIAT'

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
    xml_file = fields.Binary(
        string='Archivo XML SENIAT',
        readonly=True,
    )
    xml_filename = fields.Char(
        string='Nombre del Archivo',
        readonly=True,
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Generado'),
    ], default='draft')

    def action_generate_xml(self):
        """Genera el archivo XML reglamentario de retenciones de ISLR para el SENIAT."""
        self.ensure_one()
        company = self.company_id
        agent_rif = (
            getattr(company, 'l10n_ve_rif_clean', False) or
            company.l10n_ve_rif or
            company.partner_id.l10n_ve_rif or
            company.partner_id.vat or
            company.vat or ''
        ).replace('-', '').replace(' ', '').strip().upper()
        if not agent_rif:
            raise UserError(_('La compañía no tiene configurado un RIF válido para el SENIAT.'))

        retentions = self.env['account.wh.islr'].search([
            ('company_id', '=', company.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', '=', 'posted'),
        ])

        if not retentions:
            raise UserError(
                _('No se encontraron comprobantes de retención de ISLR confirmados '
                  'entre %s y %s.') % (self.date_from, self.date_to)
            )

        period = self.date_from.strftime('%Y%m')
        xml_lines = [
            '<?xml version="1.0" encoding="ISO-8859-1"?>',
            f'<RelacionRetencionesISLR RifAgente="{agent_rif}" Periodo="{period}">',
        ]

        for ret in retentions:
            move = ret.move_id
            supplier_rif = (
                getattr(ret.partner_id, 'l10n_ve_rif_clean', False) or
                ret.partner_id.l10n_ve_rif or
                ret.partner_id.vat or ''
            ).replace('-', '').replace(' ', '').strip().upper()
            inv_number = (move.name or '').replace('/', '').replace('-', '')[-10:] or '00000001'
            ctrl_number = (move.l10n_ve_control_number or '').replace('-', '').strip() or '00000001'
            op_date = (move.invoice_date or ret.date).strftime('%d/%m/%Y')
            concept_code = ret.concept_id.code if ret.concept_id else '001'
            base_amount = f"{abs(ret.amount_untaxed_bs):.2f}"
            rate = f"{ret.rate:.2f}"

            xml_lines.append('  <DetalleRetencion>')
            xml_lines.append(f'    <RifRetenido>{escape(supplier_rif)}</RifRetenido>')
            xml_lines.append(f'    <NumeroFactura>{escape(inv_number)}</NumeroFactura>')
            xml_lines.append(f'    <NumeroControl>{escape(ctrl_number)}</NumeroControl>')
            xml_lines.append(f'    <FechaOperacion>{op_date}</FechaOperacion>')
            xml_lines.append(f'    <CodigoConcepto>{escape(concept_code)}</CodigoConcepto>')
            xml_lines.append(f'    <MontoOperacion>{base_amount}</MontoOperacion>')
            xml_lines.append(f'    <PorcentajeRetencion>{rate}</PorcentajeRetencion>')
            xml_lines.append('  </DetalleRetencion>')

        xml_lines.append('</RelacionRetencionesISLR>')

        xml_content = "\r\n".join(xml_lines)
        xml_base64 = base64.b64encode(xml_content.encode('iso-8859-1', errors='replace'))
        filename = f"ISLR_{agent_rif}_{period}.xml"

        self.write({
            'xml_file': xml_base64,
            'xml_filename': filename,
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Generador XML Retenciones ISLR'),
            'res_model': 'l10n_ve.wh.islr.xml.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
