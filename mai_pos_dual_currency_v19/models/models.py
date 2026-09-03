# -*- coding: utf-8 -*-
import base64
import logging
import os
from odoo import fields, models, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    igtf_percentage = fields.Float(string="Porcentaje IGTF (%)", default=3.0)
    igtf_product_id = fields.Many2one('product.product', string="Producto para IGTF", help="Producto (Servicio) que se usará para agregar el cobro del IGTF como línea a la factura.")

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        if fields is None:
            fields = []
        fields.extend(['igtf_percentage', 'igtf_product_id'])
        return fields


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        if fields is None:
            fields = []
        for f in ('type', 'is_storable', 'qty_available', 'l10n_ve_list_price_usd', 'l10n_ve_list_price_bs'):
            if f in self._fields and f not in fields:
                fields.append(f)
        return fields

    @api.model
    def _load_pos_data_search_read(self, data, config):
        """
        Override para sobreescribir qty_available con la cantidad específica
        de la ubicación de origen del POS. Esto garantiza que el frontend
        recibe la cantidad exacta del almacén del POS.
        """
        products = super()._load_pos_data_search_read(data, config)
        if not products:
            return products

        config_rec = self.env['pos.config'].browse(config) if isinstance(config, int) else config
        location = config_rec.cstm_default_location_src_id or config_rec.picking_type_id.default_location_src_id
        prod_list = products.get('data', []) if isinstance(products, dict) else products

        if location and prod_list:
            product_ids = [p['id'] for p in prod_list if isinstance(p, dict) and 'id' in p]
            if product_ids:
                quants = self.env['stock.quant'].search_read([
                    ('product_id', 'in', product_ids),
                    ('location_id', 'child_of', location.id)
                ], ['product_id', 'quantity'])

                qty_map = {}
                for q in quants:
                    p_id = q['product_id'][0]
                    qty_map[p_id] = qty_map.get(p_id, 0.0) + q['quantity']

                _logger.info("==== POS DUAL CURRENCY: Stock QTY MAP (location=%s): %s ====", location.complete_name, qty_map)

                for p in prod_list:
                    if isinstance(p, dict) and 'id' in p:
                        p['qty_available'] = qty_map.get(p['id'], 0.0)

        if prod_list:
            for p in prod_list:
                if isinstance(p, dict) and 'id' in p:
                    usd = float(p.get('l10n_ve_list_price_usd') or 0.0)
                    bs = float(p.get('l10n_ve_list_price_bs') or 0.0)
                    lst = float(p.get('lst_price') or 0.0)
                    if not lst:
                        if usd > 0:
                            p['lst_price'] = usd
                        elif bs > 0:
                            p['lst_price'] = round(bs / 791.3248, 2)

        return products

    @api.model
    def get_pos_stock_by_location(self, product_ids, config_id):
        """
        Devuelve las cantidades disponibles en tiempo real para los productos
        indicados, filtrando por la ubicación de origen del POS.
        Llamado desde el frontend JS tras cada validación de venta.
        Retorna: { 'product': {id: qty}, 'template': {tmpl_id: qty} }
        """
        config = self.env['pos.config'].browse(config_id)
        location = (
            config.cstm_default_location_src_id
            or config.picking_type_id.default_location_src_id
        )

        # Inicializar todos en 0
        product_result = {pid: 0.0 for pid in product_ids}

        if location and product_ids:
            quants = self.env['stock.quant'].search_read([
                ('product_id', 'in', product_ids),
                ('location_id', 'child_of', location.id)
            ], ['product_id', 'quantity'])

            for q in quants:
                p_id = q['product_id'][0]
                product_result[p_id] = product_result.get(p_id, 0.0) + q['quantity']

        # Calcular totales por template
        template_result = {}
        products = self.browse(product_ids)
        for prod in products:
            tmpl_id = prod.product_tmpl_id.id
            template_result[tmpl_id] = (
                template_result.get(tmpl_id, 0.0) + product_result.get(prod.id, 0.0)
            )

        return {
            'product': product_result,
            'template': template_result,
        }


