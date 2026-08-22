# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de res.partner
========================================
Añade datos fiscales venezolanos al contacto: RIF, tipo de contribuyente,
territorialidad, clasificación tributaria y configuración de retenciones.

Autor: JeanPerozo / Nubelco
"""
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ------------------------------------------------------------------
    # Identificación fiscal venezolana
    # ------------------------------------------------------------------
    l10n_ve_rif = fields.Char(
        string='RIF',
        size=15,
        help=(
            'Registro de Información Fiscal ante el SENIAT. '
            'Formato: J-12345678-9 (Jurídico), V-12345678-9 (Natural), '
            'E-12345678-9 (Extranjero), G-12345678-9 (Gobierno).'
        ),
    )
    l10n_ve_rif_type = fields.Selection([
        ('J', 'J — Jurídico (Empresa)'),
        ('V', 'V — Natural (Venezolano)'),
        ('E', 'E — Extranjero'),
        ('G', 'G — Gobierno / Ente Público'),
        ('P', 'P — Pasaporte'),
    ], string='Tipo RIF', compute='_compute_rif_type', store=True,
       help='Tipo de RIF derivado del prefijo del campo RIF.',
    )
    l10n_ve_rif_clean = fields.Char(
        string='RIF (sin formato)',
        compute='_compute_rif_clean',
        store=True,
        help='RIF sin guiones ni espacios, útil para comparaciones y reportes SENIAT.',
    )

    # ------------------------------------------------------------------
    # Clasificación tributaria
    # ------------------------------------------------------------------
    l10n_ve_contributor_type = fields.Selection([
        ('ordinary',   'Contribuyente Ordinario'),
        ('formal',     'Contribuyente Formal'),
        ('special',    'Contribuyente Especial'),
        ('exonerated', 'Exonerado de IVA'),
        ('none',       'No Contribuyente'),
    ], string='Tipo de Contribuyente IVA',
       default='ordinary',
       help='Clasificación ante el SENIAT que determina el % de retención de IVA aplicable.',
    )
    l10n_ve_retention_agent_iva = fields.Boolean(
        string='Agente de Retención IVA',
        default=False,
        help='Indica que este contacto es Agente de Retención de IVA designado por el SENIAT.',
    )
    l10n_ve_retention_agent_islr = fields.Boolean(
        string='Agente de Retención ISLR',
        default=False,
    )
    l10n_ve_seniat_registry = fields.Char(
        string='N° Registro SENIAT',
        help='Número de registro formal ante el SENIAT (distinto al RIF en algunos trámites).',
    )

    # ------------------------------------------------------------------
    # Territorialidad venezolana
    # ------------------------------------------------------------------
    l10n_ve_state_id = fields.Many2one(
        comodel_name='l10n_ve.state',
        string='Estado (Venezuela)',
    )
    l10n_ve_municipality_id = fields.Many2one(
        comodel_name='l10n_ve.municipality',
        string='Municipio',
    )
    l10n_ve_parish_id = fields.Many2one(
        comodel_name='l10n_ve.parish',
        string='Parroquia',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'country_id' in fields_list and not res.get('country_id'):
            ve_country = self.env.ref('base.ve', raise_if_not_found=False)
            if ve_country:
                res['country_id'] = ve_country.id
        return res

    @api.onchange('state_id')
    def _onchange_native_state_id(self):
        """Sincroniza el estado nativo de Odoo con el catálogo de estados de Venezuela y filtra municipios."""
        if self.state_id:
            ve_state = self.env['l10n_ve.state'].search([
                '|', ('name', 'ilike', self.state_id.name),
                ('code', 'ilike', self.state_id.code or '')
            ], limit=1)
            if ve_state:
                self.l10n_ve_state_id = ve_state
            if self.l10n_ve_municipality_id and self.l10n_ve_municipality_id.state_id != self.state_id:
                self.l10n_ve_municipality_id = False
                self.l10n_ve_parish_id = False
            return {'domain': {'l10n_ve_municipality_id': [('state_id', '=', self.state_id.id)]}}
        return {'domain': {'l10n_ve_municipality_id': []}}

    @api.onchange('l10n_ve_municipality_id')
    def _onchange_l10n_ve_municipality_id(self):
        """Al seleccionar un municipio, autocompleta el estado correspondiente y filtra parroquias."""
        if self.l10n_ve_municipality_id:
            if self.l10n_ve_municipality_id.state_id:
                self.state_id = self.l10n_ve_municipality_id.state_id
                if self.l10n_ve_municipality_id.l10n_ve_state_id:
                    self.l10n_ve_state_id = self.l10n_ve_municipality_id.l10n_ve_state_id
                ve_country = self.env.ref('base.ve', raise_if_not_found=False)
                if ve_country and not self.country_id:
                    self.country_id = ve_country
            if self.l10n_ve_parish_id and self.l10n_ve_parish_id.municipality_id != self.l10n_ve_municipality_id:
                self.l10n_ve_parish_id = False
            return {'domain': {'l10n_ve_parish_id': [('municipality_id', '=', self.l10n_ve_municipality_id.id)]}}
        return {'domain': {'l10n_ve_parish_id': []}}

    @api.onchange('l10n_ve_parish_id')
    def _onchange_l10n_ve_parish_id(self):
        """Al seleccionar una parroquia, autocompleta municipio y estado."""
        if self.l10n_ve_parish_id and self.l10n_ve_parish_id.municipality_id:
            self.l10n_ve_municipality_id = self.l10n_ve_parish_id.municipality_id
            if self.l10n_ve_municipality_id.state_id:
                self.state_id = self.l10n_ve_municipality_id.state_id
                if self.l10n_ve_municipality_id.l10n_ve_state_id:
                    self.l10n_ve_state_id = self.l10n_ve_municipality_id.l10n_ve_state_id
                ve_country = self.env.ref('base.ve', raise_if_not_found=False)
                if ve_country and not self.country_id:
                    self.country_id = ve_country

    # ------------------------------------------------------------------
    # Régimen fiscal de ISLR
    # ------------------------------------------------------------------
    l10n_ve_islr_concept_id = fields.Many2one(
        comodel_name='account.wh.islr.concept',
        string='Concepto ISLR por Defecto',
        help='Concepto de retención ISLR que se usa por defecto al procesar facturas de este proveedor.',
    )

    # ------------------------------------------------------------------
    # Retención municipal
    # ------------------------------------------------------------------
    l10n_ve_municipal_activity = fields.Char(
        string='Actividad Económica Municipal',
        help='Código o descripción de la actividad económica para cálculo de retención municipal.',
    )
    l10n_ve_municipal_rate = fields.Float(
        string='Tasa Ret. Municipal (%)',
        digits=(5, 4),
        help='Porcentaje de retención municipal aplicable a este proveedor/cliente.',
    )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('l10n_ve_rif')
    def _compute_rif_type(self):
        for partner in self:
            rif = (partner.l10n_ve_rif or '').strip().upper()
            if rif and rif[0] in ('J', 'V', 'E', 'G', 'P'):
                partner.l10n_ve_rif_type = rif[0]
            else:
                partner.l10n_ve_rif_type = False

    @api.depends('l10n_ve_rif')
    def _compute_rif_clean(self):
        for partner in self:
            rif = partner.l10n_ve_rif or ''
            partner.l10n_ve_rif_clean = re.sub(r'[^A-Za-z0-9]', '', rif).upper()

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains('l10n_ve_rif')
    def _check_rif_format(self):
        """
        Valida que el RIF siga el formato venezolano básico:
        Letra-(7 u 8 dígitos)-dígito verificador
        Ej válido: J-12345678-9
        """
        rif_pattern = re.compile(r'^[JVEGP]-?\d{7,8}-?\d$', re.IGNORECASE)
        for partner in self:
            if partner.l10n_ve_rif:
                clean = re.sub(r'[^A-Za-z0-9]', '', partner.l10n_ve_rif)
                if not rif_pattern.match(partner.l10n_ve_rif) and len(clean) not in (9, 10):
                    raise ValidationError(
                        _('El RIF "%s" no tiene el formato venezolano válido. '
                          'Ejemplo correcto: J-12345678-9')
                        % partner.l10n_ve_rif
                    )

    # ------------------------------------------------------------------
    # Onchange helpers
    # ------------------------------------------------------------------
    @api.onchange('l10n_ve_state_id')
    def _onchange_ve_state(self):
        """Limpiar municipio y parroquia al cambiar estado."""
        self.l10n_ve_municipality_id = False
        self.l10n_ve_parish_id = False

    @api.onchange('l10n_ve_municipality_id')
    def _onchange_ve_municipality(self):
        """Limpiar parroquia al cambiar municipio."""
        self.l10n_ve_parish_id = False

    @api.onchange('l10n_ve_contributor_type')
    def _onchange_contributor_type(self):
        """Sugerir si es agente de retención al ser Especial."""
        if self.l10n_ve_contributor_type == 'special':
            self.l10n_ve_retention_agent_iva = True

    # ------------------------------------------------------------------
    # Helper: porcentaje de retención IVA aplicable a este partner
    # ------------------------------------------------------------------
    def get_wh_iva_rate(self, company=None):
        """
        Retorna el porcentaje de retención de IVA aplicable para este partner
        según su tipo de contribuyente y la configuración de la compañía.

        Retorna:
            float: porcentaje (ej: 75.0 o 100.0)
        """
        self.ensure_one()
        company = company or self.env.company
        if self.l10n_ve_contributor_type == 'special':
            return company.l10n_ve_wh_iva_rate_special   # 100% por defecto
        if self.l10n_ve_contributor_type == 'exonerated':
            return 0.0
        return company.l10n_ve_wh_iva_rate_general  # 75% por defecto
