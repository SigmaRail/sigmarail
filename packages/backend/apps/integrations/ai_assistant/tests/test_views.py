"""
Tests for AI Assistant views.
"""

import pytest
import httpx
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock


@pytest.mark.django_db
class TestMCPProxyView:
    """Tests for the MCP proxy endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, user_factory, tenant_factory, tenant_membership_factory):
        self.client = APIClient()
        self.user = user_factory()
        self.tenant = tenant_factory()
        self.membership = tenant_membership_factory(user=self.user, tenant=self.tenant, is_accepted=True)
        self.client.force_authenticate(user=self.user)
        self.url = reverse('ai_assistant_mcp_proxy', kwargs={'tenant_id': str(self.tenant.id)})

    def test_unauthenticated_request_fails(self):
        """Test that unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        response = self.client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unauthorized_tenant_access_fails(self, tenant_factory):
        """Test that users cannot access tenants they don't belong to."""
        other_tenant = tenant_factory()
        url = reverse('ai_assistant_mcp_proxy', kwargs={'tenant_id': str(other_tenant.id)})
        response = self.client.post(url, {'method': 'chat'}, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch('apps.integrations.ai_assistant.views.httpx.Client')
    def test_mcp_proxy_injects_tenant_id(self, mock_client_class):
        """Test that tenant ID is injected into request variables."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'response': 'Test response'}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        response = self.client.post(self.url, {'method': 'query', 'variables': {'someParam': 'value'}}, format='json')

        # Verify tenant ID was injected
        call_args = mock_client.post.call_args
        json_data = call_args.kwargs.get('json', {})
        assert json_data['variables']['tenantId'] == str(self.tenant.id)

    @patch('apps.integrations.ai_assistant.views.httpx.Client')
    @override_settings(MCP_SERVER_URL='http://test-mcp-server:4000')
    def test_mcp_proxy_uses_correct_url(self, mock_client_class):
        """Test that the proxy uses the configured MCP server URL."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'response': 'Test'}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        self.client.post(self.url, {'method': 'chat'}, format='json')

        call_args = mock_client.post.call_args
        assert call_args.args[0].startswith('http://test-mcp-server:4000')


@pytest.mark.django_db
class TestChatGPTMCPProxyView:
    """ChatGPT-facing MCP adapter protocol compatibility."""

    @pytest.fixture(autouse=True)
    def setup(self, user_factory):
        self.client = APIClient()
        self.client.force_authenticate(user=user_factory())
        self.url = reverse('ai_assistant_chatgpt_mcp_proxy')

    @patch('apps.integrations.ai_assistant.views.httpx.Client')
    @override_settings(MCP_SERVER_URL='http://test-mcp-server:4000')
    def test_server_discover_reaches_apollo_with_modern_protocol_header(self, mock_client_class):
        """Modern protocol discovery must reach Apollo rather than be downgraded in the adapter."""
        upstream_payload = {
            'jsonrpc': '2.0',
            'id': 'discover-1',
            'result': {
                'resultType': 'complete',
                'supportedVersions': ['2025-11-25', '2026-07-28'],
                'capabilities': {'tools': {}},
                'instructions': 'Upstream workflow schema is authoritative.',
            },
        }
        upstream = httpx.Response(200, json=upstream_payload)

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = False
        mock_client.post.return_value = upstream
        mock_client_class.return_value = mock_client

        request = {
            'jsonrpc': '2.0',
            'id': 'discover-1',
            'method': 'server/discover',
            'params': {'_meta': {'io.modelcontextprotocol/protocolVersion': '2026-07-28'}},
        }
        response = self.client.post(
            self.url,
            request,
            format='json',
            HTTP_MCP_PROTOCOL_VERSION='2026-07-28',
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()['result']['supportedVersions'] == ['2025-11-25', '2026-07-28']
        assert 'get_user_tenants' in response.json()['result']['instructions']
        assert 'sigmarail_readiness' in response.json()['result']['instructions']
        assert 'permission requirement needs clarification' in response.json()['result']['instructions']
        assert 'Upstream workflow schema is authoritative.' in response.json()['result']['instructions']
        args, kwargs = mock_client.post.call_args
        assert args[0] == 'http://test-mcp-server:4000/mcp'
        assert kwargs['json']['method'] == 'server/discover'
        assert kwargs['headers']['Mcp-Protocol-Version'] == '2026-07-28'
        assert kwargs['headers']['Mcp-Method'] == 'server/discover'

    @patch('apps.integrations.ai_assistant.views.httpx.Client')
    def test_tools_list_preserves_readiness_tool_and_replaces_tenant_id_with_selector(self, mock_client_class):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = False
        mock_client.post.return_value = httpx.Response(
            200,
            json={
                'jsonrpc': '2.0',
                'id': 2,
                'result': {
                    'tools': [
                        {
                            'name': 'sigmarail_readiness',
                            'description': 'Check data readiness and effective permission codes.',
                            'inputSchema': {
                                'type': 'object',
                                'properties': {'tenantId': {'type': 'string'}},
                                'required': ['tenantId'],
                            },
                        }
                    ]
                },
            },
        )
        mock_client_class.return_value = mock_client

        response = self.client.post(
            self.url,
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}},
            format='json',
        )

        assert response.status_code == status.HTTP_200_OK
        tool = response.json()['result']['tools'][0]
        assert tool['name'] == 'sigmarail_readiness'
        assert 'tenantId' not in tool['inputSchema']['properties']
        assert 'tenantContext' in tool['inputSchema']['properties']
        assert tool['inputSchema']['required'] == []

    @patch('apps.integrations.ai_assistant.views.httpx.Client')
    @override_settings(MCP_SERVER_URL='http://test-mcp-server:4000')
    def test_modern_tool_call_forwards_standard_method_and_name_headers(self, mock_client_class):
        """Modern tool calls include body-matched headers required by Apollo."""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = False
        mock_client.post.return_value = httpx.Response(
            200,
            json={'jsonrpc': '2.0', 'id': 2, 'result': {'content': []}},
        )
        mock_client_class.return_value = mock_client

        response = self.client.post(
            self.url,
            {
                'jsonrpc': '2.0',
                'id': 2,
                'method': 'tools/call',
                'params': {
                    'name': 'GetUserTenants',
                    'arguments': {},
                    '_meta': {
                        'io.modelcontextprotocol/protocolVersion': '2026-07-28',
                        'io.modelcontextprotocol/clientCapabilities': {},
                    },
                },
            },
            format='json',
            HTTP_MCP_PROTOCOL_VERSION='2026-07-28',
        )

        assert response.status_code == status.HTTP_200_OK
        _, kwargs = mock_client.post.call_args
        assert kwargs['headers']['Mcp-Method'] == 'tools/call'
        assert kwargs['headers']['Mcp-Name'] == 'GetUserTenants'

    @patch('apps.integrations.ai_assistant.views.httpx.Client')
    def test_initialize_completes_apollo_legacy_handshake(self, mock_client_class):
        """Legacy clients that omit notifications/initialized still get a ready Apollo session."""
        initialize_payload = {
            'jsonrpc': '2.0',
            'id': 1,
            'result': {
                'protocolVersion': '2025-11-25',
                'capabilities': {'tools': {}},
                'serverInfo': {'name': 'Apollo', 'version': '2.2.1'},
            },
        }
        initialize_response = httpx.Response(
            200,
            json=initialize_payload,
            headers={'Mcp-Session-Id': 'apollo-session'},
        )
        notification_response = httpx.Response(202, headers={'content-type': 'application/json'})

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = False
        mock_client.post.side_effect = [initialize_response, notification_response]
        mock_client_class.return_value = mock_client

        response = self.client.post(
            self.url,
            {
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'initialize',
                'params': {
                    'protocolVersion': '2025-11-25',
                    'capabilities': {},
                    'clientInfo': {'name': 'ChatGPT', 'version': '1'},
                },
            },
            format='json',
            HTTP_MCP_PROTOCOL_VERSION='2025-11-25',
        )

        assert response.status_code == status.HTTP_200_OK
        assert mock_client.post.call_count == 2
        notification = mock_client.post.call_args_list[1]
        assert notification.kwargs['json']['method'] == 'notifications/initialized'
        assert notification.kwargs['headers']['Mcp-Session-Id'] == 'apollo-session'


