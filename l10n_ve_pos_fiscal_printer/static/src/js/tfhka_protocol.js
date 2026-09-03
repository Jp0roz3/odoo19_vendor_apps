/** @odoo-module **/

/**
 * Motor de Protocolo y Tramas TFHKA (The Factory HKA)
 * Homologado para Bixolon SRP-812, DT-230, HKA-80, Dascom PP9
 * Cumplimiento estricto de la normativa fiscal venezolana (SENIAT)
 */

export const TFHKA_CHARS = {
    STX: 0x02,
    ETX: 0x03,
    EOT: 0x04,
    ENQ: 0x05,
    ACK: 0x06,
    NAK: 0x15,
};

export const TFHKA_TAX_FLAGS = {
    GENERAL_16: '!', // ASCII 0x21 - Tasa General (16%)
    REDUCED_8:  '"', // ASCII 0x22 - Tasa Reducida (8%)
    ADDITIONAL_31: '#', // ASCII 0x23 - Tasa Adicional (31%)
    EXEMPT:     ' ', // ASCII 0x20 - Exento (0%)
};

export const TFHKA_RETURN_TAX_FLAGS = {
    EXEMPT:     'd0',
    GENERAL_16: 'd1',
    REDUCED_8:  'd2',
    ADDITIONAL_31: 'd3',
};

export const TFHKA_PAYMENT_CODES = {
    CASH_BS: '01',        // Efectivo Bs
    CHECK: '02',          // Cheque
    CARD_DEBIT: '04',     // Tarjeta de Débito
    CARD_CREDIT: '05',    // Tarjeta de Crédito
    TRANSFER: '07',       // Transferencia / Pago Móvil
    CASH_USD: '16',       // Divisas Efectivo
    ELECTRONIC_USD: '17', // Divisas Electrónico
    IGTF: '20',           // IGTF 3% Percibido
};

export class TfhkaProtocol {
    /**
     * Calcula el LRC (Longitudinal Redundancy Check)
     * Regla oficial TFHKA: XOR sucesivo de todos los bytes entre el comando y ETX inclusive.
     */
    static calculateLRC(bytesArray) {
        let lrc = 0;
        for (let i = 0; i < bytesArray.length; i++) {
            lrc ^= bytesArray[i];
        }
        return lrc & 0xFF;
    }

    /**
     * Construye la trama física para envío serial:
     * [STX] + [Seq] + [Comando...] + [ETX] + [LRC]
     */
    static buildFrame(cmdStr, seq = 0x30) {
        const payload = [seq];
        for (let i = 0; i < cmdStr.length; i++) {
            payload.push(cmdStr.charCodeAt(i));
        }
        payload.push(TFHKA_CHARS.ETX);

        const lrc = this.calculateLRC(payload);
        return new Uint8Array([TFHKA_CHARS.STX, ...payload, lrc]);
    }

    /**
     * Formatea un precio según protocolo HKA:
     * 10 caracteres numéricos (8 enteros + 2 decimales sin punto ni coma).
     * Ejemplo: 12.50 -> "0000001250"
     */
    static formatPrice(amount, totalLen = 10) {
        const cents = Math.round(Math.abs(amount) * 100);
        return cents.toString().padStart(totalLen, '0');
    }

    /**
     * Formatea una cantidad según protocolo HKA:
     * 8 caracteres numéricos (5 enteros + 3 decimales sin punto ni coma).
     * Ejemplo: 1.500 -> "00001500"
     */
    static formatQuantity(qty, totalLen = 8) {
        const millis = Math.round(Math.abs(qty) * 1000);
        return millis.toString().padStart(totalLen, '0');
    }

    /**
     * Formatea un monto total o pago:
     * 12 caracteres numéricos (10 enteros + 2 decimales).
     * Ejemplo: 150.00 -> "000000015000"
     */
    static formatTotal(amount, totalLen = 12) {
        const cents = Math.round(Math.abs(amount) * 100);
        return cents.toString().padStart(totalLen, '0');
    }

    /**
     * Limpia y normaliza el RIF o Cédula según estándar SENIAT
     */
    static formatRif(rawRif) {
        if (!rawRif) return "V000000000";
        let clean = rawRif.toString().trim().toUpperCase().replace(/[^VJEGP0-9]/g, '');
        if (!/^[VJEGP]/.test(clean)) {
            clean = 'V' + clean;
        }
        return clean.substring(0, 15);
    }

