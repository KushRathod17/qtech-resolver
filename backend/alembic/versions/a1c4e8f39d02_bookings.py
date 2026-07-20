"""bookings

Revision ID: a1c4e8f39d02
Revises: d88cc45d28c3
Create Date: 2026-07-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1c4e8f39d02'
down_revision: Union[str, None] = 'd88cc45d28c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bookings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('booking_code', sa.String(), nullable=False),
        sa.Column('current_status', sa.String(), nullable=True),
        sa.Column('create_date', sa.DateTime(), nullable=True),
        sa.Column('confirmation_number', sa.String(), nullable=True),
        sa.Column('leader_full_name', sa.String(), nullable=True),
        sa.Column('service_date', sa.Date(), nullable=True),
        sa.Column('check_out_date', sa.Date(), nullable=True),
        sa.Column('client_name', sa.String(), nullable=True),
        sa.Column('imported_at', sa.DateTime(), nullable=True),
        sa.Column('source_file', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_bookings_organization_id'), 'bookings', ['organization_id'], unique=False)
    op.create_index(op.f('ix_bookings_booking_code'), 'bookings', ['booking_code'], unique=False)
    op.create_index(op.f('ix_bookings_current_status'), 'bookings', ['current_status'], unique=False)
    op.create_index(op.f('ix_bookings_client_name'), 'bookings', ['client_name'], unique=False)
    op.create_index('ix_bookings_org_code', 'bookings', ['organization_id', 'booking_code'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_bookings_org_code', table_name='bookings')
    op.drop_index(op.f('ix_bookings_client_name'), table_name='bookings')
    op.drop_index(op.f('ix_bookings_current_status'), table_name='bookings')
    op.drop_index(op.f('ix_bookings_booking_code'), table_name='bookings')
    op.drop_index(op.f('ix_bookings_organization_id'), table_name='bookings')
    op.drop_table('bookings')
