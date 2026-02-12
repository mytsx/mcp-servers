#!/usr/bin/env python3
"""Test SSH MCP Server functionality."""

import os
import asyncio
from dotenv import load_dotenv
import paramiko

# Load environment variables
load_dotenv()

async def test_ssh_connection():
    """Test SSH connection"""
    print("🧪 Testing SSH Connection...")
    
    host = os.getenv("SSH_HOST")
    port = int(os.getenv("SSH_PORT", "22"))
    username = os.getenv("SSH_USER")
    password = os.getenv("SSH_PASSWORD")
    
    if not password or password == "your_password_here":
        print("❌ Please set SSH_PASSWORD in .env file")
        return False
    
    try:
        ssh_client = paramiko.SSHClient()
        # NOTE: AutoAddPolicy is used here for testing convenience only
        # In production, use RejectPolicy or WarningPolicy with proper known_hosts management
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        print(f"🔗 Connecting to {username}@{host}:{port}...")
        ssh_client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            timeout=30
        )
        
        print("✅ SSH connection successful!")
        
        # Test basic commands
        test_commands = [
            "whoami",
            "pwd", 
            "uname -a",
            "uptime"
        ]
        
        for cmd in test_commands:
            print(f"\n💻 Testing command: {cmd}")
            stdin, stdout, stderr = ssh_client.exec_command(cmd)
            output = stdout.read().decode('utf-8', errors='ignore').strip()
            error = stderr.read().decode('utf-8', errors='ignore').strip()
            
            if error:
                print(f"⚠️ Error: {error}")
            else:
                print(f"✅ Output: {output}")
        
        ssh_client.close()
        print("\n✅ SSH test completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ SSH connection failed: {e}")
        return False

async def test_mcp_server():
    """Test MCP server import"""
    print("\n🧪 Testing MCP Server Import...")
    
    try:
        from server import SSHMCPServer
        print("✅ MCP server import successful!")
        
        # Test server creation
        server = SSHMCPServer()
        print("✅ MCP server instance created!")
        return True
        
    except Exception as e:
        print(f"❌ MCP server test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 SSH MCP Server Test Suite")
    print("=" * 40)
    
    # Test SSH connection
    ssh_success = asyncio.run(test_ssh_connection())
    
    # Test MCP server
    mcp_success = asyncio.run(test_mcp_server())
    
    print("\n📊 Test Results:")
    print(f"SSH Connection: {'✅ PASS' if ssh_success else '❌ FAIL'}")
    print(f"MCP Server: {'✅ PASS' if mcp_success else '❌ FAIL'}")
    
    if ssh_success and mcp_success:
        print("\n🎉 All tests passed! Server is ready to use.")
        print("\n🔧 Next steps:")
        print("1. Add to Claude Desktop configuration")
        print("2. Restart Claude Desktop")
        print("3. Test with: 'Linux sunucumda komut çalıştır: ls -la'")
    else:
        print("\n⚠️ Some tests failed. Please check configuration.")