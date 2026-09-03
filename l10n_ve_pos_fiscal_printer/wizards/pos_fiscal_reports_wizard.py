# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class PosFiscalReportsWizard(models.TransientModel):
    _name = 'pos.fiscal.reports.wizard'
    _description = 'Asistente de Operaciones y Reportes Fiscales'

    pos_config_id = fields.Many2one(
        'pos.config',
        string="Punto de Venta",
        required=True,
        default=lambda self: self.env['pos.config'].search([('fiscal_printer_active', '=', True)], limit=1) or self.env.context.get('active_id')
    )
    operation_type = fields.Selection([
        ('status', 'Consultar Estado de Impresora'),
        ('report_x', 'Emitir Reporte X (Lectura Parcial)'),
        ('report_z', 'Emitir Reporte Z (Cierre Diario)'),
        ('z_by_number', 'Reporte Z por Rango de Números'),
        ('audit_by_date', 'Auditoría Fiscal por Rango de Fechas'),
        ('open_drawer', 'Abrir Gaveta de Dinero'),
        ('cancel_doc', 'Cancelar Documento Fiscal en Curso'),
    ], string="Operación a Realizar", default='report_x', required=True)

    z_start = fields.Integer(string="Z Inicial", default=1)
    z_end = fields.Integer(string="Z Final", default=1)

    date_start = fields.Date(string="Fecha Inicial", default=fields.Date.context_today)
    date_end = fields.Date(string="Fecha Final", default=fields.Date.context_today)

    result_message = fields.Text(string="Resultado", readonly=True)

    def action_execute(self):
        self.ensure_one()
        config = self.pos_config_id
        if not config.fiscal_printer_active:
            raise UserError(_("La impresora fiscal no está activa en la configuración de este Punto de Venta."))

        # Si la comunicación es vía Agente Local
        if config.fiscal_printer_conn_type == 'local_agent':
            agent_url = (config.fiscal_printer_agent_url or 'http://localhost:9069').rstrip('/')
            payload = {
                'model': config.fiscal_printer_model,
                'port': config.fiscal_printer_port,
                'baudrate': int(config.fiscal_printer_baudrate or 9600),
                'operation': self.operation_type,
            }

            if self.operation_type == 'z_by_number':
                payload['z_start'] = self.z_start
                payload['z_end'] = self.z_end
            elif self.operation_type == 'audit_by_date':
                payload['date_start'] = fields.Date.to_string(self.date_start)
                payload['date_end'] = fields.Date.to_string(self.date_end)

            try:
                endpoint = f"{agent_url}/{self.operation_type}"
                resp = requests.post(endpoint, json=payload, timeout=15)
                data = resp.json() if resp.status_code == 200 else {}

                if resp.status_code == 200 and data.get('success'):
                    msg = data.get('message', _('Operación fiscal ejecutada con éxito en la impresora.'))
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Operación Fiscal Exitosa'),
                            'message': msg,
                            'type': 'success',
                            'sticky': False,
                        }
                    }
                else:
                    err_msg = data.get('error') or resp.text or _('Error desconocido reportado por la impresora.')
                    raise UserError(_("Error de Impresora Fiscal: %s") % err_msg)
            except requests.exceptions.RequestException as e:
                raise UserError(_(
                    "No se pudo contactar con el Agente Fiscal Local en '%s'.\n\n"
                    "Verifique que el ejecutable del agente esté iniciado en la computadora de la caja."
                ) % agent_url)

        # Si es vía Web Serial o Mock, devolver acción para ser ejecutada por el POS / Web Client
        return {
            'type': 'ir.actions.client',
            'tag': 'pos_fiscal_client_action',
            'params': {
                'operation': self.operation_type,
                'pos_config_id': config.id,
                'z_start': self.z_start,
                'z_end': self.z_end,
                'date_start': fields.Date.to_string(self.date_start),
                'date_end': fields.Date.to_string(self.date_end),
            }
        }
