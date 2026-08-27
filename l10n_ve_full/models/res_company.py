# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de res.company
========================================
Añade a res.company todos los parámetros de configuración fiscal
y contable venezolana, incluyendo configuración dual BS/USD,
parámetros de retención y la UT activa.

Autor: JeanPerozo / Nubelco
"""
import logging
import re
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    # ------------------------------------------------------------------
    # Indicador de localización activa
    # ------------------------------------------------------------------
    l10n_ve_active = fields.Boolean(
        string='Localización Venezuela360 Activa',
        default=False,
        help='Activa la localización fiscal venezolana completa para esta compañía.',
    )

    # ------------------------------------------------------------------
    # Territorialidad
    # ------------------------------------------------------------------
    l10n_ve_state_id = fields.Many2one(
        comodel_name='l10n_ve.state',
        string='Estado (Venezuela)',
        help='Estado venezolano donde está registrada la compañía ante el SENIAT.',
    )
    l10n_ve_municipality_id = fields.Many2one(
        comodel_name='l10n_ve.municipality',
        string='Municipio (Venezuela)',
        domain="[('state_id', '=', l10n_ve_state_id)]",
    )
    l10n_ve_parish_id = fields.Many2one(
        comodel_name='l10n_ve.parish',
        string='Parroquia (Venezuela)',
        domain="[('municipality_id', '=', l10n_ve_municipality_id)]",
    )

    # ------------------------------------------------------------------
    # Identificación SENIAT
    # ------------------------------------------------------------------
    l10n_ve_rif = fields.Char(
        string='RIF',
        size=15,
        help='Registro de Información Fiscal. Ej: J-12345678-9',
    )
    l10n_ve_rif_clean = fields.Char(
        string='RIF (sin formato)',
        compute='_compute_rif_clean',
        store=False,
    )
    l10n_ve_contributor_type = fields.Selection([
        ('ordinary',    'Contribuyente Ordinario'),
        ('formal',      'Contribuyente Formal'),
        ('special',     'Contribuyente Especial'),
        ('exonerated',  'Exonerado'),
    ], string='Tipo de Contribuyente IVA',
       default='ordinary',
       help='Clasificación del contribuyente ante el SENIAT para efectos de IVA.',
    )
    l10n_ve_retention_agent = fields.Boolean(
        string='Agente de Retención IVA',
        default=False,
        help='Indica que esta empresa está designada como Agente de Retención de IVA por el SENIAT.',
    )
    l10n_ve_retention_islr_agent = fields.Boolean(
        string='Agente de Retención ISLR',
        default=False,
        help='Indica que esta empresa es Agente de Retención del ISLR.',
    )
    l10n_ve_retention_municipal_agent = fields.Boolean(
        string='Agente de Retención Municipal',
        default=False,
        help='Indica que esta empresa es Agente de Retención Municipal.',
    )

    # ------------------------------------------------------------------
    # Monedas: configuración dual BS / USD
    # ------------------------------------------------------------------
    l10n_ve_currency_bs_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda Bs (Bolívar)',
        default=lambda self: self.env['res.currency'].search(
            [('name', 'in', ['VES', 'VEF', 'VEB'])], limit=1
        ),
        help='Moneda venezolana activa (Bolívar Soberano / Digital).',
    )
    l10n_ve_currency_usd_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda USD',
        default=lambda self: self.env.ref('base.USD', raise_if_not_found=False),
    )
    l10n_ve_dual_currency = fields.Boolean(
        string='Contabilidad Dual BS/USD',
        default=True,
        help=(
            'Activa el registro de montos en BS y USD de forma simultánea '
            'en todos los documentos, asientos y reportes.'
        ),
    )

    # ------------------------------------------------------------------
    # Fuente de tasa de cambio
    # ------------------------------------------------------------------
    l10n_ve_rate_source = fields.Selection([
        ('bcv',    'BCV — Banco Central de Venezuela'),
        ('seniat', 'SENIAT — Tabla Oficial'),
        ('manual', 'Manual (usuario)'),
    ], string='Fuente de Tasa BCV',
       default='bcv',
       help='Fuente utilizada para registrar y consultar la tasa de cambio oficial.',
    )

    # ------------------------------------------------------------------
    # Diarios contables de localización
    # ------------------------------------------------------------------
    l10n_ve_wh_iva_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario Retenciones IVA',
        help='Diario contable donde se registran los asientos de retención de IVA.',
    )
    l10n_ve_wh_islr_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario Retenciones ISLR',
    )
    l10n_ve_wh_municipal_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario Retenciones Municipales',
    )

    # ------------------------------------------------------------------
    # Cuentas contables de retenciones
    # ------------------------------------------------------------------
    l10n_ve_wh_iva_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta IVA Retenido (Emitido)',
        help='Cuenta donde se registra el IVA retenido al proveedor.',
    )
    l10n_ve_wh_iva_received_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta IVA Retenido (Recibido)',
        help='Cuenta donde se registra el IVA que nos han retenido como proveedores.',
    )
    l10n_ve_wh_islr_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta ISLR Retenido (Emitido)',
    )
    l10n_ve_wh_islr_received_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta ISLR Retenido (Recibido)',
    )
    l10n_ve_wh_municipal_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta Ret. Municipal (Emitido)',
    )

    # ------------------------------------------------------------------
    # Parámetros de IVA
    # ------------------------------------------------------------------
    l10n_ve_iva_rate = fields.Float(
        string='Tasa IVA General (%)',
        default=16.0,
        digits=(5, 2),
        help='Porcentaje de IVA general aplicable. Ej: 16%.',
    )
    l10n_ve_iva_reduced_rate = fields.Float(
        string='Tasa IVA Reducida (%)',
        default=8.0,
        digits=(5, 2),
    )
    l10n_ve_iva_additional_rate = fields.Float(
        string='Tasa IVA Adicional (%)',
        default=15.0,
        digits=(5, 2),
    )

    # ------------------------------------------------------------------
    # Parámetros de Retención IVA (porcentaje sobre el IVA facturado)
    # ------------------------------------------------------------------
    l10n_ve_wh_iva_rate_general = fields.Float(
        string='Ret. IVA — Contribuyente Ordinario (%)',
        default=75.0,
        digits=(5, 2),
        help='Porcentaje de retención sobre el IVA para contribuyentes ordinarios (default 75%).',
    )
    l10n_ve_wh_iva_rate_special = fields.Float(
        string='Ret. IVA — Contribuyente Especial (%)',
        default=100.0,
        digits=(5, 2),
        help='Porcentaje de retención sobre el IVA para contribuyentes especiales (default 100%).',
    )

    # ------------------------------------------------------------------
    # Numeración de comprobantes
    # ------------------------------------------------------------------
    l10n_ve_wh_iva_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Secuencia Comprobante Ret. IVA',
    )
    l10n_ve_wh_islr_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Secuencia Comprobante Ret. ISLR',
    )
    l10n_ve_wh_municipal_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Secuencia Comprobante Ret. Municipal',
    )

    # ------------------------------------------------------------------
    # UT activa (computed)
    # ------------------------------------------------------------------
    l10n_ve_current_ut_id = fields.Many2one(
        comodel_name='account.ut.history',
        string='UT Vigente',
        compute='_compute_current_ut',
        help='Valor de Unidad Tributaria actualmente vigente para esta compañía.',
    )
    l10n_ve_current_ut_value = fields.Float(
        string='Valor UT Vigente (Bs)',
        compute='_compute_current_ut',
        digits=(18, 2),
    )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('l10n_ve_rif', 'vat')
    def _compute_rif_clean(self):
        for company in self:
            rif = company.l10n_ve_rif or company.vat or ''
            company.l10n_ve_rif_clean = re.sub(r'[^A-Za-z0-9]', '', rif).upper()

    def _compute_current_ut(self):
        today = fields.Date.context_today(self)
        for company in self:
            ut = self.env['account.ut.history'].get_ut_for_date(today, company_id=company.id)
            company.l10n_ve_current_ut_id = ut.id if ut else False
            company.l10n_ve_current_ut_value = ut.value_bs if ut else 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def get_current_bcv_rate(self):
        """Retorna el valor float de la tasa BCV más reciente para esta compañía."""
        self.ensure_one()
        rate_rec = self.env['l10n_ve.exchange.rate'].get_latest_rate(company_id=self.id)
        return rate_rec.rate if rate_rec else 0.0

    def _ensure_l10n_ve_chart_and_taxes(self):
        """
        Garantiza de forma idempotente y no destructiva la existencia y asignación
        de los grupos de impuestos, cuentas fiscales auxiliares (VEN-NIF/SENIAT),
        los 14 impuestos oficiales venezolanos y los diarios/cuentas de retención.
        """
        AccountTax = self.env['account.tax']
        AccountTaxGroup = self.env['account.tax.group']
        AccountAccount = self.env['account.account']
        AccountJournal = self.env['account.journal']

        # 1. Grupos de Impuestos Oficiales (con pos_receipt_label y country_id para POS Odoo 19)
        country_ve = self.env.ref('base.ve', raise_if_not_found=False)
        tax_groups_def = {
            'tax_group_iva_general': {'name': 'IVA General 16%', 'sequence': 1, 'pos_receipt_label': 'IVA 16%'},
            'tax_group_iva_reducida': {'name': 'IVA Reducida 8%', 'sequence': 2, 'pos_receipt_label': 'IVA 8%'},
            'tax_group_iva_adicional': {'name': 'IVA Adicional 15%', 'sequence': 3, 'pos_receipt_label': 'IVA 31%'},
            'tax_group_iva_exento': {'name': 'IVA Exento (0%)', 'sequence': 4, 'pos_receipt_label': 'EXENTO'},
            'tax_group_no_sujeto': {'name': 'No Sujeto a IVA (0%)', 'sequence': 5, 'pos_receipt_label': 'NO SUJETO'},
            'tax_group_igtf': {'name': 'IGTF (3%)', 'sequence': 6, 'pos_receipt_label': 'IGTF 3%'},
            'tax_group_islr': {'name': 'ISLR (Retención)', 'sequence': 10, 'pos_receipt_label': 'ISLR'},
            'tax_group_municipal': {'name': 'Retención Municipal (IAE)', 'sequence': 11, 'pos_receipt_label': 'IAE'},
        }
        groups_map = {}
        has_country_id = 'country_id' in AccountTaxGroup._fields
        has_pos_receipt_label = 'pos_receipt_label' in AccountTaxGroup._fields

        for xml_key, g_vals in tax_groups_def.items():
            try:
                rec = self.env.ref(f'l10n_ve_full.{xml_key}', raise_if_not_found=False)
            except Exception:
                rec = False
            if not rec:
                rec = AccountTaxGroup.search([('name', '=', g_vals['name'])], limit=1)

            vals = dict(g_vals)
            if not has_pos_receipt_label and 'pos_receipt_label' in vals:
                del vals['pos_receipt_label']
            if has_country_id and country_ve:
                vals['country_id'] = country_ve.id

            if not rec:
                try:
                    rec = AccountTaxGroup.create(vals)
                except Exception as e:
                    _logger.warning("Venezuela360: Error creando grupo %s: %s", g_vals['name'], e)
            else:
                upd_vals = {}
                if has_pos_receipt_label and not rec.pos_receipt_label and 'pos_receipt_label' in g_vals:
                    upd_vals['pos_receipt_label'] = g_vals['pos_receipt_label']
                if has_country_id and country_ve and not rec.country_id:
                    upd_vals['country_id'] = country_ve.id
                if upd_vals:
                    try:
                        rec.write(upd_vals)
                    except Exception:
                        pass
            groups_map[xml_key] = rec

        for company in self:
            try:
                # 2. Cuentas Contables Fiscales VEN-NIF (si la compañía tiene plan contable)
                def _get_or_create_account(code, name, acc_type):
                    has_company_ids = 'company_ids' in AccountAccount._fields
                    has_company_id = 'company_id' in AccountAccount._fields

                    domain_code = [('code', '=', code)]
                    domain_name = [('name', 'ilike', name)]
                    if has_company_ids:
                        domain_code.append(('company_ids', 'in', [company.id]))
                        domain_name.append(('company_ids', 'in', [company.id]))
                    elif has_company_id:
                        domain_code.append(('company_id', '=', company.id))
                        domain_name.append(('company_id', '=', company.id))

                    acc = AccountAccount.search(domain_code, limit=1)
                    if not acc:
                        acc = AccountAccount.search(domain_name, limit=1)
                    if not acc:
                        try:
                            vals = {
                                'code': code,
                                'name': name,
                                'account_type': acc_type,
                            }
                            if has_company_ids:
                                vals['company_ids'] = [(6, 0, [company.id])]
                            elif has_company_id:
                                vals['company_id'] = company.id
                            acc = AccountAccount.create(vals)
                        except Exception as ex:
                            _logger.info("Venezuela360: Cuenta %s (%s) no requerida o ya manejada: %s", code, name, ex)
                            acc = False
                    return acc

                acc_wh_iva_p = _get_or_create_account('2.1.03.02.001', 'Retenciones IVA por Enterar (Proveedores)', 'liability_current')
                acc_wh_iva_r = _get_or_create_account('1.1.03.02.001', 'Retenciones IVA Recibidas (Clientes)', 'asset_current')
                acc_wh_islr_p = _get_or_create_account('2.1.03.03.001', 'Retenciones ISLR por Enterar', 'liability_current')
                acc_wh_islr_r = _get_or_create_account('1.1.03.03.001', 'Anticipo ISLR Retenido (Clientes)', 'asset_current')
                acc_wh_mun_p = _get_or_create_account('2.1.03.04.001', 'Retenciones Municipales IAE por Enterar', 'liability_current')

                # 3. Asignación de Cuentas y Diarios por Defecto en la Compañía
                if not company.l10n_ve_wh_iva_account_id and acc_wh_iva_p:
                    company.l10n_ve_wh_iva_account_id = acc_wh_iva_p
                if not company.l10n_ve_wh_iva_received_account_id and acc_wh_iva_r:
                    company.l10n_ve_wh_iva_received_account_id = acc_wh_iva_r
                if not company.l10n_ve_wh_islr_account_id and acc_wh_islr_p:
                    company.l10n_ve_wh_islr_account_id = acc_wh_islr_p
                if not company.l10n_ve_wh_islr_received_account_id and acc_wh_islr_r:
                    company.l10n_ve_wh_islr_received_account_id = acc_wh_islr_r
                if not company.l10n_ve_wh_municipal_account_id and acc_wh_mun_p:
                    company.l10n_ve_wh_municipal_account_id = acc_wh_mun_p

                # Diarios de retención
                def _get_or_create_journal(code, name, default_account):
                    j = AccountJournal.search([('code', '=', code), ('company_id', '=', company.id)], limit=1)
                    if not j:
                        try:
                            vals = {
                                'name': name,
                                'code': code,
                                'type': 'general',
                                'company_id': company.id,
                            }
                            if default_account:
                                vals['default_account_id'] = default_account.id
                            j = AccountJournal.create(vals)
                        except Exception as ex:
                            _logger.info("Venezuela360: Diario %s ya configurado o no requerido: %s", name, ex)
                            j = False
                    return j

                if not company.l10n_ve_wh_iva_journal_id:
                    j_iva = _get_or_create_journal('RIVA', 'Diario Retenciones IVA', acc_wh_iva_p)
                    if j_iva:
                        company.l10n_ve_wh_iva_journal_id = j_iva

                if not company.l10n_ve_wh_islr_journal_id:
                    j_islr = _get_or_create_journal('RISLR', 'Diario Retenciones ISLR', acc_wh_islr_p)
                    if j_islr:
                        company.l10n_ve_wh_islr_journal_id = j_islr

                if not company.l10n_ve_wh_municipal_journal_id:
                    j_mun = _get_or_create_journal('RMUN', 'Diario Retenciones Municipales', acc_wh_mun_p)
                    if j_mun:
                        company.l10n_ve_wh_municipal_journal_id = j_mun

                # 4. Catálogo de los 14 Impuestos Oficiales SENIAT
                taxes_spec = [
                    ('IVA 16% (Venta)', 'sale', 16.0, 'IVA 16%', 'tax_group_iva_general', 1),
                    ('IVA 16% (Compra)', 'purchase', 16.0, 'IVA 16%', 'tax_group_iva_general', 1),
                    ('IVA Reducido 8% (Venta)', 'sale', 8.0, 'IVA 8%', 'tax_group_iva_reducida', 2),
                    ('IVA Reducido 8% (Compra)', 'purchase', 8.0, 'IVA 8%', 'tax_group_iva_reducida', 2),
                    ('IVA Suntuario 31% (Venta)', 'sale', 31.0, 'IVA 31%', 'tax_group_iva_adicional', 3),
                    ('IVA Suntuario 31% (Compra)', 'purchase', 31.0, 'IVA 31%', 'tax_group_iva_adicional', 3),
                    ('IVA Exento (Venta)', 'sale', 0.0, 'EXENTO', 'tax_group_iva_exento', 4),
                    ('IVA Exento (Compra)', 'purchase', 0.0, 'EXENTO', 'tax_group_iva_exento', 4),
                    ('No Sujeto a IVA (Venta)', 'sale', 0.0, 'NO SUJETO', 'tax_group_no_sujeto', 5),
                    ('No Sujeto a IVA (Compra)', 'purchase', 0.0, 'NO SUJETO', 'tax_group_no_sujeto', 5),
                    ('IGTF 3% (Venta)', 'sale', 3.0, 'IGTF 3%', 'tax_group_igtf', 6),
                    ('IGTF 3% (Compra)', 'purchase', 3.0, 'IGTF 3%', 'tax_group_igtf', 6),
                    ('Retención IVA 75%', 'purchase', -75.0, 'RET IVA 75%', 'tax_group_iva_general', 10),
                    ('Retención IVA 100%', 'purchase', -100.0, 'RET IVA 100%', 'tax_group_iva_general', 11),
                ]

                created_taxes = {}
                for t_name, t_use, t_amt, t_desc, t_grp_key, t_seq in taxes_spec:
                    t_grp = groups_map.get(t_grp_key)
                    tax = AccountTax.search([
                        ('name', '=', t_name),
                        ('type_tax_use', '=', t_use),
                        ('company_id', '=', company.id)
                    ], limit=1)

                    if not tax:
                        tax_vals = {
                            'name': t_name,
                            'type_tax_use': t_use,
                            'amount_type': 'percent',
                            'amount': t_amt,
                            'description': t_desc,
                            'sequence': t_seq,
                            'active': True,
                            'company_id': company.id,
                        }
                        if t_grp:
                            tax_vals['tax_group_id'] = t_grp.id
                        try:
                            tax = AccountTax.create(tax_vals)
                            _logger.info("Venezuela360: Impuesto '%s' creado para %s.", t_name, company.name)
                        except Exception as e:
                            _logger.warning("Venezuela360: Error creando impuesto %s: %s", t_name, e)
                    else:
                        upd = {}
                        if t_grp and not tax.tax_group_id:
                            upd['tax_group_id'] = t_grp.id
                        if not tax.active:
                            upd['active'] = True
                        if upd:
                            tax.write(upd)

                    created_taxes[(t_name, t_use)] = tax

                # 5. Impuestos Predeterminados en la Compañía
                tax_sale_16 = created_taxes.get(('IVA 16% (Venta)', 'sale'))
                if tax_sale_16 and not company.account_sale_tax_id:
                    company.account_sale_tax_id = tax_sale_16

                tax_purch_16 = created_taxes.get(('IVA 16% (Compra)', 'purchase'))
                if tax_purch_16 and not company.account_purchase_tax_id:
                    company.account_purchase_tax_id = tax_purch_16

                _logger.info("Venezuela360: Inicialización contable y de impuestos completada con éxito para %s.", company.name)

            except Exception as ex:
                _logger.warning("Venezuela360: Error no crítico en _ensure_l10n_ve_chart_and_taxes para %s: %s", company.name, ex)

