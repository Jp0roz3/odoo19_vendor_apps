# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64

class LegalReportsWizard(models.TransientModel):
    _name = 'legal.reports.wizard'
    _description = 'Wizard de Entregables Legales y Gubernamentales (IVSS, SENIAT, MINTRA, INCES)'

    report_type = fields.Selection([
        ('ivss_1312', 'IVSS Forma 13-12 (Registro de Asegurado TXT/CSV)'),
        ('ivss_14100', 'IVSS Forma 14-100 (Constancia de Trabajo para IVSS)'),
        ('seniat_xml', 'SENIAT Retenciones ISLR (Archivo XML Oficial)'),
        ('mintra_txt', 'MINTRA (Reporte de Nómina Ministerio del Trabajo TXT)'),
        ('inces_pdf', 'INCES (Declaración Trimestral de Aportes Patronales)'),
    ], string="Tipo de Entregable Legal", default='ivss_1312', required=True)

    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company, required=True)
    date_from = fields.Date(string="Fecha Desde", default=fields.Date.today, required=True)
    date_to = fields.Date(string="Fecha Hasta", default=fields.Date.today, required=True)
    employee_id = fields.Many2one('hr.employee', string="Empleado (Solo para Forma 14-100)")

    file_data = fields.Binary(string="Archivo Generado", readonly=True)
    file_name = fields.Char(string="Nombre del Archivo", readonly=True)

    def action_generate_report(self):
        self.ensure_one()
        rif = (self.company_id.vat or 'J000000000').replace('-', '')
        company_name = self.company_id.name or 'EMPRESA'

        if self.report_type == 'ivss_1312':
            # IVSS Forma 13-12 TXT
            employees = self.env['hr.employee'].search([('company_id', '=', self.company_id.id), ('active', '=', True)])
            lines = ["NroRif;Nacionalidad;Cedula;PrimerNombre;SegundoNombre;PrimerApellido;SegundoApellido;FechaIngreso;SalarioBase"]
            for emp in employees:
                if emp.contract_id:
                    ced = (emp.identification_id or 'V00000000').replace('-', '')
                    nac = ced[0] if ced[0] in ('V', 'E') else 'V'
                    num_ced = ced[1:]
                    names = (emp.name or '').split(' ')
                    p_nom = names[0] if len(names) > 0 else ''
                    s_nom = names[1] if len(names) > 1 else ''
                    p_ape = names[2] if len(names) > 2 else (names[1] if len(names) > 1 else '')
                    s_ape = names[3] if len(names) > 3 else ''
                    f_ing = (emp.contract_id.date_start or fields.Date.today()).strftime('%d/%m/%Y')
                    wage = emp.contract_id.wage_bs
                    lines.append(f"{rif};{nac};{num_ced};{p_nom};{s_nom};{p_ape};{s_ape};{f_ing};{wage:.2f}")

            content = "\r\n".join(lines)
            ext = 'txt'
            filename = f"IVSS_FORMA_13_12_{fields.Date.today().strftime('%Y%m%d')}.{ext}"

        elif self.report_type == 'seniat_xml':
            # SENIAT ISLR XML Export
            slips = self.env['hr.payslip'].search([
                ('company_id', '=', self.company_id.id),
                ('date_from', '>=', self.date_from),
                ('date_to', '<=', self.date_to),
                ('state', '=', 'done')
            ])

            xml_lines = [
                '<?xml version="1.0" encoding="UTF-8"?>',
                f'<RelacionRetencionesISLR RifAgente="{rif}" Periodo="{self.date_to.strftime("%Y%m")}">',
            ]
            for slip in slips:
                contract = slip.contract_id
                if contract and contract.islr_ari_rate > 0:
                    emp_ced = (slip.employee_id.identification_id or 'V00000000').replace('-', '')
                    base_bs = slip.total_bs
                    ret_bs = round(base_bs * (contract.islr_ari_rate / 100.0), 2)
                    xml_lines.append(f'  <Retencion>')
                    xml_lines.append(f'    <RifRetenido>{emp_ced}</RifRetenido>')
                    xml_lines.append(f'    <NumeroFactura>NOM-{slip.id}</NumeroFactura>')
                    xml_lines.append(f'    <NumeroControl>CTRL-{slip.id}</NumeroControl>')
                    xml_lines.append(f'    <FechaOperacion>{slip.date_to.strftime("%d/%m/%Y")}</FechaOperacion>')
                    xml_lines.append(f'    <CodigoConcepto>001</CodigoConcepto>')
                    xml_lines.append(f'    <MontoOperacion>{base_bs:.2f}</MontoOperacion>')
                    xml_lines.append(f'    <PorcentajeRetencion>{contract.islr_ari_rate:.2f}</PorcentajeRetencion>')
                    xml_lines.append(f'    <MontoRetenido>{ret_bs:.2f}</MontoRetenido>')
                    xml_lines.append(f'  </Retencion>')

            xml_lines.append('</RelacionRetencionesISLR>')
            content = "\n".join(xml_lines)
            ext = 'xml'
            filename = f"SENIAT_ISLR_RETENCIONES_{self.date_to.strftime('%Y%m')}.{ext}"

        elif self.report_type == 'mintra_txt':
            # MINTRA TXT
            employees = self.env['hr.employee'].search([('company_id', '=', self.company_id.id), ('active', '=', True)])
            lines = []
            for emp in employees:
                if emp.contract_id:
                    ced = (emp.identification_id or 'V00000000').zfill(10)
                    name = (emp.name or '').ljust(50)[:50]
                    wage = f"{int(emp.contract_id.wage_bs * 100):012d}"
                    lines.append(f"{rif.ljust(12)}{ced}{name}{wage}")
            content = "\r\n".join(lines)
            ext = 'txt'
            filename = f"MINTRA_NOMINA_{fields.Date.today().strftime('%Y%m%d')}.{ext}"

        else:
            # INCES / IVSS 14-100 Text/CSV export
            employees = self.env['hr.employee'].search([('company_id', '=', self.company_id.id), ('active', '=', True)])
            lines = [f"INFORME TRIMESTRAL INCES - {company_name} (RIF: {rif})"]
            lines.append("Cedula;Empleado;SalarioBaseBs;AportePatronalINCES2%;DeduccionEmpleadoINCES05%")
            for emp in employees:
                if emp.contract_id:
                    wage = emp.contract_id.wage_bs
                    pat_2 = round(wage * 0.02, 2)
                    emp_05 = round(wage * 0.005, 2)
                    lines.append(f"{emp.identification_id};{emp.name};{wage:.2f};{pat_2:.2f};{emp_05:.2f}")

            content = "\r\n".join(lines)
            ext = 'txt'
            filename = f"INCES_DECLARACION_{fields.Date.today().strftime('%Y%m%d')}.{ext}"

        file_b64 = base64.b64encode(content.encode('utf-8'))
        self.write({
            'file_data': file_b64,
            'file_name': filename,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'legal.reports.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
