"""multi-tenancy: organizations table, organization_id on every tenant table

Revision ID: d88cc45d28c3
Revises: c3f9a71e5b2d
Create Date: 2026-07-15 12:00:00.000000

Turns this from a single QTech-only app into a real multi-tenant product.
Every table that holds tenant data gets an organization_id column; QTech's
existing data becomes the first real organization (name, join code, and
ticket-key prefix all preserved so nothing already in use changes shape).

What used to be GLOBAL uniqueness becomes PER-ORGANIZATION uniqueness:
label/team/parent-tag names, and ticket numbering. Ticket numbers used to come
from one shared Postgres SEQUENCE across the whole app -- that's retired here,
because a shared sequence leaks one tenant's ticket volume into another's
numbering and can't give a new org a fresh "start at 1". Numbers are now
allocated by the application (crud.create_ticket), under a row lock on the
owning Organization's next_ticket_number counter, seeded here to continue
exactly where the old sequence left off so no existing ticket key changes.

sla_policies' primary key changes from a bare `priority` (one row per
priority, globally) to a composite (organization_id, priority) -- every
tenant gets to tune its own SLA thresholds.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd88cc45d28c3'
down_revision: Union[str, None] = 'c3f9a71e5b2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every table that gets a straightforward organization_id FK + NOT NULL +
# index. sla_policies is handled separately because organization_id joins its
# primary key there instead of being a plain column.
TENANT_TABLES = [
    "users", "labels", "teams", "ticket_handoffs", "parent_tags",
    "sprints", "tickets", "saved_filters", "attachments", "notifications",
    "comments", "activity_logs",
]


def upgrade() -> None:
    # ---- 1. The tenants table itself ----
    op.create_table(
        'organizations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('key_prefix', sa.String(), nullable=False),
        sa.Column('join_code', sa.String(), nullable=False),
        sa.Column('next_ticket_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_organizations_name'), 'organizations', ['name'], unique=True)
    op.create_index(op.f('ix_organizations_join_code'), 'organizations', ['join_code'], unique=True)

    # ---- 2. organization_id on every tenant table, nullable for now so the
    # backfill below has somewhere to write ----
    for table in TENANT_TABLES:
        op.add_column(table, sa.Column('organization_id', sa.UUID(), nullable=True))
    op.add_column('sla_policies', sa.Column('organization_id', sa.UUID(), nullable=True))

    # ---- 3. Seed the one organization that owns everything that exists
    # today. next_ticket_number picks up exactly where ticket_number_seq left
    # off, so the very next ticket created keeps counting up with no gap or
    # collision. join_code is a random 8-char code -- rotatable later from
    # Settings, this just needs to exist. ----
    op.execute("""
        INSERT INTO organizations (id, name, key_prefix, join_code, next_ticket_number, created_at)
        SELECT
            gen_random_uuid(),
            'QTech Software',
            'QTR',
            upper(substr(md5(random()::text), 1, 8)),
            COALESCE((SELECT MAX(ticket_number) FROM tickets), 0) + 1,
            now()
    """)

    # ---- 4. Backfill every existing row onto that one organization ----
    for table in TENANT_TABLES + ['sla_policies']:
        op.execute(f"UPDATE {table} SET organization_id = (SELECT id FROM organizations LIMIT 1)")

    # ---- 5. Lock it down: NOT NULL + FK + index, now that every row has a
    # value ----
    for table in TENANT_TABLES:
        op.alter_column(table, 'organization_id', nullable=False)
        op.create_foreign_key(
            f'fk_{table}_organization_id', table, 'organizations',
            ['organization_id'], ['id'], ondelete='CASCADE',
        )
        op.create_index(f'ix_{table}_organization_id', table, ['organization_id'])

    op.alter_column('sla_policies', 'organization_id', nullable=False)
    op.create_foreign_key(
        'fk_sla_policies_organization_id', 'sla_policies', 'organizations',
        ['organization_id'], ['id'], ondelete='CASCADE',
    )

    # ---- 6. Global name uniqueness -> per-organization uniqueness ----
    op.drop_index(op.f('ix_labels_name'), table_name='labels')
    op.create_index(op.f('ix_labels_name'), 'labels', ['name'])
    op.create_index('ix_labels_org_name', 'labels', ['organization_id', 'name'], unique=True)

    op.drop_index(op.f('ix_teams_name'), table_name='teams')
    op.create_index(op.f('ix_teams_name'), 'teams', ['name'])
    op.create_index('ix_teams_org_name', 'teams', ['organization_id', 'name'], unique=True)

    op.drop_index(op.f('ix_parent_tags_name'), table_name='parent_tags')
    op.create_index(op.f('ix_parent_tags_name'), 'parent_tags', ['name'])
    op.create_index('ix_parent_tags_org_name', 'parent_tags', ['organization_id', 'name'], unique=True)

    # ---- 7. Ticket numbering: global unique sequence -> per-org unique
    # counter. The app (crud.create_ticket) now allocates ticket_number
    # itself under a row lock on organizations.next_ticket_number, so the
    # column no longer needs a server-side default or the old sequence. ----
    op.drop_index(op.f('ix_tickets_ticket_number'), table_name='tickets')
    op.alter_column('tickets', 'ticket_number', server_default=None)
    op.execute('DROP SEQUENCE IF EXISTS ticket_number_seq')
    op.create_index(op.f('ix_tickets_ticket_number'), 'tickets', ['ticket_number'])
    op.create_index('ix_tickets_org_number', 'tickets', ['organization_id', 'ticket_number'], unique=True)

    # ---- 8. sla_policies: bare `priority` primary key -> composite
    # (organization_id, priority). Every tenant tunes its own thresholds. ----
    op.drop_constraint('sla_policies_pkey', 'sla_policies', type_='primary')
    op.create_primary_key('sla_policies_pkey', 'sla_policies', ['organization_id', 'priority'])


def downgrade() -> None:
    # Best-effort structural reversal only, matching the pattern in the prior
    # migration: this app has only ever run as a single tenant, so there is
    # nothing to "un-merge" data-wise -- collapsing back to one implicit
    # tenant is exactly what dropping organization_id already does.
    op.drop_constraint('sla_policies_pkey', 'sla_policies', type_='primary')
    op.create_primary_key('sla_policies_pkey', 'sla_policies', ['priority'])

    op.drop_index('ix_tickets_org_number', table_name='tickets')
    op.drop_index(op.f('ix_tickets_ticket_number'), table_name='tickets')
    op.execute('CREATE SEQUENCE IF NOT EXISTS ticket_number_seq START 1')
    op.execute("SELECT setval('ticket_number_seq', COALESCE((SELECT MAX(ticket_number) FROM tickets), 1))")
    op.alter_column(
        'tickets', 'ticket_number',
        server_default=sa.text("nextval('ticket_number_seq')"),
    )
    op.create_index(op.f('ix_tickets_ticket_number'), 'tickets', ['ticket_number'], unique=True)

    op.drop_index('ix_parent_tags_org_name', table_name='parent_tags')
    op.drop_index(op.f('ix_parent_tags_name'), table_name='parent_tags')
    op.create_index(op.f('ix_parent_tags_name'), 'parent_tags', ['name'], unique=True)

    op.drop_index('ix_teams_org_name', table_name='teams')
    op.drop_index(op.f('ix_teams_name'), table_name='teams')
    op.create_index(op.f('ix_teams_name'), 'teams', ['name'], unique=True)

    op.drop_index('ix_labels_org_name', table_name='labels')
    op.drop_index(op.f('ix_labels_name'), table_name='labels')
    op.create_index(op.f('ix_labels_name'), 'labels', ['name'], unique=True)

    op.drop_constraint('fk_sla_policies_organization_id', 'sla_policies', type_='foreignkey')
    op.drop_column('sla_policies', 'organization_id')

    for table in TENANT_TABLES:
        op.drop_index(f'ix_{table}_organization_id', table_name=table)
        op.drop_constraint(f'fk_{table}_organization_id', table, type_='foreignkey')
        op.drop_column(table, 'organization_id')

    op.drop_index(op.f('ix_organizations_join_code'), table_name='organizations')
    op.drop_index(op.f('ix_organizations_name'), table_name='organizations')
    op.drop_table('organizations')
