/** @odoo-module **/

import { reactive } from "@odoo/owl";
import { registry } from "@web/core/registry";

class FiscalPrinterService {
    constructor(env) {
        this.env = env;
        this.port = null;
        this.writer = null;
        this.reader = null;
        this.keepReading = true;
        this.rxBuffer = []; // Buffer de recepcion
        this.responsePromises = []; // Promesas en espera de tramas
        // Callback para frames STATUS proactivos de la impresora (sin promise pendiente).
        // La Bixolon SRP-812 envía su status ~2s después de ACK-ear Z como handshake:
        // el host DEBE responder 0x06 para que la impresora ejecute el Z efectivamente.
        this._proactiveStatusCallback = null;
        this._zExecutionInProgress = false;
        this._currentZExecutionId = null;
        this._zTimer1 = null;
        this._zTimer2 = null;
        this._zTimer3 = null;
        this.state = reactive({
            isConnected: false,
            driver: 'hka', // default
        });
    }

    // Configura el driver desde la configuración del POS
    initFromConfig(posConfig) {
        if (posConfig.fiscal_printer_driver) {
            this.state.driver = posConfig.fiscal_printer_driver;
        }
    }

    async connect() {
        if (this.state.driver === 'mock') {
            console.log("🛠️ [Simulador] Conexión virtual exitosa.");
            this.state.isConnected = true;
            localStorage.setItem('pos_fiscal_printer_auto_connect', 'true');
            return true;
        }

        if (!("serial" in navigator)) {
            console.error("[FiscalPrinter] Web Serial API no disponible. Usa Google Chrome o Microsoft Edge.");
            return false;
        }

        try {
            // 1. Check if we already have permission for any previously authorized ports
            const existingPorts = await navigator.serial.getPorts();
            if (existingPorts.length > 0) {
                this.port = existingPorts[0];
                console.log("🔌 Auto-conectando al puerto previamente autorizado...");
            } else {
                // 2. Request new permission from the user
                this.port = await navigator.serial.requestPort();
            }
            
            // Bixolon SRP-812 TFHKA: 9600 baud, 8N1, sin control de flujo
            await this.port.open({
                baudRate: 9600,
                dataBits: 8,
                stopBits: 1,
                parity: 'none',
                flowControl: 'none',
                bufferSize: 4096,
            });

            // ⚡ ACTIVAR SEÑALES DTR/RTS (Indispensables en RS-232 / USB-Serial para que la Bixolon transmita datos de vuelta al PC)
            try {
                await this.port.setSignals({ dataTerminalReady: true, requestToSend: true });
                console.log("⚡ Señales DTR/RTS activadas para Bixolon SRP-812");
            } catch (sigErr) {
                console.warn("[FiscalPrinter] No se pudieron activar DTR/RTS:", sigErr);
            }

            this.keepReading = true;
            this.hkaSeq = 0x30; // 0x30 = ASCII '0' (Especificación Oficial TFHKA HKA Venezuela)
            this.activeLrcVariant = localStorage.getItem('pos_fiscal_hka_variant') || 'H_30';
            this.rxBuffer = [];   // Limpiar buffer residual

            // Iniciar el listener asíncrono en background
            this.readLoop();

            // Pausa de estabilización (300ms) antes de enviar comandos
            await new Promise(r => setTimeout(r, 300));

            // Handshake ENQ (0x05): sincroniza el estado de sesión con la impresora TFHKA.
            console.log("🤝 Enviando ENQ de sincronización a la Bixolon SRP-812...");
            try {
                this.writer = this.port.writable.getWriter();
                await this.writer.write(new Uint8Array([0x05])); // ENQ
                this.writer.releaseLock();
            } catch(e) {
                console.warn("[FiscalPrinter] Error enviando ENQ:", e);
            }
            const enqRes = await this.awaitResponse('STATUS_QUERY', 1500);
            console.log("📥 Respuesta ENQ:", enqRes.status, "(OK en cualquier estado)");

            this.state.isConnected = true;
            localStorage.setItem('pos_fiscal_printer_auto_connect', 'true');
            console.log("✅ Conectado a la impresora fiscal por Web Serial API");

            return true;
        } catch (error) {
            console.error("[FiscalPrinter] Error al conectar:", error);
            return false;
        }
    }

    async disconnect() {
        this.keepReading = false;
        if (this.reader) {
            try {
                await this.reader.cancel();
            } catch (e) {
                console.warn("Reader cancel error", e);
            }
        }
        if (this.port) {
            try {
                await this.port.close();
            } catch (e) {
                console.warn("Port close error", e);
            }
            this.port = null;
        }
        this.state.isConnected = false;
        localStorage.setItem('pos_fiscal_printer_auto_connect', 'false');
        console.log("🔌 Impresora fiscal desconectada");
    }

    /**
     * serialWrite — helper atómico para escritura en puerto serial.
     * Obtiene el writer, escribe y libera el lock en un solo bloque con try/finally.
     * Evita el patrón "this.writer = ..." disperso que puede dejar locks huérfanos
     * cuando se lanza una excepción antes de releaseLock().
     */
    async serialWrite(uint8Array) {
        if (!this.port || !this.port.writable) throw new Error('Puerto serial no disponible');
        const w = this.port.writable.getWriter();
        try {
            await w.write(uint8Array);
        } finally {
            w.releaseLock();
        }
    }

    // --- BUCLE DE LECTURA ASINCRONO ---
    async readLoop() {
        while (this.port && this.port.readable && this.keepReading) {
            this.reader = this.port.readable.getReader();
            try {
                while (true) {
                    const { value, done } = await this.reader.read();
                    if (done) {
                        break; // El puerto se ha cerrado
                    }
                    if (value) {
                        this._processIncomingBytes(value);
                    }
                }
            } catch (error) {
                console.error("[FiscalPrinter] Error leyendo puerto serial:", error);
            } finally {
                this.reader.releaseLock();
                this.reader = null;
            }
        }
    }

    _processIncomingBytes(uint8Array) {
        const arr = Array.from(uint8Array);
        console.log("📥 [Serial RX] Bytes recibidos de la impresora:", arr);
        // Añadir bytes al buffer
        for (let i = 0; i < uint8Array.length; i++) {
            this.rxBuffer.push(uint8Array[i]);
        }
        // Notificar a las promesas en espera
        this._checkResponsePromises();
    }

