from io import BytesIO

from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .constants import (
    CONTENT_INSET,
    CONTENT_WIDTH,
    INNER_CONTENT_WIDTH,
    PDF_ACCENT,
    PDF_ACCENT_SOFT,
    PDF_BORDER,
    PDF_DEEP,
    PDF_MUTED,
    PDF_PANEL,
    PDF_SKY,
    PDF_SUCCESS,
    PDF_TEXT,
    PDF_WARM,
)
from .fonts import register_report_font
from .formatters import (
    format_datetime,
    format_int,
    format_metric_list,
    format_number,
    format_status,
)


def _build_styles(font_name: str, bold_font_name: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "eyebrow": ParagraphStyle("AirEyebrow", parent=base["BodyText"], fontName=bold_font_name, fontSize=8.5, leading=11, textColor=PDF_ACCENT),
        "title": ParagraphStyle("AirTitle", parent=base["Title"], fontName=bold_font_name, fontSize=21, leading=25, textColor=PDF_TEXT, spaceAfter=4, alignment=TA_LEFT),
        "subtitle": ParagraphStyle("AirSubtitle", parent=base["BodyText"], fontName=font_name, fontSize=9.6, leading=13.4, textColor=PDF_MUTED),
        "section": ParagraphStyle("AirSection", parent=base["Heading2"], fontName=bold_font_name, fontSize=12.5, leading=16, textColor=PDF_TEXT, spaceAfter=6),
        "section_badge": ParagraphStyle("AirSectionBadge", parent=base["BodyText"], fontName=bold_font_name, fontSize=8.1, leading=10, textColor=PDF_ACCENT, alignment=TA_CENTER),
        "body": ParagraphStyle("AirBody", parent=base["BodyText"], fontName=font_name, fontSize=9.5, leading=13, textColor=PDF_TEXT, alignment=TA_LEFT, wordWrap="CJK"),
        "muted": ParagraphStyle("AirMuted", parent=base["BodyText"], fontName=font_name, fontSize=8.4, leading=11.5, textColor=PDF_MUTED, alignment=TA_LEFT, wordWrap="CJK"),
        "card_value": ParagraphStyle("AirCardValue", parent=base["BodyText"], fontName=bold_font_name, fontSize=16, leading=19, textColor=PDF_TEXT),
        "card_label": ParagraphStyle("AirCardLabel", parent=base["BodyText"], fontName=font_name, fontSize=8, leading=10, textColor=PDF_MUTED),
        "label": ParagraphStyle("AirLabel", parent=base["BodyText"], fontName=bold_font_name, fontSize=9.5, leading=13, textColor=PDF_TEXT, alignment=TA_LEFT, wordWrap="CJK"),
        "table_head": ParagraphStyle("AirTableHead", parent=base["BodyText"], fontName=bold_font_name, fontSize=8.3, leading=10.5, textColor=PDF_TEXT, alignment=TA_LEFT, wordWrap="CJK"),
        "table_cell": ParagraphStyle("AirTableCell", parent=base["BodyText"], fontName=font_name, fontSize=8.2, leading=10.4, textColor=PDF_TEXT, alignment=TA_LEFT, wordWrap="CJK"),
        "callout_title": ParagraphStyle("AirCalloutTitle", parent=base["BodyText"], fontName=bold_font_name, fontSize=10.5, leading=13, textColor=PDF_TEXT),
    }


def _logo_flowable(font_name: str) -> Drawing:
    drawing = Drawing(150, 36)
    drawing.add(Rect(0, 7, 22, 22, rx=5, ry=5, fillColor=PDF_ACCENT, strokeColor=PDF_ACCENT))
    drawing.add(Circle(11, 18, 5, fillColor="white", strokeColor="white"))
    drawing.add(Rect(30, 18, 54, 5, fillColor=PDF_TEXT, strokeColor=PDF_TEXT))
    drawing.add(Rect(30, 9, 41, 5, fillColor=PDF_WARM, strokeColor=PDF_WARM))
    drawing.add(String(92, 14, "AIR NPR", fontName=font_name, fontSize=12, fillColor=PDF_TEXT))
    return drawing


