# tests/unit/test_core/test_export_generator.py
import pytest
from backend.core.export_generator import (
    ExportGenerator,
    PackageInfo,
    PackageEcosystem,
)


class TestExportGenerator:
    @pytest.fixture
    def generator(self):
        """Create ExportGenerator instance for testing"""
        return ExportGenerator()

    @pytest.fixture
    def sample_packages(self):
        """Sample resolved packages for testing"""
        return {
            'numpy': {'version': '1.24.3', 'ecosystem': 'pypi'},
            'pandas': {'version': '2.0.1', 'ecosystem': 'pypi'},
            'react': {'version': '18.2.0', 'ecosystem': 'npm'}
        }

    @pytest.fixture
    def sample_system_info(self):
        """Sample system info for testing"""
        return {
            'os': {'system': 'Linux', 'release': '5.15.0', 'machine': 'x86_64'},
            'runtime_versions': {
                'python': {'version': '3.9.16'},
                'node': {'version': '18.17.0'},
            },
            'gpu': {'available': False},
        }

    def test_initialization(self, generator):
        """Test ExportGenerator initialization"""
        assert isinstance(generator.formats, dict)
        assert generator.formats == {}
        assert 'requirements.txt' in generator.template_map
        assert 'package.json' in generator.template_map
        assert 'Dockerfile' in generator.template_map

    def test_generate_requirements_txt(self, generator, sample_packages, sample_system_info):
        """Test requirements.txt generation"""
        result = generator.generate(
            sample_packages,
            'requirements.txt',
            sample_system_info
        )

        assert isinstance(result, str)
        assert 'numpy==1.24.3' in result
        assert 'pandas==2.0.1' in result
        assert 'react' not in result  # Should only include Python packages

    def test_generate_package_json(self, generator, sample_packages, sample_system_info):
        """Test package.json generation"""
        result = generator.generate(
            sample_packages,
            'package.json',
            sample_system_info
        )

        assert isinstance(result, str)
        assert '"react": "18.2.0"' in result
        assert 'numpy' not in result  # Should only include npm packages
        assert 'pandas' not in result

    def test_generate_empty_packages_raises_error(self, generator):
        """Test that empty packages raise ValueError"""
        with pytest.raises(ValueError, match="No packages provided"):
            generator.generate({}, 'requirements.txt')

    def test_generate_unsupported_format_raises_error(self, generator, sample_packages):
        """Test that unsupported format raises ValueError"""
        with pytest.raises(ValueError, match="Unsupported format"):
            generator.generate(sample_packages, 'unsupported.format')

    def test_generate_multiple_formats(self, generator, sample_packages, sample_system_info):
        """Test generating multiple formats at once"""
        formats = ['requirements.txt', 'package.json']
        result = generator.generate_multiple(
            sample_packages,
            formats,
            sample_system_info
        )

        assert isinstance(result, dict)
        assert 'requirements.txt' in result
        assert 'package.json' in result
        assert 'numpy==1.24.3' in result['requirements.txt']
        assert '"react": "18.2.0"' in result['package.json']

    def test_register_custom_format(self, generator):
        """Test registering a custom export format"""
        class CustomFormat:
            def generate(self, packages, system_info, options):
                return "custom output"

        generator.register_format('custom', CustomFormat())
        result = generator.generate({'test': {'version': '1.0.0'}}, 'custom')

        assert result == "custom output"

    def test_parse_packages(self, generator, sample_packages):
        """Test internal package parsing"""
        parsed = generator._parse_packages(sample_packages)

        assert len(parsed) == 3
        assert any(pkg.name == 'numpy' and pkg.version == '1.24.3' for pkg in parsed)
        assert any(pkg.name == 'react' and pkg.version == '18.2.0' for pkg in parsed)

    def test_generate_with_options(self, generator, sample_packages, sample_system_info):
        """Test generation with custom options"""
        options = {'include_comments': False, 'pin_versions': False}
        result = generator.generate(
            sample_packages,
            'requirements.txt',
            sample_system_info,
            options
        )

        assert isinstance(result, str)
        assert 'numpy>=1.24.3' in result  # unpinned with pin_versions=False

    def test_save_to_file_basic(self, generator, tmp_path):
        """Test basic file saving functionality"""
        content = "test content"
        filepath = tmp_path / "test.txt"

        generator.save_to_file(content, filepath, 'requirements.txt')

        assert filepath.exists()
        assert filepath.read_text() == content

    def test_save_to_file_creates_directories(self, generator, tmp_path):
        """Test that save_to_file creates parent directories"""
        content = "test content"
        filepath = tmp_path / "subdir" / "nested" / "test.txt"

        generator.save_to_file(content, filepath, 'requirements.txt')

        assert filepath.exists()
        assert filepath.read_text() == content