    _checkResponsePromises() {
        console.log("🔍 [Buffer Check] rxBuffer actual:", [...this.rxBuffer]);

        // ─── PRIORIDAD 1: DETECCIÓN DE TRAMA DE ESTADO COMPLETA [STX, S1, S2, ETX, LRC] ───
        // Extraemos y validamos si existe una trama STATUS [0x02, S1, S2, 0x03, LRC] en el rxBuffer.
        // ORDEN DE CLASIFICACIÓN Y REGLAS DE CORRELACIÓN:
        // 1. Trama STATUS -> entregada a promesa 'STATUS_QUERY' si y solo si está activa, awaitingDirectResponse=true y dentro de su ventana de validez (now <= expiresAt).
        // 2. Trama STATUS -> entregada a _proactiveStatusCallback si hay una ejecución Z activa.
        // 3. Trama STATUS espontánea -> limpia buffer y actualiza state.lastPrinterStatus (NUNCA resuelve un COMMAND_ACK).
        // 4. ACK (0x06), NAK (0x15) -> entregan a promesas 'COMMAND_ACK' / 'ACK'.
        const stxIdx = this.rxBuffer.indexOf(0x02);
        if (stxIdx >= 0) {
            const etxIdx = this.rxBuffer.indexOf(0x03, stxIdx + 1);
            if (etxIdx >= 0 && this.rxBuffer.length > etxIdx + 1) {
                const frame = this.rxBuffer.slice(stxIdx, etxIdx + 2);
                const s1 = frame[1];
                const s2 = frame[2];
                const is24hLock = Boolean(s2 & 0x40);
                const isDocOpen = Boolean(s1 & 0x38);
                const isPaperOut = Boolean(s1 & 0x04);
                const isMechError = Boolean(s1 & 0x01);

                // 1.1 Consulta explícita 'STATUS_QUERY' activa y dentro de ventana temporal válida [sentAt, expiresAt]
                /* CORRELACIÓN DE STATUS_QUERY VÍA VENTANA TEMPORAL DELIMITADA:
                 * Dado que el protocolo serial TFHKA no incluye tokens de secuencia ni IDs de solicitud en el paquete
                 * de bytes de la trama STATUS [STX, S1, S2, ETX, LRC], la asociación entre un ENQ (0x05) enviado y su respuesta
                 * se delimita mediante la ventana de tiempo activa [sentAt, expiresAt].
                 * Si un frame STATUS llega dentro de dicha ventana temporal válida (now <= p.expiresAt), se correlaciona con la consulta ENQ.
                 * Si la consulta expiró, el frame NO es absorbido por la consulta antigua y queda disponible para el callback proactivo de Z o como frame espontáneo.
                 */
                const now = Date.now();
                const statusPromiseIdx = this.responsePromises.findIndex(p =>
                    p.type === 'STATUS_QUERY' &&
                    p.awaitingDirectResponse === true &&
                    now <= p.expiresAt
                );

                if (statusPromiseIdx !== -1) {
                    const pObj = this.responsePromises[statusPromiseIdx];
                    console.log(`📥 [HKA STATUS_QUERY] Respuesta asociada al ENQ ${pObj.queryId || 'sin-id'} (Ventana temporal válida, sentAt: ${pObj.sentAt}): [S1=0x${s1.toString(16)}, S2=0x${s2.toString(16)}]`);
                    this.rxBuffer.splice(stxIdx, etxIdx + 2 - stxIdx);
                    this.responsePromises.splice(statusPromiseIdx, 1);
                    pObj.resolve({ status: 'ACK', frame, s1, s2, isDocOpen, is24hLock, isPaperOut, isMechError });
                    return;
                }

                // 1.2 Si existe un callback proactivo activo (procedente del handshake Z), entrega el frame
                if (typeof this._proactiveStatusCallback === 'function') {
                    console.log(`📡 [HKA Proactivo] Frame STATUS proactivo recibido: S1=0x${s1.toString(16)}, S2=0x${s2.toString(16)} | Bloqueo24h=${is24hLock}`);
                    this.rxBuffer.splice(stxIdx, etxIdx + 2 - stxIdx);
                    const cb = this._proactiveStatusCallback;
                    this._proactiveStatusCallback = null; // one-shot: limpiar antes de llamar
                    cb({ s1, s2, is24hLock, frame });
                    return;
                }

                // 1.3 Trama STATUS recibida sin oyente de estado (evita que COMMAND_ACK absorba erróneamente un STX)
                console.log(`ℹ️ [HKA Status Espontáneo] Frame STATUS sin oyente directo: S1=0x${s1.toString(16)}, S2=0x${s2.toString(16)}`);
                this.state.lastPrinterStatus = { s1, s2, is24hLock, isDocOpen, frame };
                this.rxBuffer.splice(stxIdx, etxIdx + 2 - stxIdx);
            }
        }

        // ─── PRIORIDAD 2: PROCESAMIENTO DE PROMESAS DE COMANDO (ACK / NAK / DATA) ───
        for (let i = 0; i < this.responsePromises.length; i++) {
            let promiseObj = this.responsePromises[i];

            if (promiseObj.type === 'ACK' || promiseObj.type === 'COMMAND_ACK') {
                let ackIndex = this.rxBuffer.indexOf(0x06); // ACK
                let nakIndex = this.rxBuffer.indexOf(0x15); // NAK

                if (ackIndex !== -1) {
                    console.log("✅ ACK (0x06) detectado en posición", ackIndex);
                    this.rxBuffer.splice(0, ackIndex + 1);
                    promiseObj.resolve({ status: 'ACK' });
                    this.responsePromises.splice(i, 1);
                    i--;
                } else if (nakIndex !== -1) {
                    console.warn("⚠️ NAK (0x15) detectado en posición", nakIndex);
                    this.rxBuffer.splice(0, nakIndex + 1);
                    promiseObj.resolve({ status: 'NAK' });
                    this.responsePromises.splice(i, 1);
                    i--;
                } else if (this.rxBuffer.length > 0 && this.rxBuffer[0] !== 0x02) {
                    let firstByte = this.rxBuffer[0];
                    console.log("ℹ️ Byte de respuesta directo detectado:", firstByte, "(0x" + firstByte.toString(16) + ")");
                    this.rxBuffer.shift();
                    promiseObj.resolve({ status: 'ACK', byte: firstByte });
                    this.responsePromises.splice(i, 1);
                    i--;
                }
            }
            else if (promiseObj.type === 'DATA') {
                let stxIndex = this.rxBuffer.indexOf(0x02);
                if (stxIndex !== -1) {
                    let etxIndex = this.rxBuffer.indexOf(0x03, stxIndex);
                    if (etxIndex !== -1 && this.rxBuffer.length > etxIndex + 1) {
                        let frame = this.rxBuffer.slice(stxIndex, etxIndex + 2);
                        this.rxBuffer.splice(stxIndex, etxIndex + 2 - stxIndex);
                        promiseObj.resolve({ status: 'DATA', frame: frame });
                        this.responsePromises.splice(i, 1);
                        i--;
                    }
                } else {
                    let nakIndex = this.rxBuffer.indexOf(0x15);
                    if (nakIndex !== -1) {
                        this.rxBuffer.splice(0, nakIndex + 1);
                        promiseObj.resolve({ status: 'NAK' });
                        this.responsePromises.splice(i, 1);
                        i--;
                    } else if (this.rxBuffer.length > 0 && this.rxBuffer[0] === 0x06) {
                        this.rxBuffer.shift();
                        promiseObj.resolve({ status: 'ACK' });
                        this.responsePromises.splice(i, 1);
                        i--;
                    }
                }
            }
        }
    }

    async awaitResponse(type, timeoutMs = 2000, extraMeta = {}) {
        return new Promise((resolve) => {
            let resolved = false;
            let timeoutId = null;

            const sentAt = extraMeta.sentAt || Date.now();
            const expiresAt = extraMeta.expiresAt || (sentAt + timeoutMs);
            const awaitingDirectResponse = extraMeta.awaitingDirectResponse !== undefined ? extraMeta.awaitingDirectResponse : true;

            const promiseObj = {
                type: type, // 'ACK', 'COMMAND_ACK', 'DATA', 'STATUS_QUERY'
                queryId: extraMeta.queryId || null,
                sentAt: sentAt,
                expiresAt: expiresAt,
                awaitingDirectResponse: awaitingDirectResponse,
                resolve: (result) => {
                    if (!resolved) {
                        resolved = true;
                        if (timeoutId) clearTimeout(timeoutId);
                        resolve(result);
                    }
                }
            };

            timeoutId = setTimeout(() => {
                if (!resolved) {
                    resolved = true;
                    this.responsePromises = this.responsePromises.filter(p => p !== promiseObj);
                    resolve({ status: 'TIMEOUT' });
                }
            }, timeoutMs);

            this.responsePromises.push(promiseObj);
            // Re-chequear inmediatamente por si el dato ya habia llegado muy rapido al rxBuffer
            this._checkResponsePromises();
        });
    }

    async sendCommandHex(hexArray) {
        if (!this.state.isConnected || !this.port) {
            console.warn("[FiscalPrinter] Intento de enviar comando sin conexion activa.");
            return false;
        }
        
        try {
            this.writer = this.port.writable.getWriter();
            const data = new Uint8Array(hexArray);
            await this.writer.write(data);
            this.writer.releaseLock();
            console.log("📤 Comando enviado a la impresora");
        } catch (error) {
            console.error("Error enviando comando:", error);
            if (this.writer) {
                this.writer.releaseLock();
            }
        }
    }

    // ── DOCUMENTOS NO FISCALES (CON COLETILLA OBLIGATORIA SENIAT) ──
    async printNonFiscalDocument(lines = []) {
        if (!this.state.isConnected) return false;
        
        switch (this.state.driver) {
            case 'hka':
                console.log("Imprimiendo Documento No Fiscal en HKA...");
                await this.sendCommandHKA("800SIN DERECHO A CREDITO FISCAL");
                await this.sendCommandHKA("800(NO VALIDO COMO FACTURA)");
                await this.sendCommandHKA("800--------------------------------");
                for (let line of lines) {
                    let text = line.substring(0, 40);
                    await this.sendCommandHKA(`800${text}`);
                }
                return await this.sendCommandHKA("810");
            case 'mock':
                console.log("🛠️ [Simulador] Imprimiendo Documento No Fiscal:");
                console.log("🛠️ [Simulador] *** SIN DERECHO A CRÉDITO FISCAL ***");
                console.log("🛠️ [Simulador] (NO VÁLIDO COMO FACTURA)");
                for (let l of lines) console.log("🛠️ [Simulador] " + l);
                return true;
            default:
                console.log(`[FiscalPrinter] Documento No Fiscal en driver ${this.state.driver}`);
                return true;
        }
    }

