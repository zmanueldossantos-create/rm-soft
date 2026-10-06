"""role COZINHA : valeur du type et droits de lecture de base dans les entreprises existantes
(les droits kitchen:* sont nouveaux : le semis du demarrage les distribue tout seul)

Revision ID: e4h1i6j05u37
Revises: d3g0h5i94t26
"""
from alembic import op
import sqlalchemy as sa

revision = "e4h1i6j05u37"
down_revision = "d3g0h5i94t26"
branch_labels = None
depends_on = None

BASE_CODES = ("activities:view", "fiscal_periods:current", "tesouraria:my_association")


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'COZINHA'")
    op.get_bind().execute(
        sa.text("""
            INSERT INTO role_permissions (id, company_id, role, permission_id, created_at)
            SELECT gen_random_uuid(), cps.company_id, 'COZINHA', cps.permission_id, now()
            FROM company_permission_seeds cps
            JOIN permissions p ON p.id = cps.permission_id
            WHERE p.code = ANY(:codes)
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp
                  WHERE rp.company_id = cps.company_id AND rp.role = 'COZINHA' AND rp.permission_id = cps.permission_id
              )
        """),
        {"codes": list(BASE_CODES)},
    )


def downgrade() -> None:
    bind = op.get_bind()
    n = bind.execute(sa.text("SELECT count(*) FROM users WHERE role = 'COZINHA'")).scalar()
    if n:
        raise RuntimeError(f"{n} utilisateur(s) ont encore le role COZINHA : changer leur role avant.")
    bind.execute(sa.text("DELETE FROM role_permissions WHERE role = 'COZINHA'"))
