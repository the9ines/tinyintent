#!/usr/bin/env python3
"""
Complete demo of TinyIntent Interactive CLI with working weather
"""

import asyncio
import os
from tinyintent.interactive import TinyIntentInteractive

async def demo_complete_session():
    """Demo a complete TinyIntent interactive session."""
    # Set environment for proper execution
    os.environ['TINYINTENT_SECRET'] = 'test-secret-for-interactive-demo-32chars'
    os.environ['TINYINTENT_EXECUTION_ENABLED'] = '1'
    
    interactive = TinyIntentInteractive()
    
    print("🎯 TinyIntent Interactive CLI - Complete Demo")
    print("=" * 60)
    
    # Demo queries showing different routing
    queries = [
        ("whats the weather in 78624?", "Weather query → Weather helper"),
        ("what is artificial intelligence?", "Question → LLM generation"),
        ("show me traffic conditions", "Traffic query → Traffic helper"),
        ("/status", "System command"),
        ("/helper info weather", "Helper management")
    ]
    
    for query, description in queries:
        print(f"\n📝 {description}")
        print(f"🔍 Query: {query}")
        print("-" * 50)
        
        if interactive.handle_command(query):
            print("✅ System command executed")
        else:
            # Process as regular query
            response = await interactive.process_query(query)
            print(f"💬 Response: {response}")
        
        print()

    print("🎉 Demo complete! TinyIntent Interactive CLI is fully functional.")
    print()
    print("To use TinyIntent interactively:")
    print("  1. Type: tinyintent")
    print("  2. Ask questions naturally")
    print("  3. Use /help for commands")
    print("  4. Type /quit to exit")

if __name__ == "__main__":
    asyncio.run(demo_complete_session())