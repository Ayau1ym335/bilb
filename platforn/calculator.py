"""
economist/calculator.py  —  Движок 3: Математическая модель
════════════════════════════════════════════════════════════
Формула ТЗ:
    E_impact = (M_brick × K_CO₂) + (M_transport × K_fuel)

Дополнительно:
    · CO₂ новой постройки vs реставрации
    · Финансовая модель: demolition path vs restoration path
    · NPV за 10 лет с дисконтированием
    · Налоговые кредиты + гранты
    · Эквиваленты: деревья, км пробега авто
    · Экспорт в Plotly-ready формат

Публичный API:
    calculate(building_id, floor_area_m2, floors, ...) → SustainabilityReport
    calculate_from_profile(profile_dict)               → SustainabilityReport
"""

from __future__ import annotations

import math
from typing import Optional

from .constants import (
    K_CO2_BRICK, K_CO2_CONCRETE, K_FUEL_TRANSPORT,
    DENSITY_BRICK, DENSITY_CONCRETE,
    DEMOLITION_WASTE_T_PER_M2, BRICK_WALL_FRACTION,
    WALL_THICKNESS_M, FLOOR_HEIGHT_M, OPENING_FRACTION,
    DEFAULT_TRANSPORT_KM, NEW_BUILD_CO2_KG_M2,
    RESTORATION_CO2_FRACTION,
    DEMOLITION_COST_USD_M2, NEW_BUILD_COST_USD_M2,
    RESTORATION_BASE_USD_M2, TAX_CREDIT_RATE, GRANT_RATE,
    BASE_REVENUE_USD_M2_YR, DISCOUNT_RATE, HERITAGE_PREMIUM,
    CO2_PER_TREE_KG_YR, CO2_PER_CAR_KM,
    # Plotly colors
    COLOR_DEMOLITION, COLOR_RESTORATION, COLOR_NEUTRAL,
    COLOR_WARNING, COLOR_GRID, COLOR_PAPER, COLOR_TEXT, COLOR_FONT,
)
from .models import (
    DemolitionImpact, RestorationImpact,
    DemolitionFinancials, RestorationFinancials,
    SustainabilityReport,
)


# ══════════════════════════════════════════════════════════════
#  I. ФИЗИКА: E_impact
# ══════════════════════════════════════════════════════════════

def calc_demolition_impact(
    floor_area_m2:     float,
    floors:            int,
    perimeter_m:       Optional[float] = None,
    transport_km:      float = DEFAULT_TRANSPORT_KM,
    wall_thickness_m:  float = WALL_THICKNESS_M,
    floor_height_m:    float = FLOOR_HEIGHT_M,
) -> DemolitionImpact:
    """
    Расчёт экологического удара при сносе и новом строительстве.

    Шаги:
    1. Оцениваем периметр здания (если не задан — из площади этажа)
    2. Считаем объём кирпичных стен → массу кирпича
    3. Считаем массу мусора при сносе
    4. Применяем формулу ТЗ:
       E_impact = (M_brick × K_CO₂) + (M_transport × K_fuel)
    5. Добавляем CO₂ бетона (фундамент + перекрытия нового здания)
    """
    total_area = floor_area_m2 * floors

    # 1. Периметр (если не задан — квадратное основание)
    if perimeter_m is None:
        side       = math.sqrt(floor_area_m2)
        perimeter_m = 4.0 * side

    # 2. Объём кирпичных стен нового здания
    #    V = периметр × высота_здания × толщина × (1 - доля_проёмов)
    total_height   = floor_height_m * floors
    wall_volume_m3 = (perimeter_m * total_height
                      * wall_thickness_m
                      * (1.0 - OPENING_FRACTION))

    # M_brick = объём × плотность
    mass_brick_kg = wall_volume_m3 * DENSITY_BRICK
    mass_brick_t  = mass_brick_kg / 1000.0

    # 3. Масса мусора при сносе существующего здания
    mass_waste_t = total_area * DEMOLITION_WASTE_T_PER_M2

    # 4. ★ ФОРМУЛА ТЗ ★
    #    E_impact = (M_brick × K_CO₂) + (M_transport × K_fuel)
    co2_brick_t     = mass_brick_t * K_CO2_BRICK
    co2_transport_t = mass_waste_t * transport_km * K_FUEL_TRANSPORT

    # 5. CO₂ бетона (30 см перекрытий + фундамент ≈ 0.15 м³/м²)
    concrete_volume_m3 = total_area * 0.15
    mass_concrete_t    = concrete_volume_m3 * DENSITY_CONCRETE / 1000.0
    co2_concrete_t     = mass_concrete_t * K_CO2_CONCRETE

    co2_total_t = co2_brick_t + co2_transport_t + co2_concrete_t

    return DemolitionImpact(
        mass_brick_t    = round(mass_brick_t,    2),
        mass_concrete_t = round(mass_concrete_t, 2),
        mass_waste_t    = round(mass_waste_t,    2),
        co2_brick_t     = round(co2_brick_t,     2),
        co2_concrete_t  = round(co2_concrete_t,  2),
        co2_transport_t = round(co2_transport_t, 2),
        co2_total_t     = round(co2_total_t,     2),
        transport_km    = transport_km,
        floor_area_m2   = floor_area_m2,
        floors          = floors,
        total_area_m2   = total_area,
    )


