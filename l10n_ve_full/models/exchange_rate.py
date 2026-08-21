# -*- coding: utf-8 -*-
"""
Venezuela360: Tasa de Cambio BCV Histórica
==========================================
Modelo: l10n_ve.exchange.rate

Registra el histórico oficial de tasas BCV (Banco Central de Venezuela)
y provee métodos de consulta por fecha para trazabilidad fiscal completa.

Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class L10nVeExchangeRate(models.Model):
    """
    Tasa de cambio histórica BCV (Bs/USD).

    Diseño:
    - Cada registro = una tasa válida para una fecha específica.
    - La tasa activa para una fecha dada se obtiene buscando el último
      registro con date <= fecha_consulta (método get_rate_for_date).
    - Soporta múltiples monedas aunque el flujo principal es Bs/USD.
    - Multi-compañía: cada empresa maneja su propio histórico.
    """
    _name = 'l10n_ve.exchange.rate'
    _description = 'Tasa de Cambio BCV Histórica'
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    # ------------------------------------------------------------------
    # Campos principales
    # ------------------------------------------------------------------
    date = fields.Date(
        string='Fecha de Vigencia',
        required=True,
        index=True,
        default=fields.Date.context_today,
        help='Fecha en la que el BCV publicó o inicia la vigencia de esta tasa.',
    )
    rate = fields.Float(
        string='Tasa (Bs/USD)',
        required=True,
        digits=(18, 6),
        help='Tasa oficial BCV expresada en Bolívares por 1 USD.',
    )
    rate_usd_to_bs = fields.Float(
        string='Bs por 1 USD',
        compute='_compute_rate_display',
        store=True,
        digits=(18, 6),
        help='Equivalente directo: cuántos Bs equivalen a 1 USD.',
    )
    rate_bs_to_usd = fields.Float(
        string='USD por 1 Bs',
        compute='_compute_rate_display',
        store=True,
        digits=(18, 10),
        help='Equivalente inverso: cuántos USD equivalen a 1 Bs.',
    )

    source = fields.Selection([
        ('bcv',     'BCV — Banco Central de Venezuela'),
        ('seniat',  'SENIAT — Tabla Oficial'),
        ('manual',  'Manual (ingresado por el usuario)'),
    ], string='Fuente', required=True, default='bcv',
       help='Fuente oficial de la tasa de cambio.')

    currency_from_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda Origen',
        required=True,
        default=lambda self: self.env.ref('base.USD', raise_if_not_found=False),
        help='Moneda de origen (generalmente USD).',
    )
    currency_to_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda Destino',
        required=True,
        default=lambda self: self.env.ref('base.VEF', raise_if_not_found=False)
                             or self.env['res.currency'].search([('name', '=', 'VES')], limit=1),
        help='Moneda de destino (Bolívar Soberano / Digital).',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    notes = fields.Text(
        string='Observaciones',
        help='Notas adicionales sobre la publicación de esta tasa.',
    )
    active = fields.Boolean(default=True)

    # ------------------------------------------------------------------
    # Campo calculado: nombre para mostrar
    # ------------------------------------------------------------------
    display_name = fields.Char(
        string='Descripción',
        compute='_compute_display_name_field',
        store=True,
    )

    # ------------------------------------------------------------------
    # SQL Constraints
    # ------------------------------------------------------------------
    _sql_constraints = [
        (
            'unique_date_company_currencies',
            'UNIQUE(date, company_id, currency_from_id, currency_to_id)',
            'Ya existe una tasa para esta fecha, compañía y par de monedas.',
        ),
    ]

    # ------------------------------------------------------------------
    # Constraints Python
    # ------------------------------------------------------------------
    @api.constrains('rate')
    def _check_rate_positive(self):
        for rec in self:
            if rec.rate <= 0:
                raise ValidationError(
                    _('La tasa de cambio debe ser mayor que cero. Valor recibido: %s') % rec.rate
                )

    @api.constrains('currency_from_id', 'currency_to_id')
    def _check_different_currencies(self):
        for rec in self:
            if rec.currency_from_id == rec.currency_to_id:
                raise ValidationError(
                    _('La moneda de origen y destino no pueden ser iguales.')
                )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('rate')
    def _compute_rate_display(self):
        for rec in self:
            rec.rate_usd_to_bs = rec.rate
            rec.rate_bs_to_usd = (1.0 / rec.rate) if rec.rate else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_res_currency_rates()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._sync_res_currency_rates()
        return res

    def _sync_res_currency_rates(self):
        """
        Sincroniza la tasa oficial BCV en res.currency.rate para Odoo nativo.
        En Odoo 17/18/19 con moneda base USD, la tasa en res.currency.rate
        para VEF/VES debe ser el valor directo (ej: 777.416100 o 60.00).
        """
        Rate = self.env['res.currency.rate']
        for rec in self:
            if rec.currency_to_id and rec.rate > 0:
                existing = Rate.search([
                    ('currency_id', '=', rec.currency_to_id.id),
                    ('name', '=', rec.date),
                    ('company_id', 'in', [rec.company_id.id, False]),
                ], limit=1)
                if existing:
                    existing.write({'rate': rec.rate})
                else:
                    Rate.create({
                        'currency_id': rec.currency_to_id.id,
                        'name': rec.date,
                        'rate': rec.rate,
                        'company_id': rec.company_id.id,
                    })

    @api.depends('date', 'rate', 'currency_from_id', 'currency_to_id')
    def _compute_display_name_field(self):
        for rec in self:
            from_name = rec.currency_from_id.name or 'N/A'
            to_name = rec.currency_to_id.name or 'N/A'
            date_str = str(rec.date) if rec.date else '?'
            rec.display_name = f'BCV {date_str} | 1 {from_name} = {rec.rate:,.6f} {to_name}'

    # ------------------------------------------------------------------
    # Métodos de negocio
    # ------------------------------------------------------------------
    @api.model
    def get_rate_for_date(self, date, company_id=None, currency_from='USD', currency_to='VES'):
        """
        Obtiene la tasa histórica más reciente para una fecha dada.

        Parámetros:
            date        : datetime.date o string 'YYYY-MM-DD'
            company_id  : int (ID de compañía). Si None, usa la compañía activa.
            currency_from: str (código de moneda origen, default 'USD')
            currency_to  : str (código de moneda destino, default 'VES'/'VEF'/'VEB')

        Retorna:
            l10n_ve.exchange.rate (record) o None si no hay tasa registrada.
        """
        company_id = company_id or self.env.company.id

        # Buscar monedas por código — tolerante con VES / VEF / VEB
        curr_from = self.env['res.currency'].search([('name', '=', currency_from)], limit=1)
        curr_to = self.env['res.currency'].search([('name', 'in', [currency_to, 'VES', 'VEF', 'VEB'])], limit=1)

        if not curr_from or not curr_to:
            _logger.warning(
                'l10n_ve.exchange.rate: No se encontraron monedas %s/%s en el sistema.',
                currency_from, currency_to
            )
            return None

        rate = self.search([
            ('date', '<=', date),
            ('company_id', '=', company_id),
            ('currency_from_id', '=', curr_from.id),
            ('currency_to_id', '=', curr_to.id),
            ('active', '=', True),
        ], order='date desc', limit=1)

        if not rate:
            _logger.warning(
                'l10n_ve.exchange.rate: Sin tasa registrada para fecha %s, compañía %s.',
                date, company_id
            )
        return rate or None

    @api.model
    def get_rate_value_for_date(self, date, company_id=None, currency_from='USD', currency_to='VES'):
        """
        Retorna directamente el valor float de la tasa (Bs/USD) para una fecha.
        Si no existe tasa, retorna 0.0 y registra un warning.
        """
        rate_record = self.get_rate_for_date(date, company_id, currency_from, currency_to)
        return rate_record.rate if rate_record else 0.0

    def convert_to_bs(self, amount_usd, date=None, company_id=None):
        """
        Convierte un monto USD a Bs usando la tasa histórica de la fecha dada.

        Parámetros:
            amount_usd : float
            date       : datetime.date (default: hoy)
            company_id : int
        Retorna:
            float (monto en Bs) o 0.0 si no hay tasa.
        """
        date = date or fields.Date.context_today(self)
        rate = self.get_rate_value_for_date(date, company_id)
        return round(amount_usd * rate, 2) if rate else 0.0

    def convert_to_usd(self, amount_bs, date=None, company_id=None):
        """
        Convierte un monto Bs a USD usando la tasa histórica de la fecha dada.
        """
        date = date or fields.Date.context_today(self)
        rate = self.get_rate_value_for_date(date, company_id)
        return round(amount_bs / rate, 6) if rate else 0.0

    @api.model
    def get_latest_rate(self, company_id=None):
        """Retorna el registro de tasa más reciente (última tasa publicada)."""
        company_id = company_id or self.env.company.id
        return self.search([
            ('company_id', '=', company_id),
            ('active', '=', True),
        ], order='date desc', limit=1)

    # ------------------------------------------------------------------
    # Sincronización Automática BCV (APIs + Cron)
    # ------------------------------------------------------------------
    @api.model
    def fetch_live_bcv_rate(self):
        """
        Consulta múltiples APIs públicas en cascada para obtener la tasa oficial BCV.

        IMPORTANTE: La tasa retornada es SIEMPRE en formato Bs/USD
        (cuántos Bolívares equivalen a 1 USD).
        Ejemplo: si el BCV publica 779.9522, retorna 779.9522

        Moneda principal del sistema: USD
        Moneda secundaria: Bs.F (VES/VEF)
        """
        import urllib.request
        import json
        import ssl

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        # ── Endpoints en orden de prioridad (5 fuentes) ──────────────────────
        # Cada parser extrae el valor en Bs/USD de la respuesta JSON
        endpoints = [
            # 1. DolarAPI Venezuela – fuente más confiable
            (
                'https://ve.dolarapi.com/v1/dolares/oficial',
                lambda d: float(d.get('promedio') or d.get('venta') or 0)
            ),
            # 2. PyDolarVenezuela API
            (
                'https://pydolarvenezuela-api.vercel.app/api/v1/dollar/unit/bcv',
                lambda d: float(d.get('price') or 0)
            ),
            # 3. ExchangeRate API (alternativa)
            (
                'https://api.exchangerate-api.com/v4/latest/USD',
                lambda d: float((d.get('rates') or {}).get('VES') or 0)
            ),
            # 4. Open Exchange Rates alternativo
            (
                'https://open.er-api.com/v6/latest/USD',
                lambda d: float((d.get('rates') or {}).get('VES') or 0)
            ),
            # 5. ExchangeRate Host
            (
                'https://api.exchangerate.host/latest?base=USD&symbols=VES',
                lambda d: float(((d.get('rates') or {}).get('VES')) or 0)
            ),
        ]

        for url, parser in endpoints:
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Venezuela360/1.0',
                        'Accept': 'application/json',
                    }
                )
                with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    rate = parser(data)
                    if rate and rate > 0:
                        _logger.info('Venezuela360: Tasa BCV obtenida desde %s: %s', url, rate)
                        return rate
            except Exception as e:
                _logger.warning('Venezuela360: No se pudo obtener tasa de %s: %s', url, e)
        return None

    @api.model
    def cron_sync_bcv_rate(self):
        """
        Sincronización automática (cron diario) de la tasa BCV oficial.

        LÓGICA DE TASAS:
        ─────────────────────────────────────────────────────────────────
        - Moneda PRINCIPAL del sistema: USD (company.currency_id = USD)
        - Moneda SECUNDARIA: Bs.F (VES/VEF)
        - La tasa BCV publica cuántos Bs equivale 1 USD (ej: 779.9522)
        - En l10n_ve.exchange.rate: se guarda rate = 779.9522 (Bs/USD)
        - En res.currency.rate: Odoo calcula la inversa automáticamente
          cuando la moneda base es USD (rate = 1/779.9522 = 0.00128211)
          PERO si la moneda base es Bs, entonces rate = 779.9522 directamente.
        ─────────────────────────────────────────────────────────────────
        """
        rate_val = self.fetch_live_bcv_rate()
        if not rate_val:
            _logger.error('Venezuela360 Cron: No se pudo obtener la tasa BCV automática.')
            return False

        # Validar que la tasa tenga sentido (debe ser > 1 para Bs/USD)
        if rate_val < 1:
            _logger.error(
                'Venezuela360 Cron: Tasa obtenida inválida (%s). '
                'Debería ser > 1 (Bs/USD). Abortando sincronización.', rate_val
            )
            return False

        today = fields.Date.context_today(self)
        companies = self.env['res.company'].search([])
        usd = self.env.ref('base.USD', raise_if_not_found=False)

        # Buscar moneda Bolívar: VES (actual) > VEF (soberano) > VEB (fuerte)
        ves = (
            self.env['res.currency'].search([('name', '=', 'VES')], limit=1)
            or self.env['res.currency'].search([('name', '=', 'VEF')], limit=1)
            or self.env['res.currency'].search([('name', '=', 'VEB')], limit=1)
        )

        if not usd or not ves:
            _logger.error(
                'Venezuela360 Cron: No se encontraron las monedas USD/VES en el sistema. '
                'Verifique que estén activas en Contabilidad → Monedas.'
            )
            return False

        _logger.info(
            'Venezuela360 Cron: Sincronizando tasa BCV %.4f Bs/USD para %d compañías...',
            rate_val, len(companies)
        )

        for company in companies:
            # ── 1. Actualizar l10n_ve.exchange.rate (tabla propia) ────────────
            existing_ve = self.search([
                ('date', '=', today),
                ('company_id', '=', company.id),
                ('currency_from_id', '=', usd.id),
                ('currency_to_id', '=', ves.id),
            ], limit=1)

            if existing_ve:
                existing_ve.write({'rate': rate_val, 'source': 'bcv'})
            else:
                self.create({
                    'date': today,
                    'rate': rate_val,
                    'source': 'bcv',
                    'currency_from_id': usd.id,
                    'currency_to_id': ves.id,
                    'company_id': company.id,
                    'notes': f'Sincronización automática BCV. Tasa: {rate_val:.4f} Bs/USD.',
                })

            # ── 2. Actualizar res.currency.rate (moneda nativa Odoo) ──────────
            # En Odoo, cuando la moneda base es USD:
            #   res.currency.rate.rate para VES = 1 / rate_val (USD por 1 Bs)
            # Cuando la moneda base es VES:
            #   res.currency.rate.rate para USD = rate_val (Bs por 1 USD) → no aplica
            #
            # Determinamos si la moneda base de la compañía es USD o VES
            company_currency = company.currency_id
            if company_currency and company_currency.name == 'USD':
                # Moneda base = USD: la rate de VES en Odoo = 1/rate_val
                odoo_rate = 1.0 / rate_val
            else:
                # Moneda base = VES/Bs: la rate del USD en Odoo = rate_val
                odoo_rate = rate_val

            # Actualizar res.currency.rate para que Odoo use la tasa correcta
            Rate = self.env['res.currency.rate']

            # Si la moneda base es USD, actualizamos la tasa de VES
            # Si la moneda base es VES, actualizamos la tasa de USD
            target_currency = ves if (company_currency and company_currency.name == 'USD') else usd

            existing_odoo = Rate.search([
                ('currency_id', '=', target_currency.id),
                ('name', '=', today),
                ('company_id', '=', company.id),
            ], limit=1)

            if existing_odoo:
                existing_odoo.write({'rate': odoo_rate})
            else:
                Rate.create({
                    'currency_id': target_currency.id,
                    'name': today,
                    'rate': odoo_rate,
                    'company_id': company.id,
                })

        _logger.info(
            'Venezuela360 Cron: ✅ Tasa BCV %.4f Bs/USD sincronizada exitosamente para %d compañías.',
            rate_val, len(companies)
        )
        return True

    def action_sync_bcv_now(self):
        """Sincroniza la tasa BCV oficial al instante (botón manual desde la vista)."""
        res = self.cron_sync_bcv_rate()
        if res:
            # Obtener la tasa actualizada para mostrarla en la notificación
            latest = self.get_latest_rate()
            rate_display = f"{latest.rate:,.4f}" if latest else "N/A"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('✅ Tasa BCV Sincronizada'),
                    'message': _(
                        'Tasa BCV oficial actualizada: %(rate)s Bs/USD\n'
                        '(1 USD = %(rate)s Bs.F)'
                    ) % {'rate': rate_display},
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            raise UserError(_(
                'No se pudo sincronizar la tasa BCV en este momento.\n'
                'Por favor verifique la conexión a internet o intente más tarde.'
            ))




