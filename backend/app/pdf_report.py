"""
Renders the Reports page (see routers/reports.py) as a downloadable PDF.

Pure-Python via reportlab -- no wkhtmltopdf/weasyprint system dependency,
which matters on Render's free tier where we can't apt-install anything.
The layout deliberately mirrors the in-app page section-for-section (overview,
ongoing, not touched, done, by employee, by label) so a printed snapshot and
the live view never disagree about what's being shown.
"""
from datetime import datetime, date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

from . import models

STATUS_LABELS = {
    "backlog": "Backlog",
    "todo": "To Do",
    "in_progress": "In Progress",
    "code_review": "Code Review",
    "done": "Done",
}


def _status_label(status) -> str:
    value = status.value if hasattr(status, "value") else str(status)
    return STATUS_LABELS.get(value, value)


def _name(user) -> str:
    return user.full_name if user else "Unassigned"


def _fmt_date(dt) -> str:
    if dt is None:
        return "—"
    if isinstance(dt, (datetime, date)):
        return dt.strftime("%b %d, %Y")
    return str(dt)


def _filters_summary(filters: dict, stale_days: int) -> str:
    parts = []
    if filters.get("date_from"):
        parts.append(f"from {filters['date_from']}")
    if filters.get("date_to"):
        parts.append(f"to {filters['date_to']}")
    if filters.get("product"):
        parts.append(f"product {filters['product']}")
    parts.append(f"stale threshold {stale_days}+ days")
    return "Filters: " + ", ".join(parts) if len(parts) > 1 else f"Stale threshold: {stale_days}+ days"


def build_report_pdf(
    *,
    organization_name: str,
    overview: dict,
    ongoing_tickets: list,
    done_tickets: list,
    stale_rows: list,
    by_employee: list,
    by_label: list,
    filters: dict,
    stale_days: int,
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.55 * inch, rightMargin=0.55 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=18, spaceAfter=2)
    meta_style = ParagraphStyle("ReportMeta", parent=styles["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=14)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, spaceBefore=16, spaceAfter=6)
    empty_style = ParagraphStyle("Empty", parent=styles["Normal"], fontSize=9.5, textColor=colors.grey, spaceAfter=6)

    header_bg = colors.HexColor("#f1f3f8")
    grid = colors.HexColor("#d8dce6")

    def table(headers, rows, col_widths=None):
        data = [headers] + rows
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.5, grid),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    story = []
    story.append(Paragraph(f"{organization_name} — Report", title_style))
    story.append(Paragraph(
        f"Generated {datetime.utcnow().strftime('%b %d, %Y %H:%M UTC')} · {_filters_summary(filters, stale_days)}",
        meta_style,
    ))

    # --- Overview ---
    story.append(Paragraph("Overview", h2))
    by_status = overview.get("by_status", {})
    overview_rows = [[
        str(overview.get("total_tickets", 0)),
        f"{overview.get('completed_points', 0)}/{overview.get('total_points', 0)}",
        str(len(ongoing_tickets)),
        str(len(stale_rows)),
        str(len(done_tickets)),
    ]]
    story.append(table(
        ["Total tickets", "Points done/total", "Ongoing", "Not touched", "Done"],
        overview_rows,
    ))
    if by_status:
        status_row = [[str(by_status.get(k, 0)) for k in STATUS_LABELS]]
        story.append(Spacer(1, 8))
        story.append(table(list(STATUS_LABELS.values()), status_row))

    # --- Ongoing tickets ---
    story.append(Paragraph("Ongoing tickets", h2))
    if ongoing_tickets:
        rows = [[
            t.key, t.title, _status_label(t.status), _name(t.assignee),
            t.product or "—", str(t.story_points) if t.story_points is not None else "—",
        ] for t in ongoing_tickets]
        story.append(table(
            ["Ticket", "Title", "Status", "Assignee", "Product", "Pts"],
            rows, col_widths=[0.7 * inch, 2.3 * inch, 0.9 * inch, 1.3 * inch, 1.1 * inch, 0.4 * inch],
        ))
    else:
        story.append(Paragraph("Nothing ongoing matches these filters.", empty_style))

    # --- Not touched ---
    story.append(Paragraph("Not touched", h2))
    if stale_rows:
        rows = [[
            row["ticket"].key, row["ticket"].title, _status_label(row["ticket"].status),
            _name(row["ticket"].assignee), _fmt_date(row["last_activity_at"]),
            str(row["days_since_activity"]),
        ] for row in stale_rows]
        story.append(table(
            ["Ticket", "Title", "Status", "Assignee", "Last activity", "Days idle"],
            rows, col_widths=[0.7 * inch, 2.1 * inch, 0.9 * inch, 1.3 * inch, 1.1 * inch, 0.6 * inch],
        ))
    else:
        story.append(Paragraph(f"Nothing has gone stale under the {stale_days}-day threshold.", empty_style))

    # --- Done ---
    story.append(Paragraph("Done", h2))
    if done_tickets:
        rows = [[
            t.key, t.title, _name(t.assignee), t.product or "—",
            str(t.story_points) if t.story_points is not None else "—",
        ] for t in done_tickets]
        story.append(table(
            ["Ticket", "Title", "Assignee", "Product", "Pts"],
            rows, col_widths=[0.7 * inch, 2.7 * inch, 1.3 * inch, 1.3 * inch, 0.5 * inch],
        ))
    else:
        story.append(Paragraph("Nothing done yet under these filters.", empty_style))

    # --- By employee ---
    story.append(Paragraph("By employee", h2))
    if by_employee:
        rows = [[
            row["user"].full_name, str(row["assigned_count"]), str(row["in_progress_count"]),
            str(row["done_count"]), str(row["points_completed"]),
        ] for row in by_employee]
        story.append(table(
            ["Employee", "Assigned", "In progress", "Done", "Points completed"],
            rows,
        ))
    else:
        story.append(Paragraph("No one on the team yet.", empty_style))

    # --- By label ---
    story.append(Paragraph("By label", h2))
    labelled = [row for row in by_label if row["total_count"] > 0]
    if labelled:
        rows = [[
            row["label"].name, str(row["total_count"]), str(row["done_count"]), str(row["points_total"]),
        ] for row in labelled]
        story.append(table(["Label", "Total", "Done", "Points"], rows))
    else:
        story.append(Paragraph("No labelled tickets match these filters.", empty_style))

    doc.build(story)
    return buf.getvalue()
