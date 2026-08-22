# -*- coding: utf-8 -*-
"""
Venezuela360: Territorialidad Venezolana
=========================================
Modelos:
    - l10n_ve.state          : Los 24 estados de Venezuela (+ Dependencias)
    - l10n_ve.municipality   : Municipios por estado
    - l10n_ve.parish         : Parroquias por municipio

Autor: JeanPerozo / Nubelco
"""
from odoo import models, fields, api, _


class L10nVeState(models.Model):
    """24 estados de Venezuela + Capital/Dependencias Federales."""
    _name = 'l10n_ve.state'
    _description = 'Estado de Venezuela'
    _order = 'name asc'
    _rec_name = 'name'

    name = fields.Char(
        string='Estado',
        required=True,
        translate=False,
        help='Nombre oficial del estado venezolano según el SENIAT.',
    )
    code = fields.Char(
        string='Código',
        size=4,
        required=True,
        help='Código de estado (ej: VE-M para Miranda, VE-GU para Guárico).',
    )
    municipality_ids = fields.One2many(
        comodel_name='l10n_ve.municipality',
        inverse_name='state_id',
        string='Municipios',
    )
    municipality_count = fields.Integer(
        string='N° Municipios',
        compute='_compute_municipality_count',
        store=True,
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'El código de estado debe ser único.'),
        ('name_unique', 'UNIQUE(name)', 'El nombre del estado debe ser único.'),
    ]

    @api.depends('municipality_ids')
    def _compute_municipality_count(self):
        for rec in self:
            rec.municipality_count = len(rec.municipality_ids)

    def name_get(self):
        return [(rec.id, f'[{rec.code}] {rec.name}') for rec in self]


class L10nVeMunicipality(models.Model):
    """Municipio venezolano, hijo de estado."""
    _name = 'l10n_ve.municipality'
    _description = 'Municipio de Venezuela'
    _order = 'state_id, name asc'
    _rec_name = 'name'

    name = fields.Char(
        string='Municipio',
        required=True,
        translate=False,
    )
    code = fields.Char(
        string='Código Municipio',
        size=10,
        help='Código fiscal del municipio ante el SENIAT.',
    )
    state_id = fields.Many2one(
        comodel_name='l10n_ve.state',
        string='Estado',
        required=True,
        ondelete='restrict',
        index=True,
    )
    parish_ids = fields.One2many(
        comodel_name='l10n_ve.parish',
        inverse_name='municipality_id',
        string='Parroquias',
    )
    parish_count = fields.Integer(
        string='N° Parroquias',
        compute='_compute_parish_count',
        store=True,
    )
    # Tasa de retención municipal por defecto para esta jurisdicción
    wh_municipal_rate = fields.Float(
        string='Tasa Ret. Municipal (%)',
        digits=(5, 4),
        default=0.0,
        help=(
            'Porcentaje de retención municipal por defecto para este municipio. '
            'Se puede sobreescribir por actividad económica en la configuración de retención.'
        ),
    )
    active = fields.Boolean(default=True)

    @api.depends('parish_ids')
    def _compute_parish_count(self):
        for rec in self:
            rec.parish_count = len(rec.parish_ids)

    def name_get(self):
        return [
            (rec.id, f'{rec.state_id.code} / {rec.name}' if rec.state_id else rec.name)
            for rec in self
        ]


class L10nVeParish(models.Model):
    """Parroquia venezolana, hija de municipio."""
    _name = 'l10n_ve.parish'
    _description = 'Parroquia de Venezuela'
    _order = 'municipality_id, name asc'
    _rec_name = 'name'

    name = fields.Char(
        string='Parroquia',
        required=True,
        translate=False,
    )
    code = fields.Char(
        string='Código Parroquia',
        size=12,
    )
    municipality_id = fields.Many2one(
        comodel_name='l10n_ve.municipality',
        string='Municipio',
        required=True,
        ondelete='restrict',
        index=True,
    )
    state_id = fields.Many2one(
        comodel_name='l10n_ve.state',
        string='Estado',
        related='municipality_id.state_id',
        store=True,
        readonly=True,
    )
    active = fields.Boolean(default=True)

    @api.depends('name', 'municipality_id.name')
    def _compute_display_name(self):
        for rec in self:
            if rec.municipality_id:
                rec.display_name = f"{rec.name} ({rec.municipality_id.name})"
            else:
                rec.display_name = rec.name

    def name_get(self):
        return [
            (rec.id, f'{rec.municipality_id.name} / {rec.name}' if rec.municipality_id else rec.name)
            for rec in self
        ]