def _hero_block(report: dict, styles: dict[str, ParagraphStyle]) -> Table:
    body = [
        [Paragraph("Итог исследовательской работы", styles["eyebrow"])],
        [Paragraph(report["title"], styles["title"])],
        [Paragraph(report["subtitle"], styles["subtitle"])],
        [Paragraph(report["study_context"], styles["body"])],
        [
            Paragraph(
                "Документ отражает полный контур системы: от сбора наблюдений и подготовки датасетов "
                "до прогноза качества воздуха, проверки результата и визуализации итогов на карте НПР.",
                styles["body"],
            )
        ],
        [Paragraph(f"Сформировано автоматически: {report['generated_at_label']}", styles["muted"])],
    ]
    return Table(
        body,
        colWidths=[CONTENT_WIDTH],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PDF_PANEL),
                ("BOX", (0, 0), (-1, -1), 0.7, PDF_BORDER),
                ("LINEBEFORE", (0, 0), (0, -1), 6, PDF_ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), CONTENT_INSET),
                ("RIGHTPADDING", (0, 0), (-1, -1), CONTENT_INSET),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        ),
    )


def _section_header(index: int, title: str, styles: dict[str, ParagraphStyle]) -> Table:
    return Table(
        [[Paragraph(f"{index:02d}", styles["section_badge"]), Paragraph(title, styles["section"])]],
        colWidths=[14 * mm, CONTENT_WIDTH - 14 * mm],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), PDF_ACCENT_SOFT),
                ("BOX", (0, 0), (0, 0), 0.6, PDF_ACCENT_SOFT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        ),
    )


def _research_flow(font_name: str) -> Drawing:
    drawing = Drawing(INNER_CONTENT_WIDTH, 28 * mm)
    steps = [
        ("Наблюдения", PDF_SKY),
        ("Датасет", PDF_ACCENT_SOFT),
        ("Модель", PDF_SUCCESS),
        ("Прогноз", PDF_ACCENT_SOFT),
        ("Проверка", PDF_SKY),
        ("Карта и отчёт", PDF_SUCCESS),
    ]
    box_w = 24 * mm
    box_h = 11 * mm
    gap = 4 * mm
    x = 0
    y = 10 * mm
    for index, (label, color) in enumerate(steps):
        drawing.add(Rect(x, y, box_w, box_h, rx=4, ry=4, fillColor=color, strokeColor=PDF_BORDER))
        drawing.add(String(x + box_w / 2, y + 4.2 * mm, label, fontName=font_name, fontSize=7.2, textAnchor="middle", fillColor=PDF_DEEP))
        if index < len(steps) - 1:
            arrow_x = x + box_w
            drawing.add(Line(arrow_x + 1.5 * mm, y + box_h / 2, arrow_x + gap - 1.5 * mm, y + box_h / 2, strokeColor=PDF_ACCENT, strokeWidth=1.4))
            drawing.add(Line(arrow_x + gap - 4, y + box_h / 2 + 2, arrow_x + gap - 1.5, y + box_h / 2, strokeColor=PDF_ACCENT, strokeWidth=1.4))
            drawing.add(Line(arrow_x + gap - 4, y + box_h / 2 - 2, arrow_x + gap - 1.5, y + box_h / 2, strokeColor=PDF_ACCENT, strokeWidth=1.4))
        x += box_w + gap
    return drawing


def _insight_panel(title: str, text: str, styles: dict[str, ParagraphStyle], background=PDF_PANEL) -> Table:
    return Table(
        [[Paragraph(title, styles["callout_title"])], [Paragraph(text, styles["body"])]],
        colWidths=[CONTENT_WIDTH],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.7, PDF_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), CONTENT_INSET),
                ("RIGHTPADDING", (0, 0), (-1, -1), CONTENT_INSET),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        ),
    )


