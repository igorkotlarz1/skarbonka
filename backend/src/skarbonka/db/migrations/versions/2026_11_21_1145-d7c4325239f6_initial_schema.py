"""Initial schema: accounts, imports, transactions, allocations and lookups (M4).

Revision ID: d7c4325239f6
Revises:
Create Date: 2026-11-21 11:45:05.491679

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d7c4325239f6"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # pgvector is needed from M6 (embeddings); enabling it here keeps every DB ready.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bank", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
        sa.UniqueConstraint("bank", "name", name=op.f("uq_accounts_bank")),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("entity", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["categories.id"], name=op.f("fk_categories_parent_id_categories")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("parent_id", "name", name=op.f("uq_categories_parent_id")),
    )
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bank", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("rows_parsed", sa.Integer(), nullable=False),
        sa.Column("inserted", sa.Integer(), nullable=False),
        sa.Column("duplicates", sa.Integer(), nullable=False),
        sa.Column("holds_skipped", sa.Integer(), nullable=False),
        sa.Column("quarantined", sa.Integer(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('ok', 'failed')", name=op.f("ck_import_batches_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_batches")),
    )
    op.create_index(op.f("ix_import_batches_sha256"), "import_batches", ["sha256"], unique=False)
    op.create_table(
        "settlements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('draft', 'sent')", name=op.f("ck_settlements_status")),
        sa.CheckConstraint("period_start <= period_end", name=op.f("ck_settlements_period")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settlements")),
    )
    op.create_table(
        "merchants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("default_category_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["default_category_id"],
            ["categories.id"],
            name=op.f("fk_merchants_default_category_id_categories"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merchants")),
        sa.UniqueConstraint("name", name=op.f("uq_merchants_name")),
    )
    op.create_table(
        "rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("personal", sa.Boolean(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], name=op.f("fk_rules_category_id_categories")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rules")),
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("import_batch_id", sa.Integer(), nullable=False),
        sa.Column("dedup_key", sa.String(length=128), nullable=False),
        sa.Column("transaction_number", sa.String(length=64), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("booking_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("original_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("original_currency", sa.String(length=3), nullable=True),
        sa.Column("counterparty", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("counterparty_account", sa.String(length=64), nullable=False),
        sa.Column("operation_code", sa.String(length=32), nullable=False),
        sa.Column("operation_kind", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount <> 0", name=op.f("ck_transactions_amount_not_zero")),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name=op.f("fk_transactions_account_id_accounts")
        ),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batches.id"],
            name=op.f("fk_transactions_import_batch_id_import_batches"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
        sa.UniqueConstraint("dedup_key", name=op.f("uq_transactions_dedup_key")),
    )
    op.create_index(
        "ix_transactions_account_date",
        "transactions",
        ["account_id", "transaction_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transactions_import_batch_id"), "transactions", ["import_batch_id"], unique=False
    )
    op.create_table(
        "allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("personal", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("settlement_id", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('import', 'rule', 'merchant', 'ml', 'llm', 'manual')",
            name=op.f("ck_allocations_source"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1",
            name=op.f("ck_allocations_confidence"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], name=op.f("fk_allocations_category_id_categories")
        ),
        sa.ForeignKeyConstraint(
            ["settlement_id"],
            ["settlements.id"],
            name=op.f("fk_allocations_settlement_id_settlements"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name=op.f("fk_allocations_transaction_id_transactions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_allocations")),
    )
    op.create_index(
        op.f("ix_allocations_category_id"), "allocations", ["category_id"], unique=False
    )
    op.create_index(
        op.f("ix_allocations_settlement_id"), "allocations", ["settlement_id"], unique=False
    )
    op.create_index(
        op.f("ix_allocations_transaction_id"), "allocations", ["transaction_id"], unique=False
    )
    op.create_table(
        "merchant_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("merchant_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=300), nullable=False),
        sa.ForeignKeyConstraint(
            ["merchant_id"],
            ["merchants.id"],
            name=op.f("fk_merchant_aliases_merchant_id_merchants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merchant_aliases")),
        sa.UniqueConstraint("alias", name=op.f("uq_merchant_aliases_alias")),
    )
    op.create_index(
        op.f("ix_merchant_aliases_merchant_id"), "merchant_aliases", ["merchant_id"], unique=False
    )
    op.create_table(
        "raw_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("import_batch_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('inserted', 'duplicate', 'hold_skipped', 'quarantined')",
            name=op.f("ck_raw_rows_status"),
        ),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batches.id"],
            name=op.f("fk_raw_rows_import_batch_id_import_batches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name=op.f("fk_raw_rows_transaction_id_transactions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_rows")),
    )
    op.create_index(
        op.f("ix_raw_rows_import_batch_id"), "raw_rows", ["import_batch_id"], unique=False
    )
    op.create_index(
        op.f("ix_raw_rows_transaction_id"), "raw_rows", ["transaction_id"], unique=False
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_raw_rows_transaction_id"), table_name="raw_rows")
    op.drop_index(op.f("ix_raw_rows_import_batch_id"), table_name="raw_rows")
    op.drop_table("raw_rows")
    op.drop_index(op.f("ix_merchant_aliases_merchant_id"), table_name="merchant_aliases")
    op.drop_table("merchant_aliases")
    op.drop_index(op.f("ix_allocations_transaction_id"), table_name="allocations")
    op.drop_index(op.f("ix_allocations_settlement_id"), table_name="allocations")
    op.drop_index(op.f("ix_allocations_category_id"), table_name="allocations")
    op.drop_table("allocations")
    op.drop_index(op.f("ix_transactions_import_batch_id"), table_name="transactions")
    op.drop_index("ix_transactions_account_date", table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("rules")
    op.drop_table("merchants")
    op.drop_table("settlements")
    op.drop_index(op.f("ix_import_batches_sha256"), table_name="import_batches")
    op.drop_table("import_batches")
    op.drop_table("categories")
    op.drop_table("audit_log")
    op.drop_table("accounts")
    # ### end Alembic commands ###
