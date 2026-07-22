"""users.is_active -- deactivate instead of delete

Revision ID: f3a8c1d92e77
Revises: e2a67c9d4f18
Create Date: 2026-07-22 00:00:00.000000

There's no way to remove a person from an organization yet. A real DELETE is
unsafe for anyone with history: tickets.assignee_id/created_by_id,
comments.author_id and activity_log.actor_id all reference users.id WITHOUT
ON DELETE CASCADE (on purpose -- a departed employee's ticket history
shouldn't vanish with them), so Postgres would just reject the delete with a
foreign key violation for anyone who's ever touched a ticket.

is_active is the alternative: a deactivated account can't log in and drops
out of the assignee picker, but every ticket/comment/activity row they ever
touched keeps their name exactly as before. The one case that CAN still be
a real DELETE -- someone with zero tickets/comments/activity, e.g. a test
account -- is handled in the application layer (DELETE /users/{id} tries a
hard delete first and only falls back to is_active=False if there's history
to protect), not here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a8c1d92e77'
down_revision: Union[str, None] = 'e2a67c9d4f18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
    )


def downgrade() -> None:
    op.drop_column('users', 'is_active')
