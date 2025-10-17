#!/usr/bin/env python3
"""
Startup script for External Signal Processor
Initializes and runs the external signal processing loop
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from core.external_signal_processor import process_external_signals_loop, get_signal_processor
from core.account_sync_manager import get_sync_manager


async def main():
    """Main function to start external signal processing"""
    print("Starting External Signal Processor for SMM NQ Trader...")
    
    try:
        # Initialize signal processor
        processor = get_signal_processor()
        print("✓ Signal processor initialized")
        
        # Initialize sync manager
        sync_manager = get_sync_manager()
        print("✓ Account sync manager initialized")
        
        # Print initial status
        print(f"✓ Long signals enabled: {processor.long_signals_enabled}")
        print(f"✓ Short signals enabled: {processor.short_signals_enabled}")
        print(f"✓ Signal cooldown: {processor.signal_cooldown_seconds}s")
        print(f"✓ Max signals per minute: {processor.max_signals_per_minute}")
        
        # Print sync statistics
        sync_stats = sync_manager.get_sync_statistics()
        print(f"✓ Total accounts: {sync_stats['total_accounts']}")
        print(f"✓ Enabled accounts: {sync_stats['enabled_accounts']}")
        print(f"✓ Sync groups: {sync_stats['sync_groups']}")
        
        print("\n🚀 Starting external signal processing loop...")
        print("Press Ctrl+C to stop")
        
        # Start the signal processing loop
        await process_external_signals_loop()
        
    except KeyboardInterrupt:
        print("\n🛑 Signal processor stopped by user")
    except Exception as e:
        print(f"❌ Error in signal processor: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
