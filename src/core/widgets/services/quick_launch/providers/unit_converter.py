import re

from PyQt6.QtWidgets import QApplication

from core.widgets.services.quick_launch.base_provider import BaseProvider, ProviderResult
from core.widgets.services.quick_launch.providers.resources.icons import ICON_UNIT

# Each category maps unit aliases to (canonical_name, factor_to_base).

_LENGTH = {
    "mm": ("毫米", 0.001),
    "millimeter": ("毫米", 0.001),
    "millimeters": ("毫米", 0.001),
    "cm": ("厘米", 0.01),
    "centimeter": ("厘米", 0.01),
    "centimeters": ("厘米", 0.01),
    "m": ("米", 1.0),
    "meter": ("米", 1.0),
    "meters": ("米", 1.0),
    "km": ("千米", 1000.0),
    "kilometer": ("千米", 1000.0),
    "kilometers": ("千米", 1000.0),
    "in": ("英寸", 0.0254),
    "inch": ("英寸", 0.0254),
    "inches": ("英寸", 0.0254),
    "ft": ("英尺", 0.3048),
    "foot": ("英尺", 0.3048),
    "feet": ("英尺", 0.3048),
    "yd": ("码", 0.9144),
    "yard": ("码", 0.9144),
    "yards": ("码", 0.9144),
    "mi": ("英里", 1609.344),
    "mile": ("英里", 1609.344),
    "miles": ("英里", 1609.344),
    "nmi": ("海里", 1852.0),
}

_WEIGHT = {
    "mg": ("毫克", 0.001),
    "milligram": ("毫克", 0.001),
    "milligrams": ("毫克", 0.001),
    "g": ("克", 1.0),
    "gram": ("克", 1.0),
    "grams": ("克", 1.0),
    "kg": ("千克", 1000.0),
    "kilogram": ("千克", 1000.0),
    "kilograms": ("千克", 1000.0),
    "t": ("公吨", 1_000_000.0),
    "ton": ("公吨", 1_000_000.0),
    "tons": ("公吨", 1_000_000.0),
    "oz": ("盎司", 28.3495),
    "ounce": ("盎司", 28.3495),
    "ounces": ("盎司", 28.3495),
    "lb": ("磅", 453.592),
    "lbs": ("磅", 453.592),
    "pound": ("磅", 453.592),
    "pounds": ("磅", 453.592),
    "st": ("英石", 6350.29),
    "stone": ("英石", 6350.29),
    "stones": ("英石", 6350.29),
}

_VOLUME = {
    "ml": ("毫升", 0.001),
    "milliliter": ("毫升", 0.001),
    "milliliters": ("毫升", 0.001),
    "l": ("升", 1.0),
    "liter": ("升", 1.0),
    "liters": ("升", 1.0),
    "gal": ("加仑（美制）", 3.78541),
    "gallon": ("加仑（美制）", 3.78541),
    "gallons": ("加仑（美制）", 3.78541),
    "qt": ("夸脱（美制）", 0.946353),
    "quart": ("夸脱（美制）", 0.946353),
    "quarts": ("夸脱（美制）", 0.946353),
    "pt": ("品脱（美制）", 0.473176),
    "pint": ("品脱（美制）", 0.473176),
    "pints": ("品脱（美制）", 0.473176),
    "cup": ("杯（美制）", 0.236588),
    "cups": ("杯（美制）", 0.236588),
    "floz": ("液盎司（美制）", 0.0295735),
    "fl oz": ("液盎司（美制）", 0.0295735),
    "tbsp": ("汤匙", 0.0147868),
    "tablespoon": ("汤匙", 0.0147868),
    "tablespoons": ("汤匙", 0.0147868),
    "tsp": ("茶匙", 0.00492892),
    "teaspoon": ("茶匙", 0.00492892),
    "teaspoons": ("茶匙", 0.00492892),
}

_SPEED = {
    "m/s": ("m/s", 1.0),
    "km/h": ("km/h", 1 / 3.6),
    "kmh": ("km/h", 1 / 3.6),
    "kph": ("km/h", 1 / 3.6),
    "mph": ("mph", 0.44704),
    "knot": ("节", 0.514444),
    "knots": ("节", 0.514444),
    "kn": ("节", 0.514444),
    "ft/s": ("ft/s", 0.3048),
}

