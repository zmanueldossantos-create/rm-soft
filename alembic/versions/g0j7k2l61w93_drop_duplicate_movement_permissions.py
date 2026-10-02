"""permissions: movements:create and movements:import dropped - duplicates of stock:receive (the movement document form
only receives stock); every grant removed, wherever it points to the permission

Revision ID: g0j7k2l61w93
Revises: f9i6j1k50v82
"""
from alembic import op

revision = "g0j7k2l61w93"
down_revision = "f9i6j1k50v82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    DO $$
    DECLARE r record;
    BEGIN
        FOR r IN
            SELECT kcu.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
            JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'permissions'
        LOOP
            EXECUTE format(
                'DELETE FROM %I WHERE %I IN (SELECT id FROM permissions WHERE code IN (''movements:create'', ''movements:import''))',
                r.table_name, r.column_name
            );
        END LOOP;
        DELETE FROM permissions WHERE code IN ('movements:create', 'movements:import');
    END $$;
    """)


def downgrade() -> None:
    # The grants cannot be restored: the routes now check stock:receive.
    pass
