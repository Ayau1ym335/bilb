"""
report/generator.py  —  PDF Report Generator
═══════════════════════════════════════════════
Генерирует многостраничный PDF-отчёт через ReportLab.

Структура:
  Стр. 1   — Обложка (dark cover: логотип, название здания, дата)
  Стр. 2   — Секция 1: Сенсорные данные (таблица + issues)
  Стр. 3   — Секция 2: AI-диагностика (статус, score, ML confidence)
  Стр. 4   — Секция 3: Сценарии адаптации (сравнительная таблица)
  Стр. 5   — Секция 4: Устойчивость (формула E_impact, финансы, CO₂)
  Стр. 6   — Подпись и колонтитул

Использование:
    from report.generator import generate_pdf

    pdf_bytes = generate_pdf(
        building    = {"name": "...", "city": "...", ...},
        sensor_data = {...},
        ml_result   = {"status": "CRITICAL", "score": 72.5, ...},
        scenarios   = [{...}, {...}, {...}],
        sus_report  = SustainabilityReport(...),
    )
    # → bytes → st.download_button(data=pdf_bytes, ...)

▶ НАСТРОЙТЕ: FONT_DIR если нужны кастомные шрифты.
"""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, Image,
    PageBreak, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)

# ── Страница ──────────────────────────────────────────────────
W, H       = A4              # 595.28 × 841.89 pt
MARGIN     = 2.0 * cm
TEXT_W     = W - 2 * MARGIN

# ══════════════════════════════════════════════════════════════
#  Палитра (тёмный tech-стиль)
# ══════════════════════════════════════════════════════════════
C_BLACK    = colors.HexColor("#080a0e")
C_BG2      = colors.HexColor("#0d1117")
C_BG3      = colors.HexColor("#111820")
C_BORDER   = colors.HexColor("#1e2d3d")
C_ACC      = colors.HexColor("#00ff88")   # акцент зелёный
C_WARN     = colors.HexColor("#ffaa00")
C_CRIT     = colors.HexColor("#E24B4A")
C_INFO     = colors.HexColor("#378ADD")
C_DEMO     = colors.HexColor("#E24B4A")   # demolition = red
C_REST     = colors.HexColor("#1D9E75")   # restoration = green
C_WHITE    = colors.white
C_TEXT     = colors.HexColor("#c8d8e8")
C_TEXT2    = colors.HexColor("#6a8090")
C_TEXT3    = colors.HexColor("#3a5060")

STATUS_COLORS = {
    "OK":       C_ACC,
    "WARNING":  C_WARN,
    "CRITICAL": C_CRIT,
}


# ══════════════════════════════════════════════════════════════
#  Шрифты
#  ReportLab встроенные: Helvetica (sans) и Courier (mono).
#  ▶ НАСТРОЙТЕ: раскомментируй TTFont-блок для кастомных шрифтов.
# ══════════════════════════════════════════════════════════════
FONT_NORMAL = "Helvetica"
FONT_BOLD   = "Helvetica-Bold"
FONT_MONO   = "Courier"

# # Пример кастомных шрифтов (JetBrains Mono):
# _FONT_DIR = os.getenv("FONT_DIR", "/usr/share/fonts")
# try:
#     pdfmetrics.registerFont(TTFont("JBMono", f"{_FONT_DIR}/JetBrainsMono-Regular.ttf"))
#     pdfmetrics.registerFont(TTFont("JBMono-Bold", f"{_FONT_DIR}/JetBrainsMono-Bold.ttf"))
#     FONT_MONO = "JBMono"
# except Exception:
#     pass  # fallback to Courier