@pytest.mark.django_db
class TestMCPChatView:
    """Tests for the high-level chat endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, user_factory, tenant_factory, tenant_membership_factory):
        self.client = APIClient()
        self.user = user_factory()
        self.tenant = tenant_factory()
        self.membership = tenant_membership_factory(user=self.user, tenant=self.tenant, is_accepted=True)
        self.client.force_authenticate(user=self.user)
        self.url = reverse('ai_assistant_chat', kwargs={'tenant_id': str(self.tenant.id)})

    def test_chat_requires_message(self):
        """Test that chat endpoint requires a message."""
        response = self.client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data

    @patch('apps.integrations.ai_assistant.views.MCPClient')
    @patch('apps.integrations.ai_assistant.views.MCPChatView.get_openai_client')
    def test_chat_returns_streaming_response(self, mock_get_openai, mock_mcp_class):
        """Test that chat endpoint returns SSE streaming response."""
        # Mock OpenAI client
        mock_openai = MagicMock()
        mock_get_openai.return_value = mock_openai

        # Mock OpenAI completion response
        mock_choice = MagicMock()
        mock_choice.message.tool_calls = None
        mock_choice.message.content = 'You have 5 active projects.'
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_openai.chat.completions.create.return_value = mock_completion

        # Mock MCP client
        mock_mcp = MagicMock()
        mock_mcp.list_tools.return_value = []
        mock_mcp.get_user_permissions.return_value = set()
        mock_mcp_class.return_value = mock_mcp

        response = self.client.post(self.url, {'message': 'How many active projects?'}, format='json')

        # Should return streaming response
        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'text/event-stream'

        # Read streaming content
        content = b''.join(response.streaming_content).decode('utf-8')
        # Should contain SSE events with content
        assert 'event:' in content or 'data:' in content


@pytest.mark.django_db
class TestMCPHealthView:
    """Tests for the MCP health check endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, user_factory):
        self.client = APIClient()
        self.user = user_factory()
        self.client.force_authenticate(user=self.user)
        self.url = reverse('ai_assistant_health')

    def test_health_check_requires_auth(self):
        """Test that health check requires authentication."""
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch('apps.integrations.ai_assistant.views.httpx.Client')
    def test_health_check_returns_healthy(self, mock_client_class):
        """Test health check returns healthy when MCP server is up."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'healthy'
