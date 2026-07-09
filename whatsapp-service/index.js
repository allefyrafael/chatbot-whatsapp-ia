/**
 * Sidecar WhatsApp (Baileys) — conexão real por código de pareamento.
 *
 * Baileys precisa de um socket persistente e roda em Node, por isso vive fora do backend
 * Python. Este serviço expõe uma API HTTP mínima consumida pelo `BaileysWhatsAppProvider`
 * (lado Python) e, a cada mensagem recebida, faz POST no webhook do FastAPI.
 *
 * Endpoints:
 *   POST /connect     { numero }            -> { code, expiresIn }   (código de pareamento)
 *   GET  /status                            -> { status }
 *   POST /send        { numero, texto }     -> { ok }
 *   POST /disconnect                        -> { ok }
 *
 * Variáveis de ambiente:
 *   PORT            (default 3001)
 *   WEBHOOK_URL     (default http://localhost:8000/webhook/whatsapp)
 *   WEBHOOK_SECRET  (deve bater com WHATSAPP_WEBHOOK_SECRET do backend)
 *   PAIRING_TTL     (segundos exibidos como expiração; default 120)
 */

const express = require("express");
const pino = require("pino");
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  Browsers,
} = require("@whiskeysockets/baileys");

const PORT = process.env.PORT || 3001;
const WEBHOOK_URL = process.env.WEBHOOK_URL || "http://localhost:8000/webhook/whatsapp";
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || "troque-este-secret-do-webhook";
const PAIRING_TTL = parseInt(process.env.PAIRING_TTL || "120", 10);

const logger = pino({ level: "trace" });

// Estado global da sessão (o serviço gerencia UMA conexão de WhatsApp).
let sock = null;
let status = "desconectado"; // 'desconectado' | 'aguardando_pareamento' | 'conectado'
let numeroAtual = null;
let globalState = null;

/** Normaliza para só dígitos (DDI+DDD+número). */
function apenasDigitos(numero) {
  return String(numero || "").replace(/\D/g, "");
}

/** Formata o código do Baileys (8 chars) como XXXX-XXXX para exibição. */
function formataCodigo(code) {
  if (code && code.length === 8) return `${code.slice(0, 4)}-${code.slice(4)}`;
  return code;
}

/** Sobe (ou reusa) o socket Baileys e mantém o estado sincronizado. */
async function iniciarSocket() {
  const { state, saveCreds } = await useMultiFileAuthState("auth");
  globalState = state;

  sock = makeWASocket({
    auth: state,
    printQRInTerminal: false, // usamos código de pareamento, não QR
    logger,
    browser: Browsers.appropriate("Chrome"),
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect } = update;
    if (connection === "open") {
      status = "conectado";
      logger.info("WhatsApp conectado");
    } else if (connection === "close") {
      const code = lastDisconnect?.error?.output?.statusCode;
      const deveReconectar = code !== DisconnectReason.loggedOut;
      status = "desconectado";
      logger.warn({ code }, "Conexão encerrada");
      if (deveReconectar) iniciarSocket().catch((e) => logger.error(e));
    }
  });

  // Mensagens recebidas -> repassa ao webhook do backend e responde o que ele devolver.
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const msg of messages) {
      if (!msg.message || msg.key.fromMe) continue;
      const jid = msg.key.remoteJid || "";
      if (jid.endsWith("@g.us")) continue; // ignora grupos
      const numero = jid.split("@")[0];
      const texto =
        msg.message.conversation ||
        msg.message.extendedTextMessage?.text ||
        "";
      if (!texto) continue;
      try {
        const resp = await fetch(WEBHOOK_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Webhook-Secret": WEBHOOK_SECRET },
          body: JSON.stringify({ numero, texto }),
        });
        const data = await resp.json().catch(() => ({}));
        // O backend devolve a resposta do bot -> enviamos de volta ao cliente.
        if (data && data.resposta) {
          await sock.sendPresenceUpdate("composing", jid).catch(() => {});
          await sock.sendMessage(jid, { text: data.resposta });
        }
      } catch (e) {
        logger.error(e, "Falha ao processar mensagem recebida");
      }
    }
  });

  return sock;
}

const app = express();
app.use(express.json());

app.post("/connect", async (req, res) => {
  try {
    const numero = apenasDigitos(req.body.numero);
    if (!numero) return res.status(400).json({ error: "numero obrigatório" });
    numeroAtual = numero;

    if (!sock) await iniciarSocket();

    // Já registrado (sessão salva em disco): não precisa de novo código.
    if (globalState && globalState.creds && globalState.creds.registered) {
      status = "conectado";
      return res.json({ code: null, expiresIn: 0, alreadyConnected: true });
    }

    // Não registrado: recria o socket do zero para um pedido de código LIMPO.
    // (Pedir código num socket antigo é a causa clássica de "código inválido".)
    try { sock.end(undefined); } catch (_) {}
    sock = null;
    await iniciarSocket();

    status = "aguardando_pareamento";
    // Aguarda o WebSocket abrir antes de pedir o código (evita código inválido).
    await new Promise((resolve) => setTimeout(resolve, 3000));

    const code = await sock.requestPairingCode(numero);
    logger.info({ numero }, "Código de pareamento gerado");
    return res.json({ code: formataCodigo(code), expiresIn: PAIRING_TTL });
  } catch (e) {
    logger.error(e, "Erro em /connect");
    return res.status(500).json({ error: String(e) });
  }
});

app.get("/status", (_req, res) => {
  res.json({ status });
});

app.post("/send", async (req, res) => {
  try {
    if (!sock || status !== "conectado") return res.status(409).json({ error: "não conectado" });
    const numero = apenasDigitos(req.body.numero);
    const texto = req.body.texto || "";
    await sock.sendMessage(`${numero}@s.whatsapp.net`, { text: texto });
    return res.json({ ok: true });
  } catch (e) {
    logger.error(e, "Erro em /send");
    return res.status(500).json({ error: String(e) });
  }
});

app.post("/disconnect", async (_req, res) => {
  try {
    if (sock) {
      await sock.logout().catch(() => { });
      sock = null;
    }
    status = "desconectado";
    numeroAtual = null;
    return res.json({ ok: true });
  } catch (e) {
    return res.status(500).json({ error: String(e) });
  }
});

app.listen(PORT, () => logger.info(`whatsapp-service ouvindo em http://localhost:${PORT}`));
