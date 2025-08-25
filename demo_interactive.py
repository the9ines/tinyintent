#!/usr/bin/env python3
"""
Demo script for TinyIntent Interactive CLI
"""

import asyncio
from tinyintent.interactive import TinyIntentInteractive

async def demo_queries():
    """Demo some queries to show how the interactive system works."""
    interactive = TinyIntentInteractive()
    
    print("🎯 TinyIntent Interactive CLI Demo")
    print("=" * 50)
    
    # Demo queries
    queries = [
        "what's the weather in 78624?",
        "what is machine learning?", 
        "show me my crypto positions",
        "/status",
        "/helper list"
    ]
    
    for query in queries:
        print(f"\n🔍 Query: {query}")
        print("-" * 30)
        
        if interactive.handle_command(query):
            print("✅ Command handled")
        else:
            # Process as regular query
            response = await interactive.process_query(query)
            print(f"📝 Response: {response}")

if __name__ == "__main__":
    asyncio.run(demo_queries())