    // ── FACTORÍA DE PROTOCOLOS (ESTRATEGIA) ──

    async printXReport() {
        if (!this.state.isConnected) return false;
        
        switch (this.state.driver) {
            case 'hka':
                return await this.printXReportHKA();
            case 'pnp':
            case 'bematech':
            case 'vmax':
            case 'epson':
            case 'custom':
            case 'aclas':
            case 'rigazsa':
                console.log("Reporte X para este protocolo no está implementado aún");
                return true;
            case 'mock':
                return await this.printXReportMock();
            default:
                console.error("[FiscalPrinter] Driver no soportado para Reporte X:", this.state.driver);
                return false;
        }
    }

    async cancelOpenDocument() {
        if (!this.state.isConnected) return { success: false, error: 'Impresora desconectada' };
        
        switch (this.state.driver) {
            case 'hka':
                return await this.cancelOpenDocumentHKA();
            case 'mock':
                console.log("🛠️ [Simulador] Anulación virtual de documento realizada.");
                return { success: true };
            default:
                return { success: false, error: 'Driver no soporta anulación' };
        }
    }

    async printZReport() {
        if (!this.state.isConnected) return false;
        
        switch (this.state.driver) {
            case 'hka':
                return await this.printZReportHKA();
            case 'pnp':
                return await this.printZReportPNP();
            case 'bematech':
                return await this.printZReportBematech();
            case 'vmax':
                return await this.printZReportVmax();
            case 'epson':
                return await this.printZReportEpson();
            case 'custom':
                return await this.printZReportCustom();
            case 'aclas':
                return await this.printZReportAclas();
            case 'rigazsa':
                return await this.printZReportRigazsa();
            case 'mock':
                return await this.printZReportMock();
            default:
                console.error("[FiscalPrinter] Driver no soportado para Reporte Z:", this.state.driver);
                return false;
        }
    }

    async printZReportByNumber(start, end) {
        if (!this.state.isConnected) return false;
        
        switch (this.state.driver) {
            case 'hka':
                // I2Z + start(4) + end(4)
                let sZ = start.toString().padStart(4, '0');
                let eZ = end.toString().padStart(4, '0');
                return await this.sendCommandHKA(`I2Z${sZ}${eZ}`);
            case 'mock':
                console.log(`🛠️ [Simulador] Reporte Z por número desde ${start} hasta ${end}`);
                await new Promise(resolve => setTimeout(resolve, 2000));
                return true;
            default:
                console.log(`Ejecutando Z por número en driver ${this.state.driver} (Trama pendiente)`);
                return true;
        }
    }

    async printAuditInvoices(start, end) {
        if (!this.state.isConnected) return false;
        
        switch (this.state.driver) {
            case 'hka':
                // U0 + start(7) + end(7) (Comando típico de reporte de facturas)
                let sI = start.toString().padStart(7, '0');
                let eI = end.toString().padStart(7, '0');
                return await this.sendCommandHKA(`U0${sI}${eI}`);
            case 'mock':
                console.log(`🛠️ [Simulador] Memoria de Auditoría: Facturas desde ${start} hasta ${end}`);
                await new Promise(resolve => setTimeout(resolve, 2000));
                return true;
            default:
                console.log(`Ejecutando Auditoría de Facturas en driver ${this.state.driver} (Trama pendiente)`);
                return true;
        }
    }

    async printAuditCreditNotes(start, end) {
        if (!this.state.isConnected) return false;
        
        switch (this.state.driver) {
            case 'hka':
                // Comando genérico para NC suele agruparse en reportes de memoria
                let sC = start.toString().padStart(7, '0');
                let eC = end.toString().padStart(7, '0');
                return await this.sendCommandHKA(`U0${sC}${eC}`); // Revisar comando específico HKA para NC
            case 'mock':
                console.log(`🛠️ [Simulador] Memoria de Auditoría: Notas de Crédito desde ${start} hasta ${end}`);
                await new Promise(resolve => setTimeout(resolve, 2000));
                return true;
            default:
                console.log(`Ejecutando Auditoría de NC en driver ${this.state.driver} (Trama pendiente)`);
                return true;
        }
    }

    async printInvoice(order) {
        if (!this.state.isConnected) return { success: false, error: 'Not connected' };
        
        switch (this.state.driver) {
            case 'mock': return await this.printInvoiceMock(order);
            case 'hka': return await this.printInvoiceHKA(order);
            case 'pnp': return await this.printInvoicePNP(order);
            case 'bematech': return await this.printInvoiceBematech(order);
            case 'vmax': return await this.printInvoiceVmax(order);
            case 'epson': return await this.printInvoiceEpson(order);
            case 'custom': return await this.printInvoiceCustom(order);
            case 'aclas': return await this.printInvoiceAclas(order);
            case 'rigazsa': return await this.printInvoiceRigazsa(order);
            default:
                console.log(`Ejecutando Factura en driver ${this.state.driver} (Trama pendiente)`);
                return { success: true, invoice_number: 'PENDING', machine_serial: 'SERIAL_PENDING' };
        }
    }

    // --- STUBS DE DRIVERS DE IMPRESORAS (Para futuras implementaciones) ---
    async printInvoicePNP(order) {
        console.log("Facturando en PNP (Driver en construcción)...");
        // TODO: Implementar protocolo PNP (STX + Secuencia + Comando + ETX + BCC)
        return { success: true, invoice_number: 'PNP-PENDING', machine_serial: 'PNP-SERIAL' };
    }

    async printInvoiceBematech(order) {
        console.log("Facturando en Bematech (Driver en construcción)...");
        // TODO: Implementar protocolo ESC/Bema
        return { success: true, invoice_number: 'BEMA-PENDING', machine_serial: 'BEMA-SERIAL' };
    }

    async printInvoiceVmax(order) {
        console.log("Facturando en Vmax (Driver en construcción)...");
        // TODO: Implementar protocolo Vmax
        return { success: true, invoice_number: 'VMAX-PENDING', machine_serial: 'VMAX-SERIAL' };
    }

    async printInvoiceEpson(order) {
        console.log("Facturando en Epson (Driver en construcción)...");
        // TODO: Implementar protocolo ESC/POS Fiscal Epson
        return { success: true, invoice_number: 'EPSON-PENDING', machine_serial: 'EPSON-SERIAL' };
    }

    async printInvoiceCustom(order) {
        console.log("Facturando en Custom (Driver en construcción)...");
        // TODO: Implementar protocolo Custom
        return { success: true, invoice_number: 'CUSTOM-PENDING', machine_serial: 'CUSTOM-SERIAL' };
    }

    async printInvoiceAclas(order) {
        console.log("Facturando en Aclas Protocolo Nativo (Driver en construcción)...");
        // TODO: Implementar protocolo Nativo Aclas (diferente a HKA)
        return { success: true, invoice_number: 'ACLAS-PENDING', machine_serial: 'ACLAS-SERIAL' };
    }

    async printInvoiceRigazsa(order) {
        console.log("Facturando en Rigazsa (Driver en construcción)...");
        // TODO: Implementar protocolo Rigazsa
        return { success: true, invoice_number: 'RIGAZSA-PENDING', machine_serial: 'RIGAZSA-SERIAL' };
    }

    async printCreditNote(order, originalInvoiceStr, originalMachineSerial) {
        if (!this.state.isConnected) return { success: false, error: 'Not connected' };
        
        switch (this.state.driver) {
            case 'mock':
                return await this.printCreditNoteMock(order, originalInvoiceStr, originalMachineSerial);
            case 'hka':
                return await this.printCreditNoteHKA(order, originalInvoiceStr, originalMachineSerial);
            default:
                console.log(`Ejecutando Nota de Crédito en driver ${this.state.driver} (Trama pendiente)`);
                return { success: true, credit_note_number: 'PENDING_NC', machine_serial: 'SERIAL_PENDING' };
        }
    }

    // Helper para formatear precios/cantidades a formato HKA
    _formatHKA(num, length, decimals) {
        let multiplier = Math.pow(10, decimals);
        let val = Math.round(num * multiplier).toString();
        return val.padStart(length, '0');
    }

