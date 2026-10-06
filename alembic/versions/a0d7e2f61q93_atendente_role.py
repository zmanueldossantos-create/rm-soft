"""role ATENDENTE : valeur du type et droits par defaut dans les entreprises existantes

Le semis distribue les droits par defaut une seule fois par (entreprise, permission) :
une entreprise ou open_accounts:* est deja seme ne donnerait jamais ses droits au nouveau role.
Cette migration les accorde la ou la permission est deja semee ; le gestor peut ensuite les retirer.

Revision ID: a0d7e2f61q93
Revises: z9c6d1e50p82
"""
from alembic import op
import sqlalchemy as sa

revision = "a0d7e2f61q93"
down_revision = "z9c6d1e50p82"
branch_labels = None
depends_on = None

WAITER_CODES = (
    "open_accounts:view", "open_accounts:open", "open_accounts:edit_lines", "open_accounts:transfer",
    "products:view", "services:view", "resources:view", "resource_types:view",
    "activities:view", "pos_terminals:view", "fiscal_periods:current", "tesouraria:my_association",
)


def upgrade() -> None:
    # Une nouvelle valeur d'enum doit etre validee avant d'etre utilisee.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'ATENDENTE'")

    op.get_bind().execute(
        sa.text("""
            INSERT INTO role_permissions (id, company_id, role, permission_id, created_at)
            SELECT gen_random_uuid(), cps.company_id, 'ATENDENTE', cps.permission_id, now()
            FROM company_permission_seeds cps
            JOIN permissions p ON p.id = cps.permission_id
            WHERE p.code = ANY(:codes)
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp
                  WHERE rp.company_id = cps.company_id
                    AND rp.role = 'ATENDENTE'
                    AND rp.permission_id = cps.permission_id
              )
        """),
        {"codes": list(WAITER_CODES)},
    )


def downgrade() -> None:
    # PostgreSQL ne retire pas une valeur d'enum : seuls les droits du role sont retires.
    bind = op.get_bind()
    n = bind.execute(sa.text("SELECT count(*) FROM users WHERE role = 'ATENDENTE'")).scalar()
    if n:
        raise RuntimeError(f"{n} utilisateur(s) ont encore le role ATENDENTE : changer leur role avant.")
    bind.execute(sa.text("DELETE FROM role_permissions WHERE role = 'ATENDENTE'"))