def calc_restoration_impact(
    demolition: DemolitionImpact,
) -> RestorationImpact:
    """
    CO₂ реставрации vs нового строительства.
    Реставрация заменяет только повреждённые элементы (≈ RESTORATION_CO2_FRACTION).
    """
    total_area = demolition.total_area_m2

    # CO₂ нового строительства (all-in embodied carbon)
    co2_new_build_t   = (total_area * NEW_BUILD_CO2_KG_M2) / 1000.0

    # CO₂ реставрации = fraction от нового строительства
    co2_restoration_t = co2_new_build_t * RESTORATION_CO2_FRACTION

    co2_saved_t  = co2_new_build_t - co2_restoration_t
    co2_saving_pct = (co2_saved_t / co2_new_build_t * 100.0) if co2_new_build_t > 0 else 0.0

    # Эквиваленты
    trees_equivalent  = int(co2_saved_t * 1000.0 / CO2_PER_TREE_KG_YR)
    car_km_equivalent = int(co2_saved_t * 1000.0 / CO2_PER_CAR_KM)

    return RestorationImpact(
        co2_new_build_t   = round(co2_new_build_t,   2),
        co2_restoration_t = round(co2_restoration_t, 2),
        co2_saved_t       = round(co2_saved_t,       2),
        co2_saving_pct    = round(co2_saving_pct,    1),
        trees_equivalent  = trees_equivalent,
        car_km_equivalent = car_km_equivalent,
    )


# ══════════════════════════════════════════════════════════════
#  II. ФИНАНСЫ
# ══════════════════════════════════════════════════════════════

def _npv(annual_revenue: float, investment: float,
         years: int = 10, rate: float = DISCOUNT_RATE) -> float:
    """NPV за N лет: ΣCF_t/(1+r)^t - I₀"""
    pv = sum(annual_revenue / (1 + rate) ** t for t in range(1, years + 1))
    return round(pv - investment, 0)


def calc_demolition_financials(
    total_area_m2:          float,
    annual_revenue_usd_m2:  float = BASE_REVENUE_USD_M2_YR,
) -> DemolitionFinancials:
    demolition_cost = total_area_m2 * DEMOLITION_COST_USD_M2
    new_build_cost  = total_area_m2 * NEW_BUILD_COST_USD_M2
    total_cost      = demolition_cost + new_build_cost
    annual_revenue  = total_area_m2 * annual_revenue_usd_m2
    roi_years       = total_cost / annual_revenue if annual_revenue > 0 else 99.0
    npv             = _npv(annual_revenue, total_cost)

    return DemolitionFinancials(
        demolition_cost = round(demolition_cost, 0),
        new_build_cost  = round(new_build_cost,  0),
        total_cost      = round(total_cost,      0),
        annual_revenue  = round(annual_revenue,  0),
        roi_years       = round(roi_years,       1),
        npv_10yr        = npv,
    )


def calc_restoration_financials(
    total_area_m2:             float,
    restoration_cost_usd_m2:   float = RESTORATION_BASE_USD_M2,
    annual_revenue_usd_m2:     float = BASE_REVENUE_USD_M2_YR,
    tax_credit_rate:           float = TAX_CREDIT_RATE,
    grant_rate:                float = GRANT_RATE,
    heritage_premium:          float = HERITAGE_PREMIUM,
    demolition_total_cost:     float = 0.0,
) -> RestorationFinancials:
    gross_cost     = total_area_m2 * restoration_cost_usd_m2
    tax_credit     = gross_cost * tax_credit_rate
    grant          = gross_cost * grant_rate
    net_cost       = gross_cost - tax_credit - grant

    # Heritage premium на выручку
    annual_revenue = total_area_m2 * annual_revenue_usd_m2 * (1.0 + heritage_premium)
    roi_years      = net_cost / annual_revenue if annual_revenue > 0 else 99.0
    npv            = _npv(annual_revenue, net_cost)

    savings     = demolition_total_cost - net_cost
    savings_pct = (savings / demolition_total_cost * 100.0) if demolition_total_cost > 0 else 0.0

    return RestorationFinancials(
        gross_cost              = round(gross_cost,     0),
        tax_credit              = round(tax_credit,     0),
        grant                   = round(grant,          0),
        net_cost                = round(net_cost,       0),
        annual_revenue          = round(annual_revenue, 0),
        roi_years               = round(roi_years,      1),
        npv_10yr                = round(npv,            0),
        savings_vs_demolition   = round(savings,        0),
        savings_pct             = round(savings_pct,    1),
    )