# ══════════════════════════════════════════════════════════════
#  Стили параграфов
# ══════════════════════════════════════════════════════════════
def _styles() -> dict:
    s = getSampleStyleSheet()

    def P(name, **kwargs) -> ParagraphStyle:
        return ParagraphStyle(name, **kwargs)

    return {
        "cover_logo": P("cover_logo",
            fontName=FONT_BOLD, fontSize=48, textColor=C_ACC,
            alignment=TA_CENTER, spaceAfter=4,
            leading=54, tracking=8,
        ),
        "cover_sub": P("cover_sub",
            fontName=FONT_NORMAL, fontSize=9, textColor=C_TEXT2,
            alignment=TA_CENTER, spaceAfter=20,
            tracking=3,
        ),
        "cover_title": P("cover_title",
            fontName=FONT_BOLD, fontSize=22, textColor=C_TEXT,
            alignment=TA_CENTER, spaceAfter=6, leading=28,
        ),
        "cover_meta": P("cover_meta",
            fontName=FONT_NORMAL, fontSize=9, textColor=C_TEXT2,
            alignment=TA_CENTER, spaceAfter=4,
        ),
        "section_num": P("section_num",
            fontName=FONT_BOLD, fontSize=8, textColor=C_ACC,
            spaceAfter=2, tracking=3,
        ),
        "section_title": P("section_title",
            fontName=FONT_BOLD, fontSize=16, textColor=C_TEXT,
            spaceAfter=10, leading=20,
        ),
        "body": P("body",
            fontName=FONT_NORMAL, fontSize=9, textColor=C_TEXT,
            spaceAfter=6, leading=14,
        ),
        "body2": P("body2",
            fontName=FONT_NORMAL, fontSize=8, textColor=C_TEXT2,
            spaceAfter=4, leading=12,
        ),
        "mono": P("mono",
            fontName=FONT_MONO, fontSize=9, textColor=C_ACC,
            spaceAfter=4, leading=13, backColor=C_BG2,
            borderPadding=(4, 6, 4, 6),
        ),
        "formula": P("formula",
            fontName=FONT_MONO, fontSize=10, textColor=C_TEXT,
            spaceAfter=6, leading=15, alignment=TA_LEFT,
            backColor=C_BG3, borderPadding=(6, 8, 6, 8),
        ),
        "label": P("label",
            fontName=FONT_BOLD, fontSize=7, textColor=C_TEXT2,
            tracking=2, spaceAfter=2,
        ),
        "big_metric": P("big_metric",
            fontName=FONT_BOLD, fontSize=22, textColor=C_ACC,
            alignment=TA_CENTER, leading=26,
        ),
        "metric_label": P("metric_label",
            fontName=FONT_NORMAL, fontSize=7, textColor=C_TEXT2,
            alignment=TA_CENTER, tracking=1,
        ),
        "footer": P("footer",
            fontName=FONT_NORMAL, fontSize=7, textColor=C_TEXT3,
            alignment=TA_CENTER,
        ),
        "issue_ok":   P("issue_ok",   fontName=FONT_BOLD, fontSize=8,
                        textColor=C_ACC,  backColor=C_BG3, borderPadding=3),
        "issue_warn": P("issue_warn", fontName=FONT_BOLD, fontSize=8,
                        textColor=C_WARN, backColor=C_BG3, borderPadding=3),
        "issue_crit": P("issue_crit", fontName=FONT_BOLD, fontSize=8,
                        textColor=C_CRIT, backColor=C_BG3, borderPadding=3),
        "th": P("th",
            fontName=FONT_BOLD, fontSize=8, textColor=C_TEXT2,
            tracking=1,
        ),
        "td": P("td",
            fontName=FONT_NORMAL, fontSize=8, textColor=C_TEXT,
            leading=11,
        ),
        "td_green": P("td_green",
            fontName=FONT_BOLD, fontSize=8, textColor=C_REST,
        ),
        "td_red": P("td_red",
            fontName=FONT_BOLD, fontSize=8, textColor=C_DEMO,
        ),
        "td_mono": P("td_mono",
            fontName=FONT_MONO, fontSize=8, textColor=C_ACC,
        ),
    }


# ══════════════════════════════════════════════════════════════
#  Shared table style helpers
# ══════════════════════════════════════════════════════════════
def _base_table_style() -> list:
    return [
        ("BACKGROUND",  (0, 0), (-1, 0),   C_BG3),
        ("TEXTCOLOR",   (0, 0), (-1, 0),   C_TEXT2),
        ("FONTNAME",    (0, 0), (-1, 0),   FONT_BOLD),
        ("FONTSIZE",    (0, 0), (-1, 0),   7),
        ("TOPPADDING",  (0, 0), (-1, -1),  5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1),  8),
        ("RIGHTPADDING",(0, 0), (-1, -1),  8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_BG2, C_BG3]),
        ("GRID",        (0, 0), (-1, -1),  0.3, C_BORDER),
        ("LINEBELOW",   (0, 0), (-1, 0),   0.8, C_BORDER),
        ("FONTSIZE",    (0, 1), (-1, -1),  8),
        ("FONTNAME",    (0, 1), (-1, -1),  FONT_NORMAL),
        ("TEXTCOLOR",   (0, 1), (-1, -1),  C_TEXT),
        ("VALIGN",      (0, 0), (-1, -1),  "MIDDLE"),
    ]


# ══════════════════════════════════════════════════════════════
#  Page background & footer callbacks
# ══════════════════════════════════════════════════════════════
class _BILBDoc(BaseDocTemplate):
    """Кастомный DocTemplate с тёмным фоном и колонтитулами."""

    def __init__(self, buf: io.BytesIO, building_name: str, **kwargs):
        self.building_name  = building_name
        self._page_num      = 0
        super().__init__(buf, pagesize=A4, **kwargs)

    def handle_pageBegin(self):
        super().handle_pageBegin()
        self._page_num += 1

    def _draw_background(self, canvas, _doc):
        canvas.saveState()
        # Dark background
        canvas.setFillColor(C_BLACK)
        canvas.rect(0, 0, W, H, fill=1, stroke=0)
        canvas.restoreState()

    def _draw_footer(self, canvas, _doc):
        if self._page_num <= 1:
            return    # нет футера на обложке
        canvas.saveState()
        canvas.setFont(FONT_NORMAL, 7)
        canvas.setFillColor(C_TEXT3)
        # Линия
        canvas.setStrokeColor(C_BORDER)
        canvas.setLineWidth(0.3)
        canvas.line(MARGIN, 1.4 * cm, W - MARGIN, 1.4 * cm)
        # Текст
        canvas.drawString(MARGIN, 1.0 * cm,
                          f"BILB Platform — {self.building_name}")
        canvas.drawRightString(W - MARGIN, 1.0 * cm,
                               f"Page {self._page_num}")
        canvas.restoreState()

    def _draw_header_accent(self, canvas, _doc):
        """Тонкая зелёная линия вверху каждой страницы (кроме обложки)."""
        if self._page_num <= 1:
            return
        canvas.saveState()
        canvas.setStrokeColor(C_ACC)
        canvas.setLineWidth(1.5)
        canvas.line(MARGIN, H - 1.0 * cm, W - MARGIN, H - 1.0 * cm)
        canvas.restoreState()

    def beforePage(self):
        # Background MUST be drawn before content — afterPage() fires after
        # flowables are painted and an opaque rect would cover all text.
        self.canv.saveState()
        self._draw_background(self.canv, self)
        self.canv.restoreState()

    def afterPage(self):
        # Header accent and footer go on top of content — correct in afterPage().
        self.canv.saveState()
        self._draw_header_accent(self.canv, self)
        self._draw_footer(self.canv, self)
        self.canv.restoreState()


