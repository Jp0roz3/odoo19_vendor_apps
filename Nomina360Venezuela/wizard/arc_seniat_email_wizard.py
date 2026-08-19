# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64

class ArcSeniatEmailWizard(models.TransientModel):
    _name = 'arc.seniat.email.wizard'
    _description = 'Wizard de Emisión y Envío Masivo por Email de Comprobantes AR-C y AR-I SENIAT'

    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company, required=True)
    year = fields.Integer(string="Año Fiscal", default=lambda self: fields.Date.today().year, required=True)
    
    employee_ids = fields.Many2many('hr.employee', string="Empleados a Enviar", help="Dejar vacío para enviar masivamente a todos los empleados activos.")

    email_subject = fields.Char(string="Asunto del Correo", default="Comprobante Anual de Retenciones ISLR (AR-C) SENIAT")
    email_body = fields.Text(string="Cuerpo del Mensaje", default="""Estimado(a) trabajador(a),

Adjunto a este correo encontrará su Comprobante de Retención Anual del Impuesto Sobre la Renta (AR-C SENIAT) correspondiente al ejercicio fiscal finalizado.

Este documento certifica las remuneraciones pagadas y las retenciones efectivas practicadas por la empresa durante el año.

Atentamente,
Gerencia de Recursos Humanos & Gestión de Nómina 360
""")

    sent_count = fields.Integer(string="Cantidad de Envíos Exitosos", default=0, readonly=True)

    def action_send_arc_emails(self):
        self.ensure_one()
        employees = self.employee_ids or self.env['hr.employee'].search([('company_id', '=', self.company_id.id), ('active', '=', True)])
        
        count = 0
        for emp in employees:
            if not emp.work_email and not emp.private_email:
                continue

            dest_email = emp.work_email or emp.private_email
            
            # Generate AR-C text report for employee
            slips = self.env['hr.payslip'].search([
                ('employee_id', '=', emp.id),
                ('state', '=', 'done')
            ])
            tot_remun = sum(slips.mapped('total_bs'))
            tot_islr = sum(slips.mapped('line_ids').filtered(lambda l: l.code == 'ISLR_AR_I').mapped('total'))

            content = f"""
================================================================================
COMPROBANTE DE RETENCIÓN ANUAL DE IMPUESTO SOBRE LA RENTA (AR-C SENIAT)
================================================================================
Empresa Agente de Retención: {self.company_id.name}
RIF Agente: {self.company_id.vat or 'J-00000000-0'}
Ejercicio Fiscal: {self.year}

DATOS DEL TRABAJADOR RETENIDO:
Nombre Completo: {emp.name}
Cédula de Identidad: {emp.identification_id or 'V-00000000'}
Cargo: {emp.job_title or 'Empleado'}

RESUMEN CONSOLIDADO DE REMUNERACIONES Y RETENCIONES:
Total Remuneraciones Pagadas en el Año: {tot_remun:,.2f} Bs
Total ISLR Retenido en el Año (AR-C): {abs(tot_islr):,.2f} Bs

Certificamos que los montos señalados corresponden fielmente a los registros
contables de la empresa depositados ante la Administración Tributaria SENIAT.
================================================================================
"""
            attachment = self.env['ir.attachment'].create({
                'name': f'COMPROBANTE_AR-C_{emp.identification_id}_{self.year}.txt',
                'type': 'binary',
                'datas': base64.b64encode(content.encode('utf-8')),
                'res_model': 'hr.employee',
                'res_id': emp.id,
                'mimetype': 'text/plain',
            })

            body_html_formatted = (self.email_body or '').replace('\n', '<br/>')
            mail_values = {
                'subject': f"{self.email_subject} - {self.year}",
                'body_html': f"<p>{body_html_formatted}</p>",
                'email_to': dest_email,
                'attachment_ids': [(6, 0, [attachment.id])],
            }
            self.env['mail.mail'].create(mail_values).send()
            count += 1

        self.write({'sent_count': count})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'arc.seniat.email.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
