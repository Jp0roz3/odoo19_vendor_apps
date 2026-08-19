/** @odoo-module */
/**
 * OrderlinePatch — Dual Currency price per line (Odoo 18/19)
 * ══════════════════════════════════════════════════════════════
 * Strategy: patch the COMPONENT (not the model) because:
 *  - `Orderline` component has guaranteed access to `this.env.services.pos`
 *  - `PosOrderline` Record (model) loses this.pos in Odoo 18/19
 *
 * The component exposes `dualPriceTotal` as a getter used in the XML template.
 *
 * Price field priority (Odoo 18/19 camelCase API):
 *   1. line.priceWithTax   — new allPrices accounting engine field
 *   2. line.priceWithoutTax
 *   3. line.price_subtotal_incl  — kept for backward compat
 *   4. line.price_subtotal
 *   5. manual calc: priceUnit * qty * (1 - discount/100)
 */
import { patch } from "@web/core/utils/patch";
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";
import { mainToSecondary } from "./dual_currency_utils";

patch(Orderline.prototype, {
    /**
     * Returns the line total converted to the secondary currency.
     * Called from the XML template as `dualPriceTotal`.
     */
    /**
     * Parse Odoo's native formatted price string to guarantee a perfect match.
     */
    getDualPriceTotal(nativeStr) {
        try {
            const pos = this.env?.services?.pos;
            if (!pos || !pos.config || !pos.config.show_dual_currency) return 0;
            
            let price = 0;

            if (typeof nativeStr === 'string' && nativeStr) {
                const cleanStr = nativeStr.replace(/[^\d,\.-]/g, '');
                if (cleanStr.includes(',') && cleanStr.includes('.')) {
                    price = parseFloat(cleanStr.replace(/\./g, '').replace(',', '.'));
                } else if (cleanStr.includes(',') && cleanStr.indexOf(',') < cleanStr.length - 3) {
                    price = parseFloat(cleanStr.replace(/,/g, ''));
                } else if (cleanStr.includes(',')) {
                    price = parseFloat(cleanStr.replace(',', '.'));
                } else {
                    price = parseFloat(cleanStr);
                }
            }

            // Fallback if native string parsing fails
            if (!price) {
                const line = this.props?.line;
                if (!line) return 0;
                const cfg = pos.config;
                const useTax = cfg.iface_tax_included !== 'subtotal';
                
                if (line.allPrices) {
                    price = useTax
                        ? (line.allPrices.priceWithTax ?? line.allPrices.priceWithoutTax ?? 0)
                        : (line.allPrices.priceWithoutTax ?? line.allPrices.priceWithTax ?? 0);
                } else if (line.priceWithTax !== undefined) {
                    price = useTax ? line.priceWithTax : (line.priceWithoutTax ?? line.priceWithTax);
                } else if (line.price_subtotal_incl !== undefined && line.price_subtotal_incl !== null) {
                    price = useTax ? line.price_subtotal_incl : (line.price_subtotal ?? line.price_subtotal_incl);
                } else if (line.price_subtotal !== undefined && line.price_subtotal !== null) {
                    price = line.price_subtotal;
                } else {
                    const unit = parseFloat(line.price_unit ?? line.priceUnit ?? line.price ?? 0);
                    const qty  = parseFloat(line.qty ?? line.quantity ?? 1);
                    const disc = parseFloat(line.discount ?? 0);
                    price = unit * qty * (1 - disc / 100);
                }
            }

            console.log('[DC-ORDERLINE] getDualPriceTotal parsed:', {
                inputStr: nativeStr,
                parsedPrice: price,
                rate: pos.config.show_currency_rate,
            });

            return mainToSecondary(price, pos);
        } catch (e) {
            console.warn('[DC-ORDERLINE] getDualPriceTotal error:', e);
            return 0;
        }
    },
});
