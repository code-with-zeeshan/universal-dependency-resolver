from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.data_sources.gomodules_client import GoModulesClient


class TestGoModulesClient:

    @pytest.fixture
    def client(self):
        return GoModulesClient()

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client):
        versions_list = ["v1.0.0", "v1.1.0", "v1.2.0"]
        latest = {"Version": "v1.2.0"}
        module_info = {
            "info": {"Version": "v1.2.0", "Time": "2023-01-01T00:00:00Z"},
            "go_mod": (
                "module github.com/example/mymodule\n"
                "go 1.19\n"
                "require (\n"
                "\tgithub.com/pkg/errors v0.9.1\n"
                "\tgithub.com/gorilla/mux v1.8.0\n"
                ")\n"
                "require golang.org/x/net v0.7.0 // indirect\n"
            )
        }

        with patch.object(client, '_get_versions_list', new_callable=AsyncMock, return_value=versions_list), \
             patch.object(client, '_get_latest_version', new_callable=AsyncMock, return_value='v1.2.0'), \
             patch.object(client, '_get_module_info', new_callable=AsyncMock, return_value=module_info):
            result = await client.get_package_info_async('github.com/example/mymodule')

        assert result is not None
        assert result['name'] == 'github.com/example/mymodule'
        assert result['version'] == 'v1.2.0'
        assert 'dependencies' in result
        assert 'required' in result['dependencies']
        assert 'indirect' in result['dependencies']
        assert result['dependencies']['required']['github.com/pkg/errors'] == 'v0.9.1'
        assert result['dependencies']['required']['github.com/gorilla/mux'] == 'v1.8.0'
        assert result['dependencies']['indirect']['golang.org/x/net'] == 'v0.7.0'

    @pytest.mark.asyncio
    async def test_get_package_info_async_no_versions(self, client):
        with patch.object(client, '_get_versions_list', new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info_async('github.com/example/mymodule')
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_async_no_latest(self, client):
        with patch.object(client, '_get_versions_list', new_callable=AsyncMock, return_value=["v1.0.0"]), \
             patch.object(client, '_get_latest_version', new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info_async('github.com/example/mymodule')
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_async_no_module_info(self, client):
        with patch.object(client, '_get_versions_list', new_callable=AsyncMock, return_value=["v1.0.0"]), \
             patch.object(client, '_get_latest_version', new_callable=AsyncMock, return_value='v1.0.0'), \
             patch.object(client, '_get_module_info', new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info_async('github.com/example/mymodule')
        assert result is None

    def test_get_package_info_sync_success(self, client):
        with patch.object(client, 'get_package_info_async', new_callable=AsyncMock, return_value={
            'name': 'github.com/example/mymodule',
            'version': 'v1.0.0',
            'dependencies': {},
            'system_requirements': {'go': '1.19'}
        }):
            result = client.get_package_info('github.com/example/mymodule')
        assert result is not None
        assert result['name'] == 'github.com/example/mymodule'

    def test_package_exists_returns_true(self, client):
        with patch('requests.head') as mock_head:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_head.return_value = mock_response
            assert client.package_exists('github.com/example/mymodule') is True

    def test_package_exists_returns_false(self, client):
        with patch('requests.head') as mock_head:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_head.return_value = mock_response
            assert client.package_exists('github.com/example/mymodule') is False

    def test_package_exists_handles_exception(self, client):
        with patch('requests.head', side_effect=Exception('Network error')):
            assert client.package_exists('github.com/example/mymodule') is False

    @pytest.mark.asyncio
    async def test_search_packages(self, client):
        results = await client.search_packages('gorilla/mux')
        assert results == []

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client):
        versions_list = ["v1.0.0", "v1.1.0", "v2.0.0"]
        with patch.object(client, '_get_versions_list', new_callable=AsyncMock, return_value=versions_list):
            versions = await client.get_versions('github.com/example/mymodule')
        assert len(versions) == 3
        assert versions[0]['version'] == 'v2.0.0'
        assert versions[-1]['version'] == 'v1.0.0'
        assert all('stable' in v for v in versions)

    @pytest.mark.asyncio
    async def test_get_versions_empty(self, client):
        with patch.object(client, '_get_versions_list', new_callable=AsyncMock, return_value=None):
            versions = await client.get_versions('github.com/example/mymodule')
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_versions_stable_flag(self, client):
        versions_list = ["v1.0.0", "v2.0.0-beta.1", "v1.0.1+incompatible"]
        with patch.object(client, '_get_versions_list', new_callable=AsyncMock, return_value=versions_list):
            versions = await client.get_versions('github.com/example/mymodule')
        for v in versions:
            if v['version'] == 'v1.0.0':
                assert v['stable'] is True
            elif v['version'] == 'v2.0.0-beta.1':
                assert v['stable'] is False
            elif v['version'] == 'v1.0.1+incompatible':
                assert v['stable'] is False

    @pytest.mark.asyncio
    async def test_get_package_version_success(self, client):
        module_info = {
            "info": {"Version": "v1.0.0"},
            "go_mod": (
                "module github.com/example/mymodule\n"
                "go 1.19\n"
                "require github.com/pkg/errors v0.9.1\n"
            )
        }
        with patch.object(client, '_get_module_info', new_callable=AsyncMock, return_value=module_info):
            result = await client.get_package_version('github.com/example/mymodule', 'v1.0.0')
        assert result is not None
        assert result['version'] == 'v1.0.0'
        assert 'dependencies' in result
        assert 'system_requirements' in result

    @pytest.mark.asyncio
    async def test_get_package_version_adds_v_prefix(self, client):
        module_info = {"info": {}, "go_mod": ""}
        with patch.object(client, '_get_module_info', new_callable=AsyncMock, return_value=module_info):
            with patch.object(client, '_get_module_info', new_callable=AsyncMock, return_value=module_info) as mock_info:
                await client.get_package_version('github.com/example/mymodule', '1.0.0')
            mock_info.assert_called_once()
            args = mock_info.call_args[0]
            assert args[1] == 'v1.0.0'

    @pytest.mark.asyncio
    async def test_get_package_version_not_found(self, client):
        with patch.object(client, '_get_module_info', new_callable=AsyncMock, return_value=None):
            result = await client.get_package_version('github.com/example/mymodule', 'v99.99.99')
        assert result is None

    @pytest.mark.asyncio
    async def test_get_dependencies_parses_require_block(self, client):
        module_info = {
            "info": {},
            "go_mod": (
                "module github.com/example/mymodule\n"
                "go 1.19\n"
                "require (\n"
                "\tgithub.com/pkg/errors v0.9.1\n"
                "\tgithub.com/gorilla/mux v1.8.0\n"
                ")\n"
            )
        }
        with patch.object(client, '_get_module_info', new_callable=AsyncMock, return_value=module_info):
            deps = await client.get_dependencies('github.com/example/mymodule', 'v1.0.0')
        assert 'required' in deps
        assert 'github.com/pkg/errors' in deps['required']
        assert 'github.com/gorilla/mux' in deps['required']
        assert deps['required']['github.com/pkg/errors'] == 'v0.9.1'

    @pytest.mark.asyncio
    async def test_get_dependencies_parses_inline_require(self, client):
        module_info = {
            "info": {},
            "go_mod": (
                "module github.com/example/mymodule\n"
                "go 1.19\n"
                "require github.com/pkg/errors v0.9.1\n"
            )
        }
        with patch.object(client, '_get_module_info', new_callable=AsyncMock, return_value=module_info):
            deps = await client.get_dependencies('github.com/example/mymodule', 'v1.0.0')
        assert 'github.com/pkg/errors' in deps['required']

    @pytest.mark.asyncio
    async def test_get_dependencies_parses_replace_directives(self, client):
        module_info = {
            "info": {},
            "go_mod": (
                "module github.com/example/mymodule\n"
                "go 1.19\n"
                "require github.com/pkg/errors v0.9.1\n"
                "replace github.com/pkg/errors => github.com/joeshaw/errors v0.9.0\n"
            )
        }
        with patch.object(client, '_get_module_info', new_callable=AsyncMock, return_value=module_info):
            deps = await client.get_dependencies('github.com/example/mymodule', 'v1.0.0')
        assert 'replace' in deps
        assert 'github.com/pkg/errors' in deps['replace']

    @pytest.mark.asyncio
    async def test_get_dependencies_returns_empty_on_no_module_info(self, client):
        with patch.object(client, '_get_module_info', new_callable=AsyncMock, return_value=None):
            deps = await client.get_dependencies('github.com/example/mymodule', 'v1.0.0')
        assert deps == {}

    def test_extract_go_version(self, client):
        module_info = {"go_mod": "module github.com/example/mymodule\ngo 1.19\n"}
        assert client._extract_go_version(module_info) == '1.19'

    def test_extract_go_version_none(self, client):
        module_info = {"go_mod": "module github.com/example/mymodule\n"}
        assert client._extract_go_version(module_info) is None

    def test_normalize_go_module_path_github(self, client):
        assert client._normalize_go_module_path('github.com/user/repo') == 'github.com/user/repo'

    def test_normalize_go_module_path_golang_org(self, client):
        assert client._normalize_go_module_path('golang.org/x/net') == 'golang.org/x/net'

    def test_normalize_go_module_path_short_name(self, client):
        result = client._normalize_go_module_path('mymodule')
        assert result == 'github.com/mymodule/mymodule'

    def test_normalize_go_module_path_strips_whitespace(self, client):
        result = client._normalize_go_module_path('  github.com/user/repo  ')
        assert result == 'github.com/user/repo'

    @pytest.mark.asyncio
    async def test_make_request_json_response(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.json = AsyncMock(return_value={'version': 'v1.0.0'})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session.get.return_value = mock_response
        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client._make_request('https://proxy.golang.org/test/@latest')

        assert result == {'version': 'v1.0.0'}

    @pytest.mark.asyncio
    async def test_make_request_text_response(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'text/plain'}
        mock_response.text = AsyncMock(return_value='v1.0.0\nv1.1.0\n')
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session.get.return_value = mock_response
        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client._make_request('https://proxy.golang.org/test/@v/list')

        assert result == 'v1.0.0\nv1.1.0\n'

    @pytest.mark.asyncio
    async def test_make_request_404(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session.get.return_value = mock_response
        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client._make_request('https://proxy.golang.org/test/@v/list')

        assert result is None

    @pytest.mark.asyncio
    async def test_make_request_non_200(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session.get.return_value = mock_response
        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client._make_request('https://proxy.golang.org/test/@v/list')

        assert result is None

    @pytest.mark.asyncio
    async def test_get_versions_list_parses_text(self, client):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value='v1.0.0\nv1.1.0\nv2.0.0\n'):
            versions = await client._get_versions_list('github.com/example/mymodule')
        assert versions == ['v1.0.0', 'v1.1.0', 'v2.0.0']

    @pytest.mark.asyncio
    async def test_get_versions_list_none(self, client):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=None):
            versions = await client._get_versions_list('github.com/example/mymodule')
        assert versions is None

    @pytest.mark.asyncio
    async def test_get_latest_version_success(self, client):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value={'Version': 'v1.2.0'}):
            version = await client._get_latest_version('github.com/example/mymodule')
        assert version == 'v1.2.0'

    @pytest.mark.asyncio
    async def test_get_latest_version_not_found(self, client):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=None):
            version = await client._get_latest_version('github.com/example/mymodule')
        assert version is None

    @pytest.mark.asyncio
    async def test_get_module_info_success(self, client):
        info_data = {"Version": "v1.0.0", "Time": "2023-01-01T00:00:00Z"}
        mod_data = "module github.com/example/mymodule\ngo 1.19\n"
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [info_data, mod_data]
            result = await client._get_module_info('github.com/example/mymodule', 'v1.0.0')
        assert result is not None
        assert result['info'] == info_data
        assert result['go_mod'] == mod_data

    @pytest.mark.asyncio
    async def test_get_module_info_fails(self, client):
        with patch.object(client, '_make_request', new_callable=AsyncMock, return_value=None):
            result = await client._get_module_info('github.com/example/mymodule', 'v1.0.0')
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_go_mod_empty(self, client):
        result = await client._parse_go_mod({"go_mod": ""})
        assert result == {'required': {}, 'indirect': {}, 'replace': {}}
