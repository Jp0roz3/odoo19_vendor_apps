/** @odoo-module */
/**
 * PaymentScreen — Dual Currency + Stock Deduction (Odoo 19)
 *
 * NOTAS DE ARQUITECTURA:
 * 1. validateOrder en Odoo 19 es una arrow function de instancia (class field).
 *    patch(prototype) no la intercepta. Se envuelve desde setup().
 * 2. La impresión fiscal NO va aquí — está en models.js > afterOrderValidation.
 *    Ponerla aquí causaba doble-impresión y un error de fecha de factura.
 * 3. PosOrder.set_to_invoice() fuerza to_invoice=false cuando fiscal_printer_active.
 *    Por tanto order.isToInvoice() siempre es false con impresora fiscal.
 */
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { getDualRate, getBsCashMethod, isMainCurrencyUSD, isPaymentMethodBs, stockOverrides, secondaryToMain, mainToSecondary } from "./dual_currency_utils";

patch(PaymentScreen.prototype, {

    // ── setup: Envolver validateOrder sea prototipo o arrow function ─────────
    setup() {
        super.setup(...arguments);

        // Guardamos la referencia DESPUÉS de que el constructor la asignó.
        // Funciona tanto si es prototipo como si es arrow function de clase.
        const original = this.validateOrder.bind(this);
        const self = this;
        this.validateOrder = async function(isForceValidate) {
            return self._dualValidateOrder(isForceValidate, original);
        };
    },

    // ── Toda la lógica de validación va aquí ─────────────────────────────────
    async _dualValidateOrder(isForceValidate, superValidate) {
        const order = this.currentOrder;

        // --- BLOQUEO ANTI-FRAUDE: SENIAT ---
        if (order) {
            let isLinkedRefund = false;
            for (const line of order.lines) {
                if (line.refunded_orderline_id) {
                    isLinkedRefund = true;
                }

                // Bloqueo Cantidad Cero
                if (line.qty <= 0 && !line.refunded_orderline_id) {
                    const productName = line.product_id ? line.product_id.display_name : 'Desconocido';
                    this.dialog.add(AlertDialog, {
                        title: _t("Cantidad Inválida"),
                        body: _t("No se puede facturar el producto '" + productName + "' con cantidad 0 o menor."),
                    });
                    return false;
                }

                // Bloqueo Stock Negativo
                if (line.product_id && line.product_id.is_storable && !line.refunded_orderline_id) {
                    const available = line.product_id.qty_available !== undefined ? line.product_id.qty_available : 0;
                    if (available < line.qty) {
                        const productName = line.product_id.display_name || 'Desconocido';
                        this.dialog.add(AlertDialog, {
                            title: _t("Stock Insuficiente"),
                            body: _t("No hay suficiente inventario para facturar '" + productName + "'. Solicitado: " + line.qty + ", Disponible: " + available + "."),
                        });
                        return false;
                    }
                }

                // Bloqueo Precio Cero o Negativo
                if (line.price_unit <= 0 && !line.refunded_orderline_id) {
                    const productName = line.product_id ? line.product_id.display_name : 'Desconocido';
                    this.dialog.add(AlertDialog, {
                        title: _t("Precio Inválido"),
                        body: _t("El SENIAT prohíbe facturar productos con precio cero o negativo. (Producto: '" + productName + "')"),
                    });
                    return false;
                }

                // Bloqueo Descuento 100%
                if (line.discount >= 100) {
                    const productName = line.product_id ? line.product_id.display_name : 'Desconocido';
                    this.dialog.add(AlertDialog, {
                        title: _t("Descuento Inválido"),
                        body: _t("No se permiten descuentos del 100% o superiores (Evasión de Base Imponible). Producto: '" + productName + "'."),
                    });
                    return false;
                }
            }

            // Bloqueo Devoluciones Manuales
            if (order.priceIncl < 0 && !isLinkedRefund) {
                this.dialog.add(AlertDialog, {
                    title: _t("Devolución No Autorizada"),
                    body: _t("El SENIAT prohíbe facturar devoluciones manuales en negativo. Para procesar un reembolso, vacíe el carrito y utilice el botón 'Reembolso' en la pantalla de Tickets para vincular la operación a una factura original."),
                });
                return false;
            }
        }

        // --- GUARDAR IGTF EN LA ORDEN ---
        if (order && this.pos.config.show_dual_currency) {
            const igtfLines = order.payment_ids.filter(l => l.payment_method_id && l.payment_method_id.is_igtf);
            const igtfBase = igtfLines.reduce((acc, l) => acc + (l.amount || 0), 0);
            const igtfPct = ((this.pos.company && this.pos.company.igtf_percentage != null) ? this.pos.company.igtf_percentage : 3.0) / 100;
            order.igtf_charge = parseFloat((igtfBase * igtfPct).toFixed(2));
        }

        // --- INYECCIÓN AUTOMÁTICA DE VUELTO EN BS ---
        // INGENIERÍA: El cajero no siempre teclea en el calculador de vuelto.
        // Este bloque detecta el sobrante EN TIEMPO DE VALIDACIÓN y lo inyecta
        // automáticamente como una línea negativa en el método "Efectivo Bs".
        // Así el cajón de Bs queda correctamente saldado en el cierre de caja.
        if (order && this.pos.config.show_dual_currency) {
            const rate = getDualRate(this.pos);
            if (rate > 0) {
                const bsCashMethod = getBsCashMethod(this.pos);
                const usdCashMethod = this.pos.config.payment_method_ids.find(
                    pm => pm.type === 'cash' && !isPaymentMethodBs(pm, this.pos)
                );

                // Calcular sobrante ANTES de añadir líneas nuevas
                const totalPaid = order.payment_ids.reduce((s, l) => s + (l.amount || 0), 0);
                const orderDue = order.priceIncl;
                const overpaymentMain = Math.round((totalPaid - orderDue) * 1000) / 1000;

                // Solo actuar si hay sobrante real (> 1 Bs de tolerancia)
                if (overpaymentMain > 1 && bsCashMethod) {
                    // Verificar que el sobrante viene de un pago en USD (no en Bs)
                    const hasUsdCashPayment = order.payment_ids.some(l =>
                        l.payment_method_id &&
                        l.payment_method_id.type === 'cash' &&
                        !isPaymentMethodBs(l.payment_method_id, this.pos) &&
                        l.amount > 0
                    );

                    if (hasUsdCashPayment) {
                        // ¿El cajero usó el calculador manual?
                        const manualBsChange = order.dual_change_primary || 0;
                        const manualUsdChange = order.dual_change_sec || 0;

                        if (manualBsChange > 0 || manualUsdChange > 0) {
                            // MODO MANUAL: respetar lo que indicó el cajero
                            if (manualBsChange > 0 && bsCashMethod) {
                                const amtMain = isMainCurrencyUSD(this.pos)
                                    ? manualBsChange / rate : manualBsChange;
                                this.currentOrder.addPaymentline(bsCashMethod);
                                const lines = order.payment_ids;
                                const ln = lines[lines.length - 1];
                                if (ln && ln.payment_method_id && ln.payment_method_id.id === bsCashMethod.id) {
                                    ln.setAmount(-amtMain);
                                }
                            }
                            if (manualUsdChange > 0 && usdCashMethod) {
                                const amtMain = isMainCurrencyUSD(this.pos)
                                    ? manualUsdChange : manualUsdChange * rate;
                                this.currentOrder.addPaymentline(usdCashMethod);
                                const lines = order.payment_ids;
                                const ln = lines[lines.length - 1];
                                if (ln && ln.payment_method_id && ln.payment_method_id.id === usdCashMethod.id) {
                                    ln.setAmount(-amtMain);
                                }
                            }
                        } else {
                            // MODO AUTOMÁTICO: dar el sobrante completo como vuelto en Bs
                            // (comportamiento predeterminado en Venezuela: vuelto en bolívares)
                            const changeAmtMain = isMainCurrencyUSD(this.pos)
                                ? overpaymentMain  // ya en USD
                                : overpaymentMain; // ya en Bs
                            this.currentOrder.addPaymentline(bsCashMethod);
                            const lines = order.payment_ids;
                            const ln = lines[lines.length - 1];
                            if (ln && ln.payment_method_id && ln.payment_method_id.id === bsCashMethod.id) {
                                ln.setAmount(-changeAmtMain);
                            }
                            console.log(`[DUAL-CHANGE] Auto-vuelto inyectado: -${changeAmtMain} Bs bajo "${bsCashMethod.name}"`);
                        }

                        order.dual_change_sec = 0;
                        order.dual_change_primary = 0;
                    }
                }
            }
        }



        // --- IMPRESIÓN FISCAL: manejada por afterOrderValidation en models.js ---
        // CRÍTICO: Si el patch set_to_invoice no funciona (arrow fn en Odoo 19),
        // forzamos to_invoice=false aquí directamente para evitar que superValidate
        // intente crear un account.move (que falla con error de fecha UTC vs UTC-4).
        if (this.pos.config.fiscal_printer_active) {
            order.to_invoice = false;
        }

        // ── STOCK DEDUCTION ────────────────────────────────────────────────────
        // Mecanismo: escribir en stockOverrides[tmplId] (reactive() de OWL).
        // ProductCard.qtyDisplay lee stockOverrides[tmplId] → OWL re-renderiza
        // automáticamente cada tarjeta cuando cambia esa clave.
        if (order && order.get_orderlines) {
            for (const line of order.get_orderlines()) {
                if (!line.refunded_orderline_id && line.get_quantity() > 0 && !line.is_igtf_line) {
                    const qty = line.get_quantity();
                    const lineProduct = line.product_id;
                    if (!lineProduct) continue;

                    // ── Determinar el tmplId ──────────────────────────────────
                    let tmplId = null;

                    // A: lineProduct ES el template (tiene product_variant_ids)
                    if (lineProduct.product_variant_ids !== undefined) {
                        tmplId = lineProduct.id;
                    }

                    // B: lineProduct tiene product_tmpl_id
                    if (tmplId === null && lineProduct.product_tmpl_id !== undefined) {
                        const ref = lineProduct.product_tmpl_id;
                        tmplId = typeof ref === 'object'
                            ? (ref?.id ?? ref?.[0] ?? null)
                            : (typeof ref === 'number' ? ref : null);
                    }

                    // C: buscar iterando product.template por sus variant IDs
                    if (tmplId === null) {
                        const prodId = typeof lineProduct === 'object' ? lineProduct.id : lineProduct;
                        const tmplModel = this.pos.models['product.template'];
                        if (tmplModel) {
                            const all = typeof tmplModel.getAll === 'function'
                                ? tmplModel.getAll()
                                : (typeof tmplModel.values === 'function' ? [...tmplModel.values()] : []);
                            for (const t of all) {
                                const vids = (t.product_variant_ids || []).map(
                                    v => typeof v === 'object' ? (v.id ?? v[0]) : v
                                );
                                if (vids.includes(prodId)) {
                                    tmplId = t.id;
                                    break;
                                }
                            }
                        }
                    }

                    if (tmplId !== null) {
                        // Calcular nuevo stock: usar stockOverrides si ya fue mutado, o qty_available
                        const currentQty = stockOverrides[tmplId] !== undefined
                            ? stockOverrides[tmplId]
                            : (lineProduct.qty_available ?? 0);
                        const newQty = Math.max(0, currentQty - qty);

                        // ★ CLAVE: escribir en reactive() → OWL re-renderiza ProductCard ★
                        stockOverrides[tmplId] = newQty;

                        console.log('[Stock] stockOverrides[' + tmplId + '] =', newQty, '(era', currentQty, ')');
                        this.env.services.notification.add(
                            `Stock: ${lineProduct.display_name || tmplId} → ${newQty} uds`,
                            { type: 'success', sticky: false }
                        );
                    } else {
                        console.warn('[Stock] FAIL: no tmplId para product', lineProduct?.id);
                    }
                }
            }
        }

        // ── EJECUTAR VALIDACIÓN ORIGINAL ──────────────────────────────────────
        return await superValidate(isForceValidate);
    },

    // ── Otros métodos del PaymentScreen ──────────────────────────────────────
    updateSelectedPaymentline(amount = false) {
        if (this.paymentLines.every((line) => line.paid)) {
            this.currentOrder.addPaymentline(this.payment_methods_from_config[0]);
        }
        if (!this.selectedPaymentLine) {
            return;
        }
        if (amount === false) {
            if (this.numberBuffer.get() === null) {
                amount = null;
            } else if (this.numberBuffer.get() === "") {
                amount = 0;
            } else {
                amount = this.numberBuffer.getFloat();
            }
        }
        const payment_terminal = this.selectedPaymentLine.payment_method_id.payment_terminal;
        const hasCashPaymentMethod = this.payment_methods_from_config.some(
            (method) => method.type === "cash"
        );
        if (
            !hasCashPaymentMethod &&
            amount > this.currentOrder.remainingDue + this.selectedPaymentLine.amount
        ) {
            this.selectedPaymentLine.setAmount(0);
            this.numberBuffer.set(this.currentOrder.remainingDue.toString());
            amount = this.currentOrder.remainingDue;
            this.showMaxValueError();
        }
        if (
            payment_terminal &&
            !["pending", "retry"].includes(this.selectedPaymentLine.getPaymentStatus())
        ) {
            return;
        }
        if (amount === null) {
            this.deletePaymentLine(this.selectedPaymentLine.uuid);
        } else {
            let rate = getDualRate(this.pos);
            let isMainUSD = isMainCurrencyUSD(this.pos);
            let price_other_currency = amount;

            let pmObj = this.pos.config.payment_method_ids?.find(p => p.id === this.selectedPaymentLine.payment_method_id.id);
            if (pmObj && isPaymentMethodBs(pmObj, this.pos)) {
                // Si la línea es de la moneda principal (Bs), el monto introducido YA está en la moneda principal.
                // A menos que por alguna extraña configuración isMainUSD sea true.
                if (isMainUSD) price_other_currency = secondaryToMain(amount, this.pos);
            } else {
                // Si la línea es USD (secundaria), y la base es Bs, el input 'amount' está en USD.
                // Hay que convertirlo a la moneda base (Bs) usando secondaryToMain.
                if (!isMainUSD) price_other_currency = secondaryToMain(amount, this.pos);
            }

            if (this.selectedPaymentLine.set_usd_amt) {
                this.selectedPaymentLine.set_usd_amt(this.numberBuffer.getFloat());
            }
            this.selectedPaymentLine.setAmount(price_other_currency);

            if (this.currentOrder && this.currentOrder.recompute_igtf_line) {
                this.currentOrder.recompute_igtf_line();
            }
        }
    },

    async addNewPaymentLine(paymentMethod) {
        let rate = getDualRate(this.pos);
        let isMainUSD = isMainCurrencyUSD(this.pos);
        let pmObj = this.pos.config.payment_method_ids?.find(p => p.id === paymentMethod.id);
        
        // FIX: Si el buffer está vacío (el usuario no tecleó nada y solo hizo clic en el método),
        // Odoo nativo pre-llenará el buffer con el remainingDue (que está en Bs). 
        // Como nuestro updateSelectedPaymentline multiplica los pagos en divisa, 
        // 5000 Bs se convertirían en 3.8 Millones de Bs.
        // Solución: Pre-llenamos el buffer en USD para que la matemática nativa fluya perfecta.
        if (this.numberBuffer.get() === "") {
            if (pmObj && !isPaymentMethodBs(pmObj, this.pos) && !isMainUSD && rate > 0) {
                let usd_due = this.currentOrder.remainingDue / rate;
                this.numberBuffer.set(usd_due.toString());
            }
        }
        
        const result = await super.addNewPaymentLine(...arguments);
        if (result && this.selectedPaymentLine) {
            // FIX: If the newly added line is USD, Odoo natively sets the numberBuffer
            // to the remaining due in Bs. We must convert it to USD so the numpad works correctly!
            if (pmObj && !isPaymentMethodBs(pmObj, this.pos)) {
                if (!isMainUSD && rate > 0) {
                    let usd_amount = this.selectedPaymentLine.getAmount() / rate;
                    this.numberBuffer.set(usd_amount.toFixed(2));
                }
            }

            if (this.currentOrder && this.currentOrder.recompute_igtf_line) {
                // Al agregar la línea, Odoo la crea por el monto total de la deuda.
                // Si la deuda queda en 0, significa que esta línea intentaba pagarlo todo.
                const wasFullyPaid = this.currentOrder.remainingDue <= 0.001;
                
                this.currentOrder.recompute_igtf_line();

                // Si al recalcular el IGTF se agregó impuesto, la orden volverá a tener deuda.
                // Si la intención del usuario era pagar todo con este método (wasFullyPaid), 
                // sumamos ese nuevo IGTF a la línea de pago actual automáticamente.
                if (wasFullyPaid && this.currentOrder.remainingDue > 0.001) {
                    const diff = this.currentOrder.remainingDue;
                    const newAmt = this.selectedPaymentLine.getAmount() + diff;
                    this.selectedPaymentLine.setAmount(newAmt);
                    
                    // Actualizamos el buffer del teclado numérico con el nuevo monto total
                    if (pmObj && !isPaymentMethodBs(pmObj, this.pos)) {
                        if (!isMainUSD && rate > 0) {
                            let usd_amount = newAmt / rate;
                            this.numberBuffer.set(usd_amount.toFixed(2));
                            if (this.selectedPaymentLine.set_usd_amt) {
                                this.selectedPaymentLine.set_usd_amt(usd_amount);
                            }
                        }
                    } else if (pmObj && isPaymentMethodBs(pmObj, this.pos)) {
                        if (isMainUSD && rate > 0) {
                            let bs_amount = newAmt * rate;
                            this.numberBuffer.set(bs_amount.toFixed(2));
                        } else {
                            this.numberBuffer.set(newAmt.toFixed(2));
                        }
                    }
                    
                    // Recalculamos por si acaso
                    this.currentOrder.recompute_igtf_line();
                } else if (wasFullyPaid && this.currentOrder.change > 0.001 && pmObj && isPaymentMethodBs(pmObj, this.pos)) {
                    // Convergencia iterativa para métodos en Bs: si al agregar el pago el IGTF bajó, generó un cambio fantasma.
                    let iter = 0;
                    while ((this.currentOrder.change > 0.001 || this.currentOrder.remainingDue > 0.001) && iter < 10) {
                        if (this.currentOrder.change > 0.001) {
                            this.selectedPaymentLine.setAmount(this.selectedPaymentLine.getAmount() - this.currentOrder.change);
                        } else if (this.currentOrder.remainingDue > 0.001) {
                            this.selectedPaymentLine.setAmount(this.selectedPaymentLine.getAmount() + this.currentOrder.remainingDue);
                        }
                        this.currentOrder.recompute_igtf_line();
                        iter++;
                    }
                    
                    if (isMainUSD && rate > 0) {
                        let bs_amount = this.selectedPaymentLine.getAmount() * rate;
                        this.numberBuffer.set(bs_amount.toFixed(2));
                    } else {
                        this.numberBuffer.set(this.selectedPaymentLine.getAmount().toFixed(2));
                    }
                }
            }
        }
        return result;
    },

    selectPaymentLine(uuid) {
        super.selectPaymentLine(...arguments);
        if (this.selectedPaymentLine) {
            // FIX: When selecting an existing USD line, the buffer must be the USD amount,
            // not the base currency (Bs) amount!
            let rate = getDualRate(this.pos);
            let isMainUSD = isMainCurrencyUSD(this.pos);
            let pmObj = this.pos.config.payment_method_ids?.find(p => p.id === this.selectedPaymentLine.payment_method_id.id);
            if (pmObj && !isPaymentMethodBs(pmObj, this.pos)) {
                if (!isMainUSD) {
                    let usd_amount = mainToSecondary(this.selectedPaymentLine.getAmount(), this.pos);
                    // If the user already set a custom USD amount, use it if available
                    if (this.selectedPaymentLine.get_usd_amt && this.selectedPaymentLine.get_usd_amt() > 0) {
                        usd_amount = this.selectedPaymentLine.get_usd_amt();
                    }
                    this.numberBuffer.set(usd_amount.toFixed(2));
                }
            }
        }
    },

    deletePaymentLine(uuid) {
        const line = this.paymentLines.find((line) => line.uuid === uuid);
        if (!line) return; // FIX: Odoo 19 native bug where double clicking X crashes
        super.deletePaymentLine(...arguments);
        if (this.currentOrder && this.currentOrder.recompute_igtf_line) {
            this.currentOrder.recompute_igtf_line();
        }
    },
});
