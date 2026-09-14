"""Add DocumentAudit model

Revision ID: d7205ab3373c
Revises: 
Create Date: 2026-08-02 01:55:56.560131

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7205ab3373c'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'document_audit',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('document_id', sa.Integer(), sa.ForeignKey('generated_document.id'), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=True),
        sa.Column('performed_by', sa.Integer(), sa.ForeignKey('admin.id'), nullable=True),
        sa.Column('performed_by_role', sa.String(length=20), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('document_audit')
