# -*- coding: utf-8 -*-
"""
Venezuela360: Reporte de Patente Municipal (Actividades Económicas)
===================================================================
Genera el reporte consolidado de retenciones municipales y base imponible
por clasificador de actividad económica para la declaración ante la Alcaldía.

Autor: JeanPerozo / Nubelco
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MunicipalTaxWizard(models.TransientModel):
    _name = 'l10n_ve.municipal.tax.wizard'
    _description = 'Reporte de Patente Municipal (Actividades Económicas)'

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

    def action_print_report(self):
        """Imprime el reporte de retenciones municipales / patente."""
        self.ensure_one()
        retentions = self.env['account.wh.municipal'].search([
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', '=', 'posted'),
        ])
        if not retentions:
            raise UserError(
                _('No se encontraron retenciones municipales entre %s y %s.')
                % (self.date_from, self.date_to)
            )
        return self.env.ref('l10n_ve_full.action_report_wh_municipal').report_action(retentions)