    /**
     * Limpia cadenas de texto para eliminar tildes, caracteres especiales incompatibles y acotar longitud
     */
    static sanitizeText(text, maxLen = 38) {
        if (!text) return "";
        let clean = text.toString()
            .normalize("NFD").replace(/[\u0300-\u036f]/g, "") // Quitar tildes
            .replace(/[^\x20-\x7E]/g, " ")                    // Solo ASCII imprimible
            .trim();
        return clean.substring(0, maxLen);
    }

    /**
     * Determina la tasa fiscal HKA aplicable a una línea de producto (Odoo 19)
     */
    static getTaxFlag(line) {
        let taxes = line.taxes_id || line.tax_ids || (line.product_id ? line.product_id.taxes_id : []) || (line.product ? line.product.taxes_id : []) || (line.get_taxes ? line.get_taxes() : []);
        if (!taxes || taxes.length === 0) return TFHKA_TAX_FLAGS.EXEMPT;

        let taxAmount = 0;
        let t = Array.isArray(taxes) ? taxes[0] : taxes;
        if (typeof t === 'object' && t !== null) {
            taxAmount = t.amount !== undefined ? t.amount : 0;
        } else if (typeof t === 'number') {
            taxAmount = t;
        }

        // Búsqueda en el modelo reactivo de account.tax si solo llegó el ID
        if (taxAmount === 0 && typeof t === 'number' && line.models && line.models['account.tax']) {
            const taxObj = line.models['account.tax'].get(t);
            if (taxObj && taxObj.amount) taxAmount = taxObj.amount;
        }

        if (Math.abs(taxAmount - 16) < 0.05) return TFHKA_TAX_FLAGS.GENERAL_16;
        if (Math.abs(taxAmount - 8) < 0.05)  return TFHKA_TAX_FLAGS.REDUCED_8;
        if (Math.abs(taxAmount - 31) < 0.05) return TFHKA_TAX_FLAGS.ADDITIONAL_31;
        return TFHKA_TAX_FLAGS.EXEMPT;
    }

    /**
     * Determina la tasa para Nota de Crédito (Devolución)
     */
    static getReturnTaxFlag(line) {
        let flag = this.getTaxFlag(line);
        if (flag === TFHKA_TAX_FLAGS.GENERAL_16) return TFHKA_RETURN_TAX_FLAGS.GENERAL_16;
        if (flag === TFHKA_TAX_FLAGS.REDUCED_8)  return TFHKA_RETURN_TAX_FLAGS.REDUCED_8;
        if (flag === TFHKA_TAX_FLAGS.ADDITIONAL_31) return TFHKA_RETURN_TAX_FLAGS.ADDITIONAL_31;
        return TFHKA_RETURN_TAX_FLAGS.EXEMPT;
    }

