/** @odoo-module */
/**
 * ClosePosPopup Patch — Dual Currency (Odoo 19)
 * ═══════════════════════════════════════════════
 * Adds dual Bs.F / USD balances to the closing popup.
 *
 * V19 API changes vs V17:
 *  - `other_payment_methods` prop → `non_cash_payment_methods`
 *  - `this.pos.pos_session` → `this.pos.session`
 *  - `this.orm.call()` → `this.pos.data.call()`
 *  - `this.popup.add()` → `this.dialog.add()`
 *  - `this.env.services.orm.searchRead()` → `this.pos.data.searchRead()`
 *  - `this.hardwareProxy.openCashbox()` → kept same (works in V19 too)
 *  - Import path updated
 */
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";
import { patch } from "@web/core/utils/patch";
import { markup, useState } from "@odoo/owl";
import { formatFloat } from "@web/core/utils/numbers";
import { getDualRate, getMainSymbol, getSecondarySymbol, isMainCurrencyUSD, isPaymentMethodBs, mainToSecondary, secondaryToMain } from "./dual_currency_utils";
import { MoneyDetailsPopup } from "@point_of_sale/app/components/popups/money_details_popup/money_details_popup";
import { _t } from "@web/core/l10n/translation";
import { PaymentReportReceipt } from "./PaymentReportReceipt";
import { AccordionItem } from "@point_of_sale/app/components/accordion_item/accordion_item";
import { UsdCashMovePopup } from "./UsdCashMovePopup";
import { CashMoveListPopup } from "@point_of_sale/app/components/popups/cash_move_popup/cash_move_list_popup/cash_move_list_popup";
import { useService } from "@web/core/utils/hooks";

const { DateTime } = luxon;

ClosePosPopup.components = {
    ...ClosePosPopup.components,
    AccordionItem
};