# ══════════════════════════════════════════════════════════════
#  Section builder helpers
# ══════════════════════════════════════════════════════════════
def _hr(story: list, color=C_BORDER, thickness=0.5):
    story.append(HRFlowable(width="100%", thickness=thickness,
                             color=color, spaceAfter=8, spaceBefore=4))


def _spacer(story: list, h_cm: float = 0.4):
    story.append(Spacer(1, h_cm * cm))


def _section_header(story: list, num: str, title: str, S: dict):
    story.append(Paragraph(f"SECTION {num}", S["section_num"]))
    story.append(Paragraph(title, S["section_title"]))
    _hr(story, C_ACC, 0.8)
    _spacer(story, 0.3)


def _metric_row(story: list, metrics: list[tuple], S: dict, cols: int = 4):
    """
    Горизонтальный ряд метрик.
    metrics = [(value_str, label_str), ...]
    """
    col_w = TEXT_W / cols
    data  = [[
        Paragraph(v, S["big_metric"]) for v, _ in metrics
    ], [
        Paragraph(l, S["metric_label"]) for _, l in metrics
    ]]
    t = Table(data, colWidths=[col_w] * cols)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_BG2),
        ("BOX",        (0, 0), (-1, -1), 0.3, C_BORDER),
        ("INNERGRID",  (0, 0), (-1, -1), 0.3, C_BORDER),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEABOVE",  (0, 0), (-1, 0), 1.5, C_ACC),
    ]))
    story.append(t)
    _spacer(story, 0.5)


# ══════════════════════════════════════════════════════════════
#  SECTION 0 — COVER
# ══════════════════════════════════════════════════════════════
def _build_cover(story: list, building: dict, sensor_data: dict, S: dict):
    """Тёмная обложка: большой логотип, название здания, дата."""
    _spacer(story, 4.0)

    # Логотип
    story.append(Paragraph("BILB", S["cover_logo"]))
    story.append(Paragraph(
        "BUILDING INSPECTION &amp; LIFECYCLE BOT",
        S["cover_sub"]
    ))

    # Разделитель
    story.append(HRFlowable(
        width="60%", thickness=0.8, color=C_ACC,
        spaceBefore=8, spaceAfter=16, hAlign="CENTER",
    ))

    # Заголовок отчёта
    story.append(Paragraph("Building Assessment Report", S["cover_title"]))
    _spacer(story, 0.3)

    name       = building.get("name",       "Unknown Building")
    city       = building.get("city",       "—")
    year_built = building.get("year_built", "—")
    bid        = building.get("building_id","BILB_001")
    area       = building.get("area_m2")
    floors     = building.get("floors")

    story.append(Paragraph(
        f'<font size="18" color="#c8d8e8"><b>{name}</b></font>',
        ParagraphStyle("cn", alignment=TA_CENTER, spaceAfter=6)
    ))
    story.append(Paragraph(
        f'{city} · Est. {year_built} · ID: {bid}',
        S["cover_meta"]
    ))
    if area or floors:
        area_str   = f"{area:,.0f} m²" if area else "—"
        floors_str = f"{floors} floors" if floors else "—"
        story.append(Paragraph(
            f'{area_str} · {floors_str}',
            S["cover_meta"]
        ))

    _spacer(story, 2.0)
    story.append(HRFlowable(
        width="60%", thickness=0.3, color=C_BORDER,
        spaceAfter=12, hAlign="CENTER",
    ))

    now = datetime.now(timezone.utc).strftime("%d %B %Y · %H:%M UTC")
    story.append(Paragraph(f"Generated: {now}", S["cover_meta"]))
    story.append(Paragraph(
        f"Scans: {sensor_data.get('total_scans', '—')} · "
        f"Readings: {sensor_data.get('total_readings', '—')}",
        S["cover_meta"]
    ))
    story.append(Paragraph(
        "Robot: ESP32 v2.1.0 · Classifier: Random Forest · LLM: Gemini 1.5",
        S["cover_meta"]
    ))

    story.append(PageBreak())


