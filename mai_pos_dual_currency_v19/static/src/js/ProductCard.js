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
import { stockOverrides, priceOverrides } from "./dual_currency_utils";

patch(ProductCard.prototype, {
    get pos() {
        return this.env.services.pos;
    },

    /**
     * Returns the qty to display.
     * OWL tracks the read of stockOverrides[tmplId] here → re-renders on write.
     */
    get qtyDisplay() {
        const tmplId = this.props.product?.id;
        if (tmplId !== undefined && stockOverrides[tmplId] !== undefined) {
            return stockOverrides[tmplId];
        }
        return this.props.product?.qty_available ?? 0;
    },

    get price_other_currency() {
        try {
            if (!this.pos || !this.pos.config || !this.pos.config.show_dual_currency) return 0;

            let product = this.props.product;

            if (!product) {
                if (this.pos.db && typeof this.pos.db.get_product_by_id === 'function') {
                    product = this.pos.db.get_product_by_id(this.props.productId);
                } else if (this.pos.models && this.pos.models['product.product']) {
                    product = this.pos.models['product.product'].get(this.props.productId);
                }
            }

            if (!product) return 0;

            let price = 0;
            try {
                // To be 100% reactive, we MUST read directly from the reactive `product` object.
                // If we parse `this.props.price`, we lose reactivity because `props.price` is a static string
                // passed by ProductList which doesn't re-render when product updates.
                
                // NEW: Read from priceOverrides first to guarantee OWL reactivity!
                const override = priceOverrides[product.id];
                const allPrices = override ? override : product.allPrices;
                
                if (allPrices) {
                    const useTax = this.pos.config.iface_tax_included === 'total' || this.pos.config.iface_tax_included === true;
                    price = useTax ? (allPrices.priceWithTax || 0) : (allPrices.priceWithoutTax || 0);
                }

                if (!price) {
                    const pricelist = this.pos.pricelists
                        ? this.pos.pricelists.find(pl => pl.id === this.pos.session?.pricelist_id?.id) || null
                        : null;
                        
                    const tmpl = product.product_tmpl_id;
                    if (tmpl && typeof tmpl.getPrice === "function") {
                        price = tmpl.getPrice(pricelist, 1, 0, false, product);
                    } else if (typeof product.getPrice === "function") {
                        price = product.getPrice(pricelist, 1, 0, false, product);
                    } else {
                        price = product.lst_price || product.list_price || 0;
                    }
                }
            } catch (e) {
                price = product.lst_price || product.list_price || 0;
            }

            if (!price || price === 0) {
                if (typeof product.getTaxDetails === "function") {
                    try {
                        const taxDetails = product.getTaxDetails();
                        price = this.pos.config.iface_tax_included === "total"
                            ? taxDetails.total_included
                            : taxDetails.total_excluded;
                    } catch (e) {
                        // Ignore
                    }
                }
            }

            if (!price || price === 0) return 0;

            const mainName = this.pos.currency ? this.pos.currency.name : '';
            const rate = parseFloat(this.pos.config.show_currency_rate) || 1;
            
            if (mainName.includes('USD') || mainName.includes('$')) {
                price = rate > 1 ? price * rate : (rate > 0 ? price / rate : 0);
            } else {
                price = rate > 1 ? price / rate : price * rate;
            }

            console.log('[DC-PRODUCTCARD] Dual price computed for', product.display_name, {
                final_dual_price: price,
                props_price: this.props.price,
                product_lst_price: product.lst_price,
                product_list_price: product.list_price,
                rate: rate
            });

            return price;

        } catch (e) {
            console.warn('[DualCurrency] ProductCard price_other_currency error:', e);
            return 0;
        }
    },

    /**
     * Gets the price in the native (main) currency directly from the reactive product object.
     * This allows us to render both prices in our custom block without relying on the frozen props.price.
     */
    get price_main_currency() {
        try {
            let product = this.props.product;

            if (!product) {
                if (this.pos.db && typeof this.pos.db.get_product_by_id === 'function') {
                    product = this.pos.db.get_product_by_id(this.props.productId);
                } else if (this.pos.models && this.pos.models['product.product']) {
                    product = this.pos.models['product.product'].get(this.props.productId);
                }
            }

            if (!product) return 0;

            let price = 0;
            try {
                // NEW: Read from priceOverrides first to guarantee OWL reactivity!
                const override = priceOverrides[product.id];
                const allPrices = override ? override : product.allPrices;
                
                if (allPrices) {
                    const useTax = this.pos.config.iface_tax_included === 'total' || this.pos.config.iface_tax_included === true;
                    price = useTax ? (allPrices.priceWithTax || 0) : (allPrices.priceWithoutTax || 0);
                }

                if (!price) {
                    const pricelist = this.pos.pricelists
                        ? this.pos.pricelists.find(pl => pl.id === this.pos.session?.pricelist_id?.id) || null
                        : null;
                        
                    const tmpl = product.product_tmpl_id;
                    if (tmpl && typeof tmpl.getPrice === "function") {
                        price = tmpl.getPrice(pricelist, 1, 0, false, product);
                    } else if (typeof product.getPrice === "function") {
                        price = product.getPrice(pricelist, 1, 0, false, product);
                    } else {
                        price = product.lst_price || product.list_price || 0;
                    }
                }
            } catch (e) {
                price = product.lst_price || product.list_price || 0;
            }

            if (!price || price === 0) {
                if (typeof product.getTaxDetails === "function") {
                    try {
                        const taxDetails = product.getTaxDetails();
                        price = this.pos.config.iface_tax_included === "total"
                            ? taxDetails.total_included
                            : taxDetails.total_excluded;
                    } catch (e) {
                        // Ignore
                    }
                }
            }
            
            return price;
        } catch (e) {
            return 0;
        }
    }
});