_DATA = {
    "b": ("字节", 1),
    "byte": ("字节", 1),
    "bytes": ("字节", 1),
    "kb": ("千字节", 1024),
    "kilobyte": ("千字节", 1024),
    "kilobytes": ("千字节", 1024),
    "mb": ("兆字节", 1024**2),
    "megabyte": ("兆字节", 1024**2),
    "megabytes": ("兆字节", 1024**2),
    "gb": ("吉字节", 1024**3),
    "gigabyte": ("吉字节", 1024**3),
    "gigabytes": ("吉字节", 1024**3),
    "tb": ("太字节", 1024**4),
    "terabyte": ("太字节", 1024**4),
    "terabytes": ("太字节", 1024**4),
    "pb": ("拍字节", 1024**5),
    "petabyte": ("拍字节", 1024**5),
    "petabytes": ("拍字节", 1024**5),
}

_TIME = {
    "ms": ("毫秒", 0.001),
    "millisecond": ("毫秒", 0.001),
    "milliseconds": ("毫秒", 0.001),
    "s": ("秒", 1.0),
    "sec": ("秒", 1.0),
    "second": ("秒", 1.0),
    "seconds": ("秒", 1.0),
    "min": ("分钟", 60.0),
    "minute": ("分钟", 60.0),
    "minutes": ("分钟", 60.0),
    "h": ("小时", 3600.0),
    "hr": ("小时", 3600.0),
    "hour": ("小时", 3600.0),
    "hours": ("小时", 3600.0),
    "d": ("天", 86400.0),
    "day": ("天", 86400.0),
    "days": ("天", 86400.0),
    "wk": ("周", 604800.0),
    "week": ("周", 604800.0),
    "weeks": ("周", 604800.0),
    "yr": ("年", 31_557_600.0),
    "year": ("年", 31_557_600.0),
    "years": ("年", 31_557_600.0),
}

_CATEGORIES: list[tuple[str, dict]] = [
    ("长度", _LENGTH),
    ("重量", _WEIGHT),
    ("体积", _VOLUME),
    ("速度", _SPEED),
    ("数据", _DATA),
    ("时间", _TIME),
]

# Temperature needs special handling since it's not a simple factor conversion
_TEMP_UNITS = {"c", "celsius", "f", "fahrenheit", "k", "kelvin"}


def _to_celsius(value: float, unit: str) -> float:
    u = unit.lower()
    if u in ("f", "fahrenheit"):
        return (value - 32) * 5 / 9
    if u in ("k", "kelvin"):
        return value - 273.15
    return value


def _from_celsius(c: float, unit: str) -> float:
    u = unit.lower()
    if u in ("f", "fahrenheit"):
        return c * 9 / 5 + 32
    if u in ("k", "kelvin"):
        return c + 273.15
    return c


_TEMP_LABELS = {
    "c": "摄氏度",
    "celsius": "摄氏度",
    "f": "华氏度",
    "fahrenheit": "华氏度",
    "k": "开尔文",
    "kelvin": "开尔文",
}

# Canonical unit for each temp label (used for "auto" conversions)
_TEMP_OTHERS = {
    "摄氏度": [("华氏度", "f"), ("开尔文", "k")],
    "华氏度": [("摄氏度", "c"), ("开尔文", "k")],
    "开尔文": [("摄氏度", "c"), ("华氏度", "f")],
}

# Pattern: "10 kg to lb" or "10kg lb" or "10 km"
_QUERY_RE = re.compile(
    r"^([\d.,]+)\s*([a-z/\s]+?)(?:\s+(?:to|in|as|->)\s+([a-z/\s]+?))?$",
    re.IGNORECASE,
)


def _find_category(unit: str) -> tuple[str, dict, str, float] | None:
    """Return (category_name, table, canonical_name, factor) or None."""
    u = unit.lower().strip()
    for cat_name, table in _CATEGORIES:
        if u in table:
            name, factor = table[u]
            return cat_name, table, name, factor
    return None


def _format_number(value: float) -> str:
    if value == 0:
        return "0"
    if abs(value) >= 1e12 or (abs(value) < 1e-6 and value != 0):
        return f"{value:.6g}"
    if value == int(value) and abs(value) < 1e15:
        return f"{int(value):,}"
    # Reasonable decimal places
    if abs(value) < 0.01:
        return f"{value:.6f}".rstrip("0").rstrip(".")
    if abs(value) < 1:
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def _get_common_targets(category: str, table: dict, from_canonical: str) -> list[tuple[str, float]]:
    """Return a list of (canonical_name, factor) for common units other than from_canonical."""
    seen = set()
    targets = []
    for name, factor in table.values():
        if name != from_canonical and name not in seen:
            seen.add(name)
            targets.append((name, factor))
    return targets[:6]


