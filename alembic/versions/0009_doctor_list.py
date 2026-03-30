"""0009 — practice_doctors table

Adds the practice_doctors table, which stores an ordered list of doctor
names for each practice. Used to populate a dropdown on the patient
Contact screen.

Columns:
- id:            integer primary key (auto-increment)
- practice_id:   foreign key to practices
- name:          doctor display name, not null
- display_order: integer used to sort the list; rewritten in full on every
                 save so ordering is always explicit

Revision ID: 0009
Revises: 0008
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE practice_doctors (
            id            SERIAL      PRIMARY KEY,
            practice_id   TEXT        NOT NULL REFERENCES practices(practice_id),
            name          TEXT        NOT NULL,
            display_order INTEGER     NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS practice_doctors")