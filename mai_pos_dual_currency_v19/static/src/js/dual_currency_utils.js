/** @odoo-module */
/**
 * DualCurrency Utilities
 * ─────────────────────────────────────────────────────────────────────────────
 * Shared helpers used across all dual-currency patches.
 * Main currency (Bs.F) ↔ Secondary currency (USD $)
 * 
 * Conversion logic:
 *   If main = Bs  → USD = Bs / tasa        | Bs = USD × tasa
 *   If main = USD → Bs  = USD × tasa       | USD = Bs / tasa
 *
 * `tasa` = pos.config.show_currency_rate (Bs por 1 USD, e.g. 36.50)
 */

/**
 * Get the active exchange rate from POS config.
 * Returns Bs per 1 USD (e.g. 36.50)
 */
export function getDualRate(pos) {
    const rate = parseFloat(pos.config.show_currency_rate) || 1;
    return rate > 0 ? rate : 1;
}

/**
 * Convert the main currency amount → secondary currency amount.
 * If main is Bs → result is USD.
 * If main is USD → result is Bs.
 */
export function mainToSecondary(amount, pos) {
    const rate = getDualRate(pos);
    const mainName = pos.currency ? pos.currency.name : '';
    // Si la tasa es > 1 (e.g. 36.5 Bs/$), dividimos. Si es < 1 (e.g. 0.0015 $/Bs), multiplicamos.
    if (mainName.includes('USD') || mainName.includes('$')) {
        return rate > 1 ? amount * rate : (rate > 0 ? amount / rate : 0);
    }
    return rate > 1 ? amount / rate : amount * rate;
}

/**
 * Convert secondary currency amount → main currency amount.
 */
export function secondaryToMain(amount, pos) {
    const rate = getDualRate(pos);
    const mainName = pos.currency ? pos.currency.name : '';
    if (mainName.includes('USD') || mainName.includes('$')) {
        return rate > 1 ? amount / rate : amount * rate;
    }
    return rate > 1 ? amount * rate : (rate > 0 ? amount / rate : 0);
}

/**
 * Format a number to 2 decimal places string.
 */
export function fmt2(n) {
    return (parseFloat(n) || 0).toFixed(2);
}

/**
 * Get the display symbol for the secondary currency.
 */
export function getSecondarySymbol(pos) {
    return pos.config.show_currency_symbol || '$';
}

/**
 * Get the display label for the main currency.
 */
export function getMainSymbol(pos) {
    return pos.currency ? pos.currency.name : 'Bs.F';
}

/**
 * Get readable rate label e.g. "Tasa: 36.50 Bs/$"
 */
export function getRateLabel(pos) {
    let rate = getDualRate(pos);
    const sec  = getSecondarySymbol(pos);
    const main = getMainSymbol(pos);
    
    // Si la tasa es < 1 (ej. 0.0015 USD por Bs), invertimos para mostrar Bs por USD (ej. 666.67 Bs/$)
    if (rate > 0 && rate < 1) {
        rate = 1 / rate;
    }
    
    if (isMainCurrencyUSD(pos)) {
        return `1 ${main} = ${rate.toLocaleString('es-VE', {minimumFractionDigits: 2, maximumFractionDigits: 2})} ${sec}`;
    }
    return `1 ${sec} = ${rate.toLocaleString('es-VE', {minimumFractionDigits: 2, maximumFractionDigits: 2})} ${main}`;
}

/**
 * Check if the company's main currency is USD
 */
export function isMainCurrencyUSD(pos) {
    const mainName = pos.currency ? pos.currency.name : '';
    return mainName.includes('USD') || mainName.includes('$');
}

/**
 * Identify if a specific payment method object is the Bs.F method
 */
