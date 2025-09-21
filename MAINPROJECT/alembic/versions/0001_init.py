from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '0001_init'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
	op.create_table(
		'service',
		sa.Column('id', sa.Integer, primary_key=True),
		sa.Column('name', sa.String(200), nullable=False, unique=True),
		sa.Column('url', sa.String(2048), nullable=False),
		sa.Column('interval_s', sa.Integer, nullable=False),
		sa.Column('timeout_s', sa.Integer, nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
	)
	op.create_table(
		'check_result',
		sa.Column('id', sa.Integer, primary_key=True),
		sa.Column('service_id', sa.Integer, sa.ForeignKey('service.id', ondelete='CASCADE'), nullable=False),
		sa.Column('ts', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.Column('ok', sa.Boolean, nullable=False),
		sa.Column('status_code', sa.Integer),
		sa.Column('latency_ms', sa.Integer),
		sa.Column('error_text', sa.String(512)),
	)
	op.create_index('idx_check_results_service_ts', 'check_result', ['service_id','ts'])
	op.create_table(
		'incident',
		sa.Column('id', sa.Integer, primary_key=True),
		sa.Column('service_id', sa.Integer, sa.ForeignKey('service.id', ondelete='CASCADE'), nullable=False),
		sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('closed_at', sa.DateTime(timezone=True)),
		sa.Column('fail_count', sa.Integer, nullable=False),
		sa.Column('is_open', sa.Boolean, nullable=False),
	)


def downgrade() -> None:
	op.drop_table('incident')
	op.drop_index('idx_check_results_service_ts', table_name='check_result')
	op.drop_table('check_result')
	op.drop_table('service') 