class ProductTemplate(models.Model):
    """Override product.template para inyectar la cantidad disponible
    en la ubicación de origen del POS. El ProductCard en el frontend
    usa product.template, por eso debemos sobreescribir qty_available
    a este nivel."""
    _inherit = 'product.template'

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        if fields is None:
            fields = []
        for f in ('qty_available', 'l10n_ve_list_price_usd', 'l10n_ve_list_price_bs'):
            if f in self._fields and f not in fields:
                fields.append(f)
        return fields

    @api.model
    def _load_pos_data_search_read(self, data, config):
        """
        Sobreescribe qty_available en cada product.template con la cantidad
        exacta de la ubicación de origen del POS, sumando todos los variants.
        También inyecta image_data_uri (base64 data URI) para que el frontend
        muestre la imagen directamente sin pasar por el Service Worker.
        """
        templates = super()._load_pos_data_search_read(data, config)
        if not templates:
            return templates

        config_rec = self.env['pos.config'].browse(config) if isinstance(config, int) else config
        tmpl_list = templates.get('data', []) if isinstance(templates, dict) else templates
        if not tmpl_list:
            return templates

        template_ids = [t['id'] for t in tmpl_list if isinstance(t, dict) and 'id' in t]

        # ── NUCLEAR IMAGE FIX ────────────────────────────────────────────────
        try:
            filestore = self.env['ir.attachment']._filestore()
            attachments = self.env['ir.attachment'].sudo().search_read([
                ('res_model', '=', 'product.template'),
                ('res_id', 'in', template_ids),
                ('res_field', '=', 'image_128'),
            ], ['res_id', 'store_fname', 'mimetype'])

            file_cache = {}
            img_map = {}
            for att in attachments:
                fname = att.get('store_fname')
                if fname:
                    if fname not in file_cache:
                        try:
                            fpath = os.path.join(filestore, fname)
                            with open(fpath, 'rb') as f:
                                raw = f.read()
                            mime = att.get('mimetype') or 'image/webp'
                            file_cache[fname] = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
                        except Exception as e:
                            _logger.warning("POS image read error for %s: %s", fname, e)
                            file_cache[fname] = False
                    img_map[att['res_id']] = file_cache[fname]

            for t in tmpl_list:
                if isinstance(t, dict) and 'id' in t:
                    t['image_data_uri'] = img_map.get(t['id'], False)

            loaded = sum(1 for t in tmpl_list if isinstance(t, dict) and t.get('image_data_uri'))
            _logger.info("==== POS IMAGES: %d/%d productos con imagen inyectada ====", loaded, len(tmpl_list))
        except Exception as e:
            _logger.error("POS nuclear image fix error: %s", e)
            for t in tmpl_list:
                if isinstance(t, dict):
                    t['image_data_uri'] = False
        # ── FIN NUCLEAR IMAGE FIX ────────────────────────────────────────────

        # ── STOCK QTY ────────────────────────────────────────────────────────
        location = config_rec.cstm_default_location_src_id or config_rec.picking_type_id.default_location_src_id
        if location and tmpl_list:
            all_variant_ids = []
            tmpl_to_variants = {}
            for t in tmpl_list:
                if isinstance(t, dict) and 'id' in t:
                    variant_ids = t.get('product_variant_ids', [])
                    tmpl_to_variants[t['id']] = variant_ids
                    all_variant_ids.extend(variant_ids)

            if all_variant_ids:
                quants = self.env['stock.quant'].search_read([
                    ('product_id', 'in', all_variant_ids),
                    ('location_id', 'child_of', location.id)
                ], ['product_id', 'quantity'])

                variant_qty_map = {}
                for q in quants:
                    p_id = q['product_id'][0]
                    variant_qty_map[p_id] = variant_qty_map.get(p_id, 0.0) + q['quantity']

                _logger.info("==== POS TEMPLATE Stock QTY MAP (loc=%s): %s ====", location.complete_name, variant_qty_map)

                for t in tmpl_list:
                    if isinstance(t, dict) and 'id' in t:
                        variant_ids = tmpl_to_variants.get(t['id'], [])
                        total_qty = sum(variant_qty_map.get(v_id, 0.0) for v_id in variant_ids)
                        t['qty_available'] = total_qty

        if tmpl_list:
            for t in tmpl_list:
                if isinstance(t, dict) and 'id' in t:
                    usd = float(t.get('l10n_ve_list_price_usd') or 0.0)
                    bs = float(t.get('l10n_ve_list_price_bs') or 0.0)
                    lst = float(t.get('list_price') or 0.0)
                    if not lst:
                        if usd > 0:
                            t['list_price'] = usd
                        elif bs > 0:
                            t['list_price'] = round(bs / 791.3248, 2)

        return templates