export function isPaymentMethodBs(pm, pos) {
    if (!pm) return false;
    // In V19, custom fields might be in pm or we might need to check if it's the main currency
    const isMainUSD = isMainCurrencyUSD(pos);
    
    // First priority: Check the name to automatically handle misconfigurations
    const pmName = (pm.name || "").toLowerCase();
    if (pmName.includes('$') || pmName.includes('usd') || pmName.includes('dolar') || pmName.includes('dólar') || pmName.includes('zelle') || pmName.includes('binance')) {
        return false; // Not Bs, it's USD
    }
    if (pmName.includes('bs') || pmName.includes('bolivar') || pmName.includes('bolívar') || 
        pmName.includes('punto') || pmName.includes('venta') || pmName.includes('tarjeta') || 
        pmName.includes('pago movil') || pmName.includes('pagomovil') || pmName.includes('movil') || pmName.includes('debito')) {
        return true; // It's Bs
    }
    
    // Second priority: Explicit boolean
    if (pm.pago_usd !== undefined) {
        if (isMainUSD) {
            return pm.pago_usd === true;
        } else {
            return pm.pago_usd === false;
        }
    }
    
    // Ultimate fallback
    if (isMainUSD) {
        return false;
    } else {
        return true;
    }
}

/**
 * Get the secondary (Bs.F) cash payment method object
 */
export function getBsCashMethod(pos) {
    if (!pos || !pos.config || !pos.config.payment_method_ids) return null;
    const cashMethods = pos.config.payment_method_ids.filter(pm => pm.type === 'cash');
    return cashMethods.find(pm => isPaymentMethodBs(pm, pos)) || null;
}

/**
 * Reactive stock overrides map — keyed by product.template ID.
 * Uses OWL's reactive() so that ANY component reading stockOverrides[id]
 * during render will be re-rendered when that key is written.
 * PaymentScreen writes here BEFORE super.validateOrder() (component still alive).
 * ProductCard reads via get qtyDisplay() — OWL tracks the read automatically.
 */
import { reactive } from "@odoo/owl";
import { registry } from "@web/core/registry";

export const stockOverrides = reactive({});
export const priceOverrides = reactive({});

/**
 * Global Format / Validation Helpers for Dual Currency & Templates
 */
export function formatCurrencySafe(amount, hasSymbol = true, options = {}) {
    if (amount === undefined || amount === null || isNaN(amount)) {
        return "0.00";
    }
    const num = parseFloat(amount) || 0;
    return num.toLocaleString('es-VE', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}

export function isValidFloatSafe(val) {
    if (val === undefined || val === null || val === '') return false;
    const n = parseFloat(String(val).replace(',', '.'));
    return !isNaN(n) && isFinite(n);
}

export function parseValidFloatSafe(val) {
    if (val === undefined || val === null || val === '') return 0.0;
    const n = parseFloat(String(val).replace(',', '.'));
    return isNaN(n) ? 0.0 : n;
}

/**
 * Service that ensures env.utils is available in all Owl components and QWeb templates
 */
export const utilsService = {
    dependencies: [],
    start(env) {
        if (!env.utils) {
            env.utils = {};
        }
        env.utils.formatCurrency = formatCurrencySafe;
        env.utils.isValidFloat = isValidFloatSafe;
        env.utils.parseValidFloat = parseValidFloatSafe;
        return env.utils;
    },
};

if (!registry.category("services").contains("utils")) {
    registry.category("services").add("utils", utilsService);
}

/**
 * Module-level singleton to hold the POS service reference.
 * Set by PosOrder.setup() so that PosOrderline (which lacks this.pos in Odoo 18/19)
 * can still access the POS config for dual-currency calculations.
 */
export let posInstance = null;
export function setPosInstance(pos) {
    posInstance = pos;
}

/**
 * Owl Error Interceptor — Exposes error.cause on screen and in console
 */
if (typeof window !== "undefined") {
    window.addEventListener("error", (e) => {
        if (e.error && e.error.cause) {
            console.error("🚨 [OWL ERROR CAUSE]:", e.error.cause);
        }
    });
    window.addEventListener("unhandledrejection", (e) => {
        if (e.reason && e.reason.cause) {
            console.error("🚨 [OWL UNHANDLED CAUSE]:", e.reason.cause);
        }
    });
}


