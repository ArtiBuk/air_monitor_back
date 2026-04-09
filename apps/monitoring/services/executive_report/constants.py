from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

PDF_ACCENT = colors.HexColor("#0F766E")
PDF_ACCENT_SOFT = colors.HexColor("#D7F2EF")
PDF_WARM = colors.HexColor("#F59E0B")
PDF_DANGER = colors.HexColor("#DC2626")
PDF_DEEP = colors.HexColor("#0B1F2A")
PDF_SKY = colors.HexColor("#DCECF7")
PDF_SUCCESS = colors.HexColor("#E7F6EE")
PDF_TEXT = colors.HexColor("#12212A")
PDF_MUTED = colors.HexColor("#54636D")
PDF_BORDER = colors.HexColor("#D9E1E7")
PDF_PANEL = colors.HexColor("#F6F9FB")
CONTENT_WIDTH = A4[0] - 32 * mm
CONTENT_INSET = 10 * mm
INNER_CONTENT_WIDTH = CONTENT_WIDTH - CONTENT_INSET * 2

METRIC_LABELS = {
    "mycityair_aqi_mean": "Индекс качества воздуха AQI",
    "mycityair_aqi_max": "Максимальный индекс AQI",
    "mycityair_aqi_min": "Минимальный индекс AQI",
    "aqi": "Индекс качества воздуха AQI",
    "plume_index": "Сводный индекс загрязнения",
    "pm25": "Мелкие частицы PM2.5",
    "plume_pm25": "Мелкие частицы PM2.5",
    "pm10": "Взвешенные частицы PM10",
    "plume_pm10": "Взвешенные частицы PM10",
    "no2": "Диоксид азота",
    "plume_no2": "Диоксид азота",
    "so2": "Диоксид серы",
    "plume_so2": "Диоксид серы",
    "o3": "Озон",
    "plume_o3": "Озон",
    "co": "Монооксид углерода",
    "plume_co": "Монооксид углерода",
}

SOURCE_LABELS = {
    "mycityair": "Посты MyCityAir",
    "plumelabs": "Городской фон Plume Labs",
}

STATUS_LABELS = {
    "completed": "завершён",
    "success": "успешно выполнен",
    "failed": "завершился с ошибкой",
    "pending": "ожидает выполнения",
    "started": "выполняется",
    "active": "активна",
    "ready": "готова к использованию",
}
