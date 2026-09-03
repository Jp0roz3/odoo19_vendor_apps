/** @odoo-module */

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { PosPayment } from "@point_of_sale/app/models/pos_payment";
import { patch } from "@web/core/utils/patch";
import { mainToSecondary, secondaryToMain, isPaymentMethodBs, posInstance, setPosInstance } from "./dual_currency_utils";

// ─────────────────────────────────────────────────────────────────────────────
// Patch PosOrder — Dual Currency logic for Odoo 19
// NOTE: We only add methods, never override setup() to avoid the
// currency.rounding initialization race in connectRecords.
// ─────────────────────────────────────────────────────────────────────────────
patch(PosOrder.prototype, {
    setup() {
        super.setup(...arguments);
        // Register singleton so PosOrderline can access POS config without this.pos
        if (this.pos) {
            setPosInstance(this.pos);
        }
        this.manual_igtf_base = null; // Can be set manually by the cashier
    },

    set_manual_igtf_base(amount) {
        this.manual_igtf_base = amount;
    },

    // ── IGTF Dynamic ─────────────────────────────────────────────────────────
    recompute_igtf_line() {
        try {
            console.log("[DualCurrency] START recompute_igtf_line");
            if (!this.company && !this.config) {
                console.log("[DualCurrency] Missing company and config!");
                return;
            }
            const igtf_product_id = (this.company && this.company.igtf_product_id) || (this.config && this.config.igtf_product_id);
            if (!igtf_product_id) {
                console.log("[DualCurrency] No igtf_product_id configured");
                return;
            }

            console.log("[DualCurrency] igtf_product_id:", igtf_product_id);
            // In Odoo 19, products are in this.models["product.product"]
            const products = this.models["product.product"];
            if (!products) console.log("[DualCurrency] No product.product model found!");
            
            let igtf_product = null;
            let productId = null;
            if (igtf_product_id && typeof igtf_product_id === 'object' && igtf_product_id.id) {
                igtf_product = igtf_product_id;
                productId = igtf_product.id;
            } else {
                productId = Array.isArray(igtf_product_id) ? igtf_product_id[0] : igtf_product_id;
                igtf_product = products ? products.get(productId) : null;
            }

            if (!igtf_product) {
                console.log("[DualCurrency] Product not found for ID:", productId);
                return;
            }
            console.log("[DualCurrency] Found IGTF product:", igtf_product.display_name);

            let totalWithoutIgtf = 0;
            for (const l of this.getOrderlines()) {
                if (l.product_id && igtf_product && l.product_id.id !== igtf_product.id) {
                    totalWithoutIgtf += l.priceIncl || 0;
                }
            }

            let nonIgtfPayments = 0;
            let totalIgtfTendered = 0;
            for (const line of (this.paymentlines || [])) {
                const pmId = line.payment_method_id ? (line.payment_method_id.id || line.payment_method_id) : null;
                const pmObj = pmId && this.pos && this.pos.config ? this.pos.config.payment_method_ids?.find(p => p.id === pmId) : null;
                if (pmObj && pmObj.is_igtf) {
                    totalIgtfTendered += line.amount || 0;
                } else {
                    nonIgtfPayments += line.amount || 0;
                }
            }

            let igtfBase = 0;
            if (this.manual_igtf_base !== null && this.manual_igtf_base !== undefined) {
                // If a manual base was entered (in USD), convert to main currency if needed
                const isMainUSD = this.config.currency_id && this.config.currency_id.name === 'USD';
                let manualBaseMain = this.manual_igtf_base;
                if (!isMainUSD) {
                    manualBaseMain = secondaryToMain(this.manual_igtf_base, this);
                }
                igtfBase = manualBaseMain;
            } else {
                const remainingForIgtf = Math.max(0, totalWithoutIgtf - nonIgtfPayments);
                igtfBase = Math.min(totalIgtfTendered, remainingForIgtf);
            }

            const igtfPct = ((this.company && this.company.igtf_percentage != null)
                ? this.company.igtf_percentage : 3.0) / 100;
            let igtfAmount = parseFloat((igtfBase * igtfPct).toFixed(2));
            console.log("[DualCurrency] IGTF Base:", igtfBase, "Pct:", igtfPct, "Amount:", igtfAmount);

            // Find existing IGTF line
            let igtfLine = null;
            for (const line of this.getOrderlines()) {
                if (line.product_id && line.product_id.id === igtf_product.id) {
                    igtfLine = line;
                    break;
                }
            }

            if (igtfAmount > 0.001) {
                if (igtfLine) {
                    if (igtfLine.price_unit !== igtfAmount) {
                        igtfLine.setUnitPrice(igtfAmount);
                    }
                } else {
                    const newLine = this.models["pos.order.line"].create({
                        order_id: this,
                        product_id: igtf_product,
                        qty: 1,
                        price_unit: igtfAmount,
                        price_type: "manual",
                    });
                    if (newLine) newLine.is_igtf_line = true;
                }
            } else {
                if (igtfLine) {
                    this.removeOrderline(igtfLine);
                }
            }
        } catch(e) {
            console.warn("[DualCurrency] recompute_igtf_line error:", e);
        }
    },
});

