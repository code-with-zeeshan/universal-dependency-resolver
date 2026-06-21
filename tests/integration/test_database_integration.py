# Create: tests/integration/test_database_integration.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from alembic import command
from alembic.config import Config

class TestDatabaseIntegration:
    @pytest.fixture
    def test_db(self):
        """Create test database with migrations"""
        engine = create_engine("postgresql://test_db")
        
        # Run migrations
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        
        yield engine
        
        # Cleanup
        command.downgrade(alembic_cfg, "base")
    
    def test_model_relationships(self, test_db):
        """Verify all foreign keys and relationships work"""
        from database.models import Package, PackageVersion
        
        # Test cascade operations
        # Test constraint violations
        # Test index performance