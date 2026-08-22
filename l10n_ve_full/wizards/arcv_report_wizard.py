# -*- coding: utf-8 -*-
"""
Venezuela360: Comprobante Anual de Retenciones de ISLR (Formato AR-CV)
======================================================================
Genera el reporte anual acumulado de retenciones de ISLR efectuadas a un
proveedor o beneficiario durante el ejercicio fiscal (Formato Oficial AR-CV).

Autor: JeanPerozo / Nubelco
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ArcvReportWizard(models.TransientModel):
    _name = 'l10n_ve.arcv.report.wizard'
    _description = 'Asistente Comprobante Anual de Retenciones ISLR (AR-CV)'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Proveedor / Beneficiario',
        required=True,
    )
    fiscal_year = fields.Char(
        string='Ejercicio Fiscal (Año)',
        default=lambda self: str(fields.Date.context_today(self).year),
        required=True,
    )

    def action_print_arcv(self):
        """Genera e imprime el reporte AR-CV para el proveedor en el ejercicio fiscal."""
        self.ensure_one()
        year = int(self.fiscal_year)
        date_from = f"{year}-01-01"
        date_to = f"{year}-12-31"

        retentions = self.env['account.wh.islr'].search([
            ('company_id', '=', self.company_id.id),
            ('partner_id', '=', self.partner_id.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('state', '=', 'posted'),
        ], order='date asc, id asc')

        if not retentions:
            raise UserError(
                _('No se encontraron retenciones de ISLR para %s en el año %s.')
                % (self.partner_id.name, self.fiscal_year)
            )

        report = self.env.ref('l10n_ve_full.action_report_arcv', raise_if_not_found=False)
        if report:
            return report.report_action(retentions)

        # Fallback si no existe la acción específica, usar el reporte general
        return self.env.ref('l10n_ve_full.action_report_wh_islr').report_action(retentions)