patch(ClosePosPopup.prototype, {

    setup() {
        super.setup();
        this.hardwareProxy = useService("hardware_proxy");
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this.notification = useService("notification");

        // We override getPayload so the POS native code captures our Dual Cash setup
        this.state = Object.assign(this.state, {
            notes: "",
            acceptClosing: false,
        });

        const isMainUSD = isMainCurrencyUSD(this.pos);

        // Fix native Odoo default_cash_details initialization
        if (this.props.default_cash_details && this.state.payments[this.props.default_cash_details.id]) {
            const pmId = this.props.default_cash_details.id;
            const pm = this.pos.config.payment_method_ids?.find(p => p.id === pmId);
            const isBs = this._isBsPaymentMethod(pm);
            let val = this.props.default_cash_details.amount || 0;
            if (!isBs && !isMainUSD) val = mainToSecondary(val, this.pos);
            else if (isBs && isMainUSD) val = mainToSecondary(val, this.pos);
            this.state.payments[pmId].counted = val.toString();
        }

        // Initialize state.payments for secondary cash and pago movil since native Odoo only does it for bank
        if (this.props.non_cash_payment_methods) {
            for (const pm of this.props.non_cash_payment_methods) {
                const isPagoMovil = pm.name && pm.name.toLowerCase().includes('pago');
                const _showDiff = (pm.type === 'bank' && (pm.number !== 0 || isPagoMovil)) || pm.type === 'cash';
                if (_showDiff) {
                    const pmObj = this.pos.config.payment_method_ids?.find(p => p.id === pm.id);
                    const isBs = this._isBsPaymentMethod(pmObj);
                    let val = pm.amount || 0;
                    if (!isBs && !isMainUSD) val = mainToSecondary(val, this.pos);
                    else if (isBs && isMainUSD) val = mainToSecondary(val, this.pos);
                    
                    if (!this.state.payments[pm.id] || pm.type === 'cash' || isPagoMovil) {
                        this.state.payments[pm.id] = { counted: val.toString() };
                    }
                }
            }
        }
    },

    openBsCashMove() {
        this.dialog.add(UsdCashMovePopup);
    },

    async openCashMoveDetails() {
        const cashMoves = await this.pos.data.call("pos.session", "get_cash_in_out_list", [
            this.pos.session.id,
        ]);
        this.dialog.add(CashMoveListPopup, {
            cashMoves: cashMoves.map((m) => ({
                ...m,
                date: DateTime.fromSQL(m.date, { zone: "UTC" }).setZone("local"),
            })),
            partnerId: this.pos.user.partner_id.id,
        });
    },

    /**
     * Helper — detect if a payment method operates in Bs.F.
     */
    _isBsPaymentMethod(pmObj) {
        return isPaymentMethodBs(pmObj, this.pos);
    },

    /**
     * Helper — detect if a payment method operates in USD.
     */
    _isUsdPaymentMethod(pmObj) {
        return !isPaymentMethodBs(pmObj, this.pos);
    },

    /**
     * Format a monetary amount in both currencies.
     * Returns markup HTML: "X USD / Y Bs.F" or "Y Bs.F / X USD"
     */
        getDualFormattedAmount(amount, paymentMethodId = null) {
        if (!this.pos.config.show_dual_currency) {
            return this.env.utils.formatCurrency(amount);
        }
        const rate      = getDualRate(this.pos);
        const isMainUSD = isMainCurrencyUSD(this.pos);

        let isBsMethod = false;
        if (paymentMethodId != null) {
            const pm = this.pos.config.payment_method_ids?.find(p => p.id === paymentMethodId);
            isBsMethod = this._isBsPaymentMethod(pm);
        }

        let usdAmount, bsAmount;
        
        if (isMainUSD) {
            usdAmount = amount;
            bsAmount = mainToSecondary(amount, this.pos);
        } else {
            bsAmount = amount;
            usdAmount = mainToSecondary(amount, this.pos);
        }

        const mainSym = getMainSymbol(this.pos);
        const secSym  = getSecondarySymbol(this.pos);

        let usd_str = isMainUSD ? this.env.utils.formatCurrency(usdAmount) : `${usdAmount.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${secSym}`;
        let bs_str  = isMainUSD ? `${bsAmount.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${secSym}` : this.env.utils.formatCurrency(bsAmount);
        
        let colored_usd_str = `<span class="text-danger">${usd_str}</span>`;
        let colored_bs_str = `<span class="text-body fw-normal">${bs_str}</span>`;

        if (isBsMethod) {
            return markup(`${colored_bs_str} / ${colored_usd_str}`);
        }
        return markup(`${colored_usd_str} / ${colored_bs_str}`);
    },

    getOpeningAmount(paymentMethodId) {
        const pmObj = this.pos.config.payment_method_ids?.find(p => p.id === paymentMethodId);
        const isBsMethod = this._isBsPaymentMethod(pmObj);
        const isMainUSD = isMainCurrencyUSD(this.pos);
        const isPagoMovil = pmObj && pmObj.name && pmObj.name.toLowerCase().includes('pago');

        let amount = 0;
        let usedNative = false;
        
        if (isPagoMovil) {
            amount = this.pos.session.opening_pm_bs || 0;
        } else if (isBsMethod) {
            amount = this.pos.session.opening_cash_bs || 0;
        } else {
            if (this.pos.session.opening_cash_usd !== undefined) {
                amount = this.pos.session.opening_cash_usd;
            } else if (this.props.default_cash_details && this.props.default_cash_details.id === paymentMethodId) {
                amount = this.props.default_cash_details.opening || 0;
                usedNative = true; 
            }
        }

        if (!usedNative) {
            if (!isBsMethod && !isMainUSD) {
                amount = secondaryToMain(amount, this.pos);
            } else if (isBsMethod && isMainUSD) {
                amount = secondaryToMain(amount, this.pos);
            }
        }

        return amount;
    },

    getFormattedCounted(counted, paymentMethodId) {
        if (!counted) return this.getDualFormattedAmount(0, paymentMethodId);
        let floatCounted = parseFloat(counted.toString().replace(/[^0-9.,-]/g, '').replace(',', '.')) || 0;
        
        const pmObj = this.pos.config.payment_method_ids?.find(p => p.id === paymentMethodId);
        const isBsMethod = this._isBsPaymentMethod(pmObj);
        const isMainUSD = isMainCurrencyUSD(this.pos);

        if (!isBsMethod && !isMainUSD) {
            floatCounted = secondaryToMain(floatCounted, this.pos);
        } else if (isBsMethod && isMainUSD) {
            floatCounted = secondaryToMain(floatCounted, this.pos);
        }

        return this.getDualFormattedAmount(floatCounted, paymentMethodId);
    },

    /**
     * Format amount in MAIN currency to display ONLY the USD part.
     * Used for the default USD cash block where dual display is not needed.
     */
    getMainFormattedAmount(amount, paymentMethodId = null) {
        if (!this.pos.config.show_dual_currency) {
            return this.env.utils.formatCurrency(amount);
        }
        const isMainUSD = isMainCurrencyUSD(this.pos);
        const mainSym = getMainSymbol(this.pos);
        const secSym  = getSecondarySymbol(this.pos);

        let pmObj = null;
        let isBsMethod = false;
        if (paymentMethodId != null) {
            pmObj = this.pos.config.payment_method_ids?.find(p => p.id === paymentMethodId);
            isBsMethod = this._isBsPaymentMethod(pmObj);
        }

        // If this is a USD method, we ONLY want to show USD.
        if (!isBsMethod) {
            let usdAmount = amount;
            if (!isMainUSD) {
                // amount is in MAIN (Bs), convert back to secondary (USD)
                usdAmount = mainToSecondary(amount, this.pos);
            }
            const usdSym = isMainUSD ? mainSym : secSym;
            const usdStr = `${usdAmount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${usdSym}`;
            const { markup } = owl;
            return markup(`<span class="text-danger">${usdStr}</span>`);
        }

        // Fallback: full dual (for Bs methods)
        return this.getDualFormattedAmount(amount, paymentMethodId);
    },

    /**
     * Format counted value for USD cash input, displaying only USD.
     */
    getMainFormattedCounted(counted, paymentMethodId) {
        if (!counted) return this.getMainFormattedAmount(0, paymentMethodId);
        let val = parseFloat(counted.toString().replace(/[^0-9.,-]/g, '').replace(',', '.')) || 0;
        
        const pmObj = this.pos.config.payment_method_ids?.find(p => p.id === paymentMethodId);
        const isBsMethod = this._isBsPaymentMethod(pmObj);
        const isMainUSD = isMainCurrencyUSD(this.pos);

        // Convert the input (which is in USD for USD methods) to MAIN currency
        // because getMainFormattedAmount expects MAIN currency.
        if (!isBsMethod && !isMainUSD) {
            val = secondaryToMain(val, this.pos);
        } else if (isBsMethod && isMainUSD) {
            val = secondaryToMain(val, this.pos);
        }

        return this.getMainFormattedAmount(val, paymentMethodId);
    },


    getExpectedAmount(paymentId) {
        let expectedAmount =
            paymentId === this.props.default_cash_details?.id
                ? this.props.default_cash_details.amount
                : this.props.non_cash_payment_methods.find((pm) => pm.id === paymentId).amount;

        const pmObj = this.pos.config.payment_method_ids?.find(p => p.id === paymentId);
        const isBsMethod = this._isBsPaymentMethod(pmObj);
        const isMainUSD = isMainCurrencyUSD(this.pos);
        const isPagoMovil = pmObj && pmObj.name && pmObj.name.toLowerCase().includes('pago');

        if (paymentId === this.props.default_cash_details?.id && this.pos.session.opening_cash_usd !== undefined) {
            const nativeOpening = this.props.default_cash_details.opening || 0;
            
            let properOpening = 0;
            if (isBsMethod) {
                properOpening = this.pos.session.opening_cash_bs || 0;
            } else {
                let customUsd = this.pos.session.opening_cash_usd || 0;
                if (!isMainUSD) {
                    properOpening = secondaryToMain(customUsd, this.pos);
                } else {
                    properOpening = customUsd;
                }
            }
            
            expectedAmount = expectedAmount - nativeOpening + properOpening;
        } else if (pmObj && (pmObj.is_cash_count || isPagoMovil)) {
            // For non-default methods (Efectivo Bs, Pago Movil), Odoo natively only calculates transactions.
            // We must manually ADD our custom opening balances to the expected amount.
            let properOpening = 0;
            if (isPagoMovil) {
                properOpening = this.pos.session.opening_pm_bs || 0;
            } else if (isBsMethod) {
                properOpening = this.pos.session.opening_cash_bs || 0;
            } else {
                let customUsd = this.pos.session.opening_cash_usd || 0;
                if (!isMainUSD) {
                    properOpening = secondaryToMain(customUsd, this.pos);
                } else {
                    properOpening = customUsd;
                }
            }
            expectedAmount += properOpening;
        }

        return expectedAmount;
    },

    _getNativeCounted(pmId, amount) {
        const pmObj = this.pos.config.payment_method_ids?.find(p => p.id === pmId);
        const isBsMethod = this._isBsPaymentMethod(pmObj);
        const isMainUSD = isMainCurrencyUSD(this.pos);
        const expectedNative = this.getExpectedAmount(pmId);

        if (!isBsMethod && !isMainUSD) {
            // Usuario cuenta en USD (Moneda Secundaria)
            let expectedUsd = mainToSecondary(expectedNative, this.pos);
            if (Math.abs(amount - expectedUsd) < 0.01) {
                return expectedNative; // Cuadre perfecto, evitamos diferencias por tasa
            }
            return secondaryToMain(amount, this.pos);
        } else if (isBsMethod && isMainUSD) {
            // Usuario cuenta en Bs (Moneda Secundaria)
            let expectedBs = mainToSecondary(expectedNative, this.pos);
            if (Math.abs(amount - expectedBs) < 0.01) {
                return expectedNative; 
            }
            return secondaryToMain(amount, this.pos);
        }
        return amount; // Moneda Principal, no hay conversión
    },

    getDifference(paymentId) {
        const countedStr = this.state.payments[paymentId]?.counted;
        if (!this.env.utils.isValidFloat(countedStr)) return NaN;
        
        let amount = parseFloat(countedStr.toString().replace(/[^0-9.,-]/g, '').replace(',', '.')) || 0;
        let nativeCounted = this._getNativeCounted(paymentId, amount);
        let expectedNative = this.getExpectedAmount(paymentId);
        
        return nativeCounted - expectedNative;
    },



    getCashMoveDataFor(pmId) {
        let pm = (this.props.non_cash_payment_methods || []).find(p => p.id === pmId);
        if (!pm || !pm.moves) return { total: 0, moves: [] };
        
        return pm.moves.reduce(
            (acc, move, i) => {
                acc.total += move.amount;
                acc.moves.push({
                    id: i,
                    name: move.name,
                    amount: move.amount,
                });
                return acc;
            },
            { total: 0, moves: [] }
        );
    },

    /**
     * Override closeSession — save dual amounts and convert for native Odoo.
     * V19: non_cash_payment_methods, this.pos.session, this.pos.data.call()
     */
    async closeSession() {
        const cfg = this.pos.config;
        if (cfg && cfg.show_dual_currency) {
            try {
                let bsAmount = 0;
                let usdAmount = 0;
                let pmBsAmount = 0;
                const rate      = getDualRate(this.pos);
                const isMainUSD = isMainCurrencyUSD(this.pos);
                const decPoint  = this.env.services.localization?.decimalPoint || ',';

                // Default cash (Efectivo $)
                if (this.props.default_cash_details &&
                    this.state.payments?.[this.props.default_cash_details.id] !== undefined) {
                    const pmId = this.props.default_cash_details.id;
                    const countedStr = this.state.payments[pmId].counted;
                    const amount = parseFloat(
                        (countedStr || '0').toString().replace(/[^0-9.,-]/g, '').replace(',', '.')
                    ) || 0;
                    const pmObj = this.pos.config.payment_method_ids?.find(p => p.id === pmId);
                    const isBsMethod = this._isBsPaymentMethod(pmObj);
                    
                    let nativeVal = this._getNativeCounted(pmId, amount);
                    if (isBsMethod) {
                        bsAmount += amount;
                        if (isMainUSD && rate > 0) {
                            this.state.payments[pmId].counted = nativeVal.toFixed(2).replace('.', decPoint);
                        }
                    } else {
                        usdAmount += amount;
                        if (!isMainUSD && rate > 0) {
                            this.state.payments[pmId].counted = nativeVal.toFixed(2).replace('.', decPoint);
                        }
                    }
                }

                // Non-cash methods (V19: non_cash_payment_methods)
                (this.props.non_cash_payment_methods || []).forEach((pm) => {
                    if (!this.state.payments?.[pm.id]) return;
                    const pmObj      = this.pos.config.payment_method_ids?.find(p => p.id === pm.id);
                    const isBsMethod = this._isBsPaymentMethod(pmObj);
                    const isPagoMovil = pmObj && pmObj.name && pmObj.name.toLowerCase().includes('pago');
                    const countedStr = this.state.payments[pm.id].counted;
                    let amount = parseFloat(
                        (countedStr || '0').toString().replace(/[^0-9.,-]/g, '').replace(',', '.')
                    ) || 0;

                    let nativeVal = this._getNativeCounted(pm.id, amount);
                    if (isPagoMovil) {
                        pmBsAmount += amount;
                        if (isMainUSD && rate > 0) {
                            this.state.payments[pm.id].counted = nativeVal.toFixed(2).replace('.', decPoint);
                        }
                    } else if (isBsMethod) {
                        if (pmObj && pmObj.is_cash_count) {
                            bsAmount += amount;
                        }
                        if (isMainUSD && rate > 0) {
                            this.state.payments[pm.id].counted = nativeVal.toFixed(2).replace('.', decPoint);
                        }
                    } else {
                        if (pmObj && pmObj.is_cash_count) {
                            usdAmount += amount;
                        }
                        if (!isMainUSD && rate > 0) {
                            this.state.payments[pm.id].counted = nativeVal.toFixed(2).replace('.', decPoint);
                        }
                    }
                });

                // V19: this.pos.session (not pos_session)
                this.pos.session.closing_cash_bs  = bsAmount;
                this.pos.session.closing_cash_usd = usdAmount;
                this.pos.session.closing_pm_bs    = pmBsAmount;

                // V19: this.pos.data.call() (not this.orm.call())
                await this.pos.data.call(
                    'pos.session',
                    'set_dual_closing_cash',
                    [[this.pos.session.id], bsAmount, usdAmount, pmBsAmount]
                );

            } catch (e) {
                console.warn('[DualCurrency] closeSession dual error:', e);
            }
        }
        return super.closeSession(...arguments);
    },

    // ─── BOTONERA FISCAL ───────────────────────────────────────────────────────

    async printReportX() {
        if (!this.env.services.fiscal_printer) return;
        if (!this.env.services.fiscal_printer.state.isConnected) {
            await this.env.services.fiscal_printer.connect();
        }
        if (!this.env.services.fiscal_printer.state.isConnected) {
            this.env.services.notification.add("No hay impresora conectada", { type: "danger" });
            return;
        }
        this.env.services.notification.add("Enviando Reporte X...", { type: "info" });
        const resX = await this.env.services.fiscal_printer.printXReport();
        if (resX && resX.success !== false) {
            this.env.services.notification.add("Reporte X impreso exitosamente", { type: "success" });
        } else {
            const err = (resX && resX.error) ? resX.error : "";
            this.env.services.notification.add("Error al imprimir Reporte X: " + err, { type: "danger" });
        }
    },

    async printReportZ() {
        if (!this.env.services.fiscal_printer) return;
        if (!this.env.services.fiscal_printer.state.isConnected) {
            await this.env.services.fiscal_printer.connect();
        }
        if (!this.env.services.fiscal_printer.state.isConnected) {
            this.env.services.notification.add("No hay impresora conectada", { type: "danger" });
            return;
        }
        this.env.services.notification.add("Enviando Reporte Z...", { type: "info" });
        const resZ = await this.env.services.fiscal_printer.printZReport();
        if (resZ && resZ.success !== false) {
            this.env.services.notification.add("Reporte Z impreso exitosamente", { type: "success" });
            try {
                let zNumber     = parseInt(localStorage.getItem('mock_z_number')     || '1000');
                let lastInvoice = parseInt(localStorage.getItem('mock_last_invoice') || '0');
                zNumber += 1;
                const firstInvoice    = lastInvoice + 1;
                const newLastInvoice  = lastInvoice + Math.floor(Math.random() * 50) + 5;
                localStorage.setItem('mock_z_number', zNumber);
                localStorage.setItem('mock_last_invoice', newLastInvoice);

                const rate   = getDualRate(this.pos);
                
                // Fetch actual calculated totals from the backend session
                let sessionTotals = { taxable_main: 0, tax_main: 0, total_main: 0, igtf_main: 0 };
                try {
                    const backendTotals = await this.pos.data.call("pos.session", "compute_z_report_totals", [this.pos.session.id]);
                    sessionTotals.taxable_main = backendTotals.taxable_main || 0;
                    sessionTotals.tax_main = backendTotals.tax_main || 0;
                    sessionTotals.total_main = backendTotals.total_main || 0;
                    sessionTotals.igtf_main = backendTotals.igtf_main || 0;
                } catch (e) {
                    console.warn("[DualCurrency] Backend method compute_z_report_totals falló (seguramente no se reinició el servidor). Usando cálculo en JS.", e);
                    const allOrders = this.pos.models["pos.order"].getAll();
                    const fiscalOrders = allOrders.filter(o => o.session_id?.id === this.pos.session.id && o.is_fiscal_printed);
                    for (const o of fiscalOrders) {
                        // Use amount_total if available, otherwise calculate it
                        let total = o.amount_total !== undefined ? o.amount_total : (o.priceIncl || 0);
                        let excl = o.amount_total !== undefined ? (o.amount_total - (o.amount_tax || 0)) : (o.priceExcl || 0);
                        let tax = total - excl;
                        let igtf = o.igtf_charge || 0;
                        
                        // En Odoo 19, los reembolsos a veces tienen priceIncl en positivo en el frontend antes de sincronizar
                        // por lo que debemos asegurar que sea negativo si es un reembolso y estamos usando el getter
                        if (o.isRefund && total > 0) {
                            total = -total;
                            excl = -excl;
                            tax = -tax;
                            igtf = -igtf;
                        }
                        
                        sessionTotals.taxable_main += excl;
                        sessionTotals.tax_main += tax;
                        sessionTotals.total_main += total;
                        sessionTotals.igtf_main += igtf;
                    }
                }
                
                const isMainUSD = isMainCurrencyUSD(this.pos);
                
                let taxable_usd = isMainUSD ? sessionTotals.taxable_main : sessionTotals.taxable_main / rate;
                let tax_usd = isMainUSD ? sessionTotals.tax_main : sessionTotals.tax_main / rate;
                let total_usd = isMainUSD ? sessionTotals.total_main : sessionTotals.total_main / rate;
                
                let taxable_bs = isMainUSD ? sessionTotals.taxable_main * rate : sessionTotals.taxable_main;
                let tax_bs = isMainUSD ? sessionTotals.tax_main * rate : sessionTotals.tax_main;
                let total_bs = isMainUSD ? sessionTotals.total_main * rate : sessionTotals.total_main;

                let igtf_usd = isMainUSD ? sessionTotals.igtf_main : sessionTotals.igtf_main / rate;
                let igtf_bs = isMainUSD ? sessionTotals.igtf_main * rate : sessionTotals.igtf_main;

                const zData  = {
                    pos_config_id: this.pos.config.id,
                    z_number: zNumber,
                    first_invoice_number: firstInvoice,
                    last_invoice_number: newLastInvoice,
                    exempt_sales_usd: 0, taxable_sales_usd: taxable_usd,
                    tax_amount_usd: tax_usd,  total_sales_usd: total_usd,
                    igtf_amount_usd: igtf_usd,
                    exempt_sales_bs: 0,  taxable_sales_bs: taxable_bs,
                    tax_amount_bs: tax_bs, total_sales_bs: total_bs,
                    igtf_amount_bs: igtf_bs,
                    time: new Date().toLocaleTimeString('en-US', { hour12: false }),
                };
                await this.pos.data.call("pos.fiscal.z.report", "save_z_report", [zData]);
            } catch (e) {
                console.error('[DualCurrency] printReportZ error:', e);
            }
        } else {
            this.env.services.notification.add("Error al imprimir Reporte Z", { type: "danger" });
        }
    },

    async printPaymentReport() {
        if (!this.env.services.printer) return;
        const rate       = getDualRate(this.pos);
        const isMainUSD  = isMainCurrencyUSD(this.pos);
        const reportData = {
            session_id: this.pos.session.name,
            rate, is_main_usd: isMainUSD,
            date: new Date().toLocaleDateString(),
            main_symbol: getMainSymbol(this.pos),
            sec_symbol:  getSecondarySymbol(this.pos),
            payments: [], total_opening: 0, total_expected: 0,
            total_counted: 0, total_difference: 0,
        };

        if (this.props.default_cash_details) {
            const pmId     = this.props.default_cash_details.id;
            const expected = this.props.default_cash_details.amount || 0;
            const diff     = this.getDifference(pmId);
            reportData.payments.push({
                name: this.props.default_cash_details.name,
                opening: this.props.default_cash_details.opening || 0,
                moves: 0, expected, counted: expected + diff,
                total_sec: isMainUSD ? (expected + diff) * rate : (expected + diff) / rate,
                difference: diff, id: pmId,
            });
        }

        (this.props.non_cash_payment_methods || []).forEach(pm => {
            const expected = this.getExpectedAmount(pm.id);
            const diff     = this.getDifference(pm.id);
            reportData.payments.push({
                name: pm.name, opening: 0, moves: 0, expected,
                counted: expected + diff,
                total_sec: isMainUSD ? (expected + diff) * rate : (expected + diff) / rate,
                difference: diff, id: pm.id,
            });
        });

        await this.env.services.printer.print(
            PaymentReportReceipt,
            { data: reportData },
            { webPrintFallback: true }
        );
    },
});
