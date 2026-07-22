"""
Renders a single ticket as a standalone PDF: everything on its detail panel
(TicketModal.jsx) in printable form — who raised it, who it's assigned to,
every comment, every status/assignment change, and the full chain-of-custody
if it ever moved through the cross-team workflow, including how long each
team/person held it. This is the "give me this one ticket as a document" export,
distinct from pdf_report.py which covers a whole filtered set of tickets.
"""
from datetime import datetime, date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)

STATUS_LABELS = {
    "backlog": "Backlog",
    "todo": "To Do",
    "in_progress": "In Progress",
    "code_review": "Code Review",
    "done": "Done",
}

TYPE_LABELS = {"task": "Task", "bug": "Bug", "subtask": "Sub-task", "story": "Story", "epic": "Epic"}
PRIORITY_LABELS = {"highest": "Highest", "high": "High", "medium": "Medium", "low": "Low", "lowest": "Lowest"}


def _label(mapping, val, fallback=None):
    value = val.value if hasattr(val, "value") else val
    return mapping.get(value, fallback or value)


def _name(user) -> str:
    return user.full_name if user else "Unassigned"


def _dt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, (datetime, date)):
        return value.strftime("%b %d, %Y %H:%M") if isinstance(value, datetime) else value.strftime("%b %d, %Y")
    return str(value)


def _duration(seconds) -> str:
    if seconds is None:
        return "still holding"
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if not days and minutes:
        parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "<1m"


def build_ticket_pdf(*, ticket, comments: list, activity: list, handoffs: list) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.55 * inch, rightMargin=0.55 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TicketTitle", parent=styles["Title"], fontSize=17, spaceAfter=2)
    meta_style = ParagraphStyle("TicketMeta", parent=styles["Normal"], fontSize=9.5, textColor=colors.grey, spaceAfter=14)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, spaceBefore=16, spaceAfter=6)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9.5, leading=13, spaceAfter=6)
    empty_style = ParagraphStyle("Empty", parent=styles["Normal"], fontSize=9.5, textColor=colors.grey, spaceAfter=6)
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8.5, leading=12)

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
    story.append(Paragraph(f"{ticket.key} — {ticket.title}", title_style))
    story.append(Paragraph(
        f"{_label(TYPE_LABELS, ticket.ticket_type)} · {_label(PRIORITY_LABELS, ticket.priority)} priority · "
        f"{_label(STATUS_LABELS, ticket.status)}"
        + (f" · {ticket.estimated_hours}h estimated" if ticket.estimated_hours is not None else ""),
        meta_style,
    ))

    # --- Key facts ---
    story.append(Paragraph("Details", h2))
    facts_rows = [
        ["Reporter", _name(ticket.reporter), "Assignee", _name(ticket.assignee)],
        ["Created", _dt(ticket.created_at), "Last updated", _dt(ticket.updated_at)],
        ["Resolved", _dt(getattr(ticket, "resolved_at", None)), "Due", _dt(ticket.due_date)],
        ["Product", ticket.product or "—", "Client", ticket.client_name or "—"],
    ]
    story.append(table(["Field", "Value", "Field", "Value"], facts_rows,
                        col_widths=[0.9 * inch, 2.35 * inch, 0.9 * inch, 2.35 * inch]))

    if getattr(ticket, "labels", None):
        story.append(Spacer(1, 6))
        story.append(Paragraph("Labels: " + ", ".join(l.name for l in ticket.labels), body))

    # --- Description ---
    story.append(Paragraph("Description", h2))
    story.append(Paragraph((ticket.description or "No description.").replace("\n", "<br/>"), body))

    ticket_type_value = ticket.ticket_type.value if hasattr(ticket.ticket_type, "value") else ticket.ticket_type
    if ticket_type_value == "bug":
        if any([ticket.steps_to_reproduce, ticket.expected_behavior, ticket.actual_behavior]):
            story.append(Paragraph("Bug report details", h2))
            if ticket.steps_to_reproduce:
                story.append(Paragraph(f"<b>Steps to reproduce:</b><br/>{ticket.steps_to_reproduce.replace(chr(10), '<br/>')}", body))
            if ticket.expected_behavior:
                story.append(Paragraph(f"<b>Expected:</b> {ticket.expected_behavior}", body))
            if ticket.actual_behavior:
                story.append(Paragraph(f"<b>Actual:</b> {ticket.actual_behavior}", body))
            if ticket.environment_stage:
                env_value = ticket.environment_stage.value if hasattr(ticket.environment_stage, "value") else ticket.environment_stage
                story.append(Paragraph(f"<b>Environment:</b> {str(env_value).title()}", body))
            if ticket.browser_version:
                story.append(Paragraph(f"<b>Browser:</b> {ticket.browser_version}", body))

    # --- Chain of custody / who worked on it, how long ---
    story.append(Paragraph("Chain of custody", h2))
    if handoffs:
        # handoffs is the list of dicts from crud.build_timeline(), the same
        # derivation the /handoffs endpoint and the ticket panel's timeline use
        # -- not raw TicketHandoff rows, which don't carry received_at/
        # handed_off_at/duration_held_seconds (those are computed, not stored).
        rows = []
        for h in handoffs:
            to_user = h["to_user"]
            to_team = h["to_team"]
            holder = to_user.full_name if to_user else (to_team.name if to_team else "—")
            action = h["action"]
            rows.append([
                holder,
                action.value if hasattr(action, "value") else str(action),
                _dt(h["received_at"]),
                _dt(h["handed_off_at"]) if h["handed_off_at"] else "still holding",
                _duration(h["duration_held_seconds"]),
            ])
        story.append(table(
            ["Held by", "Action", "Received", "Handed off", "Duration held"],
            rows, col_widths=[1.4 * inch, 1.1 * inch, 1.3 * inch, 1.3 * inch, 1.2 * inch],
        ))
    else:
        story.append(Paragraph("This ticket never entered the cross-team workflow.", empty_style))

    # --- Comments ---
    story.append(Paragraph("Comments", h2))
    if comments:
        for c in comments:
            story.append(Paragraph(
                f"<b>{_name(c.author)}</b> <font color='grey'>{_dt(c.created_at)}</font><br/>{(c.body or '').replace(chr(10), '<br/>')}",
                body,
            ))
    else:
        story.append(Paragraph("No comments.", empty_style))

    # --- Activity log: who worked on it and when ---
    story.append(Paragraph("Activity log", h2))
    if activity:
        rows = [[
            _name(a.actor), a.action.replace("_", " "), a.details or "—", _dt(a.created_at),
        ] for a in sorted(activity, key=lambda a: a.created_at)]
        story.append(table(["Who", "Action", "Details", "When"], rows,
                            col_widths=[1.3 * inch, 1.5 * inch, 2.4 * inch, 1.1 * inch]))
    else:
        story.append(Paragraph("No recorded activity.", empty_style))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Generated {datetime.utcnow().strftime('%b %d, %Y %H:%M UTC')} from QTech Resolver.", small,
    ))

    doc.build(story)
    return buf.getvalue()
