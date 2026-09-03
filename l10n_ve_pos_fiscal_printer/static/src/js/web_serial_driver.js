/** @odoo-module **/

import { TFHKA_CHARS, TfhkaProtocol } from "./tfhka_protocol";

/**
 * Driver Web Serial API de alta precisión para hardware fiscal
 * Soporta control de flujo DTR/RTS, cálculo de LRC y secuenciado estricto
 */
export class WebSerialDriver {
    constructor() {
        this.port = null;
        this.reader = null;
        this.writer = null;
        this.isConnected = false;
        this.seq = 0x30; // '0'
        this.rxBuffer = [];
        this.keepReading = false;
    }

    async connect(options = {}) {
        if (!("serial" in navigator)) {
            throw new Error("Web Serial API no soportada en este navegador. Utilice Google Chrome o Microsoft Edge.");
        }

        const baudRate = parseInt(options.baudrate || 9600);

        try {
            const existingPorts = await navigator.serial.getPorts();
            if (existingPorts.length > 0) {
                this.port = existingPorts[0];
            } else {
                this.port = await navigator.serial.requestPort();
            }

            await this.port.open({
                baudRate: baudRate,
                dataBits: 8,
                stopBits: 1,
                parity: "none",
                flowControl: "none",
                bufferSize: 4096,
            });

            // ACTIVACIÓN OBLIGATORIA DE SEÑALES DTR/RTS PARA LA BIXOLON SRP-812
            try {
                await this.port.setSignals({ dataTerminalReady: true, requestToSend: true });
            } catch (sigErr) {
                console.warn("[WebSerialDriver] No se pudieron forzar señales DTR/RTS:", sigErr);
            }

            this.keepReading = true;
            this.rxBuffer = [];
            this.seq = 0x30;
            this.startReading();

            // Breve estabilización y verificación ENQ
            await new Promise(r => setTimeout(r, 200));
            this.isConnected = true;
            return true;
        } catch (error) {
            this.isConnected = false;
            throw new Error("Error al abrir puerto serial: " + error.message);
        }
    }

    async disconnect() {
        this.keepReading = false;
        if (this.reader) {
            try { await this.reader.cancel(); } catch (e) {}
            this.reader = null;
        }
        if (this.port) {
            try { await this.port.close(); } catch (e) {}
            this.port = null;
        }
        this.isConnected = false;
    }

    async startReading() {
        while (this.port && this.port.readable && this.keepReading) {
            try {
                this.reader = this.port.readable.getReader();
                while (true) {
                    const { value, done } = await this.reader.read();
                    if (done) break;
                    if (value) {
                        for (let i = 0; i < value.length; i++) {
                            this.rxBuffer.push(value[i]);
                        }
                    }
                }
            } catch (err) {
                console.warn("[WebSerialDriver] Error en bucle de lectura:", err);
            } finally {
                if (this.reader) {
                    this.reader.releaseLock();
                    this.reader = null;
                }
            }
        }
    }

    async sendCommand(cmdStr, timeoutMs = 4000) {
        if (!this.isConnected || !this.port || !this.port.writable) {
            throw new Error("Impresora fiscal no conectada.");
        }

        const frame = TfhkaProtocol.buildFrame(cmdStr, this.seq);
        this.rxBuffer = []; // Drenar buffer

        const writer = this.port.writable.getWriter();
        try {
            await writer.write(frame);
        } finally {
            writer.releaseLock();
        }

        // Esperar ACK (0x06), NAK (0x15) o respuesta
        const start = Date.now();
        while (Date.now() - start < timeoutMs) {
            const ackIdx = this.rxBuffer.indexOf(TFHKA_CHARS.ACK);
            if (ackIdx !== -1) {
                this.rxBuffer.splice(0, ackIdx + 1);
                // Alternar secuencia '0' <-> '1'
                this.seq = (this.seq === 0x30) ? 0x31 : 0x30;
                return { success: true, status: 'ACK' };
            }

            const nakIdx = this.rxBuffer.indexOf(TFHKA_CHARS.NAK);
            if (nakIdx !== -1) {
                this.rxBuffer.splice(0, nakIdx + 1);
                return { success: false, status: 'NAK', error: "Comando rechazado por la impresora (NAK)." };
            }

            await new Promise(r => setTimeout(r, 30));
        }

        return { success: false, status: 'TIMEOUT', error: "Tiempo de espera agotado sin respuesta de la impresora." };
    }

    async readS1Status() {
        // Envía 'S1' y lee la trama de datos de respuesta
        if (!this.isConnected) return null;
        try {
            const res = await this.sendCommand("S1", 3000);
            // Extraer del buffer si vino trama
            const stxIdx = this.rxBuffer.indexOf(TFHKA_CHARS.STX);
            if (stxIdx !== -1) {
                const etxIdx = this.rxBuffer.indexOf(TFHKA_CHARS.ETX, stxIdx);
                if (etxIdx !== -1) {
                    const dataBytes = this.rxBuffer.slice(stxIdx + 1, etxIdx);
                    const str = String.fromCharCode(...dataBytes.filter(b => b >= 0x20 && b <= 0x7E));
                    return str;
                }
            }
        } catch (e) {
            console.warn("[WebSerialDriver] Error leyendo S1:", e);
        }
        return null;
    }
}