# ══════════════════════════════════════════════════════════════
#  III. PLOTLY-READY CHARTS
# ══════════════════════════════════════════════════════════════

def _plotly_layout(title: str = "", height: int = 300) -> dict:
    """Базовый layout для тёмного tech-стиля."""
    return {
        "title":       {"text": title, "font": {"size": 11, "color": COLOR_TEXT}},
        "height":      height,
        "margin":      {"l": 0, "r": 0, "t": 30 if title else 10, "b": 0},
        "paper_bgcolor": COLOR_PAPER,
        "plot_bgcolor":  "#0a0d12",
        "font":          {"family": COLOR_FONT, "color": COLOR_TEXT, "size": 11},
        "xaxis":         {"gridcolor": COLOR_GRID, "showgrid": True, "zeroline": False},
        "yaxis":         {"gridcolor": COLOR_GRID, "showgrid": True, "zeroline": False},
        "showlegend":    True,
        "legend":        {"orientation": "h", "y": 1.1,
                          "font": {"size": 10, "color": COLOR_TEXT}},
    }


def build_charts(
    dem_impact: DemolitionImpact,
    rest_impact: RestorationImpact,
    dem_fin:    DemolitionFinancials,
    rest_fin:   RestorationFinancials,
) -> dict:
    """
    Возвращает dict со всеми чартами в Plotly JSON-формате.
    Каждый чарт = {"data": [...], "layout": {...}} — можно передать в go.Figure(**chart).
    """

    # ── 1. CO₂ Bar: Demolition vs Restoration ─────────────────
    co2_chart = {
        "data": [
            {
                "type":    "bar",
                "name":    "Demolition + New Build",
                "x":       ["CO₂ Emissions"],
                "y":       [round(dem_impact.co2_total_t +
                                  rest_impact.co2_new_build_t, 1)],
                "marker":  {"color": COLOR_DEMOLITION},
                "text":    [f"{dem_impact.co2_total_t + rest_impact.co2_new_build_t:.0f}t CO₂"],
                "textposition": "outside",
            },
            {
                "type":    "bar",
                "name":    "Restoration",
                "x":       ["CO₂ Emissions"],
                "y":       [rest_impact.co2_restoration_t],
                "marker":  {"color": COLOR_RESTORATION},
                "text":    [f"{rest_impact.co2_restoration_t:.0f}t CO₂"],
                "textposition": "outside",
            },
        ],
        "layout": {
            **_plotly_layout("CO₂ Emissions: Demolition vs Restoration"),
            "yaxis": {"title": "Tonnes CO₂", "gridcolor": COLOR_GRID},
            "barmode": "group",
        },
    }

    # ── 2. CO₂ Breakdown (stacked bar — компоненты E_impact) ──
    co2_breakdown = {
        "data": [
            {
                "type":   "bar",
                "name":   "Brick (M_brick × K_CO₂)",
                "x":      ["E_impact components"],
                "y":      [dem_impact.co2_brick_t],
                "marker": {"color": COLOR_DEMOLITION},
            },
            {
                "type":   "bar",
                "name":   "Concrete",
                "x":      ["E_impact components"],
                "y":      [dem_impact.co2_concrete_t],
                "marker": {"color": COLOR_WARNING},
            },
            {
                "type":   "bar",
                "name":   "Transport (M_transport × K_fuel)",
                "x":      ["E_impact components"],
                "y":      [dem_impact.co2_transport_t],
                "marker": {"color": COLOR_NEUTRAL},
            },
        ],
        "layout": {
            **_plotly_layout("E_impact Breakdown"),
            "barmode": "stack",
            "yaxis":   {"title": "Tonnes CO₂", "gridcolor": COLOR_GRID},
        },
    }

    # ── 3. Financial Comparison Bar ───────────────────────────
    fin_chart = {
        "data": [
            {
                "type":         "bar",
                "name":         "Demolition Path",
                "x":            ["Total Investment"],
                "y":            [dem_fin.total_cost],
                "marker":       {"color": COLOR_DEMOLITION},
                "text":         [f"${dem_fin.total_cost/1_000_000:.1f}M"],
                "textposition": "outside",
            },
            {
                "type":         "bar",
                "name":         "Restoration (net)",
                "x":            ["Total Investment"],
                "y":            [rest_fin.net_cost],
                "marker":       {"color": COLOR_RESTORATION},
                "text":         [f"${rest_fin.net_cost/1_000_000:.1f}M"],
                "textposition": "outside",
            },
        ],
        "layout": {
            **_plotly_layout("Financial Comparison (USD)"),
            "barmode": "group",
            "yaxis":   {"title": "USD", "gridcolor": COLOR_GRID},
        },
    }

    # ── 4. ROI Comparison ─────────────────────────────────────
    roi_chart = {
        "data": [
            {
                "type":         "bar",
                "x":            ["Demolition Path", "Restoration"],
                "y":            [dem_fin.roi_years, rest_fin.roi_years],
                "marker":       {"color": [COLOR_DEMOLITION, COLOR_RESTORATION]},
                "text":         [f"{dem_fin.roi_years:.1f} yr",
                                 f"{rest_fin.roi_years:.1f} yr"],
                "textposition": "outside",
            },
        ],
        "layout": {
            **_plotly_layout("ROI (Years to Break Even)"),
            "showlegend": False,
            "yaxis":      {"title": "Years", "gridcolor": COLOR_GRID},
        },
    }

    # ── 5. Cost Waterfall (Restoration path) ─────────────────
    waterfall_chart = {
        "data": [
            {
                "type":    "waterfall",
                "name":    "Restoration cost breakdown",
                "orientation": "v",
                "measure": ["absolute", "relative", "relative", "total"],
                "x":       ["Gross Cost", "Tax Credit", "Grants", "Net Cost"],
                "y":       [rest_fin.gross_cost,
                            -rest_fin.tax_credit,
                            -rest_fin.grant,
                            rest_fin.net_cost],
                "text":    [f"${rest_fin.gross_cost/1000:.0f}K",
                            f"-${rest_fin.tax_credit/1000:.0f}K",
                            f"-${rest_fin.grant/1000:.0f}K",
                            f"${rest_fin.net_cost/1000:.0f}K"],
                "textposition": "outside",
                "connector": {"line": {"color": COLOR_NEUTRAL}},
                "increasing": {"marker": {"color": COLOR_DEMOLITION}},
                "decreasing": {"marker": {"color": COLOR_RESTORATION}},
                "totals":    {"marker": {"color": COLOR_NEUTRAL}},
            },
        ],
        "layout": {
            **_plotly_layout("Restoration Cost Waterfall (USD)"),
            "showlegend": False,
            "yaxis":      {"title": "USD", "gridcolor": COLOR_GRID},
        },
    }

    # ── 6. NPV Comparison ─────────────────────────────────────
    npv_chart = {
        "data": [
            {
                "type":  "bar",
                "x":     ["Demolition Path", "Restoration"],
                "y":     [dem_fin.npv_10yr, rest_fin.npv_10yr],
                "marker": {"color": [
                    COLOR_DEMOLITION if dem_fin.npv_10yr < 0 else COLOR_WARNING,
                    COLOR_RESTORATION if rest_fin.npv_10yr >= 0 else COLOR_WARNING,
                ]},
                "text":   [f"${dem_fin.npv_10yr/1000:.0f}K",
                           f"${rest_fin.npv_10yr/1000:.0f}K"],
                "textposition": "outside",
            },
        ],
        "layout": {
            **_plotly_layout("NPV (10 Years, USD)"),
            "showlegend": False,
            "yaxis":      {"title": "USD (NPV)", "gridcolor": COLOR_GRID},
        },
    }

    # ── 7. CO₂ Equivalences (Gauge-style bar) ────────────────
    equiv_chart = {
        "data": [
            {
                "type":  "bar",
                "x":     ["Trees (1 yr)", "Car km (÷1000)"],
                "y":     [rest_impact.trees_equivalent,
                          rest_impact.car_km_equivalent // 1000],
                "marker": {"color": [COLOR_RESTORATION, COLOR_NEUTRAL]},
                "text":   [f"{rest_impact.trees_equivalent:,}",
                           f"{rest_impact.car_km_equivalent:,} km"],
                "textposition": "outside",
            },
        ],
        "layout": {
            **_plotly_layout("CO₂ Savings Equivalences"),
            "showlegend": False,
            "yaxis":      {"gridcolor": COLOR_GRID},
        },
    }

    return {
        "co2_comparison":  co2_chart,
        "co2_breakdown":   co2_breakdown,
        "financial":       fin_chart,
        "roi":             roi_chart,
        "cost_waterfall":  waterfall_chart,
        "npv":             npv_chart,
        "equivalences":    equiv_chart,
    }


# ══════════════════════════════════════════════════════════════
#  IV. ПУБЛИЧНЫЙ API
# ══════════════════════════════════════════════════════════════

def calculate(
    building_id:             str   = "BILB_001",
    floor_area_m2:           float = 500.0,
    floors:                  int   = 4,
    perimeter_m:             Optional[float] = None,
    transport_km:            float = DEFAULT_TRANSPORT_KM,
    restoration_cost_usd_m2: float = RESTORATION_BASE_USD_M2,
    annual_revenue_usd_m2:   float = BASE_REVENUE_USD_M2_YR,
    tax_credit_rate:         float = TAX_CREDIT_RATE,
    grant_rate:              float = GRANT_RATE,
) -> SustainabilityReport:
    """
    Главная функция Движка 3. Все расчёты в одном вызове.

    Параметры:
        building_id              — ID здания
        floor_area_m2            — площадь одного этажа, м²
        floors                   — число этажей
        perimeter_m              — периметр (None = вычислить из площади)
        transport_km             — расстояние до полигона, км  ▶ НАСТРОЙТЕ
        restoration_cost_usd_m2  — стоимость реставрации, USD/м²  ▶ НАСТРОЙТЕ
        annual_revenue_usd_m2    — ожидаемая выручка, USD/м²/год  ▶ НАСТРОЙТЕ
        tax_credit_rate          — ставка налогового кредита  ▶ НАСТРОЙТЕ
        grant_rate               — ставка гранта  ▶ НАСТРОЙТЕ

    Возвращает SustainabilityReport со всеми расчётами и Plotly-данными.
    """
    total_area = floor_area_m2 * floors

    # Физика
    dem_impact  = calc_demolition_impact(
        floor_area_m2, floors, perimeter_m, transport_km
    )
    rest_impact = calc_restoration_impact(dem_impact)

    # Финансы
    dem_fin  = calc_demolition_financials(total_area, annual_revenue_usd_m2)
    rest_fin = calc_restoration_financials(
        total_area, restoration_cost_usd_m2, annual_revenue_usd_m2,
        tax_credit_rate, grant_rate,
        demolition_total_cost=dem_fin.total_cost,
    )

    # Ключевые метрики для дашборда / Streamlit st.metric()
    summary = {
        "co2_saved_t":          rest_impact.co2_saved_t,
        "co2_saving_pct":       rest_impact.co2_saving_pct,
        "trees_equivalent":     rest_impact.trees_equivalent,
        "car_km_equivalent":    rest_impact.car_km_equivalent,
        "money_saved_usd":      rest_fin.savings_vs_demolition,
        "money_saved_pct":      rest_fin.savings_pct,
        "roi_advantage_yr":     round(dem_fin.roi_years - rest_fin.roi_years, 1),
        "npv_advantage_usd":    round(rest_fin.npv_10yr - dem_fin.npv_10yr, 0),
        # E_impact formula values (для отображения формулы в отчёте)
        "e_impact_formula": {
            "M_brick_t":     dem_impact.mass_brick_t,
            "K_CO2":         K_CO2_BRICK,
            "M_transport_t": dem_impact.mass_waste_t,
            "K_fuel":        K_FUEL_TRANSPORT,
            "transport_km":  transport_km,
            "E_impact_t":    dem_impact.co2_total_t,
        },
    }

    # Plotly charts
    charts = build_charts(dem_impact, rest_impact, dem_fin, rest_fin)

    return SustainabilityReport(
        building_id          = building_id,
        floor_area_m2        = floor_area_m2,
        floors               = floors,
        total_area_m2        = total_area,
        demolition_impact    = dem_impact,
        restoration_impact   = rest_impact,
        demolition_fin       = dem_fin,
        restoration_fin      = rest_fin,
        summary              = summary,
        charts               = charts,
    )


def calculate_from_profile(profile: dict) -> SustainabilityReport:
    """
    Удобная обёртка: принимает dict BuildingProfile (из БД или API).
    Ожидаемые ключи: building_id, area_m2, floors.
    Отсутствующие — заменяются разумными значениями по умолчанию.
    """
    return calculate(
        building_id   = profile.get("building_id", "BILB_001"),
        floor_area_m2 = float(profile.get("area_m2")   or 500.0),
        floors        = int(  profile.get("floors")     or 4),
    )
