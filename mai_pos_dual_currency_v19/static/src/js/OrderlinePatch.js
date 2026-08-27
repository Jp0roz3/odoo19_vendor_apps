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
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { mainToSecondary, posInstance } from "./dual_currency_utils";

if (PosOrderline && PosOrderline.prototype) {
    patch(PosOrderline.prototype, {
        get taxGroupLabels() {
            try {
                const taxes = this.taxes_id || this.tax_ids || (this.product_id ? this.product_id.taxes_id : []) || [];
                if (!taxes || !taxes.length) return [];
                const taxGroups = this.models ? this.models["account.tax.group"] : null;
                return taxes.map((tax) => {
                    const grpId = (tax.tax_group_id && typeof tax.tax_group_id === 'object')
                        ? tax.tax_group_id.id
                        : tax.tax_group_id;
                    const grp = grpId && taxGroups?.get ? taxGroups.get(grpId) : null;
                    return grp?.pos_receipt_label || grp?.name || (typeof tax === 'object' ? tax.name : '') || "";
                }).filter(Boolean);
            } catch (e) {
                return [];
            }
        }
    });
}

patch(Orderline.prototype, {
    get taxGroupLabels() {
        try {
            const line = this.props?.line;
            if (!line) return [];
            const taxes = line.taxes_id || line.tax_ids || (line.product_id ? line.product_id.taxes_id : []) || [];
            if (!taxes || !taxes.length) return [];
            const pos = this.env?.services?.pos || posInstance;
            const taxGroups = pos?.models?.["account.tax.group"] || line.models?.["account.tax.group"];
            return taxes.map((tax) => {
                const grpId = (tax.tax_group_id && typeof tax.tax_group_id === 'object')
                    ? tax.tax_group_id.id
                    : tax.tax_group_id;
                const grp = grpId && taxGroups?.get ? taxGroups.get(grpId) : null;
                return grp?.pos_receipt_label || grp?.name || (typeof tax === 'object' ? tax.name : '') || "";
            }).filter(Boolean);
        } catch (e) {
            return [];
        }
    },

    /**
     * Returns the line total converted to the secondary currency.
     * Called from the XML template as `dualPriceTotal`.
     */
    getDualPriceTotal(nativeStr) {
        try {
            const pos = this.env?.services?.pos || posInstance;
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
                    let unit = parseFloat(line.price_unit ?? line.priceUnit ?? line.price ?? 0);
                    if (!unit && line.product_id) {
                        const prod = line.product_id;
                        const u = parseFloat(prod.l10n_ve_list_price_usd || 0);
                        const raw = parseFloat(prod.lst_price || prod.list_price || 0);
                        const b = parseFloat(prod.l10n_ve_list_price_bs || 0);
                        unit = u || (raw > 0 ? (raw < 500 ? raw : raw / 791.3248) : (b > 0 ? b / 791.3248 : 0));
                    }
                    const qty  = parseFloat(line.qty ?? line.quantity ?? 1);
                    const disc = parseFloat(line.discount ?? 0);
                    price = unit * qty * (1 - disc / 100);
                }
            }

            const rate = parseFloat(pos.config.show_currency_rate) || 791.3248;
            if (price > 0) {
                return price < 500 ? (price * rate) : (price / rate);
            }
            return 0;
        } catch (e) {
            return 0;
        }
    },
});
