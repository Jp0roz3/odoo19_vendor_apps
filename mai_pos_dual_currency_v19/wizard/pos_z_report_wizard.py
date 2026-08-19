from odoo import api, fields, models
from odoo.exceptions import ValidationError

class PosZReportWizard(models.TransientModel):
    _name = 'pos.z.report.wizard'
    _description = 'Asistente para Reporte Z de Conciliación'

    date_from = fields.Date(string='Fecha Inicio', required=True, default=fields.Date.context_today)
    date_to = fields.Date(string='Fecha Fin', required=True, default=fields.Date.context_today)

    def print_report(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise ValidationError("La Fecha Inicio no puede ser mayor a la Fecha Fin.")
        
        data = {
            'date_from': self.date_from,
            'date_to': self.date_to,
        }
        return self.env.ref('mai_pos_dual_currency_v19.action_report_z_details').report_action(self, data=data)