class UnitConverterProvider(BaseProvider):
    """Convert between units of measurement."""

    name = "unit_converter"
    display_name = "单位转换器"
    input_placeholder = "转换单位，例如 10 kg 转 lb..."
    icon = ICON_UNIT

    def match(self, text: str) -> bool:
        text = text.strip()
        if self.prefix and text.startswith(self.prefix):
            return True
        return False

    def get_results(self, text: str, **kwargs) -> list[ProviderResult]:
        query = self.get_query_text(text).strip()
        if not query:
            return [
                ProviderResult(
                    title="单位转换器",
                    description="例如 10 kg 转 lb, 100 mi 转 km, 72 f 转 c, 1 gb 转 mb",
                    icon_char=ICON_UNIT,
                    provider=self.name,
                )
            ]

        m = _QUERY_RE.match(query)
        if not m:
            return [
                ProviderResult(
                    title="格式无效",
                    description="试试：10 kg 转 lb, 100 f 转 c, 500 mb 转 gb",
                    icon_char=ICON_UNIT,
                    provider=self.name,
                )
            ]

        value_str, from_unit, to_unit = m.group(1), m.group(2).strip(), (m.group(3) or "").strip()
        try:
            value = float(value_str.replace(",", ""))
        except ValueError:
            return []

        from_lower = from_unit.lower()
        to_lower = to_unit.lower() if to_unit else ""

        # Temperature
        if from_lower in _TEMP_UNITS:
            return self._convert_temperature(value, from_lower, to_lower)

        # Factor-based categories
        info = _find_category(from_lower)
        if not info:
            return [
                ProviderResult(
                    title=f"未知单位：{from_unit}",
                    description="支持：长度、重量、体积、速度、数据、时间、温度",
                    icon_char=ICON_UNIT,
                    provider=self.name,
                )
            ]
        cat_name, table, from_name, from_factor = info

        if to_lower:
            to_info = _find_category(to_lower)
            if not to_info or to_info[0] != cat_name:
                return [
                    ProviderResult(
                        title=f"无法将 {from_name} 转换为 {to_unit}",
                        description=f"两个单位必须属于同一类别（{cat_name}）",
                        icon_char=ICON_UNIT,
                        provider=self.name,
                    )
                ]
            _, _, to_name, to_factor = to_info
            converted = value * from_factor / to_factor
            display = _format_number(converted)
            return [
                ProviderResult(
                    title=f"{display} {to_name}",
                    description=f"{_format_number(value)} {from_name} - 按 Enter 复制",
                    icon_char=ICON_UNIT,
                    provider=self.name,
                    action_data={"value": display},
                )
            ]

        # No target unit - show conversions to common units in the same category
        targets = _get_common_targets(cat_name, table, from_name)
        results = []
        for to_name, to_factor in targets:
            converted = value * from_factor / to_factor
            display = _format_number(converted)
            results.append(
                ProviderResult(
                    title=f"{display} {to_name}",
                    description=f"{_format_number(value)} {from_name} - 按 Enter 复制",
                    icon_char=ICON_UNIT,
                    provider=self.name,
                    action_data={"value": display},
                )
            )
        return results

    def _convert_temperature(self, value: float, from_lower: str, to_lower: str) -> list[ProviderResult]:
        from_label = _TEMP_LABELS[from_lower]
        celsius = _to_celsius(value, from_lower)

        if to_lower and to_lower in _TEMP_UNITS:
            to_label = _TEMP_LABELS[to_lower]
            converted = _from_celsius(celsius, to_lower)
            display = _format_number(converted)
            return [
                ProviderResult(
                    title=f"{display} {to_label}",
                    description=f"{_format_number(value)} {from_label} - 按 Enter 复制",
                    icon_char=ICON_UNIT,
                    provider=self.name,
                    action_data={"value": display},
                )
            ]

        # No target - show all other temperature units
        results = []
        for to_label, to_key in _TEMP_OTHERS[from_label]:
            converted = _from_celsius(celsius, to_key)
            display = _format_number(converted)
            results.append(
                ProviderResult(
                    title=f"{display} {to_label}",
                    description=f"{_format_number(value)} {from_label} - 按 Enter 复制",
                    icon_char=ICON_UNIT,
                    provider=self.name,
                    action_data={"value": display},
                )
            )
        return results

    def execute(self, result: ProviderResult) -> bool:
        value = result.action_data.get("value", "")
        if value:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(value)
        return True