// ─────────────────────────────────────────────────────────────────────────────
// Patch PosPayment — Add dual currency fields for Odoo 19
//
// IMPORTANT: Do NOT override setup(vals) here. In Odoo 19, setup() is called
// during connectRecords() and at that point currency.rounding may not be
// initialized yet, causing a TypeError crash on startup.
//
// Instead, we use getter/setter that lazily initialize usd_amt on first access.
// ─────────────────────────────────────────────────────────────────────────────
patch(PosPayment.prototype, {

    set_usd_amt(usd_amt) {
        this._dc_usd_amt = usd_amt;
    },

    get_usd_amt() {
        return parseFloat(this._dc_usd_amt) || 0.0;
    },

    get_dual_amount(pos) {
        if (!pos) return 0;
        let pm = this.payment_method_id;
        if (pm && typeof pm !== 'object') {
            pm = pos.config.payment_method_ids?.find(p => p.id === pm);
        }
        
        const mainName = pos.currency ? pos.currency.name : '';
        const isMainUSD = mainName.includes('USD') || mainName.includes('$');
        const isBsMethod = isPaymentMethodBs(pm, pos);
        
        // El monto introducido manualmente se respeta solo si el método de pago 
        // corresponde a la moneda SECUNDARIA.
        const typedSecondary = (!isMainUSD && !isBsMethod) || (isMainUSD && isBsMethod);

        if (pm && typedSecondary) {
            const rawAmt = this.get_usd_amt();
            if (rawAmt) return rawAmt;
        }
        return mainToSecondary(this.getAmount(), pos);
    },
});

// ─────────────────────────────────────────────────────────────────────────────
// Patch Orderline — Add dual currency total to display data
// ─────────────────────────────────────────────────────────────────────────────
patch(PosOrderline.prototype, {
    getDisplayData() {
        const data = super.getDisplayData(...arguments);
        const pos = this.pos || (this.order ? this.order.pos : null) || (this.env?.services?.pos) || posInstance;
        const config = pos ? pos.config : null;

        // ── DIAGNOSTIC — remove after fix confirmed ────────────────────────────
        console.log('[DC-DEBUG] getDisplayData called for line:', {
            hasPos: !!pos,
            show_dual_currency: config ? config.show_dual_currency : 'NO CONFIG',
            show_currency_rate: config ? config.show_currency_rate : 'NO CONFIG',
            price_subtotal_incl: this.price_subtotal_incl,
            price_subtotal: this.price_subtotal,
            price_unit: this.price_unit,
            qty: this.qty,
            quantity: this.quantity,
            price: this.price,
            priceIncl: this.priceIncl,
            priceExcl: this.priceExcl,
            'vals.price (formatted)': data ? data.price : 'N/A',
            allKeys: this ? Object.keys(this).filter(k => k.includes('price') || k.includes('qty') || k.includes('amount') || k.includes('subtotal')).slice(0, 20) : [],
        });
        // ── END DIAGNOSTIC ────────────────────────────────────────────────────

        if (config && config.show_dual_currency) {
            data.dual_price_total = this.dual_price_total;
        }
        return data;
    },
    set_discount(discount) {
        let parsed_discount = typeof discount === 'number' ? discount : window.parseFloat(discount) || 0;
        if (parsed_discount >= 100) {
            if (this.pos && this.pos.env && this.pos.env.services && this.pos.env.services.notification) {
                this.pos.env.services.notification.add("No se permite aplicar un descuento del 100% o superior.", { type: "danger" });
            }
            return;
        }
        if (super.set_discount) {
            return super.set_discount(discount);
        }
    },
    setDiscount(discount) {
        let parsed_discount = typeof discount === 'number' ? discount : window.parseFloat(discount) || 0;
        if (parsed_discount >= 100) {
            if (this.pos && this.pos.env && this.pos.env.services && this.pos.env.services.notification) {
                this.pos.env.services.notification.add("No se permite aplicar un descuento del 100% o superior.", { type: "danger" });
            }
            return;
        }
        if (super.setDiscount) {
            return super.setDiscount(discount);
        }
    }
});

