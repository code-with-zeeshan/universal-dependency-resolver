from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from backend.data_sources.npm_client import NPMClient


class TestNPMClient:

    @pytest.fixture
    def client(self):
        return NPMClient()

    @pytest.fixture
    def sample_search_response(self):
        return {
            "objects": [
                {
                    "package": {
                        "name": "express",
                        "version": "4.18.2",
                        "description": "Fast, unopinionated, minimalist web framework",
                        "keywords": ["express", "framework", "web"],
                        "date": "2023-12-01T00:00:00.000Z",
                        "publisher": {"username": "expressjs", "email": "express@example.com"},
                        "maintainers": [{"username": "dougwilson"}],
                        "links": {
                            "npm": "https://www.npmjs.com/package/express",
                            "homepage": "http://expressjs.com/",
                            "repository": "https://github.com/expressjs/express",
                            "bugs": "https://github.com/expressjs/express/issues"
                        },
                        "license": "MIT",
                        "scope": "unscoped"
                    },
                    "score": {
                        "final": 0.99,
                        "detail": {
                            "quality": 0.98,
                            "popularity": 0.99,
                            "maintenance": 0.97
                        }
                    },
                    "searchScore": 95.0
                }
            ],
            "total": 1
        }

    @pytest.fixture
    def sample_package_response(self):
        return {
            "name": "express",
            "description": "Fast, unopinionated, minimalist web framework",
            "dist-tags": {"latest": "4.18.2"},
            "versions": {
                "4.18.2": {
                    "name": "express",
                    "version": "4.18.2",
                    "description": "Fast, unopinionated, minimalist web framework",
                    "dependencies": {"accepts": "~1.3.8", "debug": "2.6.9"},
                    "engines": {"node": ">= 0.10.0"},
                    "license": "MIT",
                    "dist": {
                        "integrity": "sha512-some",
                        "shasum": "some",
                        "tarball": "https://registry.npmjs.org/express/-/express-4.18.2.tgz",
                        "unpackedSize": 250000,
                        "fileCount": 20
                    },
                    "scripts": {"test": "mocha --exit"}
                },
                "4.18.1": {
                    "name": "express",
                    "version": "4.18.1",
                    "description": "Express 4.18.1",
                    "dependencies": {"accepts": "~1.3.8"},
                    "engines": {"node": ">= 0.10.0"},
                    "license": "MIT"
                }
            },
            "time": {
                "created": "2010-01-02T00:00:00.000Z",
                "modified": "2023-12-01T00:00:00.000Z",
                "4.18.2": "2023-12-01T00:00:00.000Z",
                "4.18.1": "2023-10-15T00:00:00.000Z"
            },
            "homepage": "http://expressjs.com/",
            "keywords": ["express", "framework", "web"],
            "license": "MIT",
            "author": {"name": "TJ Holowaychuk", "email": "tj@example.com"},
            "maintainers": [
                {"name": "dougwilson", "email": "doug@example.com"}
            ],
            "repository": {"type": "git", "url": "https://github.com/expressjs/express"},
            "bugs": {"url": "https://github.com/expressjs/express/issues"},
            "readme": "# Express\nFast, unopinionated, minimalist web framework.",
            "users": {"user1": True}
        }

    @pytest.mark.asyncio
    async def test_search_packages_basic(self, client, sample_search_response):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=sample_search_response):
            results = await client.search_packages('express')
        assert len(results) == 1
        assert results[0]['name'] == 'express'
        assert results[0]['version'] == '4.18.2'
        assert results[0]['description'] == 'Fast, unopinionated, minimalist web framework'
        assert results[0]['license'] == 'MIT'
        assert 'score' in results[0]

    @pytest.mark.asyncio
    async def test_search_packages_correct_url(self, client, sample_search_response):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=sample_search_response) as mock_request:
            await client.search_packages('express', limit=10)
        mock_request.assert_called_once()
        url = mock_request.call_args[0][0]
        assert 'search' in url.lower()

    @pytest.mark.asyncio
    async def test_search_packages_passes_params(self, client, sample_search_response):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=sample_search_response) as mock_request:
            await client.search_packages('react', limit=5)
        url, params = mock_request.call_args[0][0], mock_request.call_args[1].get('params', {})
        assert params.get('text') == 'react'
        assert params.get('size') == 5

    @pytest.mark.asyncio
    async def test_search_packages_with_quality_filter(self, client, sample_search_response):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=sample_search_response):
            results = await client.search_packages('express', quality=0.5)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_packages_quality_filter_excludes(self, client, sample_search_response):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=sample_search_response):
            results = await client.search_packages('express', quality=0.99)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_packages_popularity_filter(self, client, sample_search_response):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=sample_search_response):
            results = await client.search_packages('express', popularity=0.5)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_packages_maintenance_filter(self, client, sample_search_response):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=sample_search_response):
            results = await client.search_packages('express', maintenance=0.5)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_packages_returns_empty_on_no_data(self, client):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=None):
            results = await client.search_packages('nonexistent')
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_handles_empty_objects(self, client):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value={"objects": []}):
            results = await client.search_packages('nothing')
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_extracts_score(self, client, sample_search_response):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=sample_search_response):
            results = await client.search_packages('express')
        assert results[0]['score']['final'] == 0.99
        assert results[0]['score']['quality'] == 0.98
        assert results[0]['score']['popularity'] == 0.99

    @pytest.mark.asyncio
    async def test_get_package_info_success(self, client, sample_package_response):
        with \
            patch.object(client, '_make_request', new_callable=AsyncMock, return_value=sample_package_response), \
            patch.object(client, '_check_typescript_support', new_callable=AsyncMock, return_value=None), \
            patch.object(client, '_get_download_stats', new_callable=AsyncMock, return_value={}), \
            patch.object(client, '_check_vulnerabilities', new_callable=AsyncMock, return_value=[]):
            result = await client.get_package_info('express')
        assert result is not None
        assert result['name'] == 'express'
        assert result['version'] == '4.18.2'
        assert result['description'] == 'Fast, unopinionated, minimalist web framework'
        assert 'versions' in result
        assert 'dist_tags' in result
        assert 'latest_version_info' in result

    @pytest.mark.asyncio
    async def test_get_package_info_handles_404(self, client):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info('nonexistent-package')
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_scoped_package(self, client):
        scoped_response = {
            "name": "@scope/test-package",
            "version": "1.0.0",
            "description": "A scoped test package",
            "dist-tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "name": "@scope/test-package",
                    "version": "1.0.0",
                    "dependencies": {},
                    "license": "MIT"
                }
            },
            "time": {"created": "2023-01-01T00:00:00.000Z", "modified": "2023-01-01T00:00:00.000Z", "1.0.0": "2023-01-01T00:00:00.000Z"},
            "license": "MIT"
        }
        with \
            patch.object(client, '_make_request', new_callable=AsyncMock, return_value=scoped_response) as mock_request, \
            patch.object(client, '_check_typescript_support', new_callable=AsyncMock, return_value=None), \
            patch.object(client, '_get_download_stats', new_callable=AsyncMock, return_value={}), \
            patch.object(client, '_check_vulnerabilities', new_callable=AsyncMock, return_value=[]):
            result = await client.get_package_info('@scope/test-package')
        assert result is not None
        assert result['name'] == '@scope/test-package'
        mock_request.assert_called_once()
        url = mock_request.call_args[0][0]
        assert '@scope/test-package' in url

    @pytest.mark.asyncio
    async def test_get_package_info_no_latest_tag(self, client, sample_package_response):
        no_tag = dict(sample_package_response)
        no_tag['dist-tags'] = {}
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=no_tag):
            result = await client.get_package_info('express')
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_includes_versions(self, client, sample_package_response):
        with \
            patch.object(client, '_make_request', new_callable=AsyncMock, return_value=sample_package_response), \
            patch.object(client, '_check_typescript_support', new_callable=AsyncMock, return_value=None), \
            patch.object(client, '_get_download_stats', new_callable=AsyncMock, return_value={}), \
            patch.object(client, '_check_vulnerabilities', new_callable=AsyncMock, return_value=[]):
            result = await client.get_package_info('express', include_versions=True)
        assert len(result['versions']) == 2

    @pytest.mark.asyncio
    async def test_get_package_version_success(self, client):
        version_data = {
            "name": "express",
            "version": "4.18.2",
            "description": "Fast, unopinionated, minimalist web framework",
            "dependencies": {"accepts": "~1.3.8"},
            "engines": {"node": ">= 0.10.0"},
            "license": "MIT",
            "dist": {"unpackedSize": 250000},
            "os": ["darwin", "linux"],
            "cpu": ["x64"]
        }
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=version_data):
            result = await client.get_package_version('express', '4.18.2')
        assert result is not None
        assert result['version'] == '4.18.2'
        assert 'dependencies' in result
        assert 'system_requirements' in result

    @pytest.mark.asyncio
    async def test_get_package_version_not_found(self, client):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=None):
            result = await client.get_package_version('express', '99.99.99')
        assert result is None

    @pytest.fixture
    def sample_versions_list(self):
        return [
            {'version': '5.0.0-beta.1', 'deprecated': None, 'published': '2023-11-01T00:00:00.000Z',
             'node': '>= 0.10.0', 'npm': None, 'dist': {}, 'hasNativeDeps': False},
            {'version': '4.18.2', 'deprecated': None, 'published': '2023-12-01T00:00:00.000Z',
             'node': '>= 0.10.0', 'npm': None, 'dist': {}, 'hasNativeDeps': False},
            {'version': '4.18.1', 'deprecated': 'This version is deprecated',
             'published': '2023-10-15T00:00:00.000Z',
             'node': '>= 0.10.0', 'npm': None, 'dist': {}, 'hasNativeDeps': False},
        ]

    @pytest.fixture
    def sample_package_info_response(self, sample_package_response, sample_versions_list):
        response = {k: v for k, v in sample_package_response.items() if k != 'versions'}
        response['versions'] = sample_versions_list
        response['latest_version_info'] = {
            'dependencies': {'dependencies': {'accepts': '~1.3.8'}},
            'engines': {'node': '>= 0.10.0'},
        }
        response['downloads'] = {}
        response['typescript'] = None
        response['vulnerabilities'] = []
        return response

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client, sample_package_info_response):
        with patch.object(client, 'get_package_info', new_callable=AsyncMock, return_value=sample_package_info_response):
            versions = await client.get_versions('express')
        assert len(versions) == 2
        assert all('version' in v for v in versions)
        assert all('published' in v for v in versions)
        assert all('dist' in v for v in versions)

    @pytest.mark.asyncio
    async def test_get_versions_empty_when_no_package(self, client):
        with patch.object(client, 'get_package_info', new_callable=AsyncMock, return_value=None):
            versions = await client.get_versions('nonexistent')
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_versions_filters_prereleases(self, client, sample_package_info_response):
        with patch.object(client, 'get_package_info', new_callable=AsyncMock, return_value=sample_package_info_response):
            versions = await client.get_versions('express', include_prereleases=False)
        assert all('beta' not in v['version'] for v in versions)

    @pytest.mark.asyncio
    async def test_get_versions_includes_prereleases(self, client, sample_package_info_response):
        with patch.object(client, 'get_package_info', new_callable=AsyncMock, return_value=sample_package_info_response):
            versions = await client.get_versions('express', include_prereleases=True)
        version_strings = [v['version'] for v in versions]
        assert '5.0.0-beta.1' in version_strings

    @pytest.mark.asyncio
    async def test_make_request_tries_mirrors(self, client):
        client.mirror_urls = ['https://mirror.example.com']
        client.registry_url = 'https://registry.npmjs.org'

        with patch.object(client, '_get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [None, {'result': 'from_mirror'}]
            result = await client._make_request('https://registry.npmjs.org/package/test')
        assert result == {'result': 'from_mirror'}
        assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_make_request_returns_first_success(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [{'result': 'primary'}]
            result = await client._make_request('https://registry.npmjs.org/package/test')
        assert result == {'result': 'primary'}
        assert mock_get.call_count == 1

    @pytest.mark.asyncio
    async def test_make_request_all_fail(self, client):
        client.mirror_urls = ['https://mirror1.example.com', 'https://mirror2.example.com']
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=None):
            result = await client._make_request('https://registry.npmjs.org/package/test')
        assert result is None

    @pytest.mark.asyncio
    async def test_search_packages_empty_query(self, client):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value={"objects": []}):
            results = await client.search_packages('')
        assert results == []

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client, sample_package_info_response):
        with patch.object(client, 'get_package_info', new_callable=AsyncMock, return_value=sample_package_info_response):
            result = await client.get_dependencies('express')
        assert 'direct' in result
        assert 'transitive' in result

    def test_format_person_string(self, client):
        result = client._format_person("TJ Holowaychuk <tj@example.com>")
        assert result['name'] == 'TJ Holowaychuk'
        assert result['email'] == 'tj@example.com'

    def test_format_person_dict(self, client):
        result = client._format_person({"name": "TJ", "email": "tj@example.com"})
        assert result['name'] == 'TJ'
        assert result['email'] == 'tj@example.com'

    def test_format_person_empty(self, client):
        result = client._format_person("")
        assert result['name'] == ''