def _bullet_panel(title: str, items: list[str], styles: dict[str, ParagraphStyle], background=PDF_PANEL) -> Table:
    rows: list[list[object]] = [[Paragraph(title, styles["callout_title"])]]
    for item in items:
        rows.append([Paragraph(f"• {item}", styles["body"])])
    return Table(
        rows,
        colWidths=[CONTENT_WIDTH],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.7, PDF_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), CONTENT_INSET),
                ("RIGHTPADDING", (0, 0), (-1, -1), CONTENT_INSET),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        ),
    )


def _inset_flowable(flowable) -> Table:
    return Table(
        [[flowable]],
        colWidths=[CONTENT_WIDTH],
        style=TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), CONTENT_INSET),
                ("RIGHTPADDING", (0, 0), (-1, -1), CONTENT_INSET),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )


def _summary_cards(report: dict, styles: dict[str, ParagraphStyle]) -> Table:
    card_width = INNER_CONTENT_WIDTH / 3 - 4
    cards = [
        ("Наблюдения", format_int(report["counts"]["observations"]), "всего записей"),
        ("Источники", format_int(report["observations"]["source_count"]), "каналы данных"),
        ("Датасеты", format_int(report["counts"]["datasets"]), "собранные срезы"),
        ("Модели", format_int(report["counts"]["models"]), "версии прогноза"),
        ("Прогнозы", format_int(report["counts"]["forecasts"]), "успешные и архивные"),
        ("Эксперименты", format_int(report["counts"]["experiments"]), "запуски серии"),
    ]
    rows = []
    row = []
    for index, (label, value, helper) in enumerate(cards, start=1):
        row.append(
            Table(
                [[Paragraph(label, styles["card_label"])], [Paragraph(value, styles["card_value"])], [Paragraph(helper, styles["muted"])]],
                colWidths=[card_width],
                style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), PDF_PANEL), ("BOX", (0, 0), (-1, -1), 0.7, PDF_BORDER), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]),
            )
        )
        if index % 3 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    grid = Table(
        rows,
        colWidths=[INNER_CONTENT_WIDTH / 3, INNER_CONTENT_WIDTH / 3, INNER_CONTENT_WIDTH / 3],
        hAlign="LEFT",
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]),
    )
    return Table(
        [[grid]],
        colWidths=[CONTENT_WIDTH],
        style=TableStyle([("LEFTPADDING", (0, 0), (-1, -1), CONTENT_INSET), ("RIGHTPADDING", (0, 0), (-1, -1), CONTENT_INSET), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]),
    )


def _simple_detail_table(rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle], col_widths=(46 * mm, INNER_CONTENT_WIDTH - 46 * mm)) -> Table:
    table_rows = [[Paragraph(label, styles["label"]), Paragraph(value, styles["body"])] for label, value in rows]
    table = Table(
        table_rows,
        colWidths=list(col_widths),
        hAlign="LEFT",
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), "white"),
                ("BOX", (0, 0), (-1, -1), 0.7, PDF_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, PDF_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        ),
    )
    return Table(
        [[table]],
        colWidths=[CONTENT_WIDTH],
        style=TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), CONTENT_INSET),
                ("RIGHTPADDING", (0, 0), (-1, -1), CONTENT_INSET),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )


def _source_chart(report: dict, font_name: str) -> Drawing:
    drawing = Drawing(INNER_CONTENT_WIDTH, 42 * mm)
    sources = report["observations"]["sources"][:4]
    if not sources:
        drawing.add(String(0, 10, "Нет данных для диаграммы.", fontName=font_name, fontSize=9, fillColor=PDF_MUTED))
        return drawing
    chart_x = 0
    chart_y = 8
    chart_w = INNER_CONTENT_WIDTH - 12 * mm
    chart_h = 24 * mm
    max_value = max(item["observation_count"] for item in sources) or 1
    bar_gap = 10
    bar_w = max(28, (chart_w - bar_gap * (len(sources) - 1)) / len(sources))
    drawing.add(Rect(chart_x, chart_y, chart_w, chart_h, strokeColor=PDF_BORDER, fillColor="white"))
    for idx, source in enumerate(sources):
        bar_height = chart_h * (source["observation_count"] / max_value)
        x = chart_x + idx * (bar_w + bar_gap) + 4
        drawing.add(Rect(x, chart_y, bar_w, bar_height, fillColor=PDF_ACCENT, strokeColor=PDF_ACCENT))
        drawing.add(String(x + bar_w / 2, chart_y + bar_height + 4, format_int(source["observation_count"]), fontName=font_name, fontSize=7.5, textAnchor="middle", fillColor=PDF_TEXT))
        drawing.add(String(x + bar_w / 2, chart_y - 8, source["label"], fontName=font_name, fontSize=7, textAnchor="middle", fillColor=PDF_MUTED))
    return drawing


