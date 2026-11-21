"""
AI Assistant URL Configuration

Provides REST endpoints for MCP proxy and chat functionality.
"""

from django.urls import path

from .views import ChatGPTMCPProxyView, MCPProxyView, MCPChatView, MCPHealthView

urlpatterns = [
    # Health check endpoint
    path("health/", MCPHealthView.as_view(), name="ai_assistant_health"),
    # MCP proxy endpoint (low-level MCP protocol)
    path("tenants/<str:tenant_id>/mcp/", MCPProxyView.as_view(), name="ai_assistant_mcp_proxy"),
    # OAuth-backed ChatGPT path. User identity is asserted by the Tailscale
    # gateway and tenant membership is checked by the same proxy logic.
    path(
        "chatgpt/tenants/<str:tenant_id>/mcp/",
        ChatGPTMCPProxyView.as_view(),
        name="ai_assistant_chatgpt_mcp_proxy",
    ),
    # Chat endpoint (high-level, simpler interface)
    path("tenants/<str:tenant_id>/chat/", MCPChatView.as_view(), name="ai_assistant_chat"),
]
