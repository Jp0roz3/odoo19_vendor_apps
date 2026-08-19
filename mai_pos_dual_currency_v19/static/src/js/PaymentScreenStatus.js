/** @odoo-module */

import { PaymentScreenStatus } from "@point_of_sale/app/screens/payment_screen/payment_status/payment_status";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
// FIX: Importamos mainToSecondary para usar la formula unificada del modulo,
// evitando la duplicacion con la formula local val*show_rate/rate_company.
import { mainToSecondary, isPaymentMethodBs, getBsCashMethod } from "./dual_currency_utils";

patch(PaymentScreenStatus.prototype, {
    setup() {
        if (super.setup) { super.setup(); }
        this.pos = usePos();
        // Reactive state for mixed-change calculator (Dual Input)
        this.changeCalc = useState({
            primaryInput: 0,      // Amount of PRIMARY currency to give as change
            primaryInputStr: '',
            secInput: 0,          // Amount of SECONDARY currency to give as change
            secInputStr: '',
            secMethodId: null,
        });
        
        // Initialize default sec method if not set
        const defaultMethod = getBsCashMethod(this.pos) || this.bsPaymentMethods[0];
        if (defaultMethod) {
            this.changeCalc.secMethodId = defaultMethod.id;
        }
    },

    // ── Core rate ──────────────────────────────────────────────────────────────
    get _rate() {
        return this.pos.config.show_currency_rate || 1;
    },

    // ── Primary to Secondary (Main -> Sec) ─────────────────────────────────────
    // FIX: Unificado con mainToSecondary() de dual_currency_utils.js.
    // La formula anterior (val * show_rate / rate_company) era equivalente solo
    // cuando rate_company = 1, lo que causaba divergencia en otros escenarios.
    value_in_other_currency(val) {
        return mainToSecondary(val, this.pos);
    },

    // ── Secondary to Primary (Sec -> Main) ─────────────────────────────────────
    _secToPrimary(secAmount) {
        const rate = this._rate;
        // Inversa de mainToSecondary: si main=Bs → sec=USD → invert: USD*rate = Bs
        // Si main=USD → sec=Bs → invert: Bs/rate = USD
        const mainName = this.pos.currency ? this.pos.currency.name : '';
        if (mainName.includes('USD') || mainName.includes('$')) {
            // sec es Bs.F, queremos USD: Bs / rate
            return rate > 0 ? secAmount / rate : 0;
        }
        // sec es USD, queremos Bs: USD * rate
        return rate > 0 ? secAmount * rate : 0;
    },

    // ── Standard display getters ───────────────────────────────────────────────
    get total_other_currency() {
        return this.value_in_other_currency(this.props.order.priceIncl);
    },

    get totaldue_other_currency() {
        const res = this.value_in_other_currency(this.props.order.remainingDue);
        return res < 0 ? 0 : res;
    },

    get change_other_currency() {
        return this.value_in_other_currency(this.props.order.change);
    },

    // ── Symbol helpers ─────────────────────────────────────────────────────────
    get secSymbol() {
        return this.pos.config.show_currency_symbol || 'Bs.F';
    },

    get mainSymbol() {
        return (this.pos.currency && this.pos.currency.name && this.pos.currency.name.includes('USD')) ? '$' : (this.pos.currency ? this.pos.currency.symbol : '$');
    },

    // ── Mixed-change calculator (Dual Input) ───────────────────────────────────
    
    // 1. Total owed in Primary (e.g. $3)
    get changePrimaryTotal() {
        return Math.abs(this.props.order.change);
    },

    // 2. Total owed in Secondary (e.g. Bs.F 2100)
    get changeSecTotal() {
        return this.value_in_other_currency(this.changePrimaryTotal);
    },

    // 3. Primary given by cashier (Input 1)
    get primaryToGive() {
        return parseFloat(this.changeCalc.primaryInput) || 0;
    },

    // 4. Secondary given by cashier (Input 2)
    get secToGive() {
        return parseFloat(this.changeCalc.secInput) || 0;
    },

    // 5. Total given expressed in Primary (Primary Input + Secondary Input converted)
    get totalGivenInPrimary() {
        return this.primaryToGive + this._secToPrimary(this.secToGive);
    },

    // 6. Remaining owed in Primary (Total Owed - Total Given)
    get primaryChangeRemaining() {
        const remaining = this.changePrimaryTotal - this.totalGivenInPrimary;
        // Small epsilon for float comparison
        return remaining > 0.001 ? remaining : 0;
    },
    
    // 7. Remaining owed expressed in Secondary
    get secChangeRemaining() {
        return this.value_in_other_currency(this.primaryChangeRemaining);
    },

    // 8. Overflow (if cashier gives too much) expressed in Secondary
    get changeOverflowSec() {
        const remaining = this.changePrimaryTotal - this.totalGivenInPrimary;
        if (remaining < -0.001) {
            return this.value_in_other_currency(Math.abs(remaining));
        }
        return 0;
    },

    // 9. Status checks
    get isChangeSplitExact() {
        const diff = Math.abs(this.changePrimaryTotal - this.totalGivenInPrimary);
        return diff <= 0.001 && (this.primaryToGive > 0 || this.secToGive > 0);
    },

    get bsPaymentMethods() {
        return this.pos.config.payment_method_ids.filter(pm => {
            if (!isPaymentMethodBs(pm, this.pos)) return false;
            const pmName = (pm.name || "").toLowerCase();
            // Do not allow "Punto Venta", "Tarjeta", or "Debito" to be used for giving change (vuelto)
            if (pmName.includes('punto') || pmName.includes('venta') || pmName.includes('tarjeta') || pmName.includes('debito')) {
                return false;
            }
            return true;
        });
    },

    // ── IGTF Calculator ────────────────────────────────────────────────────────
    // Only activates when at least one paymentline has payment_method.is_igtf = true

    /** Lines of payment that carry IGTF */
    get igtfLines() {
        const order = this.props.order;
        if (!order) return [];
        return order.payment_ids.filter(l => l.payment_method_id && l.payment_method_id.is_igtf);
    },

    /** True when any IGTF payment is present */
    get hasIgtf() {
        return this.igtfLines.length > 0;
    },

    /** IGTF % from company config (loaded via _loader_params_res_company) */
    get igtfPct() {
        const companies = this.pos.company ? [this.pos.company] : [];
        // Odoo loads company as pos.company in the session
        const pct = (this.pos.company && this.pos.company.igtf_percentage != null)
            ? this.pos.company.igtf_percentage
            : 3.0;
        return pct / 100;
    },

    /** Sum of amounts (in main currency) of IGTF lines */
    get igtfBase() {
        // Obsoleto, pero se mantiene por compatibilidad si algo lo llama
        return this.igtfLines.reduce((acc, l) => acc + (l.amount || 0), 0);
    },

    /** Base real del IGTF calculada matemáticamente igual que en models.js */
    get igtfBaseReal() {
        const order = this.props.order;
        if (!order) return 0;
        
        if (order.manual_igtf_base !== null && order.manual_igtf_base !== undefined) {
            const mainName = this.pos.currency ? this.pos.currency.name : '';
            const isMainUSD = mainName.includes('USD') || mainName.includes('$');
            if (!isMainUSD) {
                return this._secToPrimary(order.manual_igtf_base);
            }
            return order.manual_igtf_base;
        }
        
        const igtf_product_id = (this.pos.company && this.pos.company.igtf_product_id) || (this.pos.config && this.pos.config.igtf_product_id);
        if (!igtf_product_id) return 0;
        
        let productId = null;
        if (typeof igtf_product_id === 'object' && igtf_product_id.id) {
            productId = parseInt(igtf_product_id.id, 10);
        } else {
            productId = Array.isArray(igtf_product_id) ? parseInt(igtf_product_id[0], 10) : parseInt(igtf_product_id, 10);
        }

        const totalWithoutIgtf = (order.priceIncl || 0) - this.igtfAmount;

        let nonIgtfPayments = 0;
        let totalIgtfTendered = 0;
        for (const line of (order.paymentlines || [])) {
            const pmId = line.payment_method_id ? (line.payment_method_id.id || line.payment_method_id) : null;
            const pmObj = pmId ? this.pos.config.payment_method_ids?.find(p => p.id === pmId) : null;
            if (pmObj && pmObj.is_igtf) {
                totalIgtfTendered += line.get_amount() || 0;
            } else {
                nonIgtfPayments += line.get_amount() || 0;
            }
        }

        const remainingForIgtf = Math.max(0, totalWithoutIgtf - nonIgtfPayments);
        return Math.min(totalIgtfTendered, remainingForIgtf);
    },

    get igtfBaseRealSec() {
        return this.value_in_other_currency(this.igtfBaseReal);
    },

    /** IGTF charge in MAIN currency (e.g. USD) */
    get igtfAmount() {
        const order = this.props.order;
        if (!order) return 0;
        const igtf_product_id = (this.pos.company && this.pos.company.igtf_product_id) || (this.pos.config && this.pos.config.igtf_product_id);
        if (!igtf_product_id) return 0;
        
        let productId = null;
        if (typeof igtf_product_id === 'object' && igtf_product_id.id) {
            productId = parseInt(igtf_product_id.id, 10);
        } else {
            productId = Array.isArray(igtf_product_id) ? parseInt(igtf_product_id[0], 10) : parseInt(igtf_product_id, 10);
        }
        
        let amount = 0;
        for (const line of order.getOrderlines()) {
            const lineProductId = line.product_id ? (line.product_id.id || line.product_id) : null;
            if (lineProductId === productId) {
                amount += line.priceIncl || 0;
            }
        }
        return amount;
    },

    /** IGTF charge converted to SECONDARY currency (Bs.F) */
    get igtfAmountSec() {
        return this.value_in_other_currency(this.igtfAmount);
    },

    /** Total due PLUS IGTF in MAIN currency */
    get totalWithIgtf() {
        const order = this.props.order;
        if (!order) return 0;
        // Ahora que el IGTF es un orderline real, el total nativo ya lo incluye
        return order.priceIncl;
    },

    /** Total due PLUS IGTF in SECONDARY currency (Bs.F) */
    get totalWithIgtfSec() {
        return this.value_in_other_currency(this.totalWithIgtf);
    },

    /** Change to give back in SECONDARY currency after IGTF is added */
    get changeWithIgtfSec() {
        const order = this.props.order;
        if (!order) return 0;
        const change = Math.abs(order.change);
        return change > 0 ? this.value_in_other_currency(change) : 0;
    },

    get changeWithIgtfMain() {
        const order = this.props.order;
        if (!order) return 0;
        const change = Math.abs(order.change);
        return change > 0 ? change : 0;
    },

    // ── Event Handlers ─────────────────────────────────────────────────────────
    onPrimaryChangeInput(ev) {
        let valStr = ev.target.value || "";
        valStr = valStr.replace(',', '.');
        const val = parseFloat(valStr) || 0;
        this.changeCalc.primaryInput = val;
        this.changeCalc.primaryInputStr = ev.target.value;
        if (this.props.order) {
            this.props.order.dual_change_primary = val;
        }
    },

    onSecChangeInput(ev) {
        let valStr = ev.target.value || "";
        valStr = valStr.replace(',', '.');
        const val = parseFloat(valStr) || 0;
        this.changeCalc.secInput = val;
        this.changeCalc.secInputStr = ev.target.value;
        if (this.props.order) {
            this.props.order.dual_change_sec = val;
            this.props.order.dual_change_sec_method_id = this.changeCalc.secMethodId;
        }
    },

    onChangeSecMethod(ev) {
        const val = parseInt(ev.target.value);
        this.changeCalc.secMethodId = val;
        if (this.props.order) {
            this.props.order.dual_change_sec_method_id = val;
        }
    },

    setManualIgtfBase() {
        const order = this.props.order;
        if (!order) return;
        const current = order.manual_igtf_base !== null ? order.manual_igtf_base : 0;
        const raw = window.prompt("Fijar Base IGTF ($)\nIngrese el monto en Dólares sobre el cual calcular el IGTF:", current.toFixed(2));
        if (raw === null) return; // user cancelled
        const val = parseFloat(raw.replace(',', '.'));
        if (!isNaN(val) && val >= 0) {
            order.set_manual_igtf_base(val);
            order.recompute_igtf_line();
        }
    },

    clearManualIgtfBase() {
        const order = this.props.order;
        if (!order) return;
        order.set_manual_igtf_base(null);
        order.recompute_igtf_line();
    },
});
