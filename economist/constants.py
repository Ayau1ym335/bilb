"""
economist/constants.py  —  Physical & Financial Constants
══════════════════════════════════════════════════════════
Единственный источник правды для всех коэффициентов.

▶ НАСТРОЙТЕ: значения помечены # ▶
  Все можно переопределить через .env — см. os.getenv() ниже.
  Источники указаны в комментариях для аудита инвесторами.
"""

from __future__ import annotations
import os

# ══════════════════════════════════════════════════════════════
#  I. КОЭФФИЦИЕНТЫ CO₂ (Embodied Carbon)
#  Источник: ECOTECT / ICE Database v3.0 (2019)
# ══════════════════════════════════════════════════════════════

# kg CO₂ на кг производимого материала
K_CO2_BRICK      = float(os.getenv("K_CO2_BRICK",      "0.24"))   # ▶ керамический кирпич
K_CO2_CONCRETE   = float(os.getenv("K_CO2_CONCRETE",   "0.18"))   # ▶ монолитный бетон
K_CO2_STEEL      = float(os.getenv("K_CO2_STEEL",      "1.46"))   # ▶ прокат
K_CO2_GLASS      = float(os.getenv("K_CO2_GLASS",      "0.85"))   # ▶ флоат стекло
K_CO2_INSULATION = float(os.getenv("K_CO2_INSULATION", "3.30"))   # ▶ пенополистирол

# kg CO₂ на тонну·км транспортировки (грузовик Euro-VI)
K_FUEL_TRANSPORT = float(os.getenv("K_FUEL_TRANSPORT", "0.062"))  # ▶ ICE DB

# ══════════════════════════════════════════════════════════════
#  II. СТРОИТЕЛЬНЫЕ ПАРАМЕТРЫ
#  ▶ НАСТРОЙТЕ под локальный рынок (Алматы / Казахстан)
# ══════════════════════════════════════════════════════════════

# Плотности материалов, кг/м³
DENSITY_BRICK    = 1800.0   # ▶
DENSITY_CONCRETE = 2400.0   # ▶

# Строительный мусор при сносе, т/м² общей площади
DEMOLITION_WASTE_T_PER_M2 = 1.2   # ▶ EN 12342

# Доля кирпичных стен в объёме здания (от общего объёма)
BRICK_WALL_FRACTION = 0.12   # ▶ типовые советские здания 1950–1980

# Толщина кирпичных стен, м
WALL_THICKNESS_M = float(os.getenv("WALL_THICKNESS_M", "0.51"))   # ▶ 2 кирпича

# Высота этажа, м
FLOOR_HEIGHT_M   = float(os.getenv("FLOOR_HEIGHT_M", "3.2"))       # ▶

# Доля проёмов в стенах (окна + двери)
OPENING_FRACTION = 0.30   # ▶ снижает объём кирпича

# Расстояние транспортировки мусора до полигона, км
DEFAULT_TRANSPORT_KM = float(os.getenv("DEFAULT_TRANSPORT_KM", "50.0"))   # ▶

# CO₂ новой постройки, кг/м² общей площади (all-in embodied)
NEW_BUILD_CO2_KG_M2 = float(os.getenv("NEW_BUILD_CO2_KG_M2", "900.0"))    # ▶ RICS 2023

# CO₂ реставрации, % от нового строительства (только замена повреждённых элементов)
RESTORATION_CO2_FRACTION = float(os.getenv("RESTORATION_CO2_FRACTION", "0.30"))  # ▶

# ══════════════════════════════════════════════════════════════
#  III. ФИНАНСОВЫЕ ПАРАМЕТРЫ (USD)
#  ▶ НАСТРОЙТЕ под реальный рынок
# ══════════════════════════════════════════════════════════════

# Стоимость сноса, USD/м²
DEMOLITION_COST_USD_M2  = float(os.getenv("DEMOLITION_COST_USD_M2",  "120.0"))  # ▶
# Стоимость нового строительства, USD/м²
NEW_BUILD_COST_USD_M2   = float(os.getenv("NEW_BUILD_COST_USD_M2",   "2500.0")) # ▶
# Базовая стоимость реставрации, USD/м²
RESTORATION_BASE_USD_M2 = float(os.getenv("RESTORATION_BASE_USD_M2", "1200.0")) # ▶

# Налоговый кредит на историческую реставрацию (% от затрат)
TAX_CREDIT_RATE  = float(os.getenv("TAX_CREDIT_RATE",  "0.20"))   # ▶ 20% — US HTC; 0 если не применимо

# Гранты на реставрацию (% от затрат, усреднённые)
GRANT_RATE       = float(os.getenv("GRANT_RATE",       "0.10"))   # ▶ 10% по умолчанию

# Базовый доход, USD/м²/год (для ROI)
BASE_REVENUE_USD_M2_YR = float(os.getenv("BASE_REVENUE_USD_M2_YR", "150.0"))  # ▶

# Ставка дисконтирования для NPV
DISCOUNT_RATE    = float(os.getenv("DISCOUNT_RATE",    "0.10"))   # ▶ 10%

# Исторический premium к арендной ставке для heritage зданий
HERITAGE_PREMIUM = float(os.getenv("HERITAGE_PREMIUM", "0.20"))   # ▶ +20%

# ══════════════════════════════════════════════════════════════
#  IV. ЭКВИВАЛЕНТЫ CO₂
#  Источник: EPA / IPCC AR6
# ══════════════════════════════════════════════════════════════

# Поглощение CO₂ одним деревом в год, кг
CO2_PER_TREE_KG_YR   = 22.0    # ▶ среднее зрелое дерево (EPA)

# Выброс CO₂ на 1 км пробега автомобиля, кг
CO2_PER_CAR_KM       = 0.21    # ▶ средний легковой автомобиль

# Выброс CO₂ на 1 кВт·ч электроэнергии (Казахстан, угольная энергетика)
CO2_PER_KWH_KG       = float(os.getenv("CO2_PER_KWH_KG", "0.71"))  # ▶ IEA 2023

# ══════════════════════════════════════════════════════════════
#  V. PLOTLY ЦВЕТА (согласованы с dark-tech UI)
# ══════════════════════════════════════════════════════════════
COLOR_DEMOLITION  = "#E24B4A"   # красный — путь сноса
COLOR_RESTORATION = "#1D9E75"   # зелёный — реставрация
COLOR_NEUTRAL     = "#378ADD"   # синий — нейтральные данные
COLOR_WARNING     = "#EF9F27"   # amber — предупреждения
COLOR_GRID        = "#111820"   # фон сетки Plotly
COLOR_PAPER       = "rgba(0,0,0,0)"  # прозрачный фон
COLOR_TEXT        = "#6a8090"   # цвет текста осей
COLOR_FONT        = "JetBrains Mono, monospace"
