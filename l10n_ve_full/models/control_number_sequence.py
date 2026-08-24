# -*- coding: utf-8 -*-
"""
Venezuela360: Configuración y Gestión de Números de Control Fiscal
==================================================================
Administra los rangos de control fiscal asignados por la imprenta autorizada
o sistema digital (ej: 00-00000001 hasta 00-00005000) para facturas, notas
de crédito, notas de débito y guías de despacho.

Autor: JeanPerozo / Nubelco
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ControlNumberSequence(models.Model):
    _name = 'l10n_ve.control.sequence'
    _description = 'Control Fiscal - Talonarios y Secuencias SENIAT'
    _order = 'company_id, id desc'

    name = fields.Char(
        string='Nombre del Talonario / Rango',
        required=True,
        help='Ej: Talonario Facturas Forma Libre 2026',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )
    document_type = fields.Selection([
        ('invoice', 'Facturas'),
        ('credit_note', 'Notas de Crédito'),
        ('debit_note', 'Notas de Débito'),
        ('delivery_guide', 'Guías de Despacho'),
    ], string='Tipo de Documento', required=True, default='invoice')

    journal_ids = fields.Many2many(
        comodel_name='account.journal',
        relation='l10n_ve_control_seq_journal_rel',
        column1='sequence_id',
        column2='journal_id',
        string='Diarios Aplicables',
        domain="[('company_id', '=', company_id)]",
        help='Diarios contables que utilizan este talonario. Si se deja vacío, aplica a todos los diarios.',
    )

    emission_type = fields.Selection([
        ('free_format', 'Forma Libre (Imprenta Autorizada)'),
        ('digital', 'Emisión Digital / Pre-Impreso'),
        ('manual', 'Talonario Manual'),
    ], string='Tipo de Emisión', default='free_format', required=True)

    prefix = fields.Char(
        string='Prefijo de Control (2 dígitos)',
        size=2,
        default='00',
        required=True,
        help='Prefijo asignado por la imprenta (ej: 00, 01, 02).',
    )
    range_from = fields.Integer(
        string='Número Inicial',
        required=True,
        default=1,
        help='Número de inicio del rango autorizado (ej: 1 para 00-00000001).',
    )
    range_to = fields.Integer(
        string='Número Final',
        required=True,
        default=5000,
        help='Número final del rango autorizado (ej: 5000 para 00-00005000).',
    )
    current_number = fields.Integer(
        string='Número Actual',
        default=1,
        required=True,
        help='Próximo número de control a asignar.',
    )
    printer_name = fields.Char(
        string='Nombre de la Imprenta',
        help='Razón social de la imprenta autorizada por el SENIAT.',
    )
    printer_vat = fields.Char(
        string='RIF de la Imprenta',
        help='RIF de la imprenta autorizada (ej: J-12345678-9).',
    )
    seniat_authorization_number = fields.Char(
        string='N° Providencia / Autorización SENIAT',
        help='Número de providencia administrativa de autorización.',
    )
    authorization_date = fields.Date(
        string='Fecha de Asignación / Autorización',
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
    )

    def next_control_number(self):
        """Genera y retorna el siguiente número de control fiscal con formato 00-XXXXXXXX."""
        self.ensure_one()
        if self.current_number > self.range_to:
            raise UserError(
                _('El talonario de control fiscal "%s" ha alcanzado el límite máximo autorizado (%s). '
                  'Registre un nuevo rango de control.') % (self.name, self.range_to)
            )
        prefix = (self.prefix or '00').zfill(2)
        number_str = str(self.current_number).zfill(8)
        formatted = f"{prefix}-{number_str}"
        self.current_number += 1
        return formatted
