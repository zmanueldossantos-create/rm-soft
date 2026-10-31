"""Modo formação / demonstração: companies.training_mode (documents issued in mode FORMACAO, their own series, never
sent to the AGT, out of the SAF-T and the VAT, printed with a watermark), goods_movements.is_training; on for the demo
company and the companies on a TESTE contract.

Revision ID: s5q9j3d71i03
Revises: r4p8i2c60h92
"""
import sqlalchemy as sa
from alembic import op

revision = "s5q9j3d71i03"
down_revision = "r4p8i2c60h92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("training_mode", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("goods_movements", sa.Column("is_training", sa.Boolean(), server_default="false", nullable=False))
    # the companies whose current contract is a TESTE one start in Modo formação (their documents to come)
    op.execute("""
        UPDATE companies SET training_mode = true
        WHERE id IN (SELECT company_id FROM company_contracts WHERE is_current AND billing = 'TESTE')
    """)


def downgrade() -> None:
    op.drop_column("goods_movements", "is_training")
    op.drop_column("companies", "training_mode")
