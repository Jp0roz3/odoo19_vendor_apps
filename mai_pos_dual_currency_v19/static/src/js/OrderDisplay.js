/** @odoo-module */
/**
 * OrderDisplay Patch — Dual Currency Totals (Odoo 19)
 * ════════════════════════════════════════════════════
 * Shows secondary-currency totals alongside the main currency.
 *
 * V19 API changes vs V17:
 *  - Component name: OrderWidget → OrderDisplay
 *  - Import path: generic_components/order_widget → components/order_display
 *  - pos.get_order() → pos.getOrder()
 *  - order.get_total_with_tax() → order.priceIncl
 *  - order.get_total_without_tax() → order.priceExcl
 *  - order.get_tax() → order.amountTaxes
 */
import { patch } from "@web/core/utils/patch";
import { OrderDisplay } from "@point_of_sale/app/components/order_display/order_display";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { mainToSecondary } from "./dual_currency_utils";

patch(OrderDisplay.prototype, {

    setup() {
        if (super.setup) { super.setup(); }
        this.pos = usePos();
        this._dc_subtotal     = '';
        this._dc_tax          = '';
        this._dc_total        = '';
        this._dc_subtotal_sec = '';
        this._dc_taxes_sec    = '';
        this._dc_total_sec    = '';
    },

    _updateSummary() {
        if (!this.env || !this.env.utils) return;
        try {
            let total    = 0;
            let tax      = 0;
            let subtotal = 0;

            const parseFormatted = (str) => {
                if (typeof str === 'number') return str;
                if (!str) return 0;
                let cleaned = String(str).replace(/[^\d,\.-]/g, '');
                const lastComma = cleaned.lastIndexOf(',');
                const lastDot   = cleaned.lastIndexOf('.');
                if (lastComma > lastDot) {
                    cleaned = cleaned.replace(/\./g, '').replace(',', '.');
                } else if (lastDot > lastComma) {
                    cleaned = cleaned.replace(/,/g, '');
                }
                return parseFloat(cleaned) || 0;
            };

            if (this.props && this.props.total !== undefined) {
                // Ticket / receipt screen — totals passed via props as formatted strings
                total    = parseFormatted(this.props.total);
                tax      = parseFormatted(this.props.tax);
                subtotal = total - tax;
            } else {
                // V19 API: pos.getOrder() and order.priceIncl / priceExcl / amountTaxes
                const order = this.props.order || (this.pos.get_order ? this.pos.get_order() : (this.pos.getOrder ? this.pos.getOrder() : null));
                if (!order) return;
                total    = parseFloat(order.priceIncl)    || 0;
                subtotal = parseFloat(order.priceExcl)    || 0;
                tax      = parseFloat(order.amountTaxes)  || (total - subtotal);
            }

            this._dc_subtotal = this.env.utils.formatCurrency(subtotal);
            this._dc_tax      = this.env.utils.formatCurrency(tax);
            this._dc_total    = this.env.utils.formatCurrency(total);

            if (this.pos.config.show_dual_currency) {
                const sym = this.pos.config.show_currency_symbol || 'Bs.F';
                const pos = this.pos.config.show_currency_position;

                const fmt = (n) => n.toLocaleString('es-VE', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                });

                const build = (n) => pos === 'before'
                    ? `${sym} ${fmt(n)}`
                    : `${fmt(n)} ${sym}`;

                // Conversión correcta usando la utilidad compartida
                this._dc_subtotal_sec = build(mainToSecondary(subtotal, this.pos));
                this._dc_taxes_sec    = build(mainToSecondary(tax, this.pos));
                this._dc_total_sec    = build(mainToSecondary(total, this.pos));
            } else {
                this._dc_subtotal_sec = '';
                this._dc_taxes_sec    = '';
                this._dc_total_sec    = '';
            }
        } catch (e) {
            console.warn('[DualCurrency] OrderDisplay._updateSummary:', e);
        }
    },

    getSubtotal_currency_text() {
        this._updateSummary();
        return this._dc_subtotal_sec || '';
    },
    getTaxes_currency_text() {
        this._updateSummary();
        return this._dc_taxes_sec || '';
    },
    getTotal_currency_text() {
        this._updateSummary();
        return this._dc_total_sec || '';
    },
    getSubtotal() {
        this._updateSummary();
        return this._dc_subtotal || this.props.total || '';
    },
    getTax() {
        this._updateSummary();
        return this._dc_tax || '';
    },
    getTotal() {
        this._updateSummary();
        return this._dc_total || '';
    },
});
