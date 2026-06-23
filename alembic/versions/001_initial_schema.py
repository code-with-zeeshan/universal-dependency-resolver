"""Initial schema creation

Revision ID: 001
Revises: 
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create packages table
    op.create_table(
        "packages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("ecosystem", sa.String(length=50), nullable=False),
        sa.Column("latest_version", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("homepage", sa.String(length=500), nullable=True),
        sa.Column("repository", sa.String(length=500), nullable=True),
        sa.Column("license", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "ecosystem", name="_name_ecosystem_uc"),
    )
    op.create_index("idx_package_ecosystem", "packages", ["ecosystem"], unique=False)
    op.create_index("idx_package_name", "packages", ["name"], unique=False)
    op.create_index(
        "idx_package_name_ecosystem", "packages", ["name", "ecosystem"], unique=False
    )

    # Create package_versions table
    op.create_table(
        "package_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("release_date", sa.DateTime(), nullable=True),
        sa.Column("python_requires", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("download_count", sa.Integer(), nullable=True),
        sa.Column("system_requirements", sa.JSON(), nullable=True),
        sa.Column("dependencies", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["packages.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_id", "version", name="_package_version_uc"),
    )
    op.create_index(
        "idx_version_package_id", "package_versions", ["package_id"], unique=False
    )
    op.create_index(
        "idx_version_version", "package_versions", ["version"], unique=False
    )

    # Create compatibility_reports table
    op.create_table(
        "compatibility_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("os_name", sa.String(length=50), nullable=True),
        sa.Column("os_version", sa.String(length=50), nullable=True),
        sa.Column("cpu_architecture", sa.String(length=50), nullable=True),
        sa.Column("gpu_name", sa.String(length=255), nullable=True),
        sa.Column("cuda_version", sa.String(length=20), nullable=True),
        sa.Column("cudnn_version", sa.String(length=20), nullable=True),
        sa.Column("python_version", sa.String(length=20), nullable=True),
        sa.Column("system_info", sa.JSON(), nullable=True),
        sa.Column("works", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("user_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["packages.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_report_created", "compatibility_reports", ["created_at"], unique=False
    )
    op.create_index(
        "idx_report_package_version",
        "compatibility_reports",
        ["package_id", "version"],
        unique=False,
    )

    # Create conflict_rules table
    op.create_table(
        "conflict_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("package1_id", sa.Integer(), nullable=False),
        sa.Column("package1_version_spec", sa.String(length=100), nullable=True),
        sa.Column("package2_id", sa.Integer(), nullable=False),
        sa.Column("package2_version_spec", sa.String(length=100), nullable=True),
        sa.Column("conflict_type", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["package1_id"],
            ["packages.id"],
        ),
        sa.ForeignKeyConstraint(
            ["package2_id"],
            ["packages.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_conflict_packages",
        "conflict_rules",
        ["package1_id", "package2_id"],
        unique=False,
    )

    # Create verified_combinations table
    op.create_table(
        "verified_combinations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("packages", sa.JSON(), nullable=False),
        sa.Column("system_requirements", sa.JSON(), nullable=True),
        sa.Column("verified_by", sa.String(length=100), nullable=True),
        sa.Column("verification_date", sa.DateTime(), nullable=True),
        sa.Column("test_results", sa.JSON(), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=True),
        sa.Column("success_rate", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_combination_created", "verified_combinations", ["created_at"], unique=False
    )
    op.create_index(
        "idx_combination_name", "verified_combinations", ["name"], unique=False
    )

    # Create system_benchmarks table
    op.create_table(
        "system_benchmarks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("system_hash", sa.String(length=64), nullable=True),
        sa.Column("os_name", sa.String(length=50), nullable=True),
        sa.Column("os_version", sa.String(length=50), nullable=True),
        sa.Column("cpu_model", sa.String(length=255), nullable=True),
        sa.Column("cpu_cores", sa.Integer(), nullable=True),
        sa.Column("ram_gb", sa.Float(), nullable=True),
        sa.Column("gpu_model", sa.String(length=255), nullable=True),
        sa.Column("gpu_memory_gb", sa.Float(), nullable=True),
        sa.Column("system_info", sa.JSON(), nullable=True),
        sa.Column("benchmarks", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("system_hash"),
    )
    op.create_index(
        "idx_benchmark_hash", "system_benchmarks", ["system_hash"], unique=False
    )

    # Create resolution_cache table
    op.create_table(
        "resolution_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.Column("packages", sa.JSON(), nullable=True),
        sa.Column("system_info", sa.JSON(), nullable=True),
        sa.Column("constraints", sa.JSON(), nullable=True),
        sa.Column("resolution", sa.JSON(), nullable=True),
        sa.Column("resolution_time_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("hit_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_hash"),
    )
    op.create_index(
        "idx_resolution_created", "resolution_cache", ["created_at"], unique=False
    )
    op.create_index(
        "idx_resolution_expires", "resolution_cache", ["expires_at"], unique=False
    )
    op.create_index(
        "idx_resolution_hash", "resolution_cache", ["request_hash"], unique=False
    )


def downgrade() -> None:
    # Drop all tables in reverse order
    op.drop_index("idx_resolution_hash", table_name="resolution_cache")
    op.drop_index("idx_resolution_expires", table_name="resolution_cache")
    op.drop_index("idx_resolution_created", table_name="resolution_cache")
    op.drop_table("resolution_cache")

    op.drop_index("idx_benchmark_hash", table_name="system_benchmarks")
    op.drop_table("system_benchmarks")

    op.drop_index("idx_combination_name", table_name="verified_combinations")
    op.drop_index("idx_combination_created", table_name="verified_combinations")
    op.drop_table("verified_combinations")

    op.drop_index("idx_conflict_packages", table_name="conflict_rules")
    op.drop_table("conflict_rules")

    op.drop_index("idx_report_package_version", table_name="compatibility_reports")
    op.drop_index("idx_report_created", table_name="compatibility_reports")
    op.drop_table("compatibility_reports")

    op.drop_index("idx_version_version", table_name="package_versions")
    op.drop_index("idx_version_package_id", table_name="package_versions")
    op.drop_table("package_versions")

    op.drop_index("idx_package_name_ecosystem", table_name="packages")
    op.drop_index("idx_package_name", table_name="packages")
    op.drop_index("idx_package_ecosystem", table_name="packages")
    op.drop_table("packages")
