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
import { mainToSecondary, formatCurrencySafe, posInstance } from "./dual_currency_utils";

patch(OrderDisplay.prototype, {

    setup() {
        if (super.setup) { super.setup(); }
        try {
            this.pos = usePos();
        } catch (e) {
            this.pos = posInstance;
        }
    },

    _getRawTotals() {
        try {
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

            let total = 0;
            let tax = 0;
            let subtotal = 0;

            if (this.props && this.props.total !== undefined) {
                total = parseFormatted(this.props.total);
                tax = parseFormatted(this.props.tax);
                subtotal = total - tax;
            } else {
                const pos = this.pos || posInstance;
                const order = this.props?.order || (pos?.get_order ? pos.get_order() : (pos?.getOrder ? pos.getOrder() : null));
                if (order) {
                    total = parseFloat(order.priceIncl ?? (order.get_total_with_tax ? order.get_total_with_tax() : 0)) || 0;
                    subtotal = parseFloat(order.priceExcl ?? (order.get_total_without_tax ? order.get_total_without_tax() : 0)) || 0;
                    tax = parseFloat(order.amountTaxes ?? (order.get_total_tax ? order.get_total_tax() : 0)) || (total - subtotal);

                    // Fallback to sum of orderlines
                    if (!total && order.getOrderlines) {
                        for (const l of order.getOrderlines()) {
                            const p = parseFloat(l.priceIncl ?? l.price_subtotal_incl ?? l.price_subtotal ?? ((l.price_unit || l.price || 0) * (l.qty || 1)) ?? 0);
                            total += p;
                            subtotal += parseFloat(l.priceExcl ?? l.price_subtotal ?? p ?? 0);
                        }
                        tax = total - subtotal;
                    }
                }
            }
            return { total, tax, subtotal };
        } catch (e) {
            return { total: 0, tax: 0, subtotal: 0 };
        }
    },

    getSubtotal() {
        const { subtotal } = this._getRawTotals();
        return formatCurrencySafe(subtotal);
    },

    getTax() {
        const { tax } = this._getRawTotals();
        return formatCurrencySafe(tax);
    },

    getTotal() {
        const { total } = this._getRawTotals();
        return formatCurrencySafe(total);
    },

    _buildSecondary(amount) {
        const pos = this.pos || posInstance;
        if (!pos || !pos.config || !pos.config.show_dual_currency) return '';
        const sym = pos.config.show_currency_symbol || 'Bs.F';
        const position = pos.config.show_currency_position;
        const rate = parseFloat(pos.config.show_currency_rate) || 791.3248;
        const converted = amount < 500 ? (amount * rate) : (amount / rate);
        const formatted = formatCurrencySafe(converted);
        return position === 'before' ? `${sym} ${formatted}` : `${formatted} ${sym}`;
    },

    getSubtotal_currency_text() {
        const { subtotal } = this._getRawTotals();
        return this._buildSecondary(subtotal);
    },

    getTaxes_currency_text() {
        const { tax } = this._getRawTotals();
        return this._buildSecondary(tax);
    },

    getTotal_currency_text() {
        const { total } = this._getRawTotals();
        return this._buildSecondary(total);
    },
});