def _aqi_forecast_chart(report: dict, font_name: str) -> Drawing:
    drawing = Drawing(INNER_CONTENT_WIDTH, 48 * mm)
    series = (report.get("latest_forecast") or {}).get("aqi_series") or []
    if len(series) < 2:
        drawing.add(String(0, 10, "Для прогноза AQI пока недостаточно точек.", fontName=font_name, fontSize=9, fillColor=PDF_MUTED))
        return drawing
    chart_x = 0
    chart_y = 10
    chart_w = INNER_CONTENT_WIDTH - 14 * mm
    chart_h = 28 * mm
    values = [item["value"] for item in series]
    min_value = min(values)
    max_value = max(values)
    spread = max(max_value - min_value, 1)
    drawing.add(Rect(chart_x, chart_y, chart_w, chart_h, strokeColor=PDF_BORDER, fillColor="white"))
    points = []
    for idx, item in enumerate(series):
        x = chart_x + (chart_w * idx / max(len(series) - 1, 1))
        y = chart_y + ((item["value"] - min_value) / spread) * chart_h
        points.append((x, y))
    for idx in range(1, len(points)):
        x1, y1 = points[idx - 1]
        x2, y2 = points[idx]
        drawing.add(Line(x1, y1, x2, y2, strokeColor=PDF_WARM, strokeWidth=2))
    step = max(1, len(series) // 5)
    for idx, (x, y) in enumerate(points):
        drawing.add(Circle(x, y, 1.8, fillColor=PDF_WARM, strokeColor=PDF_WARM))
        if idx % step == 0 or idx == len(points) - 1:
            label = series[idx]["label"][11:16] if len(series[idx]["label"]) >= 16 else series[idx]["label"]
            drawing.add(String(x, chart_y - 8, label, fontName=font_name, fontSize=6.8, textAnchor="middle", fillColor=PDF_MUTED))
    drawing.add(String(chart_x + chart_w + 6, chart_y + chart_h - 2, format_number(max_value), fontName=font_name, fontSize=7, fillColor=PDF_MUTED))
    drawing.add(String(chart_x + chart_w + 6, chart_y - 2, format_number(min_value), fontName=font_name, fontSize=7, fillColor=PDF_MUTED))
    return drawing


def _build_source_observation_table(report: dict, styles: dict[str, ParagraphStyle]) -> Table:
    rows = [[Paragraph("Источник", styles["table_head"]), Paragraph("Наблюдения", styles["table_head"]), Paragraph("Станции", styles["table_head"]), Paragraph("Метрики", styles["table_head"]), Paragraph("Последняя точка", styles["table_head"])]]
    for source in report["observations"]["sources"]:
        rows.append([Paragraph(source["label"], styles["table_cell"]), Paragraph(format_int(source["observation_count"]), styles["table_cell"]), Paragraph(format_int(source["station_count"]), styles["table_cell"]), Paragraph(format_metric_list(source["metrics"], limit=3), styles["table_cell"]), Paragraph(format_datetime(source["latest_timestamp"]), styles["table_cell"])])
    table = Table(
        rows,
        colWidths=[28 * mm, 20 * mm, 16 * mm, 62 * mm, INNER_CONTENT_WIDTH - 126 * mm],
        hAlign="LEFT",
        style=TableStyle([("BACKGROUND", (0, 0), (-1, 0), PDF_ACCENT_SOFT), ("BOX", (0, 0), (-1, -1), 0.7, PDF_BORDER), ("INNERGRID", (0, 0), (-1, -1), 0.5, PDF_BORDER), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("VALIGN", (0, 0), (-1, -1), "TOP")]),
    )
    return Table(
        [[table]],
        colWidths=[CONTENT_WIDTH],
        style=TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), CONTENT_INSET),
                ("RIGHTPADDING", (0, 0), (-1, -1), CONTENT_INSET),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )


