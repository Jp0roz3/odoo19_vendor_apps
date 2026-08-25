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
        Sincroniza la tasa BCV en res.currency.rate (motor de conversión nativo de Odoo).

        FÓRMULA ODOO 17+:
        ─────────────────────────────────────────────────────────────────
        conversion_rate(from, to) = to.rate / from.rate
        La moneda base (company.currency_id) siempre tiene rate implícito = 1.0.

        Caso A: base = USD, convirtiendo USD → VES:
            rate_ves / 1.0 = rate_ves → se guarda rate_ves = 779.9522 ✅

        Caso B: base = VES, convirtiendo VES → USD:
            1.0 / rate_usd = tasa → rate_usd = 1/779.9522 ✅
        ─────────────────────────────────────────────────────────────────
        """
        Rate = self.env['res.currency.rate']
        for rec in self:
            if not rec.currency_to_id or rec.rate <= 0:
                continue

            company_currency = rec.company_id.currency_id
            is_usd_base = bool(company_currency and company_currency.name == 'USD')

            # Determinar qué monedas van en res.currency.rate y con qué valor
            if is_usd_base:
                target_currencies = self.env['res.currency'].search([('name', 'in', ['VES', 'VEF', 'VEB'])])
                if not target_currencies and rec.currency_to_id:
                    target_currencies = rec.currency_to_id
                odoo_rate = rec.rate          # ej: 784.6633 Bs/USD ✅
            else:
                target_currencies = rec.currency_from_id or self.env['res.currency'].search([('name', '=', 'USD')])
                odoo_rate = (1.0 / rec.rate) if rec.rate else 0.0   # ej: 0.001274 USD/Bs ✅

            for target_currency in target_currencies:
                existing = Rate.search([
                    ('currency_id', '=', target_currency.id),
                    ('name', '=', rec.date),
                    ('company_id', 'in', [rec.company_id.id, False]),
                ], limit=1)

                if existing:
                    existing.write({'rate': odoo_rate})
                else:
                    Rate.create({
                        'currency_id': target_currency.id,
                        'name': rec.date,
                        'rate': odoo_rate,
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
        Tolera cualquier variante de moneda VES/VEF/VEB y busca la tasa más reciente registrada.
        """
        company_id = company_id or self.env.company.id
        curr_from_ids = self.env['res.currency'].search([('name', '=', currency_from)]).ids
        curr_to_ids = self.env['res.currency'].search([('name', 'in', [currency_to, 'VES', 'VEF', 'VEB'])]).ids

        domain = [
            ('date', '<=', date),
            ('active', '=', True),
        ]
        if company_id:
            domain.append(('company_id', 'in', [company_id, False]))
        if curr_from_ids:
            domain.append(('currency_from_id', 'in', curr_from_ids))
        if curr_to_ids:
            domain.append(('currency_to_id', 'in', curr_to_ids))

        rate = self.search(domain, order='date desc, write_date desc, id desc', limit=1)
        if not rate:
            # Búsqueda fallback sin restricción de par de monedas
            rate = self.search([
                ('date', '<=', date),
                ('active', '=', True),
            ], order='date desc, write_date desc, id desc', limit=1)
        return rate or None

    @api.model
    def get_rate_value_for_date(self, date, company_id=None, currency_from='USD', currency_to='VES'):
        """
        Retorna directamente el valor float de la tasa (Bs/USD) para una fecha.
        """
        rate_record = self.get_rate_for_date(date, company_id, currency_from, currency_to)
        return rate_record.rate if rate_record else 0.0

    def convert_to_bs(self, amount_usd, date=None, company_id=None):
        """
        Convierte un monto USD a Bs usando la tasa histórica de la fecha dada.
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
        """Retorna el registro de tasa más reciente (última tasa publicada activa)."""
        company_id = company_id or self.env.company.id
        curr_to_ids = self.env['res.currency'].search([('name', 'in', ['VES', 'VEF', 'VEB'])]).ids

        domain = [('active', '=', True)]
        if company_id:
            domain.append(('company_id', 'in', [company_id, False]))
        if curr_to_ids:
            domain.append(('currency_to_id', 'in', curr_to_ids))

        rate = self.search(domain, order='date desc, write_date desc, id desc', limit=1)
        if not rate:
            rate = self.search([('active', '=', True)], order='date desc, write_date desc, id desc', limit=1)
        return rate or None

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

        LÓGICA DE TASAS (Odoo 17/18/19):
        ─────────────────────────────────────────────────────────────────
        - Moneda PRINCIPAL: USD  |  Moneda SECUNDARIA: Bs.F (VES/VEF)
        - BCV publica: 1 USD = 779.9522 Bs (rate_val = 779.9522)
        - res.currency.rate.rate en Odoo 17+:
            * Si base = USD → rate para VES = 779.9522  (Bs por 1 USD)
            * Si base = VES → rate para USD = 1/779.9522 (USD por 1 Bs)
        - CRITICAL: search currencies with active_test=False para encontrar
          VES/VEF aunque estén inactivas cuando base=USD.
        ─────────────────────────────────────────────────────────────────
        """
        rate_val = self.fetch_live_bcv_rate()
        if not rate_val:
            _logger.error('Venezuela360 Cron: No se pudo obtener la tasa BCV automática.')
            return False

        # Validar dirección correcta: tasa Bs/USD debe ser > 1
        if rate_val < 1:
            _logger.error(
                'Venezuela360 Cron: Tasa inválida (%s Bs/USD). Debe ser > 1. Abortando.', rate_val
            )
            return False

        today = fields.Date.context_today(self)
        companies = self.env['res.company'].search([])

        # ── Buscar USD: siempre activo como moneda base ────────────────────────
        usd = (
            self.env.ref('base.USD', raise_if_not_found=False)
            or self.env['res.currency'].with_context(active_test=False).search(
                [('name', '=', 'USD')], limit=1
            )
        )

        # ── Buscar Bolívar con active_test=False (puede estar inactivo) ────────
        # Cuando la moneda base es USD, VES queda inactiva por defecto en Odoo.
        # CRITICAL: debemos buscarlo incluso si está inactivo.
        CurrencyModel = self.env['res.currency'].with_context(active_test=False)
        ves = (
            CurrencyModel.search([('name', '=', 'VES')], limit=1)
            or CurrencyModel.search([('name', '=', 'VEF')], limit=1)
            or CurrencyModel.search([('name', '=', 'VEB')], limit=1)
        )

        if not usd or not ves:
            _logger.error(
                'Venezuela360 Cron: No se encontraron las monedas USD/VES/VEF en la BD. '
                'Vaya a Contabilidad → Configuración → Monedas y asegúrese de que '
                'USD (dólar) y VES/VEF (bolívar) existen.'
            )
            return False

        # ── Activar VES si está inactiva (necesario para usarla como moneda secundaria) ──
        if not ves.active:
            _logger.info(
                'Venezuela360 Cron: Activando moneda %s (estaba inactiva) para sincronización BCV.',
                ves.name
            )
            ves.sudo().write({'active': True})

        _logger.info(
            'Venezuela360 Cron: Sincronizando tasa BCV %.4f %s/USD para %d compañías...',
            rate_val, ves.name, len(companies)
        )

        for company in companies:
            # ── 1. Actualizar l10n_ve.exchange.rate (tabla histórica propia) ──
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

            # ── 2. Actualizar res.currency.rate (motor de conversión Odoo) ────
            #
            # FÓRMULA ODOO 17+:
            #   conversion_rate = to_currency.rate / from_currency.rate
            #   La moneda base siempre tiene rate implícito = 1.0
            #
            #   Si base = USD (rate=1.0) y queremos 1 USD → X Bs:
            #     X = ves_rate / usd_rate → ves_rate = rate_val (779.9522)
            #
            #   Si base = VES (rate=1.0) y queremos 1 VES → Y USD:
            #     Y = usd_rate / ves_rate → usd_rate = 1/rate_val (0.001282)
            #
            company_currency = company.currency_id
            is_usd_base = bool(company_currency and company_currency.name == 'USD')

            if is_usd_base:
                # Base = USD: la rate de VES en Odoo = rate_val (ej: 779.9522)
                target_currency = ves
                odoo_rate = rate_val          # ✅ CORRECTO para Odoo 17+
            else:
                # Base = VES: la rate de USD en Odoo = 1/rate_val (ej: 0.001282)
                target_currency = usd
                odoo_rate = 1.0 / rate_val   # ✅ CORRECTO para Odoo 17+

            Rate = self.env['res.currency.rate']
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
                'Venezuela360 Cron: Compañía [%s] | Base=%s | Rate BCV=%.4f | OdooRate(%s)=%.6f',
                company.name, company_currency.name if company_currency else '?',
                rate_val, target_currency.name, odoo_rate
            )

        _logger.info(
            'Venezuela360 Cron: ✅ Tasa BCV %.4f Bs/USD sincronizada para %d compañías.',
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