class AccountTaxGroup(models.Model):
    _inherit = 'account.tax.group'

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id) if hasattr(super(), '_load_pos_data_fields') else []
        if fields is None:
            fields = []
        for f in ('name', 'pos_receipt_label', 'country_id'):
            if f in self._fields and f not in fields:
                fields.append(f)
        return fields

    @api.model
    def _load_pos_data_search_read(self, data, config):
        fields = ['name', 'pos_receipt_label']
        tax_groups = self.env['account.tax.group'].search_read([], fields)
        for tg in tax_groups:
            if not tg.get('pos_receipt_label'):
                tg['pos_receipt_label'] = tg.get('name') or 'IVA'
        return tax_groups


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    pago_usd = fields.Boolean(
        "Moneda secundaria",
        help="Seleccione si este método de pago opera en moneda secundaria (ej. USD cuando la caja es en Bs)"
    )
    is_igtf = fields.Boolean(
        "Aplica IGTF",
        help="Seleccione si los pagos con este método deben cobrar el Impuesto IGTF (ej. Divisas en efectivo)."
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        fields.extend(['pago_usd', 'is_igtf'])
        return fields


class PosPayment(models.Model):
    _inherit = "pos.payment"

    usd_amt = fields.Float("Monto USD $", digits=(16, 2))

    # ── Campos computados para la vista de doble moneda ────────────────────────
    tasa_sesion = fields.Float(
        string="Tasa Sesión",
        compute="_compute_dual_currency",
        store=True,
        digits=(16, 4),
    )
    importe_bs = fields.Float(
        string="Importe Bs.F",
        compute="_compute_dual_currency",
        store=True,
        digits=(16, 2),
    )
    importe_usd = fields.Float(
        string="Monto Ref $",
        compute="_compute_dual_currency",
        store=True,
        digits=(16, 2),
    )

    importe_bs_str = fields.Char(
        string="Importe Bs.F",
        compute="_compute_dual_currency_str",
    )
    importe_usd_str = fields.Char(
        string="Monto Ref $",
        compute="_compute_dual_currency_str",
    )

    @api.depends('importe_bs', 'importe_usd', 'session_id.config_id.show_currency_symbol')
    def _compute_dual_currency_str(self):
        for payment in self:
            config = payment.session_id.config_id
            if config and config.show_dual_currency:
                bs_val = payment.importe_bs or 0.0
                usd_val = payment.importe_usd or 0.0

                bs_fmt = f"{bs_val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                usd_fmt = f"{usd_val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

                # Forzamos los símbolos correctos independientemente de la configuración de Odoo
                payment.importe_bs_str = f"Bs.F {bs_fmt}"
                payment.importe_usd_str = f"$ {usd_fmt}"
            else:
                payment.importe_bs_str = ""
                payment.importe_usd_str = ""

    # FIX: agregado 'payment_method_id.pago_usd' al depends para recomputar si cambia
    @api.depends('amount', 'payment_method_id', 'payment_method_id.pago_usd', 'session_id')
    def _compute_dual_currency(self):
        for payment in self:
            config = payment.session_id.config_id
            rate = float(config.show_currency_rate or 0.0)
            payment.tasa_sesion = rate

            amount = payment.amount or 0.0

            if rate > 0:
                main_currency = config.currency_id
                main_name = main_currency.name or ''
                is_main_usd = 'USD' in main_name or '$' in main_name
                
                if is_main_usd:
                    # Main is USD: amount = USD, Bs = USD × rate
                    payment.importe_usd = amount
                    payment.importe_bs  = amount * rate
                else:
                    # Main is Bs.F: amount = Bs.F, USD = Bs / rate
                    payment.importe_bs  = amount
                    if rate > 1:
                        payment.importe_usd = amount / rate
                    else:
                        payment.importe_usd = amount * rate if rate else 0.0
            else:
                payment.importe_bs  = amount
                payment.importe_usd = payment.usd_amt or 0.0


class PosOrder(models.Model):
    _inherit = "pos.order"

    is_fiscal_printed = fields.Boolean("Impreso Fiscalmente", default=False, readonly=True)
    fiscal_invoice_number = fields.Char("Factura Fiscal", readonly=True, help="Número de factura legal emitido por la máquina fiscal")
    credit_note_number = fields.Char("Nota de Crédito Fiscal", readonly=True, help="Número de nota de crédito legal emitido por la máquina fiscal")
    fiscal_machine_serial = fields.Char("Serial Máquina Fiscal", readonly=True, help="Serial de la máquina que emitió el documento fiscal")
    igtf_charge = fields.Float("Cargo IGTF", digits=(16, 2), default=0.0)

    @api.model
    def _payment_fields(self, order, ui_paymentline):
        res = super()._payment_fields(order, ui_paymentline)
        res.update({
            'usd_amt': ui_paymentline.get('usd_amt') or 0.0,
        })
        return res

    @api.model
    def _order_fields(self, ui_order):
        res = super()._order_fields(ui_order)
        res.update({
            'is_fiscal_printed': ui_order.get('is_fiscal_printed') or False,
            'fiscal_invoice_number': ui_order.get('fiscal_invoice_number') or '',
            'credit_note_number': ui_order.get('credit_note_number') or '',
            'fiscal_machine_serial': ui_order.get('fiscal_machine_serial') or '',
            'igtf_charge': ui_order.get('igtf_charge') or 0.0,
        })
        return res

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()
        vals.update({
            'fiscal_invoice_number': self.fiscal_invoice_number,
            'fiscal_machine_serial': self.fiscal_machine_serial,
            'credit_note_number': self.credit_note_number,
        })
        return vals

    def _create_misc_journal_entry(self):
        """Override: after the POS session creates the grouped journal entry,
        force-attach the IGTF tax to any invoice line that belongs to the
        IGTF product. This is what makes l10n_ve_igtf_perceived_report
        pick up the amounts."""
        res = super()._create_misc_journal_entry()
        self._inject_igtf_tax_on_move_lines()
        return res

    def _inject_igtf_tax_on_move_lines(self):
        """Find the IGTF product and attach the corresponding account.tax
        to every account.move.line that came from that product, so the
        Venezuelan IGTF tax report can aggregate them correctly."""
        igtf_product = self.env['res.company'].browse(
            self.env.company.id
        ).igtf_product_id
        if not igtf_product:
            _logger.warning('[IGTF] igtf_product_id not configured on company — skipping tax injection')
            return

        # Search for an account.tax named or tagged as IGTF
        igtf_tax = self.env['account.tax'].search([
            ('company_id', '=', self.env.company.id),
            '|',
            ('name', 'ilike', 'IGTF'),
            ('description', 'ilike', 'IGTF'),
        ], limit=1)

        if not igtf_tax:
            _logger.warning('[IGTF] No account.tax with name/description containing "IGTF" found — report will stay empty')
            return

        # Walk all POS orders that have igtf_charge and find their account.move lines
        for order in self:
            if not order.igtf_charge:
                continue
            if not order.account_move:
                continue
            for line in order.account_move.line_ids:
                if line.product_id and line.product_id.id == igtf_product.id:
                    if igtf_tax not in line.tax_ids:
                        try:
                            line.with_context(check_move_validity=False).write({
                                'tax_ids': [(4, igtf_tax.id)]
                            })
                            _logger.info('[IGTF] Tax %s injected into move line %s (order %s)',
                                         igtf_tax.name, line.id, order.name)
                        except Exception as e:
                            _logger.warning('[IGTF] Could not inject tax on line %s: %s', line.id, e)


class PosSession(models.Model):
    _inherit = 'pos.session'

    # ── Apertura dual ──────────────────────────────────────────────────────────
    opening_cash_bs  = fields.Float(
        string="Apertura Bs.F",
        digits=(16, 2),
        default=0.0,
        help="Efectivo inicial en Bolívares declarado al abrir la caja"
    )
    opening_cash_usd = fields.Float(
        string="Apertura USD $",
        digits=(16, 2),
        default=0.0,
        help="Efectivo inicial en Dólares declarado al abrir la caja"
    )
    opening_pm_bs = fields.Float(
        string="Apertura Pago Móvil (Bs.F)",
        digits=(16, 2),
        default=0.0,
        help="Saldo inicial en Pago Móvil declarado al abrir la caja"
    )

    # ── Cierre dual ───────────────────────────────────────────────────────────
    closing_cash_bs  = fields.Float(
        string="Cierre Bs.F",
        digits=(16, 2),
        default=0.0,
        help="Efectivo en Bolívares contado al cerrar la caja"
    )
    closing_cash_usd = fields.Float(
        string="Cierre USD $",
        digits=(16, 2),
        default=0.0,
        help="Efectivo en Dólares contado al cerrar la caja"
    )
    closing_pm_bs = fields.Float(
        string="Cierre Pago Móvil (Bs.F)",
        digits=(16, 2),
        default=0.0,
        help="Saldo en Pago Móvil contado al cerrar la caja"
    )

    # ── Totales IGTF de sesión ────────────────────────────────────────────────
    igtf_total_bs = fields.Float(
        string="Total IGTF Bs.F",
        compute="_compute_igtf_session_totals",
        store=True,
        digits=(16, 2),
        help="Suma de todos los cargos IGTF de las órdenes de esta sesión, en Bs.F"
    )
    igtf_total_usd = fields.Float(
        string="Total IGTF USD $",
        compute="_compute_igtf_session_totals",
        store=True,
        digits=(16, 2),
        help="Suma de todos los cargos IGTF de las órdenes de esta sesión, en USD"
    )

    @api.depends('order_ids.igtf_charge', 'config_id.show_currency_rate')
    def _compute_igtf_session_totals(self):
        """Suma igtf_charge (que está almacenado en Bs.F, la moneda principal)
        de todas las órdenes pagadas y calcula el equivalente en USD."""
        for session in self:
            total_bs = sum(o.igtf_charge for o in session.order_ids if o.igtf_charge)
            rate = session.config_id.show_currency_rate or 0.0
            is_main_usd = session.config_id.currency_id.name == 'USD'

            if is_main_usd:
                # igtf_charge está en USD (moneda principal)
                session.igtf_total_usd = total_bs
                # rate en is_main_usd es Bs por 1 USD
                session.igtf_total_bs = total_bs * rate if rate else 0.0
            else:
                # igtf_charge está en Bs.F (moneda principal)
                session.igtf_total_bs = total_bs
                # OJO: Si config_id.show_currency_rate es > 1 (e.g. 737.23 Bs / USD), para sacar USD dividimos.
                # Pero en Odoo nativo la tasa de USD suele ser 0.001356 (1 / 737.23).
                # Vamos a manejar ambos casos dinámicamente para ser a prueba de balas:
                if rate > 0:
                    if rate > 1:
                        # rate es 737.23 Bs/$
                        session.igtf_total_usd = total_bs / rate
                    else:
                        # rate es 0.001356 $/Bs
                        session.igtf_total_usd = total_bs * rate
                else:
                    session.igtf_total_usd = 0.0

    dual_balance_start = fields.Char(string="Saldo inicial", compute="_compute_dual_balances")
    dual_balance_end = fields.Char(string="Saldo final", compute="_compute_dual_balances")


    def _compute_dual_balances(self):
        for session in self:
            config = session.config_id
            main_sym = config.currency_id.symbol or '$'
            sec_sym  = config.show_currency_symbol or 'Bs.F'

            def _fmt(v):
                return f"{v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

            usd_start = session.opening_cash_usd or 0.0
            bs_start  = session.opening_cash_bs or 0.0
            session.dual_balance_start = f"{main_sym} {_fmt(usd_start)} / {sec_sym} {_fmt(bs_start)}"

            usd_end = session.closing_cash_usd or 0.0
            bs_end  = session.closing_cash_bs or 0.0
            
            is_main_usd = config.currency_id.name == 'USD'
            
            if is_main_usd:
                session.dual_balance_start = f"{main_sym} {_fmt(usd_start)} / {sec_sym} {_fmt(bs_start)}"
                session.dual_balance_end   = f"{main_sym} {_fmt(usd_end)} / {sec_sym} {_fmt(bs_end)}"
            else:
                session.dual_balance_start = f"{main_sym} {_fmt(bs_start)} / {sec_sym} {_fmt(usd_start)}"
                session.dual_balance_end   = f"{main_sym} {_fmt(bs_end)} / {sec_sym} {_fmt(usd_end)}"

    # -------------------------------------------------------------------------
    # DEPENDS
    # -------------------------------------------------------------------------
    @api.depends('config_id', 'payment_method_ids')
    def _compute_cash_journal(self):
        super()._compute_cash_journal()
        for session in self:
            is_main_usd = session.config_id.currency_id.name == 'USD'
            for pm in session.payment_method_ids:
                if not pm.is_cash_count: continue
                pm_name = pm.name.lower()
                is_bs = 'bs' in pm_name or 'bolivar' in pm_name or 'bolívar' in pm_name
                is_usd = '$' in pm_name or 'usd' in pm_name or 'dolar' in pm_name or 'dólar' in pm_name
                
                if is_main_usd and is_usd:
                    session.cash_journal_id = pm.journal_id
                    break
                if not is_main_usd and is_bs:
                    session.cash_journal_id = pm.journal_id
                    break

    def _load_pos_data_fields(self, config):
        config_rec = self.env['pos.config'].browse(config) if isinstance(config, int) else config
        # --- PROTECCIÓN Y AUTO-ACTIVACIÓN DE LICENCIA POR CAMBIO DE BASE DE DATOS ---
        import hashlib
        db_name = self.env.cr.dbname
        secret_salt = "MAI_POS_NUBELCO_2026"
        hash_obj = hashlib.md5((db_name + secret_salt).encode('utf-8'))
        expected_key = hash_obj.hexdigest().upper()[:16]
        
        if config_rec and getattr(config_rec, 'show_dual_currency', False):
            if not config_rec.mai_license_key or config_rec.mai_license_key.strip() != expected_key:
                _logger.info("⚡ MAI POS Dual Currency: Auto-actualizando clave de licencia para la base de datos '%s' -> Key '%s'", db_name, expected_key)
                try:
                    config_rec.sudo().write({'mai_license_key': expected_key})
                except Exception as e:
                    _logger.warning("No se pudo escribir mai_license_key: %s", e)

        fields = super()._load_pos_data_fields(config)
        if fields is None:
            fields = []
        fields.extend([
            'opening_cash_bs',
            'opening_cash_usd',
            'closing_cash_bs',
            'closing_cash_usd',
            'opening_pm_bs',
            'closing_pm_bs',
        ])
        return fields

    def set_dual_opening_cash(self, bs_amount, usd_amount, pm_bs_amount=0.0):
        """RPC method called from JS when cashier confirms opening amounts."""
        self.ensure_one()
        self.sudo().write({
            'opening_cash_bs':  float(bs_amount or 0.0),
            'opening_cash_usd': float(usd_amount or 0.0),
            'opening_pm_bs': float(pm_bs_amount or 0.0),
        })
        return True

    def set_dual_closing_cash(self, bs_amount, usd_amount, pm_bs_amount=0.0):
        """RPC method called from JS when cashier confirms closing amounts.
        Uses a savepoint to avoid serialization conflicts with native Odoo closing."""
        self.ensure_one()
        try:
            self.sudo().with_context(mail_notrack=True).write({
                'closing_cash_bs':  float(bs_amount or 0.0),
                'closing_cash_usd': float(usd_amount or 0.0),
                'closing_pm_bs': float(pm_bs_amount or 0.0),
            })
        except Exception as e:
            _logger.warning('[DualCurrency] set_dual_closing_cash failed (non-critical): %s', e)
        return True

    def try_bs_cash_in_out(self, _type, amount, reason, extras):
        """Custom RPC method to register Cash In/Out in Secondary Currency."""
        sign = 1 if _type == 'in' else -1
        for session in self:
            is_main_usd = session.config_id.currency_id.name == 'USD'
            bs_journal = False
            for pm in session.payment_method_ids:
                if not pm.is_cash_count: continue
                pm_name = pm.name.lower()
                is_bs = 'bs' in pm_name or 'bolivar' in pm_name or 'bolívar' in pm_name
                is_usd = '$' in pm_name or 'usd' in pm_name or 'dolar' in pm_name or 'dólar' in pm_name
                
                # We want the SECONDARY currency
                if is_main_usd and is_bs:
                    bs_journal = pm.journal_id
                    break
                if not is_main_usd and is_usd:
                    bs_journal = pm.journal_id
                    break
            
            if not bs_journal:
                # Fallback to the old logic if names don't match
                fallback_pm = session.payment_method_ids.filtered(lambda p: p.is_cash_count and p.pago_usd)
                if fallback_pm:
                    bs_journal = fallback_pm[0].journal_id

            if not bs_journal:
                raise UserError("No se encontró un método de pago secundario configurado.")

            self.env['account.bank.statement.line'].create({
                'pos_session_id': session.id,
                'journal_id': bs_journal.id,
                'amount': sign * amount,
                'date': fields.Date.context_today(self),
                'payment_ref': '-'.join([session.name, extras.get('translatedType', _type), reason]),
            })
        return True

    def get_closing_control_data(self):
        res = super().get_closing_control_data()
        
        cash_pms = self.payment_method_ids.filtered(lambda pm: pm.type == 'cash')
        if not cash_pms:
            return res
            
        default_pm = cash_pms[0]
        
        # Group statement lines by journal
        lines_by_journal = {}
        for line in self.sudo().statement_line_ids:
            if line.journal_id.id not in lines_by_journal:
                lines_by_journal[line.journal_id.id] = []
            lines_by_journal[line.journal_id.id].append(line)
            
        # Helper to generate the 'moves' list for a journal without converting amounts
        def _get_moves_for_journal(journal_id):
            lines = lines_by_journal.get(journal_id, [])
            moves = []
            cash_in_count = 0
            cash_out_count = 0
            for line in sorted(lines, key=lambda l: l.create_date):
                if line.amount > 0:
                    cash_in_count += 1
                    name = f'Cash in {cash_in_count}'
                else:
                    cash_out_count += 1
                    name = f'Cash out {cash_out_count}'
                if line.pos_session_id:
                    name = '%s - %s' % (name, line.pos_session_id.name)
                elif line.payment_id:
                    name = '%s - %s' % (name, line.payment_id.name)
                moves.append({
                    'name': name,
                    'amount': line.amount,
                })
            return moves

        # Correct default_cash_details
        if res.get('default_cash_details'):
            journal_id = default_pm.journal_id.id
            lines = lines_by_journal.get(journal_id, [])
            sum_lines = sum(l.amount for l in lines)
            res['default_cash_details']['moves'] = _get_moves_for_journal(journal_id)
            # Recompute amount: Opening + Payments + Sum of lines for THIS journal only
            res['default_cash_details']['amount'] = (
                res['default_cash_details'].get('opening', 0) +
                res['default_cash_details'].get('payment_amount', 0) +
                sum_lines
            )

        # Fix other cash payment methods in non_cash_payment_methods
        for pm_dict in res.get('non_cash_payment_methods', []):
            if pm_dict.get('type') == 'cash':
                pm = self.payment_method_ids.browse(pm_dict['id'])
                if pm.exists():
                    journal_id = pm.journal_id.id
                    lines = lines_by_journal.get(journal_id, [])
                    sum_lines = sum(l.amount for l in lines)
                    pm_dict['moves'] = _get_moves_for_journal(journal_id)
                    pm_dict['cash_moves_amount'] = sum_lines

        return res

    def get_cash_in_out_list(self):
        res = super().get_cash_in_out_list()
        for move in res:
            move_id = move.get('id')
            if move_id:
                statement_line = self.env['account.bank.statement.line'].browse(move_id)
                if statement_line.exists():
                    pm = self.payment_method_ids.filtered(lambda p: p.journal_id == statement_line.journal_id)
                    is_bs = False
                    is_usd = False
                    if pm:
                        p = pm[0]
                        pm_name = p.name.lower()
                        if '$' in pm_name or 'usd' in pm_name or 'dolar' in pm_name or 'dólar' in pm_name:
                            is_usd = True
                        elif 'bs' in pm_name or 'bolivar' in pm_name or 'bolívar' in pm_name:
                            is_bs = True
                        else:
                            is_usd = p.pago_usd
                            is_bs = not p.pago_usd
                    move['is_usd'] = is_usd
                    move['is_bs'] = is_bs
        return res

    def compute_z_report_totals(self):
        """
        RPC method llamado desde el frontend JS (ClosePosPopup.js) al imprimir el Reporte Z.
        Calcula los totales fiscales de la sesión sobre las órdenes marcadas como
        is_fiscal_printed=True, devolviendo base imponible, IVA, total e IGTF
        en la moneda principal del POS.

        Retorna un dict con:
            taxable_main  -- Base imponible gravada (sin IVA)
            tax_main      -- Monto de IVA
            total_main    -- Total general (base + IVA)
            igtf_main     -- Cargo IGTF acumulado
        """
        self.ensure_one()
        _logger.info("[Z-Report] compute_z_report_totals para sesion %s", self.name)

        taxable_main = 0.0
        tax_main = 0.0
        total_main = 0.0
        igtf_main = 0.0

        fiscal_orders = self.order_ids.filtered(lambda o: o.is_fiscal_printed)
        _logger.info("[Z-Report] Ordenes fiscales encontradas: %d", len(fiscal_orders))

        for order in fiscal_orders:
            order_total = order.amount_total or 0.0
            order_tax = order.amount_tax or 0.0
            order_excl = order_total - order_tax
            order_igtf = order.igtf_charge or 0.0

            # Los reembolsos (refunds) tienen amount_total positivo en la BD
            # pero deben restarse del acumulado fiscal.
            if order.amount_total < 0:
                # Ya viene negativo — sumamos directamente
                taxable_main += order_excl
                tax_main += order_tax
                total_main += order_total
                igtf_main += order_igtf
            else:
                taxable_main += order_excl
                tax_main += order_tax
                total_main += order_total
                igtf_main += order_igtf

        result = {
            'taxable_main': round(taxable_main, 2),
            'tax_main': round(tax_main, 2),
            'total_main': round(total_main, 2),
            'igtf_main': round(igtf_main, 2),
        }
        _logger.info("[Z-Report] Totales calculados: %s", result)
        return result


class PosConfig(models.Model):
    _inherit = "pos.config"

    mai_license_key      = fields.Char("Clave de Activación", default="", help="Clave de activación para proteger el módulo contra uso no autorizado.")
    
    show_dual_currency   = fields.Boolean("Mostrar doble moneda", default=False)
    show_currency         = fields.Many2one(
        'res.currency', string='Moneda secundaria',
        default=lambda self: self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
    )
    show_currency_rate   = fields.Float(string='Tasa Bs/$', related='show_currency.rate', store=True, readonly=False)
    show_currency_symbol = fields.Char(related='show_currency.symbol', store=True, readonly=False)
    show_currency_position = fields.Selection(related='show_currency.position', store=True)
    rate_company = fields.Float(
        string='Tasa de Compa\'ia',
        related='company_id.currency_id.rate',
        readonly=True,
        digits=(12, 6)
    )
    cstm_default_location_src_id = fields.Many2one(
        "stock.location", related="picking_type_id.default_location_src_id"
    )

    # ── Campos de balance del último cierre (para el Kanban) ──────────────────
    last_session_dual_balance_str = fields.Char(compute='_compute_last_session_dual_balance')
    # Campos separados para mostrar USD y Bs.F con colores distintos en el Kanban
    last_session_usd_str = fields.Char(compute='_compute_last_session_dual_balance')
    last_session_bs_str  = fields.Char(compute='_compute_last_session_dual_balance')

    @api.model
    def _load_pos_data_read(self, records, config):
        """Inyectar campos de doble moneda y forzar show_product_images=True."""
        read_records = super()._load_pos_data_read(records, config)
        if not read_records:
            return read_records

        rec_list = read_records.get('data', []) if isinstance(read_records, dict) else read_records
        if not rec_list:
            return read_records

        try:
            config_rec = self.env['pos.config'].browse(config) if isinstance(config, int) else config

            # Forzar imágenes de producto siempre visibles en el POS
            for r in rec_list:
                if isinstance(r, dict):
                    r['show_product_images'] = True

            record = rec_list[0]
            if isinstance(record, dict) and config_rec and config_rec.exists():
                show_curr = getattr(config_rec, 'show_currency', False)
                show_curr_id = show_curr.id if show_curr else False
                show_curr_sym = (show_curr.symbol if show_curr else 'Bs.F') or 'Bs.F'
                show_curr_pos = (show_curr.position if show_curr else 'before') or 'before'
                show_curr_rate = getattr(config_rec, 'show_currency_rate', 1.0) or 1.0
                rate_comp = getattr(config_rec, 'rate_company', 1.0) or 1.0

                record['show_dual_currency']        = bool(getattr(config_rec, 'show_dual_currency', False))
                record['rate_company']              = rate_comp
                record['show_currency_rate']        = show_curr_rate
                record['show_currency_symbol']      = show_curr_sym
                record['show_currency_position']    = show_curr_pos
                record['show_currency']             = show_curr_id
                record['mai_license_key']           = getattr(config_rec, 'mai_license_key', '') or ''
        except Exception as e:
            _logger.error("Error en PosConfig._load_pos_data_read: %s", e)

        return read_records

    def _compute_last_session_dual_balance(self):
        for pos_config in self:
            session = self.env['pos.session'].search_read(
                [('config_id', '=', pos_config.id), ('state', '=', 'closed')],
                ['closing_cash_bs', 'closing_cash_usd'],
                order="stop_at desc", limit=1)

            if session and pos_config.show_dual_currency:
                bs  = session[0].get('closing_cash_bs', 0.0)
                usd = session[0].get('closing_cash_usd', 0.0)

                # Formato venezolano: 1.234,56
                def _fmt(v):
                    return f"{v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

                is_main_usd = pos_config.currency_id.name == 'USD'
                
                if is_main_usd:
                    main_sym = '$'
                    sec_sym = 'Bs'
                    native_amt = usd
                    sec_amt = bs
                else:
                    main_sym = pos_config.currency_id.symbol or 'Bs'
                    sec_sym = pos_config.show_currency_symbol or '$'
                    native_amt = bs
                    sec_amt = usd

                main_str = f"{main_sym} {_fmt(native_amt)}"
                sec_str = f"{sec_sym} {_fmt(sec_amt)}"

                # Compatibilidad con los campos de la vista Kanban (bs_str = negro, usd_str = rojo)
                pos_config.last_session_dual_balance_str = f"{main_str} | {sec_str}"
                pos_config.last_session_bs_str  = main_str
                pos_config.last_session_usd_str = sec_str
            else:
                pos_config.last_session_dual_balance_str = ''
                pos_config.last_session_usd_str = ''
                pos_config.last_session_bs_str  = ''



    def get_statistics_for_session(self, session):
        """Override to provide dual currency opening cash data to the Kanban dashboard."""
        statistics = super().get_statistics_for_session(session)
        
        if self.show_dual_currency:
            if 'cash' in statistics:
                bs  = session.opening_cash_bs or 0.0
                usd = session.opening_cash_usd or 0.0
                
                def _fmt(v):
                    return f"{v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

                main_sym = self.currency_id.symbol or '$'
                sec_sym  = self.show_currency_symbol or 'Bs.F'
                
                statistics['cash']['opening_cash_dual'] = True
                
                native_amt = usd
                sec_amt = bs
                
                statistics['cash']['opening_cash_bs'] = f"{main_sym} {_fmt(native_amt)}"
                statistics['cash']['opening_cash_usd'] = f"{sec_sym} {_fmt(sec_amt)}"
                
            # Hide the "Sold" (Vendido) and "Draft" lines from the Kanban view
            if 'orders' in statistics:
                statistics['orders']['paid'] = False
                statistics['orders']['draft'] = False
            
        return statistics


class ResConfigSettings(models.TransientModel):
    """Herencia consolidada de res.config.settings — todos los campos del módulo en una sola clase."""
    _inherit = 'res.config.settings'

    # ── IGTF ──────────────────────────────────────────────────────────────────
    igtf_percentage = fields.Float(related='company_id.igtf_percentage', readonly=False)
    igtf_product_id = fields.Many2one(related='company_id.igtf_product_id', readonly=False)

    def action_create_igtf_product(self):
        """Crea el producto IGTF sorteando las validaciones de las localizaciones contables (asignando precio 0.01)."""
        Product = self.env['product.product']
        
        # Buscar si ya existe un producto IGTF
        igtf_product = Product.search([('name', '=', 'IGTF 3%')], limit=1)
        
        if not igtf_product:
            igtf_product = Product.create({
                'name': 'IGTF 3%',
                'type': 'service',
                'available_in_pos': True,
                'list_price': 0.01,
                'taxes_id': [(5, 0, 0)], # Vaciar impuestos para que no haya IVA
                'supplier_taxes_id': [(5, 0, 0)],
            })
            
        # Asignarlo a la configuración
        self.igtf_product_id = igtf_product.id
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Producto Creado',
                'message': 'El producto IGTF 3% ha sido creado y asignado exitosamente (con precio 0.01 para burlar validaciones de localización).',
                'type': 'success',
                'sticky': False,
            }
        }

    # ── Licencia y configuración POS ──────────────────────────────────────────
    mai_license_key       = fields.Char(related='pos_config_id.mai_license_key', readonly=False)
    show_dual_currency    = fields.Boolean(related='pos_config_id.show_dual_currency', readonly=False)
    rate_company          = fields.Float(related='pos_config_id.rate_company', readonly=False)
    show_currency         = fields.Many2one(related='pos_config_id.show_currency', readonly=False)
    show_currency_rate    = fields.Float(related='pos_config_id.show_currency_rate', readonly=False)
    show_currency_symbol  = fields.Char(related='pos_config_id.show_currency_symbol', readonly=False)
    show_currency_position = fields.Selection(related='pos_config_id.show_currency_position', readonly=False)
    cstm_default_location_src_id = fields.Many2one(
        related='pos_config_id.cstm_default_location_src_id', readonly=False
    )


