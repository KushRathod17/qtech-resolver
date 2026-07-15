"""task/bug-only type, product replaces components, parent tags replace
epics, task category, start date, and rich bug-report fields

Revision ID: c3f9a71e5b2d
Revises: b7340a413aee
Create Date: 2026-07-14 18:00:00.000000

This is the migration that was supposed to accompany the models.py changes
for the Type/Priority simplification, Components -> Product, and Epic ->
Parent Tag work — models.py already described this schema, but no migration
was ever generated to make the live database match it. Written by hand
against the confirmed plan (all seven points agreed "go") rather than via
autogenerate, since autogenerate can't be run against a database this
sandbox has no network path to.

Data migrations in here are ONE-SHOT and lossy in the sense described below
-- they collapse real rows (Highest/Lowest priority, Story/Epic type,
Components) into their replacements. That is the intended outcome, not a
bug: the whole point was "migrate the data, don't just delete it."
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f9a71e5b2d'
down_revision: Union[str, None] = 'b7340a413aee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- Structure: new table, new columns ----

    op.create_table(
        'parent_tags',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_parent_tags_name'), 'parent_tags', ['name'], unique=True)

    # Unlike create_table, op.add_column does NOT auto-emit CREATE TYPE for a
    # new enum -- confirmed by actually running this migration end to end
    # (it failed with "type taskcategory does not exist" until this explicit
    # .create() was added). The type must exist before the column references it.
    task_category_enum = sa.Enum(
        'NEW_DEVELOPMENT', 'ENHANCEMENT', 'MAINTENANCE', 'DOCUMENTATION',
        'INVESTIGATION', 'CONFIGURATION', name='taskcategory',
    )
    task_category_enum.create(op.get_bind(), checkfirst=True)
    op.add_column('tickets', sa.Column(
        'task_category', task_category_enum, nullable=True,
    ))

    op.add_column('tickets', sa.Column('product', sa.String(), nullable=True))
    op.create_index(op.f('ix_tickets_product'), 'tickets', ['product'], unique=False)

    op.add_column('tickets', sa.Column('start_date', sa.Date(), nullable=True))

    op.add_column('tickets', sa.Column('parent_tag_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_tickets_parent_tag_id'), 'tickets', ['parent_tag_id'], unique=False)
    op.create_foreign_key(None, 'tickets', 'parent_tags', ['parent_tag_id'], ['id'], ondelete='SET NULL')

    # Rich bug-report fields.
    op.add_column('tickets', sa.Column('steps_to_reproduce', sa.Text(), nullable=True))
    op.add_column('tickets', sa.Column('expected_behavior', sa.Text(), nullable=True))
    op.add_column('tickets', sa.Column('actual_behavior', sa.Text(), nullable=True))

    environment_stage_enum = sa.Enum('PRODUCTION', 'STAGING', 'OTHER', name='environmentstage')
    environment_stage_enum.create(op.get_bind(), checkfirst=True)
    op.add_column('tickets', sa.Column(
        'environment_stage', environment_stage_enum, nullable=True,
    ))
    op.add_column('tickets', sa.Column('browser_version', sa.String(), nullable=True))

    # ---- Data: migrate, don't delete ----

    # Components -> Product. A ticket's product becomes the migrated
    # component's name; the fixed Product list on the frontend is exactly
    # these six names.
    op.execute("""
        UPDATE tickets
        SET product = components.name
        FROM components
        WHERE tickets.component_id = components.id
    """)

    # Story -> Task. Story was feature work; task_category is what now carries
    # that distinction. Every migrated Story defaults to New Development,
    # which is bulk-editable afterward rather than forcing a per-ticket choice
    # during the migration itself.
    op.execute("""
        UPDATE tickets
        SET ticket_type = 'TASK', task_category = 'NEW_DEVELOPMENT'
        WHERE ticket_type = 'STORY'
    """)

    # Epic -> Parent Tag. The parent_tags row REUSES the epic ticket's own id
    # as its primary key -- tickets and parent_tags are different tables, so
    # this isn't a collision, and it means every child's existing epic_id
    # value is already the correct parent_tag_id with no id-mapping step.
    op.execute("""
        INSERT INTO parent_tags (id, name, description, color, created_at)
        SELECT id, title, description, '#8B5CF6', created_at
        FROM tickets
        WHERE ticket_type = 'EPIC'
    """)
    op.execute("""
        UPDATE tickets
        SET parent_tag_id = epic_id
        WHERE epic_id IS NOT NULL
    """)

    # comments.ticket_id and activity_logs.ticket_id have no DB-level ON DELETE
    # (the app relies on SQLAlchemy's ORM-side cascade="all, delete-orphan" for
    # a normal ticket delete, which this raw DELETE bypasses entirely). Without
    # this, the DELETE below fails with a ForeignKeyViolation the moment any
    # epic has ever had a comment or a logged activity event. Same one-shot,
    # lossy collapse as everything else here: the epic stops being a ticket, so
    # its ticket-shaped history (comments, activity) goes with it -- the
    # ParentTag it becomes has no comment or activity-log concept to inherit it.
    op.execute("""
        DELETE FROM comments
        WHERE ticket_id IN (SELECT id FROM tickets WHERE ticket_type = 'EPIC')
    """)
    op.execute("""
        DELETE FROM activity_logs
        WHERE ticket_id IN (SELECT id FROM tickets WHERE ticket_type = 'EPIC')
    """)
    op.execute("""
        DELETE FROM tickets
        WHERE ticket_type = 'EPIC'
    """)

    # Priority collapse: Highest -> High, Lowest -> Low. The enum values
    # themselves stay in Postgres (can't cleanly drop them), but no row uses
    # them after this and the UI never offers them again.
    op.execute("UPDATE tickets SET priority = 'HIGH' WHERE priority = 'HIGHEST'")
    op.execute("UPDATE tickets SET priority = 'LOW' WHERE priority = 'LOWEST'")

    # SLA fixup: the merged High inherits Highest's stricter 4h threshold
    # (not High's old 8h) -- these were your most-urgent tickets, don't
    # relax their deadline as a side effect of collapsing the priority list.
    op.execute("UPDATE sla_policies SET threshold_hours = 4 WHERE priority = 'HIGH'")
    op.execute("DELETE FROM sla_policies WHERE priority IN ('HIGHEST', 'LOWEST')")

    # ---- Drop what's now superseded ----
    # Postgres drops a column's own single-column FK constraint automatically
    # when the column itself is dropped -- no separate drop_constraint needed.
    op.drop_column('tickets', 'component_id')
    op.drop_column('tickets', 'epic_id')
    op.drop_index(op.f('ix_components_name'), table_name='components')
    op.drop_table('components')


def downgrade() -> None:
    # Best-effort structural reversal only. The data transformations above are
    # deliberately one-directional (Story/Epic/Highest/Lowest/Components were
    # collapsed into their replacements) -- reconstructing the exact original
    # rows isn't attempted here, matching how 'SUBTASK' was left behind in an
    # earlier migration's downgrade rather than pretending to undo it.
    op.add_column('tickets', sa.Column('epic_id', sa.UUID(), nullable=True))
    op.create_foreign_key(None, 'tickets', 'tickets', ['epic_id'], ['id'], ondelete='SET NULL')
    op.add_column('tickets', sa.Column('component_id', sa.UUID(), nullable=True))

    op.create_table(
        'components',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.String(), nullable=False),
        sa.Column('lead_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['lead_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_components_name'), 'components', ['name'], unique=True)
    op.create_foreign_key(None, 'tickets', 'components', ['component_id'], ['id'], ondelete='SET NULL')

    op.execute(
        "INSERT INTO sla_policies (priority, threshold_hours) VALUES "
        "('HIGHEST', 4), ('LOWEST', NULL) "
        "ON CONFLICT (priority) DO NOTHING"
    )

    op.drop_column('tickets', 'browser_version')
    op.drop_column('tickets', 'environment_stage')
    op.drop_column('tickets', 'actual_behavior')
    op.drop_column('tickets', 'expected_behavior')
    op.drop_column('tickets', 'steps_to_reproduce')

    op.drop_index(op.f('ix_tickets_parent_tag_id'), table_name='tickets')
    op.drop_column('tickets', 'parent_tag_id')
    op.drop_column('tickets', 'start_date')
    op.drop_index(op.f('ix_tickets_product'), table_name='tickets')
    op.drop_column('tickets', 'product')
    op.drop_column('tickets', 'task_category')
    sa.Enum(name='taskcategory').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='environmentstage').drop(op.get_bind(), checkfirst=True)

    op.drop_index(op.f('ix_parent_tags_name'), table_name='parent_tags')
    op.drop_table('parent_tags')
