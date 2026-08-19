# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64

class TiunaFaovExportWizard(models.TransientModel):
    _name = 'tiuna.faov.export.wizard'
    _description = 'Wizard de Exportación para TIUNA (IVSS) y FAOV (BANAVIH)'

    export_type = fields.Selection([
        ('faov', 'FAOV en Línea - Archivo Carga Masiva (BANAVIH CSV)'),
        ('tiuna_ingreso', 'TIUNA IVSS - Archivo de Ingreso Trabajadores (TXT)'),
        ('tiuna_egreso', 'TIUNA IVSS - Archivo de Egreso Trabajadores (TXT)'),
    ], string="Tipo de Exportación Portal", default='faov', required=True)

    date_from = fields.Date(string="Fecha Desde", default=fields.Date.today)
    date_to = fields.Date(string="Fecha Hasta", default=fields.Date.today)

    file_data = fields.Binary(string="Archivo Generado", readonly=True)
    file_name = fields.Char(string="Nombre de Archivo", readonly=True)

    def action_export(self):
        self.ensure_one()
        employees = self.env['hr.employee'].search([('company_id', '=', self.env.company.id)])
        lines = []

        if self.export_type == 'faov':
            # FAOV BANAVIH CSV Format: NroRif, LetraNacionalidad, Cedula, PrimerNombre, SegundoNombre, PrimerApellido, SegundoApellido, SalarioNormal
            rif = (self.env.company.vat or 'J000000000').replace('-', '')
            lines.append("RIF,Nacionalidad,Cedula,PrimerNombre,SegundoNombre,PrimerApellido,SegundoApellido,SalarioBase")
            for emp in employees:
                if emp.contract_id and emp.contract_id.state == 'open':
                    ced = (emp.identification_id or 'V00000000').replace('-', '')
                    nac = ced[0] if ced[0] in ('V', 'E') else 'V'
                    num_ced = ced[1:]
                    names = (emp.name or '').split(' ')
                    p_nom = names[0] if len(names) > 0 else ''
                    s_nom = names[1] if len(names) > 1 else ''
                    p_ape = names[2] if len(names) > 2 else (names[1] if len(names) > 1 else '')
                    s_ape = names[3] if len(names) > 3 else ''
                    wage = emp.contract_id.wage_bs
                    lines.append(f"{rif},{nac},{num_ced},{p_nom},{s_nom},{p_ape},{s_ape},{wage:.2f}")

        elif 'tiuna' in self.export_type:
            # TIUNA TXT Format
            for emp in employees:
                ced = (emp.identification_id or 'V00000000').zfill(10)
                name = (emp.name or '').ljust(50)[:50]
                date_str = (emp.contract_id.date_start or fields.Date.today()).strftime('%d%m%Y')
                lines.append(f"{ced}{name}{date_str}")

        content = "\n".join(lines)
        file_b64 = base64.b64encode(content.encode('utf-8'))
        ext = 'csv' if self.export_type == 'faov' else 'txt'
        filename = f"Export_{self.export_type.upper()}_{fields.Date.today().strftime('%Y%m%d')}.{ext}"

        self.write({
            'file_data': file_b64,
            'file_name': filename,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'tiuna.faov.export.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