    _getTaxFlagHKA(line) {
        let taxes = line.tax_ids;
        if (!taxes || taxes.length === 0) return ' '; // Exento
        let amount = taxes[0].amount;
        if (amount === 16) return '!'; // Tasa General (G)
        if (amount === 8) return '"';  // Tasa Reducida (R)
        if (amount === 31) return '#'; // Tasa Adicional (A)
        return ' '; // Por defecto Exento
    }

    _buildHKAFrame(cmdStr, seq, lrcVariant = 'A') {
        const STX = 0x02; const ETX = 0x03;
        
        // Variantes Modo Directo ASCII (Sin encuadre STX/Seq/LRC)
        if (lrcVariant === 'E') {
            let bytes = [];
            for (let i = 0; i < cmdStr.length; i++) bytes.push(cmdStr.charCodeAt(i));
            bytes.push(0x0D, 0x0A); // \r\n
            return bytes;
        }
        if (lrcVariant === 'F') {
            let bytes = [];
            for (let i = 0; i < cmdStr.length; i++) bytes.push(cmdStr.charCodeAt(i));
            bytes.push(0x0A); // \n
            return bytes;
        }
        if (lrcVariant === 'G') {
            let bytes = [];
            for (let i = 0; i < cmdStr.length; i++) bytes.push(cmdStr.charCodeAt(i));
            bytes.push(0x0D); // \r
            return bytes;
        }

        // Variantes Modo Trama HKA STX...ETX LRC
        let payload = [seq];
        for (let i = 0; i < cmdStr.length; i++) {
            payload.push(cmdStr.charCodeAt(i));
        }
        payload.push(ETX);

        // Especificación Bixolon SRP-812 TFHKA: Raw XOR sobre [Seq, Cmd..., ETX] (sin incluir STX)
        let lrc = 0;
        for (let i = 0; i < payload.length; i++) {
            lrc ^= payload[i];
        }

        /* REGLA LRC TFHKA RAW:
         * En el protocolo oficial TFHKA / Bixolon SRP-812, el LRC es el byte XOR puro (RAW).
         * NO debe modificarse sumándole 0x20 aunque sea < 0x20 (ej. '810' con seq 0x30 da XOR 0x0A).
         * La modificación previa 'lrc += 0x20' alteraba 0x0A a 0x2A (42), provocando NAK (0x15)
         * por rechazo de checksum en la impresora fiscal.
         */
        if (lrcVariant === 'A' || lrcVariant === 'B') {
            if (lrc < 0x20) lrc += 0x20;
        } else if (lrcVariant === 'C') {
            if (lrc < 0x20) lrc |= 0x40;
        } else if (lrcVariant === 'I') {
            if (lrc < 0x20) lrc |= 0x80;
        }
        // Variante 'H' / 'RAW' / default: LRC binario puro (RAW) tal cual sale del XOR

        return [STX, ...payload, lrc];
    }

    async sendCommandHKA(cmdStr, waitForData = false, timeoutMs = 3000) {
        // ── MOTOR DUAL 1: Intentar primero vía Proxy HTTP Local (http://localhost:5000 - VenPOS Print Server / 3Mit Agent) ──
        const proxyRes = await this.tryLocalPrintServerProxy(cmdStr);
        if (proxyRes.success && proxyRes.viaProxy) {
            return { success: true, frame: proxyRes.data, format: 'PROXY_5000' };
        }

        // ── MOTOR DUAL 2: WebSerial Nativo directo ──
        if (!this.state.isConnected || !this.port) return { success: false, error: 'Impresora no conectada por WebSerial' };
        
        if (this.hkaSeq !== 0x30 && this.hkaSeq !== 0x31) {
            this.hkaSeq = 0x30; // 0x30 = ASCII '0'
        }

        const currentSeq = this.hkaSeq;
        const altSeq = (currentSeq === 0x30) ? 0x31 : 0x30;

        // Opciones de trama TFHKA: Secuencia actual y secuencia alternante con LRC RAW puro
        const sequenceOptions = [
            { seq: currentSeq, variant: 'RAW', name: 'RAW_CURR_SEQ' },
            { seq: altSeq,     variant: 'RAW', name: 'RAW_ALT_SEQ'  }
        ];

        for (let option of sequenceOptions) {
            let fullFrame = this._buildHKAFrame(cmdStr, option.seq, option.variant);

            // Drenar rxBuffer antes de enviar — pero si hay un frame STATUS proactivo pendiente,
            // disparar el callback ANTES de drenar (race condition: el frame puede haber llegado
            // entre el sendCommandHKA anterior y este nuevo intento de trama).
            if (this.rxBuffer.length > 0) {
                const stx = this.rxBuffer.indexOf(0x02);
                if (stx >= 0) {
                    const etx = this.rxBuffer.indexOf(0x03, stx + 1);
                    if (etx >= 0 && this.rxBuffer.length > etx + 1) {
                        const frame = this.rxBuffer.slice(stx, etx + 2);
                        const s1 = frame[1], s2 = frame[2];
                        console.log(`📡 [HKA Pre-Drain] Frame STATUS en buffer antes de enviar '${cmdStr}': S1=0x${s1.toString(16)}, S2=0x${s2.toString(16)}`);
                        if (typeof this._proactiveStatusCallback === 'function') {
                            const cb = this._proactiveStatusCallback;
                            this._proactiveStatusCallback = null;
                            cb({ s1, s2, is24hLock: Boolean(s2 & 0x40), frame });
                        }
                    }
                }
                console.log(`🧹 [HKA Pre-Send] Drenando ${this.rxBuffer.length} bytes previos del buffer.`);
                this.rxBuffer = [];
            }
            console.log(`📤 [HKA] Probando trama '${option.name}' (Seq 0x${option.seq.toString(16)}) para '${cmdStr}':`, fullFrame);
            
            let ackPromise = this.awaitResponse('ACK', timeoutMs);

            try {
                this.writer = this.port.writable.getWriter();
                await this.writer.write(new Uint8Array(fullFrame));
                this.writer.releaseLock();
            } catch(e) {
                console.error("Error escribiendo en puerto serial:", e);
                return { success: false, error: e.message };
            }

            let ackRes = await ackPromise;
            console.log(`📥 Respuesta HKA a trama '${option.name}':`, ackRes);

            if (ackRes.status === 'ACK') {
                console.log(`🎯 ¡Trama Protocolar '${option.name}' ACEPTADA por la Bixolon SRP-812!`);
                this.activeLrcVariant = option.name;
                localStorage.setItem('pos_fiscal_hka_variant', option.name);
                
                // Conmutación estricta 0/1 ('0' <-> '1') oficial de TFHKA
                this.hkaSeq = (this.hkaSeq === 0x30) ? 0x31 : 0x30;

                if (waitForData) {
                    let dataRes = await this.awaitResponse('DATA', timeoutMs);
                    if (dataRes.status === 'DATA') {
                        try {
                            this.writer = this.port.writable.getWriter();
                            await this.writer.write(new Uint8Array([0x06]));
                            this.writer.releaseLock();
                        } catch (e) {}
                        return { success: true, frame: dataRes.frame, format: option.name };
                    }
                }
                return { success: true, frame: ackRes.frame, format: option.name };
            }
        }

        console.error(`❌ [HKA] Todas las opciones de secuencia fueron rechazadas por la impresora (NAK / TIMEOUT).`);
        return { success: false, error: 'All sequence options NAKed' };
    }

    async cancelOpenDocumentHKA() {
        console.log("🧹 [HKA] Ejecutando secuencia de liberación y cierre de documento atascado...");
        try {
            let status = await this.queryPrinterStatusHKA();
            if (!status.success) return { success: false, error: 'No se pudo obtener estado para cancelar' };

            // Bit 0x20 (0x20) = No Fiscal, Bit 0x08 (0x08) = Fiscal
            if (status.s1 & 0x20) {
                console.log("🧹 [HKA] Cerrando documento No Fiscal (810)...");
                const res = await this.sendCommandHKA("810");
                // Si el comando fue aceptado (ACK), el documento está cerrado.
                // No hacer ENQ de verificación: en la Bixolon SRP-812 el estado
                // S1=0x60/0x62 persiste como baseline incluso sin documentos abiertos.
                if (res.success) {
                    console.log("✅ [HKA] Documento No Fiscal cerrado exitosamente (ACK recibido).");
                    return { success: true };
                }
            } else if (status.s1 & 0x08) {
                console.log("🧹 [HKA] Cancelando documento Fiscal (7)...");
                const res = await this.sendCommandHKA("7");
                if (res.success) {
                    console.log("✅ [HKA] Documento Fiscal cancelado exitosamente (ACK recibido).");
                    return { success: true };
                }
            }

            // Fallback: si ningún comando específico tuvo éxito, reportar
            console.warn("⚠️ [HKA] No se pudo confirmar cierre de documento (comandos rechazados).");
            return { success: false, reason: 'CMDS_REJECTED' };
        } catch (e) {
            console.warn("⚠️ [HKA] Error liberando documento atascado:", e);
            return { success: false, reason: e.message };
        }
    }

