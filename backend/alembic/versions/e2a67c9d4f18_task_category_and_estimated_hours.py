"""task_category becomes a free-text column, story_points replaced by estimated_hours

Revision ID: e2a67c9d4f18
Revises: a1c4e8f39d02
Create Date: 2026-07-21 00:00:00.000000

Two independent changes, bundled because both touch the tickets table:

1. task_category: the fixed list of categories changed (Manual/Task/Issue/
   Change Request/New Development, replacing New Development/Enhancement/
   Maintenance/Documentation/Investigation/Configuration). Rather than
   ALTER TYPE the Postgres enum again -- the exact pain that prompted this --
   the column becomes plain VARCHAR, same as `product` already is. The next
   time this list changes, it's an app deploy, not a migration.

2. story_points (integer, an abstract point scale) is replaced by
   estimated_hours (float, actual hours) -- this team estimates work in
   hours, not points. Existing values are carried over 1:1 as a starting
   point (an old estimate of "3" becomes 3.0 hours) since a rough carried-over
   number is more useful than silently discarding every existing estimate.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2a67c9d4f18'
down_revision: Union[str, None] = 'a1c4e8f39d02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- task_category: enum -> free text ----
    op.alter_column(
        'tickets', 'task_category',
        existing_type=sa.Enum(
            'NEW_DEVELOPMENT', 'ENHANCEMENT', 'MAINTENANCE', 'DOCUMENTATION',
            'INVESTIGATION', 'CONFIGURATION', name='taskcategory',
        ),
        type_=sa.String(),
        postgresql_using='task_category::text',
    )
    # The old enum stored the Python member NAME (uppercase), not its value --
    # e.g. 'NEW_DEVELOPMENT', not 'new_development'. The new picker's values
    # are lowercase snake_case, matching every other free-text category field
    # in this app (see Booking.current_status). Normalize the one category
    # that survives into the new list so those tickets keep showing a picked
    # category instead of silently becoming "none selected". Every other old
    # category (enhancement/maintenance/documentation/investigation/
    # configuration) has no equivalent in the new list -- left as-is, same
    # tolerance this app already extends to old Epic/Story tickets: the data
    # isn't touched, it just isn't offered as a choice going forward.
    op.execute("UPDATE tickets SET task_category = 'new_development' WHERE task_category = 'NEW_DEVELOPMENT'")

    op.execute('DROP TYPE IF EXISTS taskcategory')

    # ---- story_points -> estimated_hours ----
    op.add_column('tickets', sa.Column('estimated_hours', sa.Float(), nullable=True))
    op.execute('UPDATE tickets SET estimated_hours = story_points WHERE story_points IS NOT NULL')
    op.drop_column('tickets', 'story_points')


def downgrade() -> None:
    # ---- estimated_hours -> story_points ----
    op.add_column('tickets', sa.Column('story_points', sa.Integer(), nullable=True))
    # Rounds hours back to a whole-number point -- lossy, same as any
    # downgrade that collapses a wider type back into a narrower one.
    op.execute('UPDATE tickets SET story_points = ROUND(estimated_hours) WHERE estimated_hours IS NOT NULL')
    op.drop_column('tickets', 'estimated_hours')

    # ---- task_category: free text -> enum ----
    # Anything not in the old six values (i.e. every row written under the
    # new picker) can't round-trip into the old enum -- cleared rather than
    # left as a value the enum type would reject outright.
    op.execute("""
        UPDATE tickets SET task_category = NULL
        WHERE task_category IS NOT NULL
          AND upper(task_category) NOT IN (
              'NEW_DEVELOPMENT', 'ENHANCEMENT', 'MAINTENANCE',
              'DOCUMENTATION', 'INVESTIGATION', 'CONFIGURATION'
          )
    """)
    op.execute("UPDATE tickets SET task_category = upper(task_category) WHERE task_category IS NOT NULL")

    task_category_enum = sa.Enum(
        'NEW_DEVELOPMENT', 'ENHANCEMENT', 'MAINTENANCE', 'DOCUMENTATION',
        'INVESTIGATION', 'CONFIGURATION', name='taskcategory',
    )
    task_category_enum.create(op.get_bind(), checkfirst=True)
    op.alter_column(
        'tickets', 'task_category',
        existing_type=sa.String(),
        type_=task_category_enum,
        postgresql_using='task_category::taskcategory',
    )