# ══════════════════════════════════════════════════════════════
#  SECTION 1 — SENSOR DATA
# ══════════════════════════════════════════════════════════════
def _build_sensor_section(story: list, sensor_data: dict, S: dict):
    _section_header(story, "1", "Environmental & Structural Data", S)

    # Ряд метрик
    _metric_row(story, [
        (f"{sensor_data.get('avg_temperature', 0):.1f}°C", "AVG TEMPERATURE"),
        (f"{sensor_data.get('avg_humidity', 0):.1f}%",     "AVG HUMIDITY"),
        (f"{sensor_data.get('avg_light_lux', 0):.0f} lx",  "AVG LIGHT"),
        (f"{sensor_data.get('max_tilt_roll', 0):.1f}°",    "MAX TILT (ROLL)"),
    ], S, cols=4)

    _metric_row(story, [
        (str(sensor_data.get("vibration_events", 0)), "VIBRATION EVENTS"),
        (f"{sensor_data.get('max_tilt_pitch', 0):.1f}°",  "MAX TILT (PITCH)"),
        (str(sensor_data.get("total_readings", 0)),       "TOTAL READINGS"),
        (str(sensor_data.get("total_scans", 0)),          "SCAN SESSIONS"),
    ], S, cols=4)

    _spacer(story, 0.3)

    # Детальная таблица
    story.append(Paragraph("SENSOR READINGS SUMMARY", S["label"]))
    _spacer(story, 0.2)

    rows = [
        ["Parameter",          "Min",   "Avg",   "Max",   "Unit",  "Status"],
        ["Temperature",
         f"{sensor_data.get('min_temperature', '—')}",
         f"{sensor_data.get('avg_temperature', 0):.1f}",
         f"{sensor_data.get('max_temperature', '—')}",
         "°C",
         _status_badge(sensor_data.get('avg_temperature', 0), 30, 40)],
        ["Humidity",
         f"{sensor_data.get('min_humidity', '—')}",
         f"{sensor_data.get('avg_humidity', 0):.1f}",
         f"{sensor_data.get('max_humidity', '—')}",
         "%",
         _status_badge(sensor_data.get('avg_humidity', 0), 55, 70)],
        ["Light (lux)",
         f"{sensor_data.get('min_light', '—')}",
         f"{sensor_data.get('avg_light_lux', 0):.0f}",
         f"{sensor_data.get('max_light', '—')}",
         "lux",
         "OK" if sensor_data.get('avg_light_lux', 200) >= 100 else "WARN"],
        ["Tilt Roll",
         "—",
         f"{sensor_data.get('avg_tilt_roll', 0):.2f}",
         f"{sensor_data.get('max_tilt_roll', 0):.2f}",
         "°",
         _status_badge(abs(sensor_data.get('max_tilt_roll', 0)), 5, 15)],
        ["Vibration Events",
         "—", "—",
         str(sensor_data.get("vibration_events", 0)),
         "count",
         "CRITICAL" if sensor_data.get("vibration_events", 0) > 5
         else "WARNING" if sensor_data.get("vibration_events", 0) > 0
         else "OK"],
    ]

    col_w = [TEXT_W * x for x in [0.28, 0.12, 0.12, 0.12, 0.12, 0.24]]
    t = Table(rows, colWidths=col_w)
    style = _base_table_style() + [
        ("ALIGN", (1, 0), (-2, -1), "CENTER"),
    ]
    # Цвет последней колонки по статусу
    for ri, row in enumerate(rows[1:], 1):
        status = row[-1]
        c = (C_CRIT if "CRIT" in status
             else C_WARN if "WARN" in status or "WARNING" in status
             else C_ACC)
        style.append(("TEXTCOLOR", (-1, ri), (-1, ri), c))
        style.append(("FONTNAME",  (-1, ri), (-1, ri), FONT_BOLD))

    t.setStyle(TableStyle(style))
    story.append(t)
    _spacer(story, 0.6)

    # Issues list
    issues = sensor_data.get("issues") or []
    if isinstance(issues, str):
        import json
        try:
            issues = json.loads(issues)
        except Exception:
            issues = [i.strip() for i in issues.split(",") if i.strip()]
    issues = [i for i in issues if i and i.upper() != "NONE"]

    if issues:
        story.append(Paragraph("IDENTIFIED ISSUES", S["label"]))
        _spacer(story, 0.15)
        issue_data = [issues[i:i+3] for i in range(0, len(issues), 3)]
        for row_items in issue_data:
            while len(row_items) < 3:
                row_items.append("")
            row = []
            for item in row_items:
                if not item:
                    row.append(Paragraph("", S["body"]))
                    continue
                c   = C_CRIT if "CRIT" in item or "STRUCTURAL" in item else C_WARN
                row.append(Paragraph(
                    f'<font color="#{c.hexval()[2:]}">{item}</font>',
                    ParagraphStyle("issue", fontName=FONT_BOLD, fontSize=8,
                                   backColor=C_BG3, borderPadding=4,
                                   leading=11)
                ))
            t_row = Table([row], colWidths=[TEXT_W / 3] * 3)
            t_row.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.3, C_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(t_row)
            _spacer(story, 0.15)

    story.append(PageBreak())