    async queryPrinterStatusHKA() {
        if (!this.state.isConnected || !this.port) return { success: false, error: 'Impresora desconectada' };

        // ─── PURGAR FRAMES STALE DEL BUFFER ─────────────────────────────────────
        // El printer envía proactivamente status frames durante operaciones largas (Z, 810).
        // Si el buffer tiene esos frames, el ENQ resolvería con datos viejos en lugar de
        // leer el estado ACTUAL. Drenamos el buffer y esperamos 150ms para que cualquier
        // byte en tránsito llegue y sea descartado antes de registrar la nueva Promise.
        if (this.rxBuffer && this.rxBuffer.length > 0) {
            console.log(`🧹 [HKA ENQ] Drenando ${this.rxBuffer.length} bytes stale del rxBuffer antes de ENQ...`);
            this.rxBuffer = [];
        }
        await new Promise(r => setTimeout(r, 150)); // Esperar bytes en tránsito
        this.rxBuffer = [];                          // Segunda limpieza por si llegaron más

        const statusQueryId = `SQ_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
        const sentAt = Date.now();
        const timeoutMs = 1500;
        const expiresAt = sentAt + timeoutMs;
        let enqPromise = this.awaitResponse('STATUS_QUERY', timeoutMs, {
            queryId: statusQueryId,
            sentAt: sentAt,
            expiresAt: expiresAt,
            awaitingDirectResponse: true
        });

        try {
            this.writer = this.port.writable.getWriter();
            await this.writer.write(new Uint8Array([0x05])); // ENQ (0x05)
            this.writer.releaseLock();
        } catch (e) {
            return { success: false, error: e.message };
        }

        let res = await enqPromise;
        if (res.status === 'ACK' && res.frame) {
            let s1 = res.s1;
            let s2 = res.s2;
            let isDocOpen = Boolean((s1 & 0x08) || (s1 & 0x10) || ((s1 & 0x20) && !(s1 & 0x40))); // 0x08 (Factura), 0x10 (NC), 0x20 (No Fiscal)
            let isMechError = Boolean(s1 & 0x01); // Error Mecanico / Tapa Abierta (Bloqueante)
            let isNearPaperEnd = Boolean(s1 & 0x02); // Advertencia Sensor Poco Papel (NO Bloqueante)
            let isPaperOut = Boolean(s1 & 0x04); // Sin Papel Total (Bloqueante)
            let is24hLock = Boolean(s2 & 0x80); // Bit 0x80 indica bloqueo real de 24 horas. (0x40 es estado fiscal activo baseline).

            let statusObj = {
                success: true,
                s1: s1,
                s2: s2,
                isDocOpen: isDocOpen,
                isMechError: isMechError,
                isNearPaperEnd: isNearPaperEnd,
                isPaperOut: isPaperOut,
                is24hLock: is24hLock,
                frame: res.frame
            };
            this.state.lastPrinterStatus = statusObj;
            return statusObj;
        }
        return { success: false, error: 'Sin respuesta ENQ' };
    }

    async recoverPrinterState(targetOperation = 'invoice') {
        console.log(`🛡️ [HKA Ingeniería] Evaluando estado fiscal previo para operación '${targetOperation}'...`);
        let status = await this.queryPrinterStatusHKA();

        if (!status.success) {
            console.warn("⚠️ [HKA] No se pudo leer el estado ENQ de la impresora. Continuando con cautela...");
            return { success: true };
        }

        console.log(`📊 [HKA Estado Actual] S1=0x${status.s1.toString(16)}, S2=0x${status.s2.toString(16)} | DocAbierto=${status.isDocOpen}, Bloqueo24h=${status.is24hLock}, PocoPapelWarning=${status.isNearPaperEnd}, SinPapelTotal=${status.isPaperOut}`);

        if (status.isPaperOut) {
            throw new Error(`🚨 IMPRESORA FISCAL SIN PAPEL TOTAL (S1=0x${status.s1.toString(16)}).\n\nPor favor coloque un nuevo rollo de papel en la impresora Bixolon SRP-812 antes de continuar.`);
        }
        if (status.isMechError) {
            throw new Error(`🚨 ERROR MECÁNICO EN IMPRESORA FISCAL (S1=0x${status.s1.toString(16)}).\n\nPor favor verifique la tapa superior o el cortador térmico.`);
        }

        // ── FACTURA / X: Limpiar documentos abiertos si los hay ──────
        if (targetOperation === 'invoice' || targetOperation === 'x_report') {
            if (status.is24hLock) {
                const opLabel = targetOperation === 'x_report' ? 'emitir el Reporte X' : 'continuar facturando';
                throw new Error(
                    `🔒 La impresora fiscal requiere emitir el Reporte Z antes de ${opLabel}.\n\n` +
                    'El período de 24 horas fiscal ha vencido (S2=0x80).\n' +
                    'Vaya al popup de Cierre de Sesión → botón "Reporte Z".'
                );
            }
            // S1 bit 0x08 o 0x10: Factura fiscal o NC abierta real → cancelar con 7
            if ((status.s1 & 0x08) || (status.s1 & 0x10)) {
                console.log("🧹 [HKA Prep] Documento fiscal abierto (S1=0x08/0x10). Cancelando con '7'...");
                const res7 = await this.sendCommandHKA("7");
                if (res7.success) {
                    await new Promise(r => setTimeout(r, 2000));
                }
            }
            // S1 bit 0x20 activo SOLO si NO está en reposo (0x40): Documento No Fiscal abierto real → cerrar con 810
            if ((status.s1 & 0x20) && !(status.s1 & 0x40)) {
                console.log("🧹 [HKA Prep] Doc No Fiscal abierto real. Cerrando con '810'...");
                const res810 = await this.sendCommandHKA("810");
                if (res810.success) {
                    console.log("✅ [HKA Prep] Doc No Fiscal cerrado (ACK).");
                    await new Promise(r => setTimeout(r, 2000));
                }
            }
        }

        if (targetOperation === 'z_report') {
            // Solo cancelar factura fiscal si hay una abierta (S1 bit 0x08)
            if (status.s1 & 0x08) {
                console.log("🧹 [HKA Z-Prep] Factura fiscal abierta (S1=0x08). Cancelando con '7'...");
                const res7 = await this.sendCommandHKA("7");
                if (res7.success) {
                    await new Promise(r => setTimeout(r, 3000));
                }
            }
        }

        return { success: true };
    }

    async checkPostCommandState(cmdName) {
        const isZCmd = ['Z', 'IZ', 'I0Z', 'I1Z', 'I3Z'].includes(cmdName);
        const waitMs = isZCmd ? 5000 : 600;
        console.log(`⏳ [HKA Post-Cmd] Esperando ${waitMs/1000}s para finalización de '${cmdName}'...`);
        await new Promise(r => setTimeout(r, waitMs));
        let postStatus = await this.queryPrinterStatusHKA();
        if (postStatus.success) {
            console.log(`📥 [HKA Post-Comando '${cmdName}'] S1=0x${postStatus.s1.toString(16)}, S2=0x${postStatus.s2.toString(16)}`);
            if (postStatus.isPaperOut) {
                throw new Error(`🚨 IMPRESORA FISCAL SIN PAPEL (S1=0x${postStatus.s1.toString(16)}).\n\nColoque un rollo de papel nuevo.`);
            }
            if (postStatus.isMechError) {
                throw new Error(`🚨 ERROR MECÁNICO EN IMPRESORA FISCAL (S1=0x${postStatus.s1.toString(16)}).\n\nVerifique la tapa superior.`);
            }
        }
        return postStatus;
    }

    async printXReportHKA() {
        console.log("📊 Iniciando emisión de Reporte X en Bixolon SRP-812 TFHKA ('I0X' / 'IX' / 'I')...");
        await this.recoverPrinterState('x_report');

        this.hkaSeq = 0x30;

        let res = await this.sendCommandHKA("I0X", false, 6000);
        if (res.success) {
            await this.checkPostCommandState("I0X");
            console.log("✅ Reporte X ('I0X') aceptado e impreso exitosamente por la Bixolon SRP-812.");
            return res;
        }
        console.warn("[HKA] 'I0X' no aceptado. Probando variante 'IX' (6000ms)...");
        this.hkaSeq = 0x30;
        res = await this.sendCommandHKA("IX", false, 6000);
        if (res.success) {
            await this.checkPostCommandState("IX");
            return res;
        }

        console.warn("[HKA] 'IX' no aceptado. Probando variante 'I' (6000ms)...");
        this.hkaSeq = 0x30;
        res = await this.sendCommandHKA("I", false, 6000);
        if (res.success) {
            await this.checkPostCommandState("I");
            return res;
        }
        return res;
    }

    // ─── HELPERS DE NOTIFICACIÓN ──────────────────────────────────────────────

    _notifyPOSUser(message, type = 'warning') {
        if (this.notification && typeof this.notification.add === 'function') {
            this.notification.add(message, { type, sticky: true });
        } else {
            const prefix = type === 'warning' ? '⚠️' : type === 'danger' ? '❌' : 'ℹ️';
            console.warn(`${prefix} [FiscalPrinter Notify] ${message}`);
        }
    }

    _cleanupZExecutionState(targetExecutionId = null) {
        if (targetExecutionId && this._currentZExecutionId && this._currentZExecutionId !== targetExecutionId) {
            console.warn(`⚠️ [HKA Z] Solicitud de limpieza obsoleta ignorada (ID actual: ${this._currentZExecutionId}, ID objetivo: ${targetExecutionId}).`);
            return;
        }

        let clearedTimers = false;
        if (this._zTimer1) { clearTimeout(this._zTimer1); this._zTimer1 = null; clearedTimers = true; }
        if (this._zTimer2) { clearTimeout(this._zTimer2); this._zTimer2 = null; clearedTimers = true; }
        if (this._zTimer3) { clearTimeout(this._zTimer3); this._zTimer3 = null; clearedTimers = true; }
        if (clearedTimers) {
            console.log("🧹 [HKA Z] Timers fallback cancelados.");
        }
        this._proactiveStatusCallback = null;
        this._currentZExecutionId = null;
        console.log("🧹 [HKA Z] Estado de ejecución limpiado.");
    }

    // ─── NÚCLEO Z — executeZCommandHKA ───────────────────────────────────────

    async executeZCommandHKA(cmdStr = 'Z', attempt = 1, zExecutionId) {
        console.log(`📤 [HKA Z] Enviando variante '${cmdStr}' (intento ${attempt}, ID: ${zExecutionId})...`);

        // ── Pre-verificación de estado con ENQ ──────────────────────────────────
        const preStatus = await this.queryPrinterStatusHKA();
        if (preStatus.success) {
            if ((preStatus.s1 & 0x20) && !(preStatus.s1 & 0x40)) {
                console.warn(`⚠️ [HKA Z Prep] Doc No Fiscal abierto real (S1=0x${preStatus.s1.toString(16)}). Ejecutando '810'...`);
                const res810 = await this.sendCommandHKA('810');
                if (res810.success) {
                    console.log(`✅ [HKA Prep] Doc No Fiscal cerrado con éxito (ACK).`);
                    await new Promise(r => setTimeout(r, 1000));
                }
            }
        }

        // ── Forzar hkaSeq = 0x30 antes de Z (protocolo TFHKA) ─────────────────
        this.hkaSeq = 0x30;

        // ── Enviar comando Z ('I0Z' / 'IZ' / 'Z') ───────────────────────────
        const cmdRes = await this.sendCommandHKA(cmdStr, false, 15000);

        if (!cmdRes.success) {
            console.warn(`[HKA Z] '${cmdStr}' rechazado (NAK/timeout).`);
            return { success: false, confirmed: false, reason: 'COMMAND_REJECTED' };
        }

        console.log(`🎯 [HKA Z] ACK (0x06) recibido de la Bixolon SRP-812; comando '${cmdStr}' aceptado por el hardware.`);
        return { success: true, confirmed: true, reason: 'Z_ACCEPTED' };
    }

    // ─────────────────────────────────────────────────────────────────────────

    /**
     * tryLocalPrintServerProxy(cmdStr)
     *
     * Intenta enviar el comando a un Proxy / Spooler Local en Windows (ej. 3Mit Print Server / HKA Agent en localhost:5000).
     * Si la aplicación local responde OK, retorna { success: true, viaProxy: true }.
     * Si no está disponible o falla, retorna { success: false, viaProxy: false }.
     */
    getProxyUrl() {
        const posConfig = this.env && this.env.services && this.env.services.pos && this.env.services.pos.config;
        let host = (posConfig && posConfig.fiscal_printer_proxy_host) ? posConfig.fiscal_printer_proxy_host.trim() : 'http://localhost:5000';
        
        // Sanitizar: Si el host contiene código JS pegado accidentalmente o caracteres no válidos de URL
        if (host.includes('document.') || host.includes('{') || host.includes(';') || host.length > 200) {
            console.warn(`[HKA Proxy] URL de Proxy inválida detectada ('${host.substring(0, 30)}...'). Usando default http://localhost:5000`);
            return 'http://localhost:5000';
        }

