from .builder import build_monitoring_executive_report
from .pdf import render_monitoring_executive_report_pdf

__all__ = [
    "build_monitoring_executive_report",
    "build_monitoring_executive_report_pdf",
    "render_monitoring_executive_report_pdf",
]


def build_monitoring_executive_report_pdf() -> bytes:
    return render_monitoring_executive_report_pdf(build_monitoring_executive_report())
