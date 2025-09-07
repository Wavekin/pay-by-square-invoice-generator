import os
os.chdir(os.path.dirname(__file__))
import random
import datetime
import configparser
from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP
import re

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import qrcode
from qrcode.constants import ERROR_CORRECT_Q

# ✅ Official PAY by Square library
import pay_by_square

# ---------- FONT REGISTRATION ----------
def _try_register_fonts():
    candidates = [
        os.path.join("assets", "fonts", "DejaVuSans.ttf"),
        os.path.join("assets", "fonts", "DejaVuSans-Bold.ttf"),
        "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf",
    ]
    normal = None
    bold = None
    for path in candidates:
        if os.path.isfile(path) and path.lower().endswith("dejavusans.ttf"):
            normal = path
        if os.path.isfile(path) and "bold" in path.lower():
            bold = path
    try:
        if normal:
            pdfmetrics.registerFont(TTFont("DejaVu", normal))
        if bold:
            pdfmetrics.registerFont(TTFont("DejaVu-Bold", bold))
        return ("DejaVu" if normal else "Helvetica",
                "DejaVu-Bold" if bold else "Helvetica-Bold")
    except Exception:
        return "Helvetica", "Helvetica-Bold"

FONT_REGULAR, FONT_BOLD = _try_register_fonts()

# ---------- PAGE NUMBERING ----------
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        if not self._saved_page_states:
            self.showPage()
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(num_pages)
            super().showPage()
        super().save()

    def _draw_page_number(self, page_count: int):
        self.setFont(FONT_REGULAR, 8)
        page_str = f"Strana {self._pageNumber} z {page_count}"
        self.drawRightString(self._pagesize[0] - 50, 30, page_str)

# ---------- UTILITIES ----------
def generate_invoice_number() -> str:
    today = datetime.datetime.today().strftime("%Y%m%d")
    rnd = random.randint(10, 99)
    return f"{today}{rnd}"

def _parse_date_any(s: str) -> datetime.datetime:
    s = s.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {s}. Use dd.mm.yyyy or yyyy-mm-dd.")

def read_invoice_data(filename: str) -> configparser.SectionProxy:
    config = configparser.ConfigParser()
    with open(filename, "r", encoding="utf-8") as f:
        raw = f.read()
    config.read_string("[DEFAULT]\n" + raw)
    return config["DEFAULT"]

def parse_items(items_text: str):
    items = []
    for line in items_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 4:
            name, qty, unit, price = parts
            qty_f = float(qty.replace(",", "."))
            price_f = float(price.replace(",", "."))
            total = qty_f * price_f
            items.append((name, qty_f, unit, price_f, total))
    return items