def render_monitoring_executive_report_pdf(report: dict) -> bytes:
    font_name, bold_font_name = register_report_font()
    styles = _build_styles(font_name, bold_font_name)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=14 * mm, title=report["title"], author="Air Monitor Back")
    story = [
        _logo_flowable(bold_font_name),
        Spacer(1, 8),
        _hero_block(report, styles),
        Spacer(1, 8),
        _inset_flowable(_research_flow(font_name)),
        Spacer(1, 8),
        _insight_panel(
            "Смысл отчёта",
            "Этот отчёт показывает не только текущее состояние наблюдений, но и весь исследовательский цикл: "
            "как из сырых измерений формируются датасеты, как обучаются модели, как строится городской прогноз "
            "и как итог визуализируется на карте загрязнения Норильского промышленного района.",
            styles,
            background=PDF_SKY,
        ),
        Spacer(1, 8),
        _bullet_panel("Практическая ценность", report["practical_value"], styles, background=PDF_SUCCESS),
        Spacer(1, 8),
        _summary_cards(report, styles),
        Spacer(1, 10),
        HRFlowable(color=PDF_BORDER, thickness=0.8, width="100%"),
        Spacer(1, 8),
        _section_header(1, "Что показывает система сейчас", styles),
        Spacer(1, 4),
        Paragraph(
            f"На момент формирования отчёта в приложении накоплено {format_int(report['observations']['total_count'])} наблюдений. "
            f"Данные поступают из {format_int(report['observations']['source_count'])} источников и покрывают период "
            f"с {report['observations']['first_label']} по {report['observations']['latest_label']}. "
            "Это позволяет одновременно видеть ситуацию по отдельным постам MyCityAir и по городскому фону загрязнения.",
            styles["body"],
        ),
        Spacer(1, 6),
        _section_header(2, "Источники наблюдений", styles),
        Spacer(1, 4),
        Paragraph("Ниже показано, какой вклад в систему вносит каждый источник данных. Чем больше наблюдений и станций, тем устойчивее последующие датасеты и прогнозы.", styles["body"]),
        Spacer(1, 4),
        _inset_flowable(_source_chart(report, font_name)),
        Spacer(1, 6),
        _simple_detail_table(
            [
                ("Период данных", f"{report['observations']['first_label']} — {report['observations']['latest_label']}"),
                ("Количество станций", format_int(report["observations"]["station_count"])),
                ("Источники", ", ".join(item["label"] for item in report["observations"]["sources"]) or "—"),
            ],
            styles,
        ),
        Spacer(1, 6),
        _build_source_observation_table(report, styles),
        Spacer(1, 10),
        _section_header(3, "Из чего обучалась модель", styles),
        Spacer(1, 4),
    ]

    dataset = report["latest_dataset"]
    if dataset:
        story.extend([
            Paragraph("Последняя обучающая выборка собрана из реальных наблюдений и временных признаков. Она нужна для того, чтобы модель улавливала суточные и краткосрочные колебания загрязнения.", styles["body"]),
            Spacer(1, 4),
            _simple_detail_table(
                [
                    ("Когда собран датасет", format_datetime(dataset["created_at"])),
                    ("Размер обучающей выборки", f"{format_int(dataset['sample_count'])} временных фрагментов"),
                    ("Общий объём исходных строк", format_int(dataset["master_row_count"])),
                    ("Окно входных данных", f"{dataset['input_len_hours']} часов истории на один прогноз"),
                    ("Горизонт прогноза", f"{dataset['forecast_horizon_hours']} часов вперёд"),
                    ("Основные прогнозируемые показатели", dataset["target_preview_label"]),
                ],
                styles,
            ),
            Spacer(1, 5),
            _insight_panel(
                "Почему это важно",
                "Качество датасета напрямую определяет качество прогноза: именно здесь фиксируются горизонт прогнозирования, "
                "набор целевых показателей и полнота временного ряда, на котором дальше обучается модель.",
                styles,
                background=PDF_SUCCESS,
            ),
        ])
    else:
        story.append(Paragraph("Датасеты ещё не собраны.", styles["body"]))

    active_model = report["active_model"]
    story.append(Spacer(1, 6))
    if active_model:
        story.extend([
            Paragraph("Ниже указана текущая рабочая модель. Именно её backend использует для формирования последних прогнозов по городу.", styles["body"]),
            Spacer(1, 4),
            _simple_detail_table(
                [
                    ("Название модели", active_model["name"]),
                    ("На чём обучалась", f"выборка на {format_int(active_model['dataset_sample_count'])} фрагментов"),
                    ("Какие показатели прогнозирует", active_model["target_preview_label"]),
                    ("Основная ошибка модели", f"RMSE {active_model['avg_overall_rmse_label']}"),
                    ("Средняя абсолютная ошибка", f"MAE {active_model['avg_overall_mae_label']}"),
                    ("Средняя относительная ошибка", f"MAPE {active_model['avg_macro_mape_label']}%"),
                    ("Откуда взята оценка качества", active_model["metric_source_label"]),
                ],
                styles,
            ),
            Spacer(1, 4),
            Paragraph("Пояснение к метрикам: RMSE показывает типичный масштаб ошибки с усилением крупных промахов; MAE показывает среднюю абсолютную ошибку; MAPE отражает среднюю относительную ошибку в процентах.", styles["muted"]),
        ])
    else:
        story.append(Paragraph("Готовая активная модель пока отсутствует.", styles["body"]))

    story.extend([Spacer(1, 10), _section_header(4, "Последний прогноз по городу", styles), Spacer(1, 4)])
    latest_forecast = report["latest_forecast"]
    if latest_forecast:
        story.extend([
            Paragraph("График ниже показывает, как меняется прогнозный индекс качества воздуха AQI на горизонте последнего запуска модели.", styles["body"]),
            Spacer(1, 4),
            _inset_flowable(_aqi_forecast_chart(report, font_name)),
            Spacer(1, 6),
            _simple_detail_table(
                [
                    ("Когда построен прогноз", format_datetime(latest_forecast["created_at"])),
                    ("На сколько часов вперёд", f"{latest_forecast['forecast_horizon_hours']} часов"),
                    ("Использованная модель", latest_forecast["model_name"] or "—"),
                    ("Изменение прогнозного AQI", f"{latest_forecast['aqi_start_label']} → {latest_forecast['aqi_end_label']} (изменение {latest_forecast['aqi_delta_label']})"),
                    ("Количество временных точек", format_int(latest_forecast["record_count"])),
                    ("Какие показатели считает прогноз", latest_forecast["target_metrics_label"]),
                ],
                styles,
            ),
            Spacer(1, 5),
            _insight_panel(
                "Связь с картой воздуха",
                "Именно этот расчётный слой затем попадает в пользовательский интерфейс: карта получает городской прогнозный фон, "
                "а пользователь видит итог исследования в форме понятного пространственного сценария.",
                styles,
                background=PDF_SKY,
            ),
            Spacer(1, 5),
            _insight_panel(
                "Интерпретация прогноза",
                report["forecast_interpretation"],
                styles,
                background=PDF_PANEL,
            ),
        ])
    else:
        story.append(Paragraph("Успешный прогноз пока отсутствует.", styles["body"]))

    latest_evaluation = report["latest_evaluation"]
    story.extend([Spacer(1, 10), _section_header(5, "Насколько прогнозу можно доверять", styles), Spacer(1, 4)])
    if latest_evaluation:
        story.extend([
            Paragraph("После того как появляются фактические наблюдения, система сравнивает их с прогнозом. Это позволяет оценить точность модели на реальных данных, а не только на этапе обучения.", styles["body"]),
            Spacer(1, 4),
            _simple_detail_table(
                [
                    ("Статус проверки", format_status(latest_evaluation["status"])),
                    ("Ошибка с усилением крупных отклонений", f"RMSE {latest_evaluation['overall_rmse_label']}"),
                    ("Средняя абсолютная ошибка", f"MAE {latest_evaluation['overall_mae_label']}"),
                    ("Средняя относительная ошибка", f"MAPE {latest_evaluation['macro_mape_label']}%"),
                    ("Покрытие проверкой", f"{latest_evaluation['coverage_ratio_label']}% ({latest_evaluation['matched_record_count']}/{latest_evaluation['expected_record_count']})"),
                    ("Когда выполнена проверка", format_datetime(latest_evaluation["evaluated_at_utc"])),
                ],
                styles,
            ),
        ])
    else:
        story.append(Paragraph("Оценка прогнозов ещё не проводилась.", styles["body"]))

    story.extend([Spacer(1, 10), _section_header(6, "Как развивался исследовательский контур", styles), Spacer(1, 4)])
    best_series = report["best_series"]
    latest_run = report["latest_experiment_run"]
    experiment_rows = []
    if best_series:
        experiment_rows.extend([
            ("Основная серия экспериментов", best_series["name"]),
            ("Количество запусков в серии", format_int(best_series["run_count"])),
            ("Лучшая ошибка на исторической проверке", best_series["best_backtest_overall_rmse_label"]),
        ])
    if latest_run:
        experiment_rows.extend([
            ("Последний эксперимент", latest_run["name"]),
            ("Текущий статус эксперимента", latest_run["status_label"]),
            ("Связанная модель", latest_run["model_name"] or "—"),
        ])
    if experiment_rows:
        story.extend([
            Paragraph("Этот блок показывает, что исследование не ограничивается одной моделью: система сохраняет серии экспериментов и позволяет сравнивать разные запуски между собой.", styles["body"]),
            Spacer(1, 4),
            _simple_detail_table(experiment_rows, styles),
            Spacer(1, 5),
            _insight_panel(
                "Исследовательский смысл",
                "Сохранение серий и отдельных запусков важно для магистерской работы: оно позволяет не просто показать один удачный результат, "
                "а продемонстрировать воспроизводимый процесс поиска рабочей конфигурации модели.",
                styles,
                background=PDF_SKY,
            ),
        ])
    else:
        story.append(Paragraph("Экспериментальные серии и запуски пока не накоплены.", styles["body"]))

    story.extend([
        Spacer(1, 10),
        _section_header(7, "Итоговые выводы", styles),
        Spacer(1, 4),
        _insight_panel(
            "Главный результат работы",
            "Система уже замыкает полный прикладной контур: реальные наблюдения превращаются в очищенные временные ряды, "
            "на их основе обучается модель, затем строится прогноз, проводится проверка качества и итог отображается на карте "
            "и в этом аналитическом отчёте.",
            styles,
            background=PDF_PANEL,
        ),
        Spacer(1, 6),
        ListFlowable([ListItem(Paragraph(item, styles["body"])) for item in report["conclusions"]], bulletType="bullet", leftPadding=12, bulletFontName=font_name, bulletColor=PDF_ACCENT),
        Spacer(1, 8),
        Paragraph("Отчёт сформирован автоматически backend-сервисом проекта Air Monitor и оформлен как краткая финальная сводка по исследовательскому контуру, а не как технический дамп внутренних данных.", styles["muted"]),
    ])

    def draw_page(canvas, document):
        canvas.saveState()
        canvas.setFillColor(PDF_ACCENT)
        canvas.rect(0, A4[1] - 8, A4[0], 8, fill=1, stroke=0)
        canvas.setFillColor(PDF_MUTED)
        canvas.setFont(font_name, 8)
        canvas.drawRightString(A4[0] - 16 * mm, 8 * mm, f"Страница {document.page}")
        canvas.drawString(16 * mm, 8 * mm, f"НПР Air Monitor · {report['report_date_label']}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return buffer.getvalue()