        if (!host.startsWith('http://') && !host.startsWith('https://')) {
            host = 'http://' + host;
        }
        try {
            new URL(host);
        } catch(e) {
            console.warn(`[HKA Proxy] URL malformada ('${host}'). Usando default http://localhost:5000`);
            return 'http://localhost:5000';
        }

        return host.replace(/\/+$/, '');
    }

    getComPort() {
        const posConfig = this.env && this.env.services && this.env.services.pos && this.env.services.pos.config;
        return (posConfig && posConfig.fiscal_printer_com_port) ? posConfig.fiscal_printer_com_port.trim() : 'COM4';
    }

    async tryLocalPrintServerProxy(cmdStr) {
        try {
            const proxyHost = this.getProxyUrl();
            const comPort = this.getComPort();
            console.log(`🌐 [Proxy Check] Verificando si existe Print Server en ${proxyHost} para '${cmdStr}'...`);
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 2000);

            const response = await fetch(`${proxyHost}/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    cmd: cmdStr,
                    command: cmdStr,
                    action: cmdStr === 'I0Z' || cmdStr === 'Z' ? 'z_report' : 'cmd',
                    port: comPort,
                    driver: 'hka'
                }),
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (response.ok) {
                const data = await response.json().catch(() => ({}));
                console.log(`✅ [Proxy Server] Comando '${cmdStr}' procesado exitosamente vía ${proxyHost}:`, data);
                return { success: true, viaProxy: true, data };
            }
        } catch (e) {
            console.log(`ℹ️ [Proxy Server] Print Server no disponible en ${this.getProxyUrl()} (${e.message}). Continuando por WebSerial nativo.`);
        }
        return { success: false, viaProxy: false };
    }

    async printZReportHKA() {
        if (this._zExecutionInProgress) {
            console.warn("🛑 [HKA Z] Ya existe un Reporte Z en ejecución. Solicitud duplicada ignorada.");
            this._notifyPOSUser("⚠️ Ya hay un Cierre Z en curso. Por favor espere...", "warning");
            return { success: false, confirmed: false, reason: 'ALREADY_IN_PROGRESS' };
        }

        const zExecutionId = `Z_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
        this._zExecutionInProgress = true;
        this._currentZExecutionId = zExecutionId;
        console.log(`🆔 [HKA Z] Iniciando ejecución ${zExecutionId}.`);

        try {
            console.log("📊 Iniciando emisión de Reporte Z en Bixolon SRP-812 TFHKA...");

            // ── MOTOR DUAL 1: Probar primero vía Proxy HTTP Local (localhost:5000 - 3Mit / HKA Agent) ──
            const proxyRes = await this.tryLocalPrintServerProxy('I0Z');
            if (proxyRes.success && proxyRes.viaProxy) {
                console.log("✅ [HKA Z] Reporte Z ejecutado exitosamente a través del Proxy Local 5000.");
                return { success: true, confirmed: true, variant: 'I0Z_PROXY' };
            }

            // ── MOTOR DUAL 2: WebSerial Nativo directo a COM4 ──
            await this.recoverPrinterState('z_report');

            // Probar variantes en orden oficial TFHKA: 'I0Z' (diario oficial TFHKA), 'IZ', 'Z'
            const zVariants = ['I0Z', 'IZ', 'Z'];
            let lastResult = null;

            for (let i = 0; i < zVariants.length; i++) {
                const cmdStr = zVariants[i];
                console.log(`📤 [HKA Z] Probando variante de Reporte Z '${cmdStr}' (intento ${i + 1}/${zVariants.length})...`);
                lastResult = await this.executeZCommandHKA(cmdStr, i + 1, zExecutionId);

                if (lastResult.success && lastResult.confirmed) {
                    console.log(`✅ [HKA Z] Reporte Z impreso y confirmado exitosamente con variante '${cmdStr}'.`);
                    return { success: true, confirmed: true, variant: cmdStr };
                }
                console.warn(`⚠️ [HKA Z] Variante '${cmdStr}' no confirmó Z (Razón: ${lastResult.reason}). Proband siguiente variante si existe...`);
            }

            console.error(`❌ [HKA Z] Ninguna variante de Reporte Z fue confirmada por el hardware.`);
            return lastResult || { success: false, confirmed: false, reason: 'ALL_VARIANTS_FAILED' };
        } catch (e) {
            console.error(`❌ [HKA Z] Excepción durante la ejecución ${zExecutionId}:`, e);
            this._notifyPOSUser(`❌ Error en Cierre Z: ${e.message}`, 'danger');
            return { success: false, confirmed: false, error: e.message };
        } finally {
            this._cleanupZExecutionState(zExecutionId);
            this._zExecutionInProgress = false;
        }
    }

    _formatRIFHKA(rif) {
        if (!rif) return "V-00000000";
        let clean = rif.toString().trim().toUpperCase().replace(/\s+/g, '').replace(/-/g, '');
        // Validar: debe tener prefijo [VJEGP] seguido de al menos un dígito
        if (/^[VJEGP]\d+/.test(clean)) {
            // Formato correcto: insertar guion después del prefijo
            clean = clean.charAt(0) + "-" + clean.substring(1);
        } else {
            // RIF inválido (solo letra, vacío, sin dígitos) → usar default SENIAT
            console.warn(`[HKA] RIF '${rif}' inválido (sin dígitos). Usando default V-00000000.`);
            return "V-00000000";
        }
        return clean.substring(0, 18);
    }

    _getTaxFlagHKA(line) {
        let tax = 0;
        let tax_ids = line.tax_ids || (line.get_taxes ? line.get_taxes() : []);
        if (tax_ids && tax_ids.length > 0) {
            let t = tax_ids[0];
            tax = typeof t === 'object' ? (t.amount || 0) : t;
        }
        if (tax === 16) return "!"; // Tasa General (16%) -> '!' (ASCII 33)
        if (tax === 8)  return "2"; // Tasa Reducida (8%) -> '2'
        if (tax === 31) return "3"; // Tasa Adicional (31%) -> '3'
        return "0";                 // Exento (0%) -> '0'
    }

    async printInvoiceHKA(order) {
        try {
            console.log("Facturando en HKA...");
            await this.recoverPrinterState('invoice');
            
            // Reset forzado de secuencia a 0x30 ('0') para el inicio de la factura
            this.hkaSeq = 0x30;

            const posConfig = this.env && this.env.services && this.env.services.pos && this.env.services.pos.config;
            const HKA_FIRMWARE_V8 = posConfig ? posConfig.igtf_machine_native_calc : false;

            let partner = order.getPartner();
            let rawClientName = partner ? partner.name.trim() : "CLIENTE DE CONTADO";
            let rawRif = partner && partner.vat ? partner.vat : "V-00000000";
            let clientRif = this._formatRIFHKA(rawRif);

            // Formato iS* oficial HKA: Combinar Nombre y RIF en la línea iS* (Máx 38 caracteres)
            // Ejemplo: "Prueba test - V-22457545"
            let combinedHeader = `${rawClientName} - ${clientRif}`.substring(0, 38);

            // 1. Enviar Encabezado Cliente y RIF en un solo comando iS* (100% libre de NAKs)
            try {
                const resHeader = await this.sendCommandHKA("iS*" + combinedHeader);
                if (resHeader.success) {
                    console.log(`✅ [HKA Invoice] Encabezado cliente aceptado (iS*${combinedHeader}).`);
                }
            } catch(e) { console.warn("[HKA] Warning iS*:", e); }

            // 2. Imprimir líneas de producto
            let res;
            for (let line of order.getOrderlines()) {
                if (HKA_FIRMWARE_V8 && line.product_id && line.product_id.display_name && line.product_id.display_name.toUpperCase().includes('IGTF')) {
                    continue;
                }

                let name = line.getProduct().display_name.substring(0, 36);
                let price = this._formatHKA(line.price_unit, 10, 2);
                let qty = this._formatHKA(line.getQuantity(), 5, 3);
                let taxFlag = this._getTaxFlagHKA(line);
                
                // Comando Item HKA: probar sin espacio inicial (`!precio...`) y fallback con espacio (` !precio...`)
                let cmdLineDirect = `${taxFlag}${price}${qty}${name}`;
                let cmdLineSpace  = ` ${taxFlag}${price}${qty}${name}`;

                res = await this.sendCommandHKA(cmdLineDirect);
                if (!res.success) {
                    console.log(`⚠️ [HKA Item] Comando directo '${cmdLineDirect}' no aceptado, reintentando variante con espacio...`);
                    res = await this.sendCommandHKA(cmdLineSpace);
                }
                if (!res.success) throw new Error("Fallo al enviar Item: " + name);
            }

            // 3. Subtotal
            res = await this.sendCommandHKA("3");
            if (!res.success) throw new Error("Fallo al calcular Subtotal");

            // 4. Pagos y Totalización (Compatibilidad Odoo 17/18/19: order.paymentlines o get_paymentlines())
            let paymentLines = (typeof order.get_paymentlines === 'function')
                ? order.get_paymentlines()
                : (order.paymentlines || order.payment_ids || []);
            if (!paymentLines || paymentLines.length === 0) {
                // Pago por defecto si no hay líneas (ej. totalizar exacto en efectivo)
                res = await this.sendCommandHKA("101");
                if (!res.success) throw new Error("Fallo al totalizar factura");
            } else {
                for (let i = 0; i < paymentLines.length; i++) {
                    let pLine = paymentLines[i];
                    // Compatibilidad Odoo 18/19: payment_method_id tiene precedencia
                    let pm = pLine.payment_method_id || pLine.payment_method || null;
                    let pmName = (pm && pm.name) ? pm.name : '';
                    let isUSD = pm && (
                        pm.is_igtf ||
                        pmName.includes('$') ||
                        pmName.toLowerCase().includes('usd') ||
                        pmName.toLowerCase().includes('dolar') ||
                        pmName.toLowerCase().includes('dólar')
                    );

                    // Códigos HKA Venezuela:
                    //   01 = Efectivo Bs.F    04 = T.Débito Bs    05 = T.Crédito Bs
                    //   16 = Divisas Efectivo  17 = Divisas Electrónico
                    let paymentCode = isUSD ? "16" : "01";

                    // '1' = Último pago (Totalizar+Cerrar doc)  '2' = Pago Parcial
                    let cmdPrefix = (i === paymentLines.length - 1) ? "1" : "2";
                    let amt = this._formatHKA(Math.abs(pLine.amount), 12, 2);

                    res = await this.sendCommandHKA(`${cmdPrefix}${paymentCode}${amt}`);
                    if (!res.success) throw new Error(`Fallo al enviar pago ${paymentCode} por ${pLine.amount}`);
                }
            }

            // 5. Extraer Nro Factura — consultar estado extendido S1 post-cierre
            // Tras '1XX...' la impresora cierra el doc fiscal y actualiza contadores internos.
            // Esperamos 1s para que el firmware termine de procesar el cierre.
            await new Promise(r => setTimeout(r, 1000));
            let invoice_number = 'N/A';
            let machine_serial = 'N/A';

            try {
                let statusRes = await this.sendCommandHKA("S1", true, 3000); // waitForData=true
                if (statusRes.success && statusRes.frame) {
                    // Log del frame RAW completo para diagnóstico de campo
                    let frameBytes = Array.isArray(statusRes.frame) ? statusRes.frame : Array.from(statusRes.frame);
                    let frameHex   = frameBytes.map(b => '0x' + b.toString(16).padStart(2, '0')).join(' ');
                    let frameStr   = String.fromCharCode(...frameBytes.filter(b => b >= 0x20 && b < 0x7F));
                    console.log(`🔍 [HKA S1] Frame RAW (hex): ${frameHex}`);
                    console.log(`🔍 [HKA S1] Frame STR (printable): ${frameStr}`);

                    // Extraer número de factura: buscar el primer bloque de 6-8 dígitos consecutivos.
                    // La Bixolon SRP-812 retorna el último contador fiscal como 8 dígitos en la trama S1.
                    let digitMatch = frameStr.match(/\d{6,8}/);
                    if (digitMatch) {
                        invoice_number = digitMatch[0];
                        console.log(`✅ [HKA] Número de factura extraído: ${invoice_number}`);
                    } else {
                        // Fallback: offset empírico posición 6-14 del string imprimible
                        invoice_number = frameStr.substring(6, 14).trim() || 'N/A';
                        console.log(`⚠️ [HKA] Número de factura (fallback offset 6-14): ${invoice_number}`);
                    }
                }
            } catch(sErr) {
                console.warn('[HKA] No se pudo consultar S1 post-factura:', sErr);
            }

            return { success: true, invoice_number: invoice_number, machine_serial: machine_serial };
        } catch (error) {
            console.error("Error en HKA Invoice:", error);
            return { success: false, error: error.message };
        }
    }

    _getReturnTaxFlagHKA(line) {
        let taxes = line.tax_ids;
        if (!taxes || taxes.length === 0) return 'd0'; // Exento
        let amount = taxes[0].amount;
        if (amount === 16) return 'd1'; // Tasa General (G)
        if (amount === 8) return 'd2';  // Tasa Reducida (R)
        if (amount === 31) return 'd3'; // Tasa Adicional (A)
        return 'd0'; // Por defecto Exento
    }

    async printCreditNoteHKA(order, originalInvoiceStr, originalMachineSerial) {
        try {
            console.log("Generando Nota de Crédito en HKA...");
            let partner = order.getPartner();
            let clientName = partner ? partner.name.substring(0, 35) : "CLIENTE DE CONTADO";
            let clientRif = partner && partner.vat ? partner.vat.substring(0, 15) : "V000000000";

            await this.sendCommandHKA("iS*" + clientName);
            await this.sendCommandHKA("iR*" + clientRif);
            
            // Referencia a la factura original
            if (originalInvoiceStr) {
                await this.sendCommandHKA("iF*" + originalInvoiceStr);
            }
            if (originalMachineSerial) {
                await this.sendCommandHKA("iI*" + originalMachineSerial);
            }

            // Líneas de devolución
            for (let line of order.getOrderlines()) {
                // Para las devoluciones, las cantidades en Odoo POS suelen venir negativas.
                // Tomamos el valor absoluto porque la máquina fiscal espera cantidades positivas para el comando 'd'
                let qtyAbs = Math.abs(line.getQuantity());
                let priceAbs = Math.abs(line.price_unit);
                
                let name = line.getProduct().display_name.substring(0, 36);
                let price = this._formatHKA(priceAbs, 10, 2);
                let qty = this._formatHKA(qtyAbs, 5, 3);
                let taxFlag = this._getReturnTaxFlagHKA(line);
                
                let cmdLine = `${taxFlag}${price}${qty}${name}`;
                await this.sendCommandHKA(cmdLine);
            }

            // Subtotal
            await this.sendCommandHKA("3");
            
            // Pago (Devolución)
            await this.sendCommandHKA("101");

            return { success: true, credit_note_number: 'N/A', machine_serial: 'N/A' };
        } catch (error) {
            console.error("Error en HKA NC:", error);
            return { success: false, error: error.message };
        }
    }
    async printZReportPNP() {
        // PNP suele usar secuencias Esc/Pos modificadas o binarias específicas
        console.log("Ejecutando Z en PNP...");
        // Implementación pendiente
        return true;
    }

    // ── 3. PROTOCOLO: BEMATECH ──
    async printZReportBematech() {
        const ACK = 0x06;
        console.log("Ejecutando Z en Bematech...");
        // Implementación pendiente
        return true;
    }

    // ── 4. PROTOCOLO: VMAX ──
    async printZReportVmax() {
        console.log("Ejecutando Z en Vmax...");
        return true;
    }

    // ── 5. PROTOCOLO: EPSON ──
    async printZReportEpson() {
        // Epson Fiscal suele usar comandos como [ESC] [CMD]
        console.log("Ejecutando Z en Epson...");
        return true;
    }

    // ── 6. PROTOCOLO: CUSTOM ──
    async printZReportCustom() {
        console.log("Ejecutando Z en Custom...");
        return true;
    }

    // ── 7. PROTOCOLO: ACLAS NATIVO ──
    async printZReportAclas() {
        console.log("Ejecutando Z en Aclas...");
        return true;
    }

    // ── 8. PROTOCOLO: RIGAZSA ──
    async printZReportRigazsa() {
        console.log("Ejecutando Z en Rigazsa...");
        return true;
    }

    // ── 9. SIMULADOR VIRTUAL (PRUEBAS SIN HARDWARE) ──
    async printXReportMock() {
        console.log("🛠️ [Simulador] Iniciando proceso de Reporte X...");
        console.log("🛠️ [Simulador] Enviando trama binaria: [0x02, 0x20, 0x49, 0x58, 0x03, 0x33] al puerto invisible.");
        await new Promise(resolve => setTimeout(resolve, 2000));
        console.log("🛠️ [Simulador] Impresora respondió con éxito. (Reporte X)");
        return true;
    }

    async printZReportMock() {
        console.log("🛠️ [Simulador] Iniciando proceso de Reporte Z...");
        console.log("🛠️ [Simulador] Enviando trama binaria: [0x02, 0x20, 0x49, 0x5A, 0x03, 0x31] al puerto invisible.");
        
        // Simulamos el tiempo de espera mecánico de la impresora imprimiendo el ticket (2 segundos)
        await new Promise(resolve => setTimeout(resolve, 2000));
        
        console.log("🛠️ [Simulador] Impresora respondió con éxito. Retornando datos...");
        return true;
    }

    async printInvoiceMock(order) {
        console.log("🛠️ [Simulador] Iniciando proceso de Factura Fiscal...");
        console.log("🛠️ [Simulador] Facturando orden: " + order.name);
        
        // Simular tiempo de impresión de factura larga
        await new Promise(resolve => setTimeout(resolve, 1500));
        
        // Generar un número de factura consecutivo ficticio
        let lastInvoice = parseInt(localStorage.getItem('mock_last_invoice') || '0');
        lastInvoice += 1;
        localStorage.setItem('mock_last_invoice', lastInvoice);

        // Retornar en un formato estandarizado "00000XXX"
        let invoiceNumberStr = lastInvoice.toString().padStart(8, '0');

        console.log(`🛠️ [Simulador] Factura impresa con éxito. Número de factura: ${invoiceNumberStr}`);
        return {
            success: true,
            invoice_number: invoiceNumberStr,
            machine_serial: 'Z1A1234567'
        };
    }

    async printCreditNoteMock(order, originalInvoiceStr, originalMachineSerial) {
        console.log("🛠️ [Simulador] Iniciando proceso de Nota de Crédito Fiscal...");
        console.log(`🛠️ [Simulador] Devolución de factura original: ${originalInvoiceStr} (Máquina: ${originalMachineSerial})`);
        
        // Simular tiempo de impresión
        await new Promise(resolve => setTimeout(resolve, 1500));
        
        // Generar un número de nota de crédito consecutivo ficticio
        let lastCreditNote = parseInt(localStorage.getItem('mock_last_credit_note') || '0');
        lastCreditNote += 1;
        localStorage.setItem('mock_last_credit_note', lastCreditNote);

        let cnNumberStr = lastCreditNote.toString().padStart(8, '0');

        console.log(`🛠️ [Simulador] Nota de Crédito impresa con éxito. Número NC: ${cnNumberStr}`);
        return {
            success: true,
            credit_note_number: cnNumberStr,
            machine_serial: 'Z1A1234567'
        };
    }
}

export const fiscalPrinterService = {
    dependencies: ['notification'],
    start(env, { notification }) {
        const svc = new FiscalPrinterService(env);
        svc.notification = notification;
        return svc;
    },
};

registry.category("services").add("fiscal_printer", fiscalPrinterService, { force: true });
