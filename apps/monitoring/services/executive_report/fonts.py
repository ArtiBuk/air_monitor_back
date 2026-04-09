from functools import lru_cache
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


@lru_cache(maxsize=1)
def register_report_font() -> tuple[str, str]:
    font_dir = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"
    regular_candidates = [
        font_dir / "Arial.ttf",
        font_dir / "ArialUnicode.ttf",
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
    ]
    bold_candidates = [
        font_dir / "ArialBold.ttf",
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
    ]

    regular_path = next((candidate for candidate in regular_candidates if candidate.exists()), None)
    if regular_path is None:
        return "Helvetica", "Helvetica-Bold"

    bold_path = next((candidate for candidate in bold_candidates if candidate.exists()), None) or regular_path

    regular_name = "AirReportUnicode"
    bold_name = "AirReportUnicodeBold"
    if regular_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
    if bold_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
    pdfmetrics.registerFontFamily(
        "AirReportFamily",
        normal=regular_name,
        bold=bold_name,
        italic=regular_name,
        boldItalic=bold_name,
    )
    return regular_name, bold_name