class AccountMove(models.Model):
    _inherit = "account.move"

    currency_rate    = fields.Monetary(
        string='Tasa', compute='_compute_currency_amount', currency_field='vef_currency_id'
    )
    impuesto_en_vef  = fields.Monetary(
        string='Impuesto en USD', compute='_compute_currency_amount', currency_field='vef_currency_id'
    )
    total_amount_vef = fields.Monetary(
        string='Total en USD', compute='_compute_currency_amount', currency_field='vef_currency_id'
    )
    vef_currency_id  = fields.Many2one(
        'res.currency', 'Moneda Bs',
        default=lambda self: self.env.ref('base.VEF', raise_if_not_found=False)
    )
    usd_currency_id  = fields.Many2one(
        'res.currency', 'Moneda USD',
        default=lambda self: self.env.ref('base.USD', raise_if_not_found=False)
    )

    @api.onchange('vef_currency_id')
    def onchange_vef_currency(self):
        # FIX: api.onchange siempre opera sobre 1 registro, no necesita for loop
        self.currency_id = self.vef_currency_id.id

    def _compute_currency_amount(self):
        for move in self:
            move.currency_rate = 0.0
            move.impuesto_en_vef = 0.0
            move.total_amount_vef = 0.0
            if not move.vef_currency_id:
                continue
            date = move.invoice_date or (move.create_date.date() if move.create_date else False)
            if not date:
                continue
            domain = [
                ('currency_id', '=', move.vef_currency_id.id),
                ('name', '<=', date),
            ]
            if move.company_id:
                domain += ['|', ('company_id', '=', False), ('company_id', '=', move.company_id.id)]
                
            rate_rec = self.env['res.currency.rate'].search(domain, order='name desc', limit=1)
            
            if not rate_rec:
                fallback_domain = [('currency_id', '=', move.vef_currency_id.id)]
                if move.company_id:
                    fallback_domain += ['|', ('company_id', '=', False), ('company_id', '=', move.company_id.id)]
                rate_rec = self.env['res.currency.rate'].search(fallback_domain, order='name asc', limit=1)

            currency_rate = rate_rec.rate if rate_rec else 0.0

            if not currency_rate:
                continue
            move.currency_rate = currency_rate
            try:
                move.impuesto_en_vef = move.amount_tax_signed / currency_rate
            except Exception:
                pass
            try:
                move.total_amount_vef = move.amount_total_signed / currency_rate
            except Exception:
                pass

