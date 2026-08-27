/** @odoo-module */
/**
 * ProductCard — Dual Currency Price Badge + Reactive Stock Display (Odoo 19)
 *
 * STOCK LOGIC:
 *  - `stockOverrides` is a reactive() object from OWL exported by dual_currency_utils.
 *  - Reading stockOverrides[tmplId] inside a getter called from the template
 *    causes OWL to TRACK that read. When PaymentScreen writes to stockOverrides[tmplId],
 *    OWL automatically re-renders every ProductCard that read that key.
 *  - No useState() needed — reactive() is cross-component by design.
 */
import { ProductCard } from "@point_of_sale/app/components/product_card/product_card";
import { patch } from "@web/core/utils/patch";
import { stockOverrides, priceOverrides, posInstance } from "./dual_currency_utils";

function computeCardPrices(product, pos, propsPrice) {
    const rate = (pos?.config && parseFloat(pos.config.show_currency_rate)) || 791.3248;
    let usd = 0;
    let bs = 0;

    if (product) {
        const u = parseFloat(product.l10n_ve_list_price_usd || 0);
        const b = parseFloat(product.l10n_ve_list_price_bs || 0);
        if (u > 0) usd = u;
        if (b > 0) bs = b;

        if (!usd && !bs) {
            const raw = parseFloat(product.lst_price || product.list_price || 0);
            if (raw > 0) {
                if (raw < 500) {
                    usd = raw;
                    bs = raw * rate;
                } else {
                    bs = raw;
                    usd = raw / rate;
                }
            }
        } else if (!bs && usd) {
            bs = usd * rate;
        } else if (!usd && bs) {
            usd = bs / rate;
        }
    }

    if (!usd && !bs && propsPrice) {
        let p = 0;
        const cleanStr = String(propsPrice).replace(/[^\d,\.-]/g, '');
        if (cleanStr.includes(',') && cleanStr.includes('.')) {
            p = parseFloat(cleanStr.replace(/\./g, '').replace(',', '.'));
        } else if (cleanStr.includes(',')) {
            p = parseFloat(cleanStr.replace(',', '.'));
        } else {
            p = parseFloat(cleanStr);
        }
        if (p > 0) {
            if (p < 500) {
                usd = p;
                bs = p * rate;
            } else {
                bs = p;
                usd = p / rate;
            }
        }
    }

    return {
        usd: Math.round((usd + Number.EPSILON) * 100) / 100,
        bs: Math.round((bs + Number.EPSILON) * 100) / 100,
    };
}

patch(ProductCard.prototype, {
    get pos() {
        return this.env?.services?.pos || posInstance;
    },

    /**
     * Returns the qty to display.
     * OWL tracks the read of stockOverrides[tmplId] here → re-renders on write.
     */
    get qtyDisplay() {
        const product = this.props?.product || this.props?.record;
        const tmplId = product?.id || this.props?.productId || this.props?.id;
        if (tmplId !== undefined && stockOverrides[tmplId] !== undefined) {
            return stockOverrides[tmplId];
        }
        return product?.qty_available ?? 0;
    },

    get price_other_currency() {
        try {
            const pos = this.pos || posInstance;
            if (!pos || !pos.config || !pos.config.show_dual_currency) return 0;

            let product = this.props?.product || this.props?.record;
            const pId = this.props?.productId || this.props?.id;

            if (!product && pId && pos) {
                if (pos.db && typeof pos.db.get_product_by_id === 'function') {
                    product = pos.db.get_product_by_id(pId);
                } else if (pos.models && pos.models['product.product']) {
                    product = pos.models['product.product'].get(pId);
                }
            }

            const { bs } = computeCardPrices(product, pos, this.props?.price);
            return bs;
        } catch (e) {
            return 0;
        }
    },

    /**
     * Gets the price in the native (main) currency directly from the reactive product object.
     * This allows us to render both prices in our custom block without relying on the frozen props.price.
     */
    get price_main_currency() {
        try {
            const pos = this.pos || posInstance;
            let product = this.props?.product || this.props?.record;
            const pId = this.props?.productId || this.props?.id;

            if (!product && pId && pos) {
                if (pos.db && typeof pos.db.get_product_by_id === 'function') {
                    product = pos.db.get_product_by_id(pId);
                } else if (pos.models && pos.models['product.product']) {
                    product = pos.models['product.product'].get(pId);
                }
            }

            const { usd } = computeCardPrices(product, pos, this.props?.price);
            return usd;
        } catch (e) {
            return 0;
        }
    }
});
