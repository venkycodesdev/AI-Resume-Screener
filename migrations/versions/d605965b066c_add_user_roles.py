"""Add user roles

Revision ID: d605965b066c
Revises: adca466b46ae
Create Date: 2026-09-13 12:57:46.533624

"""
from alembic import op
import sqlalchemy as sa


revision = "d605965b066c"
down_revision = "adca466b46ae"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "role",
                sa.String(length=20),
                server_default="candidate",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_user_role_allowed",
            "role IN ('candidate', 'recruiter', 'admin')",
        )


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_user_role_allowed",
            type_="check",
        )
        batch_op.drop_column("role")