class PosFiscalZReport(models.Model):
    _name = 'pos.fiscal.z.report'
    _description = 'Reporte Z Diario Fiscal'

    name = fields.Char(string='Referencia Interna', compute='_compute_name', store=True)
    pos_config_id = fields.Many2one('pos.config', string='Punto de Venta', required=True, ondelete='cascade')
    z_number = fields.Integer(string='Número Z', required=True)
    date = fields.Date(string='Fecha Última', default=fields.Date.context_today)
    time = fields.Char(string='Hora Última')
    
    first_invoice_number = fields.Integer(string='Número Inicial (Factura)')
    last_invoice_number = fields.Integer(string='Última Factura')
    
    # 💰 Montos en USD (Base) 💰
    exempt_sales_usd = fields.Float(string='Ventas Exentas ($)', digits=(16, 2))
    taxable_sales_usd = fields.Float(string='Base Imponible ($)', digits=(16, 2))
    tax_amount_usd = fields.Float(string='Impuesto ($)', digits=(16, 2))
    igtf_amount_usd = fields.Float(string='IGTF ($)', digits=(16, 2))
    total_sales_usd = fields.Float(string='Total Ventas ($)', digits=(16, 2))

    # 💰 Montos en Bs.F (Legal) 💰
    exempt_sales_bs = fields.Float(string='Ventas Exentas (Bs.F)', digits=(16, 2))
    taxable_sales_bs = fields.Float(string='Base Imponible (Bs.F)', digits=(16, 2))
    tax_amount_bs = fields.Float(string='Impuesto (Bs.F)', digits=(16, 2))
    igtf_amount_bs = fields.Float(string='IGTF (Bs.F)', digits=(16, 2))
    total_sales_bs = fields.Float(string='Total Ventas (Bs.F)', digits=(16, 2))

    @api.depends('pos_config_id', 'z_number')
    def _compute_name(self):
        for rec in self:
            rec.name = f"Z-{rec.z_number} [{rec.pos_config_id.name if rec.pos_config_id else 'POS'}]"

    @api.model
    def save_z_report(self, data):
        """
        Llamado desde JS cuando la impresora retorna los datos del Z
        """
        # data = {'pos_config_id': 1, 'z_number': 1250, 'date': '2026-02-12', ...}
        return self.create(data).id