# ---------- Генерация счета ----------
def create_invoice(data: configparser.SectionProxy):
    invoice_number = generate_invoice_number()
    vs = invoice_number

    # --- Dodávateľ ---
    seller_name = data.get("seller_name", "").strip()
    seller_address = data.get("seller_address", "").strip()
    seller_ico = data.get("seller_ico", "").strip()
    seller_dic = data.get("seller_dic", "").strip()
    seller_icdph = data.get("seller_icdph", "").strip()
    seller_note1 = data.get("seller_note1", "").strip()
    seller_note2 = data.get("seller_note2", "").strip()

    # --- Odberateľ ---
    client_name = data.get("client_name", "").strip()
    client_address = data.get("client_address", "").strip()
    client_ico = data.get("client_ico", "").strip()
    client_dic = data.get("client_dic", "").strip()
    client_icdph = data.get("client_icdph", "").strip()

    iban = data.get("iban", "").strip()
    currency = data.get("currency", "EUR").strip() or "EUR"
    days_due = int(data.get("days_due", "14").strip() or "14")
    note_txt = data.get("note", "").strip()
    vs = re.sub(r"\D", "", data.get("vs", "").strip()) or generate_invoice_number()
    bic = data.get("bic", "").strip()

    issue_date_raw = data.get("issue_date", "").strip()
    issue_dt = _parse_date_any(issue_date_raw)
    due_dt = issue_dt + datetime.timedelta(days=days_due)

    items = parse_items(data.get("items", ""))
    total_amount = sum(i[4] for i in items)

    save_dir = os.path.join(".", "invoices")
    os.makedirs(save_dir, exist_ok=True)
    pdf_path = os.path.join(save_dir, f"invoice_{invoice_number}.pdf")

    c = NumberedCanvas(pdf_path, pagesize=A4)
    width, height = A4

    # Заголовок
    c.setFont(FONT_BOLD, 14)
    c.drawString(50, height - 50, f"Evidenčné číslo: {invoice_number}")

    # Dodávateľ
    c.setFont(FONT_BOLD, 12)
    c.drawString(50, height - 100, "DODÁVATEĽ")
    c.setFont(FONT_REGULAR, 10)
    c.drawString(50, height - 120, seller_name)
    c.drawString(50, height - 135, seller_address)
    y = height - 150
    if seller_ico:
        c.setFont(FONT_BOLD, 10); c.drawString(50, y, "IČO:")
        c.setFont(FONT_REGULAR, 10); c.drawString(80, y, seller_ico); y -= 15
    if seller_dic:
        c.setFont(FONT_BOLD, 10); c.drawString(50, y, "DIČ:")
        c.setFont(FONT_REGULAR, 10); c.drawString(80, y, seller_dic); y -= 15

    if seller_icdph and seller_icdph.strip() != "-":
        c.setFont(FONT_BOLD, 10); c.drawString(50, y, "IČ DPH:")
        c.setFont(FONT_REGULAR, 10); c.drawString(100, y, seller_icdph.strip()); y -= 15
    else:
        c.setFont(FONT_BOLD, 10); c.drawString(50, y, "Neplatiteľ DPH"); y -= 15

    c.setFont(FONT_REGULAR, 8)
    for line in [seller_note1, seller_note2]:
        if line:
            c.drawString(50, y, line); y -= 10

    # Odberateľ
    c.setFont(FONT_BOLD, 12)
    c.drawString(350, height - 100, "ODBERATEĽ")
    c.setFont(FONT_REGULAR, 10)
    c.drawString(350, height - 120, client_name)
    c.drawString(350, height - 135, client_address)
    y2 = height - 150
    def _kv(label, val, xlbl, xval):
        nonlocal y2
        if val:
            c.setFont(FONT_BOLD, 10); c.drawString(xlbl, y2, f"{label}:")
            c.setFont(FONT_REGULAR, 10); c.drawString(xval, y2, str(val))
            y2 -= 15
    _kv("IČO", client_ico, 350, 380)
    _kv("DIČ", client_dic, 350, 380)
    if client_icdph and client_icdph.strip() != "-":
        _kv("IČ DPH", client_icdph, 350, 400)
    else:
        c.setFont(FONT_BOLD, 10)
        c.drawString(350, y2, "Neplatiteľ DPH")
        y2 -= 15


    # Platobné údaje
    c.setFillColor(colors.white)
    c.rect(50, height - 280, 500, 70, fill=True, stroke=False)
    c.setFillColor(colors.black)
    c.setFont(FONT_BOLD, 10); c.drawString(60, height - 250, "Platobné údaje")
    c.setFont(FONT_REGULAR, 9)
    c.drawString(60, height - 265, f"IBAN: {iban}")
    c.drawString(250, height - 265, "Forma úhrady: Prevodom")
    c.drawString(60, height - 280, f"Variabilný symbol: {vs}")
    c.drawString(50, height - 300, f"Dátum vystavenia: {issue_dt.strftime('%d.%m.%Y')}")
    c.drawString(350, height - 300, f"Dátum splatnosti: {due_dt.strftime('%d.%m.%Y')}")

    # Табуľка
    c.setFont(FONT_BOLD, 10)
    c.drawString(50, height - 340, "Počet")
    c.drawString(100, height - 340, "Popis")
    c.drawString(350, height - 340, "Jedn. cena")
    c.drawString(450, height - 340, "Celkom")

    y_tbl = height - 360
    c.setFont(FONT_REGULAR, 10)
    for name, qty, unit, price, total in items:
        qty_str = f"{int(qty)}" if float(qty).is_integer() else f"{qty:g}"
        c.drawString(50, y_tbl, f"{qty_str} {unit}")
        c.drawString(100, y_tbl, name)
        c.drawRightString(420, y_tbl, f"{price:.2f} €")
        c.drawRightString(530, y_tbl, f"{total:.2f} €")
        y_tbl -= 20

    c.setFillColor(colors.blue)
    c.rect(350, y_tbl - 30, 200, 30, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont(FONT_BOLD, 12)
    c.drawString(360, y_tbl - 15, f"Celkom k úhrade: {total_amount:.2f} €")

    # --- QR (Pay by Square) — через библиотеку matusf/pay-by-square ---
    vs_str = re.sub(r"\D", "", str(vs))[:10]
    if not vs_str:
        raise ValueError("Variabilný symbol musí byť číselný.")
    amount_dec = Decimal(str(total_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    iban_norm = iban.replace(" ", "").upper()

    # Разнесём адрес поставщика на 2 строки для красоты QR (если есть запятая)
    addr1, addr2 = seller_address, ""
    if "," in seller_address:
        p1, p2 = seller_address.split(",", 1)
        addr1 = p1.strip()
        addr2 = p2.strip()

    # Генерим ПРАВИЛЬНУЮ строку для QR (Base32hex PAY by square)
    code = pay_by_square.generate(
        amount=float(Decimal(str(total_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        iban=iban.replace(" ", "").upper(),
        swift=(bic or None),
        currency=currency,
        date=due_dt.date(),
        variable_symbol=vs[:10],
        note=note_txt or f"Faktura {invoice_number}",
        beneficiary_name=seller_name or None,
        beneficiary_address_1=(seller_address.split(",")[0].strip() if "," in seller_address else seller_address) or None,
        beneficiary_address_2=(seller_address.split(",", 1)[1].strip() if "," in seller_address else "") or None,
    )

    # Рисуем QR со строкой `code`
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_Q, box_size=6, border=4)
    qr.add_data(code)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    qr_buffer = BytesIO()
    img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    qr_reader = ImageReader(qr_buffer)

    qr_size = 90
    qr_x = width - 10 - qr_size
    qr_y = height - 10 - qr_size
    c.drawImage(qr_reader, qr_x, qr_y, qr_size, qr_size)
    c.setFont(FONT_BOLD, 10)
    c.setFillColor(colors.black)
    c.drawString(qr_x + 10, qr_y - 10, "PAY by square")

    # Footer
    c.setFont(FONT_REGULAR, 8)
    c.setFillColor(colors.black)
    c.drawString(50, 30, f"Vystavil(a): {seller_name}")

    c.showPage()
    c.save()
    print(f"Faktúra uložená: {pdf_path}")