# ══════════════════════════════════════════════════════════════
#  SECTION 2 — AI DIAGNOSTICS
# ══════════════════════════════════════════════════════════════
def _build_ai_section(story: list, ml_result: dict, S: dict):
    _section_header(story, "2", "AI Degradation Assessment", S)

    status     = ml_result.get("status",     "UNKNOWN")
    score      = ml_result.get("score",      0)
    confidence = ml_result.get("confidence", 0)
    model      = ml_result.get("model",      "—")
    proba      = ml_result.get("probabilities", {})
    rule_st    = ml_result.get("rule_status", status)

    sc  = STATUS_COLORS.get(status, C_TEXT)
    sc2 = STATUS_COLORS.get(rule_st, C_TEXT)

    # Статус + score — крупно
    status_data = [[
        Paragraph(status, ParagraphStyle(
            "big_status", fontName=FONT_BOLD, fontSize=32,
            textColor=sc, alignment=TA_CENTER, leading=38,
        )),
        Paragraph(f"{score:.1f}<br/><font size='9' color='#6a8090'>/ 100</font>",
                  ParagraphStyle("score_big", fontName=FONT_BOLD, fontSize=28,
                                 textColor=sc, alignment=TA_CENTER, leading=34)),
        Paragraph(f"{confidence:.0%}<br/><font size='8' color='#6a8090'>CONFIDENCE</font>",
                  ParagraphStyle("conf_big", fontName=FONT_BOLD, fontSize=22,
                                 textColor=C_INFO, alignment=TA_CENTER, leading=28)),
    ]]
    t_status = Table(status_data, colWidths=[TEXT_W * 0.4, TEXT_W * 0.3, TEXT_W * 0.3])
    t_status.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1),  C_BG2),
        ("BOX",        (0, 0), (-1, -1),  1.5, sc),
        ("INNERGRID",  (0, 0), (-1, -1),  0.3, C_BORDER),
        ("ALIGN",      (0, 0), (-1, -1),  "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1),  "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
    ]))
    story.append(t_status)
    _spacer(story, 0.6)

    # Score bar (visual progress)
    story.append(Paragraph("DEGRADATION SCORE", S["label"]))
    _spacer(story, 0.15)

    bar_w   = TEXT_W
    fill_w  = TEXT_W * (score / 100.0)
    bar_t = Table(
        [[Paragraph("", S["body"])]],
        colWidths=[bar_w],
        rowHeights=[14],
    )
    bar_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_BG3),
        ("BOX",        (0, 0), (-1, -1), 0.3, C_BORDER),
    ]))
    story.append(bar_t)

    # Fill overlay (второй ряд — имитация заполнения)
    bar_fill = Table(
        [[Paragraph(f"  {score:.1f} / 100", ParagraphStyle(
            "bf", fontName=FONT_BOLD, fontSize=8,
            textColor=C_BLACK, leading=10,
        ))]],
        colWidths=[max(fill_w, 30)], rowHeights=[12],
    )
    bar_fill.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), sc),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
    ]))
    story.append(bar_fill)
    _spacer(story, 0.5)

    # Таблица деталей
    story.append(Paragraph("ASSESSMENT DETAILS", S["label"]))
    _spacer(story, 0.2)

    detail_rows = [
        ["Property",        "Value"],
        ["ML Model",         model.upper()],
        ["Rule-based Status",rule_st],
        ["RF Status",        status],
        ["Agreement",       "YES" if rule_st == status else "NO — RF overrides rules"],
    ]
    # Добавляем вероятности если есть
    if proba:
        for cls, p in sorted(proba.items(), key=lambda x: x[1], reverse=True):
            detail_rows.append([f"P({cls})", f"{p:.1%}"])

    col_w = [TEXT_W * 0.5, TEXT_W * 0.5]
    t_det = Table(detail_rows, colWidths=col_w)
    style = _base_table_style()
    # Покрасим значение статуса
    for ri, row in enumerate(detail_rows[1:], 1):
        val = row[1]
        if val in STATUS_COLORS:
            style.append(("TEXTCOLOR", (1, ri), (1, ri),
                          STATUS_COLORS[val]))
            style.append(("FONTNAME",  (1, ri), (1, ri), FONT_BOLD))
    t_det.setStyle(TableStyle(style))
    story.append(t_det)

    story.append(PageBreak())