patch(PosOrder.prototype, {
    // ── Contadores de orden (cst_pos_order_lines_count integrado) ─────────────
    // this.lines es reactivo → OWL re-renderiza al agregar/quitar productos
    get itemCount() {
        return this.lines?.length ?? 0;
    },
    get totalQuantity() {
        return this.lines?.reduce((sum, line) => sum + (line.getQuantity?.() ?? line.qty ?? 0), 0) ?? 0;
    },

    pay() {
        const has100PercentDiscount = this.get_orderlines().some(line => line.discount >= 100);
        if (has100PercentDiscount) {
            if (this.pos && this.pos.env && this.pos.env.services && this.pos.env.services.notification) {
                this.pos.env.services.notification.add("Error de validación: No se permite procesar órdenes con líneas al 100% de descuento.", { type: "danger" });
            }
            return;
        }
        if ((this.priceIncl || 0) <= 0) {
            const hasNegativeLine = this.get_orderlines().some(line => line.get_display_price() < 0);
            if (hasNegativeLine) {
                if (this.pos && this.pos.env && this.pos.env.services && this.pos.env.services.notification) {
                    this.pos.env.services.notification.add("Error de validación: No se permite aplicar un descuento global del 100%. El total de la orden no puede ser 0 por descuentos.", { type: "danger" });
                }
                return;
            }
        }
        return super.pay(...arguments);
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Patch PosOrderline — Dual Currency logic
// ─────────────────────────────────────────────────────────────────────────────
patch(PosOrderline.prototype, {
    setup() {
        super.setup(...arguments);
        if (!this.price_unit || this.price_unit === 0) {
            const prod = this.product_id || (this.product && typeof this.product === 'object' ? this.product : null);
            if (prod) {
                const u = parseFloat(prod.l10n_ve_list_price_usd || 0);
                const raw = parseFloat(prod.lst_price || prod.list_price || 0);
                const b = parseFloat(prod.l10n_ve_list_price_bs || 0);
                const price = u || (raw > 0 ? (raw < 500 ? raw : raw / 791.3248) : (b > 0 ? b / 791.3248 : 0));
                if (price > 0) {
                    if (typeof this.set_unit_price === 'function') {
                        this.set_unit_price(price);
                    } else {
                        this.price_unit = price;
                    }
                }
            }
        }
    },

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
    },

    get dual_price_total() {
        // In Odoo 18/19 PosOrderline loses this.pos — use singleton fallback
        const pos = this.pos || (this.order ? this.order.pos : null) || posInstance;
        const config = pos ? pos.config : null;
        if (!config || !config.show_dual_currency) return 0;

        let price = 0;
        try {
            if (this.price_subtotal_incl !== undefined && this.price_subtotal_incl !== null && this.price_subtotal_incl !== 0) {
                price = config.iface_tax_included === 'total'
                    ? parseFloat(this.price_subtotal_incl) || 0
                    : parseFloat(this.price_subtotal) || 0;
            } else if (this.price_subtotal !== undefined && this.price_subtotal !== null && this.price_subtotal !== 0) {
                price = parseFloat(this.price_subtotal) || 0;
            } else {
                const qty   = parseFloat(this.qty || this.quantity || 1);
                let unit    = parseFloat(this.price_unit || this.price || 0);
                if (!unit && this.product_id) {
                    const u = parseFloat(this.product_id.l10n_ve_list_price_usd || 0);
                    const raw = parseFloat(this.product_id.lst_price || this.product_id.list_price || 0);
                    const b = parseFloat(this.product_id.l10n_ve_list_price_bs || 0);
                    unit = u || (raw > 0 ? (raw < 500 ? raw : raw / 791.3248) : (b > 0 ? b / 791.3248 : 0));
                }
                const disc  = parseFloat(this.discount || 0);
                price = unit * qty * (1 - disc / 100);
            }
        } catch (e) {
            console.warn('[DualCurrency] dual_price_total: error extracting price', e);
        }

        const rate = parseFloat(config.show_currency_rate) || 791.3248;
        return price < 500 ? (price * rate) : (price / rate);
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Safe taxGroupLabels and get_price patch for ProductProduct & ProductTemplate (Odoo 19)
// ─────────────────────────────────────────────────────────────────────────────
(async () => {
    try {
        const prodMod = await odoo.loader.modules.get("@point_of_sale/app/models/product_product");
        const ProductProduct = prodMod?.ProductProduct;
        if (ProductProduct && ProductProduct.prototype) {
            patch(ProductProduct.prototype, {
                get_price(pricelist, quantity, price_extra = 0, recurring = false) {
                    let price = super.get_price ? super.get_price(...arguments) : 0;
                    if (!price || price === 0) {
                        const u = parseFloat(this.l10n_ve_list_price_usd || 0);
                        const raw = parseFloat(this.lst_price || this.list_price || 0);
                        const b = parseFloat(this.l10n_ve_list_price_bs || 0);
                        price = u || (raw > 0 ? (raw < 500 ? raw : raw / 791.3248) : (b > 0 ? b / 791.3248 : 0));
                    }
                    return price;
                },
                getPrice(pricelist, quantity, price_extra = 0, recurring = false) {
                    let price = super.getPrice ? super.getPrice(...arguments) : 0;
                    if (!price || price === 0) {
                        const u = parseFloat(this.l10n_ve_list_price_usd || 0);
                        const raw = parseFloat(this.lst_price || this.list_price || 0);
                        const b = parseFloat(this.l10n_ve_list_price_bs || 0);
                        price = u || (raw > 0 ? (raw < 500 ? raw : raw / 791.3248) : (b > 0 ? b / 791.3248 : 0));
                    }
                    return price;
                },
                get taxGroupLabels() {
                    try {
                        if (!this.taxes_id) return [];
                        const taxGroups = this.models ? this.models["account.tax.group"] : null;
                        return this.taxes_id.map((tax) => {
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
    } catch (e) {
        // Ignore
    }

    try {
        const tmplMod = await odoo.loader.modules.get("@point_of_sale/app/models/product_template");
        const ProductTemplate = tmplMod?.ProductTemplate;
        if (ProductTemplate && ProductTemplate.prototype) {
            patch(ProductTemplate.prototype, {
                get_price(pricelist, quantity, price_extra = 0, recurring = false) {
                    let price = super.get_price ? super.get_price(...arguments) : 0;
                    if (!price || price === 0) {
                        const u = parseFloat(this.l10n_ve_list_price_usd || 0);
                        const raw = parseFloat(this.lst_price || this.list_price || 0);
                        const b = parseFloat(this.l10n_ve_list_price_bs || 0);
                        price = u || (raw > 0 ? (raw < 500 ? raw : raw / 791.3248) : (b > 0 ? b / 791.3248 : 0));
                    }
                    return price;
                },
                getPrice(pricelist, quantity, price_extra = 0, recurring = false) {
                    let price = super.getPrice ? super.getPrice(...arguments) : 0;
                    if (!price || price === 0) {
                        const u = parseFloat(this.l10n_ve_list_price_usd || 0);
                        const raw = parseFloat(this.lst_price || this.list_price || 0);
                        const b = parseFloat(this.l10n_ve_list_price_bs || 0);
                        price = u || (raw > 0 ? (raw < 500 ? raw : raw / 791.3248) : (b > 0 ? b / 791.3248 : 0));
                    }
                    return price;
                },
                get taxGroupLabels() {
                    try {
                        if (!this.taxes_id) return [];
                        const taxGroups = this.models ? this.models["account.tax.group"] : null;
                        return this.taxes_id.map((tax) => {
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
    } catch (e) {
        // Ignore
    }
})();

