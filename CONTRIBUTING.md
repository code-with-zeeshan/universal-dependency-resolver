# Contributing to Universal Dependency Resolver 🤝

Thank you for your interest in contributing to the Universal Dependency Resolver! This document provides guidelines and information for contributors.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Contributing Guidelines](#contributing-guidelines)
- [Pull Request Process](#pull-request-process)
- [Issue Guidelines](#issue-guidelines)
- [Code Standards](#code-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation Standards](#documentation-standards)
- [Community](#community)

## 📜 Code of Conduct

This project and everyone participating in it is governed by our Code of Conduct. By participating, you are expected to uphold this code.

### Our Pledge

We pledge to make participation in our project a harassment-free experience for everyone, regardless of:
- Age, body size, disability, ethnicity, gender identity and expression
- Level of experience, nationality, personal appearance, race, religion
- Sexual identity and orientation

### Our Standards

**Positive behavior includes:**
- ✅ Using welcoming and inclusive language
- ✅ Being respectful of differing viewpoints and experiences
- ✅ Gracefully accepting constructive criticism
- ✅ Focusing on what is best for the community
- ✅ Showing empathy towards other community members

**Unacceptable behavior includes:**
- ❌ Trolling, insulting/derogatory comments, and personal attacks
- ❌ Public or private harassment
- ❌ Publishing others' private information without permission
- ❌ Other conduct which could reasonably be considered inappropriate

## 🚀 Getting Started

### Prerequisites

Before contributing, ensure you have:

- **Git** installed and configured
- **Python 3.9+** for backend development
- **Node.js 16+** for frontend development
- **Docker & Docker Compose** for local development
- **PostgreSQL 15+** (or use Docker)
- **Redis 7+** (or use Docker)

### Quick Setup

```bash
# 1. Fork and clone the repository
git clone https://github.com/yourusername/universal-dependency-resolver.git
cd universal-dependency-resolver

# 2. Set up development environment
cp .env.example .env
# Edit .env with your local configuration

# 3. Start with Docker (recommended)
docker-compose up -d

# 4. Or set up manually
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head

# Frontend
cd frontend
npm install
npm run serve
```

## 🛠️ Development Setup

### Backend Development

```bash
# Install development dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov black flake8 mypy

# Set up pre-commit hooks
pre-commit install

# Run backend server
uvicorn backend.api.main:app --reload

# Run tests
pytest tests/ -v --cov=.

# Format code
black .
flake8 .
```
### Frontend Development

```bash
# Install dependencies
npm install

# Start development server
npm run serve

# Run tests
npm run test:unit

# Lint code
npm run lint

# Build for production
npm run build
```
### Database Management

```bash
# Create new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```
## 📝 Contributing Guidelines

### Types of Contributions

#### We welcome various types of contributions:

Type	                     Description	                        Labels
🐛 Bug Fixes	             Fix existing issues	                bug, fix
✨ Features	                Add new functionality	               enhancement, feature
📚 Documentation	         Improve docs	                        documentation
🧪 Tests	                 Add or improve tests	                testing
🎨 UI/UX	                 Frontend improvements	                frontend, ui/ux
⚡ Performance	             Optimize performance	                 performance
🔧 Refactoring	             Code improvements	                     refactor
🔒 Security	                 Security enhancements	                 security
📊 Monitoring	             Add monitoring/metrics	               monitoring
🔄 Async/Concurrency	     Improve async processing	             async, concurrency

### Contribution Workflow

```bash
graph LR
    A[Fork Repository] --> B[Create Branch]
    B --> C[Make Changes]
    C --> D[Write Tests]
    D --> E[Update Documentation]
    E --> F[Commit Changes]
    F --> G[Push Branch]
    G --> H[Create Pull Request]
    H --> I[Code Review]
    I --> J[Merge]
```

### Branch Naming Convention

#### Use descriptive branch names with prefixes:

```bash
# Feature branches
feature/add-rust-ecosystem-support
feature/improve-dependency-resolution

# Bug fix branches
fix/package-search-timeout
fix/authentication-token-refresh

# Documentation branches
docs/update-api-documentation
docs/add-deployment-guide

# Hotfix branches (for production issues)
hotfix/critical-security-patch
```
## 🔄 Pull Request Process

### Before Submitting

* Code quality: Ensure code passes all linters
* Tests: Add tests for new functionality
* Documentation: Update relevant documentation
* Changelog: Add entry to CHANGELOG.md
* Commits: Use conventional commit messages

### PR Checklist

```bash
## 📋 Pull Request Checklist

- [ ] I have read the [Contributing Guidelines](CONTRIBUTING.md)
- [ ] My code follows the project's style guidelines
- [ ] I have performed a self-review of my code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] Any dependent changes have been merged and published

## 📖 Description

Brief description of changes and why they're needed.

## 🧪 Testing

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## 📚 Documentation

- [ ] README updated
- [ ] API documentation updated
- [ ] Code comments added

## 🔗 Related Issues

Closes #123
Relates to #456
```
### PR Title Format

#### Use conventional commit format:

```bash
<type>(<scope>): <description>

Examples:
feat(api): add support for Rust crates ecosystem
fix(frontend): resolve package search timeout issue
docs(readme): update installation instructions
test(backend): add unit tests for conflict resolver
```
### Review Process

* Automated Checks: CI/CD pipeline runs automatically
* Code Review: At least one maintainer reviews the code
* Testing: Reviewers test the changes locally if needed
* Approval: PR approved by maintainer(s)
* Merge: Squash and merge into main branch

## 🐛 Issue Guidelines

### Bug Reports

#### Use our bug report template:

```bash
## 🐛 Bug Report

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

**Expected behavior**
A clear and concise description of what you expected to happen.

**Screenshots**
If applicable, add screenshots to help explain your problem.

**Environment:**
- OS: [e.g. Ubuntu 20.04]
- Python Version: [e.g. 3.9.16]
- Browser: [e.g. Chrome 91]
- Version: [e.g. 1.2.3]

**Additional context**
Add any other context about the problem here.
```
### Feature Requests

```bash
## ✨ Feature Request

**Is your feature request related to a problem? Please describe.**
A clear and concise description of what the problem is.

**Describe the solution you'd like**
A clear and concise description of what you want to happen.

**Describe alternatives you've considered**
A clear and concise description of any alternative solutions or features you've considered.

**Additional context**
Add any other context or screenshots about the feature request here.
```
## 📏 Code Standards

### Python (Backend)

* Style Guide: Follow PEP 8
* Formatter: Black with line length 88
* Linter: Flake8 with max line length 127
* Type Hints: Use type hints for all functions
* Docstrings: Use Google-style docstrings

```bash
def resolve_dependencies(
    packages: List[Package], 
    system_info: SystemInfo
) -> DependencyTree:
    """Resolve package dependencies with conflict resolution.
    
    Args:
        packages: List of packages to resolve
        system_info: Target system information
        
    Returns:
        Resolved dependency tree with conflicts handled
        
    Raises:
        DependencyResolutionError: If resolution fails
    """
    pass
```
### JavaScript/Vue.js (Frontend)

* Style Guide: ESLint with Vue.js plugin
* Formatter: Prettier with 2-space indentation
* Components: Use Composition API and <script setup>
* Naming: PascalCase for components, camelCase for functions

```bash
<script setup>
import { ref, computed, onMounted } from 'vue'

// Props with TypeScript-style definition
const props = defineProps({
  packages: {
    type: Array,
    required: true
  }
})

// Reactive data
const loading = ref(false)
const results = ref([])

// Computed properties
const filteredResults = computed(() => {
  return results.value.filter(result => result.compatible)
})

// Methods
const searchPackages = async (query) => {
  loading.value = true
  try {
    // Implementation
  } finally {
    loading.value = false
  }
}

// Lifecycle
onMounted(() => {
  searchPackages()
})
</script>
```
### Commit Message Format

#### Use Conventional Commits:

```bash
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]

Types:
- feat: A new feature
- fix: A bug fix
- docs: Documentation only changes
- style: Changes that do not affect the meaning of the code
- refactor: A code change that neither fixes a bug nor adds a feature
- perf: A code change that improves performance
- test: Adding missing tests or correcting existing tests
- build: Changes that affect the build system or external dependencies
- ci: Changes to CI configuration files and scripts
- chore: Other changes that don't modify src or test files

Examples:
feat(api): add support for Go modules
fix(frontend): resolve search input validation
docs(readme): update installation instructions
test(backend): add integration tests for conflict resolver
```

## 🧪 Testing Guidelines

### Backend Testing

```bash
# Test file naming: test_*.py
# Test class naming: TestClassName
# Test method naming: test_method_name_scenario

import pytest
from backend.core.conflict_resolver import ConflictResolver

class TestConflictResolver:
    """Test cases for dependency conflict resolution."""
    
    @pytest.fixture
    def resolver(self):
        """Create a ConflictResolver instance for testing."""
        return ConflictResolver()
    
    def test_resolve_simple_dependency(self, resolver):
        """Test resolving a simple dependency without conflicts."""
        # Arrange
        packages = [{"name": "numpy", "version": ">=1.20.0"}]
        
        # Act
        result = resolver.resolve_dependencies(packages)
        
        # Assert
        assert result.success
        assert "numpy" in result.resolved
    
    @pytest.mark.asyncio
    async def test_resolve_with_conflicts(self, resolver):
        """Test resolving dependencies with version conflicts."""
        # Implementation
        pass
```
### Frontend Testing

```bash
// Component test example
import { mount } from '@vue/test-utils'
import PackageCard from '@/components/PackageCard.vue'

describe('PackageCard.vue', () => {
  const mockPackage = {
    name: 'vue',
    ecosystem: 'npm',
    version: '3.3.0',
    description: 'The progressive JavaScript framework'
  }

  it('renders package information correctly', () => {
    const wrapper = mount(PackageCard, {
      props: { package: mockPackage }
    })
    
    expect(wrapper.find('.package-name').text()).toBe('vue')
    expect(wrapper.find('.ecosystem-badge').text()).toBe('NPM')
  })

  it('emits click event when clicked', async () => {
    const wrapper = mount(PackageCard, {
      props: { package: mockPackage }
    })
    
    await wrapper.trigger('click')
    
    expect(wrapper.emitted('click')).toBeTruthy()
    expect(wrapper.emitted('click')[0]).toEqual([mockPackage])
  })
})
```
### Test Coverage Requirements

* Backend: Minimum 80% code coverage
* Frontend: Minimum 70% code coverage
* Critical paths: 95% coverage required
* New features: Must include comprehensive tests

## 📚 Documentation Standards

### Code Documentation

* Functions: Document all public functions and methods
* Classes: Include class-level documentation
* Modules: Add module-level docstrings
* Type hints: Use type hints consistently

### API Documentation

* OpenAPI: Keep OpenAPI specs up to date
* Examples: Include practical examples
* Error codes: Document all error responses
* Rate limits: Document rate limiting

### User Documentation

* README: Keep installation and usage up to date
* Guides: Write step-by-step guides for complex features
* Troubleshooting: Document common issues and solutions
* Changelog: Maintain detailed changelog

## 👥 Community

### Getting Help

* Discord: Join our Discord server
* GitHub Discussions: Use for questions and discussions
* Issues: Use for bug reports and feature requests
* Email: maintainers@yourdomain.com for sensitive topics

### Recognition

#### Contributors are recognized in:

* README: Contributors section
* Releases: Release notes mention contributors
* Discord: Special contributor role
* Website: Contributors page (if applicable)

### Maintainers

#### Current maintainers:

Name	             GitHub	                Role	         Focus Area
Mohammad Zeeshan	@codewithzeeshan	 Lead Maintainer	  Architecture, Backend
Mohammad Zeeshan	@codewithzeeshan	 Frontend Lead	      UI/UX, Frontend
Mohammad Zeeshan	@codewithzeeshan	 DevOps Lead	      CI/CD, Infrastructure

## 🎯 Development Roadmap

### Current Sprint
- ✅ Multi-ecosystem package search
- ✅ Dependency conflict resolution
- ✅ System compatibility checking
- 🔄 Performance optimization for large dependency trees

### Next Sprint
- 📦 Add more ecosystem support
- 🛡️ Implement dependency vulnerability scanning
- 📊 Add package recommendation system

### Future Releases (Q2-Q3 2026)
- **📚 Official SDK Libraries**
  - Python SDK with async support
  - JavaScript/TypeScript SDK
  - Go client library
  - Command-line interface (CLI)
- **🔌 WebSocket Support** for real-time updates
- **🤖 Machine learning** for conflict resolution
- **📈 Visual dependency graphs**
- **🔧 Plugin system** for custom ecosystems

### SDK Development Roadmap
- [ ] Define SDK specifications and API standards
- [ ] Create OpenAPI code generation pipeline
- [ ] Develop Python SDK with full test coverage
- [ ] Build JavaScript/TypeScript SDK
- [ ] Create CLI tool using Click/Typer
- [ ] Write comprehensive SDK documentation
- [ ] Set up SDK versioning and release process

## 📄 License

By contributing to Universal Dependency Resolver, you agree that your contributions will be licensed under the same license as the project (MIT License).

Thank you for contributing to Universal Dependency Resolver! 🎉

Together, we're building the future of dependency management across all ecosystems.