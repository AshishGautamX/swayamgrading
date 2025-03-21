"""Models with named constraints

Revision ID: db0a187dada6
Revises: 6cfb4e7b501c
Create Date: 2025-03-12 15:37:44.218421

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'db0a187dada6'
down_revision = '6cfb4e7b501c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('class', schema=None) as batch_op:
        batch_op.add_column(sa.Column('type', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('rubric_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_googleclass_rubric', 'rubric', ['rubric_id'], ['id'])

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('google_tokens', sa.Text(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('google_tokens')

    with op.batch_alter_table('class', schema=None) as batch_op:
        batch_op.drop_constraint('fk_googleclass_rubric', type_='foreignkey')
        batch_op.drop_column('rubric_id')
        batch_op.drop_column('type')

    # ### end Alembic commands ###