# ══════════════════════════════════════════════════════════════
#  SECTION 3 — SCENARIOS
# ══════════════════════════════════════════════════════════════
def _build_scenarios_section(story: list, scenarios: list[dict], S: dict):
    _section_header(story, "3", "Adaptive Reuse Scenarios", S)

    story.append(Paragraph(
        "Three AI-generated scenarios ranked by feasibility. "
        "Scenarios account for current building condition and local market data.",
        S["body2"]
    ))
    _spacer(story, 0.3)

    if not scenarios:
        story.append(Paragraph("No scenarios available.", S["body"]))
        story.append(PageBreak())
        return

    # Сравнительная таблица
    story.append(Paragraph("SCENARIO COMPARISON TABLE", S["label"]))
    _spacer(story, 0.2)

    header = ["Metric",
              scenarios[0].get("title", "Scenario 1")[:22],
              scenarios[1].get("title", "Scenario 2")[:22] if len(scenarios) > 1 else "—",
              scenarios[2].get("title", "Scenario 3")[:22] if len(scenarios) > 2 else "—",
              ]

    def _sc(idx: int, key: str, fmt: str = "{}") -> str:
        if idx >= len(scenarios):
            return "—"
        v = scenarios[idx].get(key, "—")
        return fmt.format(v) if v not in (None, "—") else "—"

    rows = [
        header,
        ["Type",
         _sc(0, "type").capitalize(),
         _sc(1, "type").capitalize(),
         _sc(2, "type").capitalize()],
        ["Feasibility",
         _sc(0, "feasibility_score", "{}%"),
         _sc(1, "feasibility_score", "{}%"),
         _sc(2, "feasibility_score", "{}%")],
        ["Cost / m²",
         _sc(0, "estimated_cost_usd_m2", "${:,.0f}"),
         _sc(1, "estimated_cost_usd_m2", "${:,.0f}"),
         _sc(2, "estimated_cost_usd_m2", "${:,.0f}")],
        ["ROI",
         _sc(0, "roi_years", "{:.1f} yr"),
         _sc(1, "roi_years", "{:.1f} yr"),
         _sc(2, "roi_years", "{:.1f} yr")],
        ["CO₂ Saving",
         _sc(0, "co2_saving_pct", "{}%"),
         _sc(1, "co2_saving_pct", "{}%"),
         _sc(2, "co2_saving_pct", "{}%")],
    ]

    col_w = [TEXT_W * 0.22] + [TEXT_W * 0.26] * 3
    t_sc = Table(rows, colWidths=col_w)
    style = _base_table_style()

    # Покрасить feasibility по цвету
    for ri in range(1, len(rows)):
        if rows[ri][0] == "Feasibility":
            for ci in range(1, 4):
                val_str = rows[ri][ci].replace("%", "")
                try:
                    val = int(val_str)
                    c   = C_ACC if val >= 75 else C_WARN if val >= 50 else C_CRIT
                    style.append(("TEXTCOLOR", (ci, ri), (ci, ri), c))
                    style.append(("FONTNAME",  (ci, ri), (ci, ri), FONT_BOLD))
                except ValueError:
                    pass
        if rows[ri][0] == "ROI":
            for ci in range(1, 4):
                style.append(("FONTNAME", (ci, ri), (ci, ri), FONT_MONO))
        if rows[ri][0] == "CO₂ Saving":
            for ci in range(1, 4):
                style.append(("TEXTCOLOR", (ci, ri), (ci, ri), C_REST))
                style.append(("FONTNAME",  (ci, ri), (ci, ri), FONT_BOLD))

    t_sc.setStyle(TableStyle(style))
    story.append(t_sc)
    _spacer(story, 0.5)

    # Детали каждого сценария
    for i, sc in enumerate(scenarios[:3]):
        scenario_color = [C_INFO, C_WARN, C_REST][i]
        story.append(HRFlowable(
            width="100%", thickness=1.0, color=scenario_color,
            spaceBefore=8, spaceAfter=6,
        ))
        story.append(Paragraph(
            f'<font color="#{scenario_color.hexval()[2:]}">#{i+1}</font>  '
            f'<b>{sc.get("title", "—")}</b>',
            ParagraphStyle("sc_title", fontName=FONT_BOLD, fontSize=11,
                           textColor=C_TEXT, spaceAfter=3, leading=14)
        ))
        story.append(Paragraph(
            f'<i>{sc.get("tagline", "")}</i>',
            ParagraphStyle("sc_tag", fontName=FONT_NORMAL, fontSize=8,
                           textColor=C_TEXT2, spaceAfter=4, leading=11)
        ))
        story.append(Paragraph(sc.get("description", ""), S["body2"]))

        # Плюсы / минусы в 2 колонки
        benefits   = sc.get("benefits", [])
        challenges = sc.get("challenges", [])
        pw         = sc.get("priority_works", [])

        def _bullet_list(items: list, color) -> str:
            return "<br/>".join(
                f'<font color="#{color.hexval()[2:]}">▸</font> {item}'
                for item in items
            )

        if benefits or challenges:
            bc_data = [[
                Paragraph(
                    "<b>Benefits</b><br/>" + _bullet_list(benefits[:4], C_REST),
                    ParagraphStyle("bc", fontName=FONT_NORMAL, fontSize=8,
                                   textColor=C_TEXT, leading=12)
                ),
                Paragraph(
                    "<b>Challenges</b><br/>" + _bullet_list(challenges[:3], C_WARN),
                    ParagraphStyle("bc", fontName=FONT_NORMAL, fontSize=8,
                                   textColor=C_TEXT, leading=12)
                ),
            ]]
            t_bc = Table(bc_data, colWidths=[TEXT_W * 0.5, TEXT_W * 0.5])
            t_bc.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), C_BG3),
                ("BOX",        (0, 0), (-1, -1), 0.3, C_BORDER),
                ("INNERGRID",  (0, 0), (-1, -1), 0.3, C_BORDER),
                ("TOPPADDING",    (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ]))
            story.append(t_bc)
            _spacer(story, 0.2)

        if pw:
            story.append(Paragraph(
                "Priority works: " + " → ".join(pw[:3]),
                ParagraphStyle("pw", fontName=FONT_NORMAL, fontSize=8,
                               textColor=C_TEXT2, leading=11, spaceAfter=4)
            ))

    story.append(PageBreak())