    /**
     * Genera la secuencia completa de comandos fiscales para una Factura
     */
    static buildInvoiceCommands(order, options = {}) {
        const cmds = [];
        const partner = order.getPartner ? order.getPartner() : (order.partner || order.partner_id);
        const clientName = partner ? (partner.name || partner.display_name) : "CLIENTE DE CONTADO";
        const clientRif = partner ? (partner.vat || partner.rif || "") : "V000000000";

        // 1. Datos del Cliente
        cmds.push(`i01${this.sanitizeText(clientName, 38)}`);
        cmds.push(`i02${this.formatRif(clientRif)}`);
        if (partner && partner.street) {
            cmds.push(`i03${this.sanitizeText(partner.street, 38)}`);
        }
        if (partner && (partner.phone || partner.mobile)) {
            cmds.push(`i04${this.sanitizeText(partner.phone || partner.mobile, 38)}`);
        }

        // 2. Líneas de Producto
        const lines = order.lines || (order.getOrderlines ? order.getOrderlines() : (order.get_orderlines ? order.get_orderlines() : []));
        for (const line of lines) {
            const prod = line.product_id || (line.getProduct ? line.getProduct() : line.product);
            const name = this.sanitizeText(prod ? (prod.display_name || prod.name) : "PRODUCTO", 36);

            let unitPrice = line.priceUnit ?? line.price_unit ?? (line.get_unit_price ? line.get_unit_price() : (line.price || 0));
            const discount = line.discount || 0;
            if (discount > 0) {
                unitPrice = unitPrice * (1 - (discount / 100));
            }

            const price = this.formatPrice(unitPrice, 10);
            const qtyVal = line.qty ?? (line.getQuantity ? line.getQuantity() : (line.get_quantity ? line.get_quantity() : 1));
            const qty = this.formatQuantity(qtyVal, 8);
            const taxFlag = this.getTaxFlag(line);

            cmds.push(`${taxFlag}${price}${qty}${name}`);
        }

        // 3. Subtotal
        cmds.push("3");

        // 4. Pagos
        const payments = order.payment_ids || (order.get_paymentlines ? order.get_paymentlines() : (order.paymentlines || []));
        if (!payments || payments.length === 0) {
            cmds.push("101"); // Cierre en efectivo total
        } else {
            for (let i = 0; i < payments.length; i++) {
                const p = payments[i];
                const pm = p.payment_method_id || p.payment_method || {};
                const pmName = (pm.name || (typeof pm === 'string' ? pm : '') || '').toLowerCase();
                const isLast = (i === payments.length - 1);
                const prefix = isLast ? "1" : "2";

                let code = TFHKA_PAYMENT_CODES.CASH_BS;
                if (pmName.includes("dolar") || pmName.includes("usd") || pmName.includes("$") || pm.is_igtf) {
                    code = TFHKA_PAYMENT_CODES.CASH_USD;
                } else if (pmName.includes("debit") || pmName.includes("debito")) {
                    code = TFHKA_PAYMENT_CODES.CARD_DEBIT;
                } else if (pmName.includes("credit") || pmName.includes("credito")) {
                    code = TFHKA_PAYMENT_CODES.CARD_CREDIT;
                } else if (pmName.includes("transfer") || pmName.includes("movil") || pmName.includes("pago movil")) {
                    code = TFHKA_PAYMENT_CODES.TRANSFER;
                }

                const amtFormatted = this.formatTotal(p.amount || 0, 12);
                cmds.push(`${prefix}${code}${amtFormatted}`);
            }
        }

        return cmds;
    }

    /**
     * Genera la secuencia completa de comandos para Nota de Crédito
     */
    static buildCreditNoteCommands(order, origInvoice, origSerial) {
        const cmds = [];
        const partner = order.getPartner ? order.getPartner() : (order.partner || order.partner_id);
        const clientName = partner ? (partner.name || partner.display_name) : "CLIENTE DE CONTADO";
        const clientRif = partner ? (partner.vat || partner.rif || "") : "V000000000";

        cmds.push(`i01${this.sanitizeText(clientName, 38)}`);
        cmds.push(`i02${this.formatRif(clientRif)}`);
        if (origInvoice) {
            cmds.push(`i05Factura Afectada: ${this.sanitizeText(origInvoice, 20)}`);
        }
        if (origSerial) {
            cmds.push(`i06Serial Impresora: ${this.sanitizeText(origSerial, 20)}`);
        }

        const lines = order.lines || (order.getOrderlines ? order.getOrderlines() : (order.get_orderlines ? order.get_orderlines() : []));
        for (const line of lines) {
            const prod = line.product_id || (line.getProduct ? line.getProduct() : line.product);
            const name = this.sanitizeText(prod ? (prod.display_name || prod.name) : "DEVOLUCION", 36);

            let unitPrice = Math.abs(line.priceUnit ?? line.price_unit ?? (line.get_unit_price ? line.get_unit_price() : (line.price || 0)));
            const discount = line.discount || 0;
            if (discount > 0) {
                unitPrice = unitPrice * (1 - (discount / 100));
            }

            const price = this.formatPrice(unitPrice, 10);
            const qtyVal = Math.abs(line.qty ?? (line.getQuantity ? line.getQuantity() : (line.get_quantity ? line.get_quantity() : 1)));
            const qty = this.formatQuantity(qtyVal, 8);
            const taxFlag = this.getReturnTaxFlag(line);

            cmds.push(`${taxFlag}${price}${qty}${name}`);
        }

        cmds.push("3");
        cmds.push("101"); // Cierre total devolución
        return cmds;
    }
}
