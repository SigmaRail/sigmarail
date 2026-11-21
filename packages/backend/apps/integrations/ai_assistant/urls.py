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
    # One OAuth-backed ChatGPT path. The authenticated user discovers tenants
    # through MCP; membership is checked on each tenant-scoped tool call.
    path("chatgpt/mcp/", ChatGPTMCPProxyView.as_view(), name="ai_assistant_chatgpt_mcp_proxy"),
    # Chat endpoint (high-level, simpler interface)
    path("tenants/<str:tenant_id>/chat/", MCPChatView.as_view(), name="ai_assistant_chat"),
]