# ══════════════════════════════════════════════════════════════
#  SECTION 4 — SUSTAINABILITY
# ══════════════════════════════════════════════════════════════
def _build_sustainability_section(
    story: list,
    sus,          # SustainabilityReport or dict
    S: dict,
):
    _section_header(story, "4", "Sustainability & Financial Analysis", S)

    # Унифицируем доступ: dict или dataclass
    if hasattr(sus, "summary"):
        summary   = sus.summary
        dem_imp   = sus.demolition_impact
        rest_imp  = sus.restoration_impact
        dem_fin   = sus.demolition_fin
        rest_fin  = sus.restoration_fin
    else:
        summary   = sus.get("summary",   {})
        dem_imp   = type("O", (), sus.get("demolition_impact",  {}))()
        rest_imp  = type("O", (), sus.get("restoration_impact", {}))()
        dem_fin   = type("O", (), sus.get("demolition_fin",     {}))()
        rest_fin  = type("O", (), sus.get("restoration_fin",    {}))()

    def _g(obj, attr, default=0):
        return (getattr(obj, attr, None) or
                (obj.__dict__.get(attr) if hasattr(obj, "__dict__") else default)
                or default)

    # ── Ключевые метрики ──────────────────────────────────────
    _metric_row(story, [
        (f"{summary.get('co2_saved_t', 0):,.0f} t",  "CO₂ SAVED"),
        (f"{summary.get('co2_saving_pct', 0):.0f}%", "LESS EMISSIONS"),
        (f"${summary.get('money_saved_usd', 0)/1000:,.0f}K", "MONEY SAVED"),
        (f"{summary.get('trees_equivalent', 0):,}", "TREES EQUIV."),
    ], S, cols=4)

    # ── E_impact формула ──────────────────────────────────────
    story.append(Paragraph("EMBODIED CARBON FORMULA  (E_impact)", S["label"]))
    _spacer(story, 0.15)

    ef = summary.get("e_impact_formula", {})
    story.append(Paragraph(
        "E_impact  =  ( M_brick × K_CO₂ )  +  ( M_transport × K_fuel )",
        S["formula"]
    ))
    _spacer(story, 0.1)

    if ef:
        story.append(Paragraph(
            f"  M_brick     = {ef.get('M_brick_t', 0):,.1f} tonnes  ×  "
            f"K_CO₂ = {ef.get('K_CO2', 0.24)} kg·CO₂/kg",
            ParagraphStyle("fv", fontName=FONT_MONO, fontSize=8,
                           textColor=C_TEXT2, leading=12, spaceAfter=2)
        ))
        story.append(Paragraph(
            f"  M_transport = {ef.get('M_transport_t', 0):,.1f} tonnes  ×  "
            f"{ef.get('transport_km', 50):.0f} km  ×  "
            f"K_fuel = {ef.get('K_fuel', 0.062)} kg·CO₂/(t·km)",
            ParagraphStyle("fv", fontName=FONT_MONO, fontSize=8,
                           textColor=C_TEXT2, leading=12, spaceAfter=2)
        ))
        story.append(Paragraph(
            f"  E_impact    = {ef.get('E_impact_t', 0):,.2f} tonnes CO₂",
            ParagraphStyle("fv", fontName=FONT_MONO, fontSize=9,
                           textColor=C_ACC, leading=13, spaceAfter=4,
                           fontWeight=700)
        ))
    _spacer(story, 0.4)

    # ── Финансовое сравнение ──────────────────────────────────
    story.append(Paragraph("FINANCIAL COMPARISON: DEMOLITION vs RESTORATION", S["label"]))
    _spacer(story, 0.2)

    fin_rows = [
        ["Criterion",              "Demolition Path",   "Restoration"],
        ["Demolition cost",
         f"${_g(dem_fin,'demolition_cost',0)/1000:,.0f}K",  "—"],
        ["Construction / Gross cost",
         f"${_g(dem_fin,'new_build_cost',0)/1000:,.0f}K",
         f"${_g(rest_fin,'gross_cost',0)/1000:,.0f}K"],
        ["Tax credit",             "—",
         f"-${_g(rest_fin,'tax_credit',0)/1000:,.0f}K"],
        ["Grant",                  "—",
         f"-${_g(rest_fin,'grant',0)/1000:,.0f}K"],
        ["Net investment",
         f"${_g(dem_fin,'total_cost',0)/1000:,.0f}K",
         f"${_g(rest_fin,'net_cost',0)/1000:,.0f}K"],
        ["Annual revenue",
         f"${_g(dem_fin,'annual_revenue',0)/1000:,.0f}K/yr",
         f"${_g(rest_fin,'annual_revenue',0)/1000:,.0f}K/yr"],
        ["ROI",
         f"{_g(dem_fin,'roi_years',99):.1f} years",
         f"{_g(rest_fin,'roi_years',99):.1f} years"],
        ["NPV (10 yr)",
         f"${_g(dem_fin,'npv_10yr',0)/1000:,.0f}K",
         f"${_g(rest_fin,'npv_10yr',0)/1000:,.0f}K"],
    ]

    col_w = [TEXT_W * 0.40, TEXT_W * 0.30, TEXT_W * 0.30]
    t_fin = Table(fin_rows, colWidths=col_w)
    fin_style = _base_table_style() + [
        ("ALIGN",    (1, 0), (-1, -1), "CENTER"),
    ]
    # Demolition col = красный, Restoration = зелёный (числовые ячейки)
    for ri in range(1, len(fin_rows)):
        fin_style.append(("TEXTCOLOR", (1, ri), (1, ri), C_DEMO))
        fin_style.append(("TEXTCOLOR", (2, ri), (2, ri), C_REST))
        fin_style.append(("FONTNAME",  (1, ri), (1, ri), FONT_BOLD))
        fin_style.append(("FONTNAME",  (2, ri), (2, ri), FONT_BOLD))
    # ROI и Net investment — подсветить особо
    for ri, row in enumerate(fin_rows):
        if row[0] in ("Net investment", "ROI"):
            fin_style.append(("FONTSIZE",   (0, ri), (-1, ri), 9))
            fin_style.append(("BACKGROUND", (0, ri), (-1, ri), C_BG2))

    t_fin.setStyle(TableStyle(fin_style))
    story.append(t_fin)
    _spacer(story, 0.5)

    # ── CO₂ сравнение ─────────────────────────────────────────
    story.append(Paragraph("CO₂ EMISSIONS COMPARISON", S["label"]))
    _spacer(story, 0.2)

    co2_dem  = _g(dem_imp, "co2_total_t", 0)
    co2_rest = _g(rest_imp, "co2_restoration_t", 0)
    co2_new  = _g(rest_imp, "co2_new_build_t", 0)
    co2_saved= _g(rest_imp, "co2_saved_t", 0)

    co2_rows = [
        ["Path",               "CO₂ Emissions",   "vs New Build"],
        ["Demolition + New Build",
         f"{co2_dem + co2_new:,.1f} t CO₂",  "baseline"],
        ["Restoration",
         f"{co2_rest:,.1f} t CO₂",
         f"-{_g(rest_imp,'co2_saving_pct',0):.0f}%  SAVED"],
    ]

    col_w2 = [TEXT_W * 0.45, TEXT_W * 0.30, TEXT_W * 0.25]
    t_co2 = Table(co2_rows, colWidths=col_w2)
    co2_style = _base_table_style() + [
        ("ALIGN",    (1, 0), (-1, -1), "CENTER"),
        ("TEXTCOLOR",(1, 1), (1, 1), C_DEMO),
        ("TEXTCOLOR",(1, 2), (1, 2), C_REST),
        ("TEXTCOLOR",(2, 2), (2, 2), C_REST),
        ("FONTNAME", (1, 1), (-1, -1), FONT_BOLD),
        ("FONTSIZE", (1, 2), (-1, 2), 9),
    ]
    t_co2.setStyle(TableStyle(co2_style))
    story.append(t_co2)
    _spacer(story, 0.4)

    # CO₂ эквиваленты
    trees = summary.get("trees_equivalent", 0)
    km    = summary.get("car_km_equivalent", 0)
    story.append(Paragraph(
        f"Saving {co2_saved:,.0f} tonnes CO₂ ≡  "
        f"<b>{trees:,}</b> trees growing for 1 year  ≡  "
        f"<b>{km:,}</b> km driven in an average car",
        ParagraphStyle("equiv", fontName=FONT_NORMAL, fontSize=8,
                       textColor=C_TEXT2, leading=12, spaceAfter=6,
                       backColor=C_BG3, borderPadding=(6, 8, 6, 8))
    ))


