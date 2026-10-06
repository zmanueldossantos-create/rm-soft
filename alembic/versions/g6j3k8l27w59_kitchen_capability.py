"""Cozinha devient une capacite a part : une ligne pour chaque module existant (cochee pour Restaurante seulement),
et le Bar recoit les mesas (Recursos). Les autres reglages du super admin ne sont pas touches.

Revision ID: g6j3k8l27w59
Revises: f5i2j7k16v48
"""
from alembic import op

revision = "g6j3k8l27w59"
down_revision = "f5i2j7k16v48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO module_capabilities (module_id, capability, is_enabled, updated_at)
        SELECT m.id, 'KITCHEN', m.code = 'RESTAURANTE', now()
        FROM modules m
        WHERE EXISTS (SELECT 1 FROM module_capabilities x WHERE x.module_id = m.id)
          AND NOT EXISTS (SELECT 1 FROM module_capabilities x WHERE x.module_id = m.id AND x.capability = 'KITCHEN')
    """)
    op.execute("""
        UPDATE module_capabilities SET is_enabled = true, updated_at = now()
        WHERE capability = 'RESOURCES' AND module_id IN (SELECT id FROM modules WHERE code = 'BAR')
    """)


def downgrade() -> None:
    op.execute("DELETE FROM module_capabilities WHERE capability = 'KITCHEN'")
