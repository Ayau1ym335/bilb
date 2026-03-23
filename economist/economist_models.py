"""
economist/models.py  —  Result Dataclasses
═══════════════════════════════════════════
Все возвращаемые типы — dataclass с методом to_dict().
Plotly-ready форматы — вложенные dict готовые к go.Figure().
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional


# ══════════════════════════════════════════════════════════════
#  Физические расчёты
# ══════════════════════════════════════════════════════════════

@dataclass
class DemolitionImpact:
    """Экологический удар при сносе и новом строительстве."""
    # Масса материалов (тонны)
    mass_brick_t:        float   # кирпич для нового здания
    mass_concrete_t:     float   # бетон для нового здания
    mass_waste_t:        float   # строительный мусор при сносе

    # CO₂ по компонентам формулы (тонны CO₂)
    co2_brick_t:         float   # M_brick × K_CO2
    co2_concrete_t:      float   # M_concrete × K_CO2
    co2_transport_t:     float   # M_transport × K_fuel
    co2_total_t:         float   # E_impact = сумма

    # Параметры расчёта (для аудита)
    transport_km:        float
    floor_area_m2:       float
    floors:              int
    total_area_m2:       float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RestorationImpact:
    """Экологический профиль реставрации."""
    co2_new_build_t:      float   # CO₂ если бы строили новое
    co2_restoration_t:    float   # CO₂ при реставрации (≈30% от нового)
    co2_saved_t:          float   # сэкономленный CO₂
    co2_saving_pct:       float   # %

    # Эквиваленты
    trees_equivalent:     int     # деревьев × 1 год
    car_km_equivalent:    int     # км пробега автомобиля

    def to_dict(self) -> dict:
        return asdict(self)


# ══════════════════════════════════════════════════════════════
#  Финансовые расчёты
# ══════════════════════════════════════════════════════════════

@dataclass
class DemolitionFinancials:
    """Финансы пути «снос + новое строительство»."""
    demolition_cost:      float
    new_build_cost:       float
    total_cost:           float
    annual_revenue:       float
    roi_years:            float
    npv_10yr:             float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RestorationFinancials:
    """Финансы пути «реставрация»."""
    gross_cost:           float
    tax_credit:           float
    grant:                float
    net_cost:             float           # после вычета льгот
    annual_revenue:       float           # с heritage premium
    roi_years:            float
    npv_10yr:             float
    savings_vs_demolition: float
    savings_pct:          float

    def to_dict(self) -> dict:
        return asdict(self)


# ══════════════════════════════════════════════════════════════
#  Сводный отчёт
# ══════════════════════════════════════════════════════════════

@dataclass
class SustainabilityReport:
    """
    Полный отчёт Движка 3.
    Сохраняется в BuildingProfile.sustainability_json.
    """
    # Входные параметры
    building_id:    str
    floor_area_m2:  float
    floors:         int
    total_area_m2:  float

    # Физика
    demolition_impact:   DemolitionImpact
    restoration_impact:  RestorationImpact

    # Финансы
    demolition_fin:      DemolitionFinancials
    restoration_fin:     RestorationFinancials

    # Ключевые метрики для дашборда
    summary: dict = field(default_factory=dict)

    # Plotly-ready данные для фронтенда
    charts:  dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "building_id":         self.building_id,
            "floor_area_m2":       self.floor_area_m2,
            "floors":              self.floors,
            "total_area_m2":       self.total_area_m2,
            "demolition_impact":   self.demolition_impact.to_dict(),
            "restoration_impact":  self.restoration_impact.to_dict(),
            "demolition_fin":      self.demolition_fin.to_dict(),
            "restoration_fin":     self.restoration_fin.to_dict(),
            "summary":             self.summary,
            "charts":              self.charts,
        }