# ══════════════════════════════════════════════════════════════
#  HELPER: status text from thresholds
# ══════════════════════════════════════════════════════════════
def _status_badge(val: float, warn_thr: float, crit_thr: float) -> str:
    if val >= crit_thr:
        return "CRITICAL"
    if val >= warn_thr:
        return "WARNING"
    return "OK"


# ══════════════════════════════════════════════════════════════
#  MAIN: generate_pdf()
# ══════════════════════════════════════════════════════════════
def generate_pdf(
    building:    dict,
    sensor_data: dict,
    ml_result:   dict,
    scenarios:   list[dict],
    sus_report,               # SustainabilityReport or dict
) -> bytes:
    """
    Генерирует полный PDF-отчёт.

    Параметры:
        building    — dict BuildingProfile (name, city, year_built, area_m2, floors, ...)
        sensor_data — dict агрегированных показателей датчиков:
                      avg_temperature, avg_humidity, avg_light_lux,
                      max_tilt_roll, max_tilt_pitch, vibration_events,
                      total_readings, total_scans, issues
        ml_result   — dict из get_status() / BILBClassifier.predict():
                      status, score, confidence, probabilities, model, rule_status
        scenarios   — list[dict] из generate_scenarios()
        sus_report  — SustainabilityReport или dict из calculate()

    Возвращает:
        bytes — готовый PDF для st.download_button(data=pdf_bytes, ...)
    """
    buf = io.BytesIO()
    S   = _styles()

    building_name = building.get("name", "BILB Report")

    doc = _BILBDoc(
        buf,
        building_name = building_name,
        leftMargin    = MARGIN,
        rightMargin   = MARGIN,
        topMargin     = MARGIN,
        bottomMargin  = 2.0 * cm,
    )

    frame = Frame(
        MARGIN, 2.0 * cm,
        W - 2 * MARGIN, H - MARGIN - 2.0 * cm,
        leftPadding=0, rightPadding=0,
        topPadding=0,  bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])

    story: list = []

    # ── Build all sections ────────────────────────────────────
    _build_cover(story, building, sensor_data, S)
    _build_sensor_section(story, sensor_data, S)
    _build_ai_section(story, ml_result, S)
    _build_scenarios_section(story, scenarios, S)
    _build_sustainability_section(story, sus_report, S)

    # ── Last page: footer note ────────────────────────────────
    _spacer(story, 1.0)
    _hr(story, C_BORDER)
    story.append(Paragraph(
        f"This report was automatically generated by BILB Platform on "
        f"{datetime.now(timezone.utc).strftime('%d %B %Y at %H:%M UTC')}. "
        f"Building ID: {building.get('building_id', 'BILB_001')}. "
        f"All sensor data collected via ESP32-based inspection robot. "
        f"AI diagnostics: Random Forest. Scenarios: Gemini 1.5 Pro + RAG. "
        f"Financial model based on local market data — verify with qualified surveyor.",
        S["footer"]
    ))

    # ── Build PDF ─────────────────────────────────────────────
    doc.build(story)
    return buf.getvalue()
