"""
Генерира PDF дневен репорт с ReportLab.
Съдържа:
  - Заглавие с дата
  - Таблица с потвърдени поръчки
  - Таблица с отказани/незавършени поръчки + причини
"""
from io import BytesIO
from typing import List
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# Използваме вграден шрифт (Helvetica) — поддържа латиница, за кирилица
# трябва TTF шрифт. Ако имате DejaVuSans.ttf, разкоментирайте:
# pdfmetrics.registerFont(TTFont("DejaVu", "DejaVuSans.ttf"))
# FONT = "DejaVu"
FONT = "Helvetica"  # Fallback — кирилицата ще е транслитерирана


def _transliterate(text: str) -> str:
    """Транслитерация BG -> Latin за PDF без кирилски шрифт."""
    table = str.maketrans(
        "абвгдежзийклмнопрстуфхцчшщъьюяАБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЬЮЯ",
        "abvgdezhziyklmnoprstuftschshshtuyyaABVGDEZHZIYKLMNOPRSTUFTSCHSHSHTUYYA",
    )
    return text.translate(table)


def _t(text: str) -> str:
    """Транслитерира само ако шрифтът е Helvetica."""
    if FONT == "Helvetica":
        return _transliterate(str(text or ""))
    return str(text or "")


_PLATFORM_LABELS = {
    "facebook_messenger": "FB Messenger",
    "facebook_comment": "FB Komentar",
    "tiktok_dm": "TikTok DM",
    "tiktok_comment": "TikTok Komentar",
    "olx_email": "OLX Email",
}


def generate_report_pdf(orders: List[dict], declined: List[dict], date_str: str) -> bytes:
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", parent=styles["Title"], fontName=FONT, fontSize=18, alignment=TA_CENTER
    )
    subtitle_style = ParagraphStyle(
        "Sub", parent=styles["Heading2"], fontName=FONT, fontSize=13, spaceAfter=6
    )
    normal_style = ParagraphStyle(
        "Normal", parent=styles["Normal"], fontName=FONT, fontSize=9
    )

    elements = []

    # Заглавие
    elements.append(Paragraph(_t(f"Dnevyen Report — {date_str}"), title_style))
    elements.append(Spacer(1, 0.3 * cm))
    elements.append(
        Paragraph(_t(f"Potvarhdeni porachki: {len(orders)}   |   Otkazani: {len(declined)}"), normal_style)
    )
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
    elements.append(Spacer(1, 0.5 * cm))

    # ── Потвърдени поръчки ──────────────────────────────────────────────────
    elements.append(Paragraph(_t("Potvarhdeni Porachki"), subtitle_style))

    if orders:
        header = [_t(h) for h in ["#", "Platforma", "Produkt", "Kol.", "Klient", "Telefon", "Dostavka", "Adres", "Tsena", "Chas"]]
        rows = [header]
        for i, o in enumerate(orders, 1):
            dt = (o.get("created_at") or "")[:16].replace("T", " ")
            rows.append([
                str(i),
                _t(_PLATFORM_LABELS.get(o.get("platform", ""), o.get("platform", ""))),
                _t(o.get("product_name", "")),
                str(o.get("quantity", "")),
                _t(o.get("customer_name", "")),
                _t(o.get("phone", "")),
                _t("Ofis" if o.get("delivery_type") == "econt_office" else "Adres"),
                _t(o.get("delivery_address", "")),
                _t(o.get("total_price", "")),
                _t(dt),
            ])

        col_widths = [0.6*cm, 2.2*cm, 3*cm, 0.8*cm, 3*cm, 2.5*cm, 1.5*cm, 3.5*cm, 1.5*cm, 2.2*cm]
        tbl = Table(rows, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), FONT),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("FONTSIZE", (0, 1), (-1, -1), 7.5),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EBF5FB")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BDC3C7")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(tbl)
    else:
        elements.append(Paragraph(_t("Nyama potvarhdeni porachki za dnes."), normal_style))

    elements.append(Spacer(1, 0.8 * cm))

    # ── Отказани поръчки ────────────────────────────────────────────────────
    elements.append(Paragraph(_t("Otkazani / Nezavarsheni Porachki"), subtitle_style))

    if declined:
        header2 = [_t(h) for h in ["#", "Platforma", "Produkt", "Prichina za otkaz", "Chas"]]
        rows2 = [header2]
        for i, d in enumerate(declined, 1):
            dt = (d.get("created_at") or "")[:16].replace("T", " ")
            rows2.append([
                str(i),
                _t(_PLATFORM_LABELS.get(d.get("platform", ""), d.get("platform", ""))),
                _t(d.get("product_name") or "—"),
                _t(d.get("reason") or "Klientat spra da komunikirazhe bez prichina"),
                _t(dt),
            ])

        col_widths2 = [0.6*cm, 2.5*cm, 3*cm, 10*cm, 2.2*cm]
        tbl2 = Table(rows2, colWidths=col_widths2, repeatRows=1)
        tbl2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#922B21")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), FONT),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("FONTSIZE", (0, 1), (-1, -1), 7.5),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FDEDEC")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BDC3C7")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(tbl2)
    else:
        elements.append(Paragraph(_t("Nyama otkazani porachki za dnes."), normal_style))

    elements.append(Spacer(1, 1 * cm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    elements.append(Spacer(1, 0.2 * cm))
    elements.append(
        Paragraph(_t(f"Generiran avtomatichno — {date_str}"), normal_style)
    )

    doc.build(elements)
    return buffer.getvalue()
