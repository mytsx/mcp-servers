#!/usr/bin/env python3
"""Test raw JSON output from MCP server"""

import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_raw_output():
    """Test the raw JSON output"""
    print("Testing raw JSON output from MCP server...")
    print("=" * 80)
    
    server_params = StdioServerParameters(
        command="python3",
        args=["server.py"],
        env=None
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Test get_gemini_reviews with simplified parameters
            print("Testing simplified usage - just repo name...")
            result = await session.call_tool(
                "get_gemini_reviews",
                arguments={
                    "repo": "YtbMp3Indir"  # Just repo name, will auto-detect owner
                }
            )
            
            if result.content and len(result.content) > 0:
                raw_text = result.content[0].text
                print(f"\n✅ Received {len(raw_text)} characters")
                
                # Parse as JSON to verify it's valid
                try:
                    data = json.loads(raw_text)
                    print(f"✅ Valid JSON with {len(data)} items")
                    
                    # Print the raw JSON
                    print("\n📄 Raw JSON output:")
                    print("-" * 80)
                    print(raw_text)
                    
                except json.JSONDecodeError as e:
                    print(f"❌ Invalid JSON: {e}")
                    print("Raw text:")
                    print(raw_text[:1000])
            else:
                print("❌ No content received")

if __name__ == "__main__":
    asyncio.run(test_raw_output())