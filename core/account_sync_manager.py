"""
Account Synchronization Manager for SMM NQ Trader
Ensures all accounts are synchronized when processing external signals
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

from exec.enhanced_executor import EnhancedExecutionEngine


@dataclass
class AccountState:
    """Account state tracking"""
    account_id: str
    enabled: bool
    position_side: Optional[str] = None
    position_qty: int = 0
    unrealized_pnl: float = 0.0
    daily_pnl: float = 0.0
    last_order_time: float = 0.0
    last_signal_time: float = 0.0
    sync_status: str = "unknown"  # synced, pending, error


class AccountSyncManager:
    """Manages multi-account synchronization for external signals"""
    
    def __init__(self, state_dir: str = "storage/state"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.accounts_path = self.state_dir / "accounts.json"
        self.sync_state_path = self.state_dir / "account_sync_state.json"
        
        # Account state tracking
        self.accounts: Dict[str, AccountState] = {}
        self.sync_groups: Dict[str, List[str]] = {}  # Group accounts for synchronized trading
        
        # Synchronization settings
        self.sync_timeout_seconds = 30.0
        self.max_sync_retries = 3
        self.sync_cooldown_seconds = 5.0
        
        # Load initial state
        self._load_accounts()
        self._load_sync_state()
        
    def _load_accounts(self) -> None:
        """Load account information from file"""
        try:
            if self.accounts_path.exists():
                with self.accounts_path.open("r") as f:
                    accounts_data = json.load(f)
                    accounts_list = accounts_data.get("accounts", [])
                    
                    for acc_data in accounts_list:
                        account_id = acc_data.get("account_id", "")
                        if account_id:
                            self.accounts[account_id] = AccountState(
                                account_id=account_id,
                                enabled=acc_data.get("enabled", False),
                                position_side=acc_data.get("position_side"),
                                position_qty=acc_data.get("position_qty", 0),
                                unrealized_pnl=acc_data.get("unrealized_pnl", 0.0),
                                daily_pnl=acc_data.get("daily_pnl", 0.0)
                            )
        except Exception as e:
            print(f"Error loading accounts: {e}")
    
    def _load_sync_state(self) -> None:
        """Load synchronization state from file"""
        try:
            if self.sync_state_path.exists():
                with self.sync_state_path.open("r") as f:
                    sync_data = json.load(f)
                    self.sync_groups = sync_data.get("sync_groups", {})
        except Exception as e:
            print(f"Error loading sync state: {e}")
    
    def _save_sync_state(self) -> None:
        """Save synchronization state to file"""
        try:
            sync_data = {
                "sync_groups": self.sync_groups,
                "last_updated": time.time()
            }
            with self.sync_state_path.open("w") as f:
                json.dump(sync_data, f)
        except Exception as e:
            print(f"Error saving sync state: {e}")
    
    def add_account(self, account_id: str, enabled: bool = True) -> None:
        """Add account to synchronization manager"""
        self.accounts[account_id] = AccountState(
            account_id=account_id,
            enabled=enabled
        )
        self._save_sync_state()
    
    def remove_account(self, account_id: str) -> None:
        """Remove account from synchronization manager"""
        if account_id in self.accounts:
            del self.accounts[account_id]
            
        # Remove from sync groups
        for group_name, accounts in self.sync_groups.items():
            if account_id in accounts:
                accounts.remove(account_id)
                if not accounts:  # Remove empty group
                    del self.sync_groups[group_name]
        
        self._save_sync_state()
    
    def create_sync_group(self, group_name: str, account_ids: List[str]) -> None:
        """Create a synchronization group for accounts"""
        # Validate accounts exist
        valid_accounts = [acc_id for acc_id in account_ids if acc_id in self.accounts]
        
        if valid_accounts:
            self.sync_groups[group_name] = valid_accounts
            self._save_sync_state()
            print(f"Created sync group '{group_name}' with {len(valid_accounts)} accounts")
        else:
            print(f"No valid accounts found for sync group '{group_name}'")
    
    def get_enabled_accounts(self) -> List[str]:
        """Get list of enabled account IDs"""
        return [acc_id for acc_id, acc in self.accounts.items() if acc.enabled]
    
    def get_sync_group_accounts(self, group_name: str) -> List[str]:
        """Get accounts in a synchronization group"""
        return self.sync_groups.get(group_name, [])
    
    def get_all_sync_groups(self) -> Dict[str, List[str]]:
        """Get all synchronization groups"""
        return self.sync_groups.copy()
    
    def update_account_state(self, account_id: str, **kwargs) -> None:
        """Update account state"""
        if account_id in self.accounts:
            account = self.accounts[account_id]
            for key, value in kwargs.items():
                if hasattr(account, key):
                    setattr(account, key, value)
    
    def check_account_sync_status(self, account_ids: List[str]) -> Dict[str, str]:
        """Check synchronization status of accounts"""
        status = {}
        current_time = time.time()
        
        for account_id in account_ids:
            if account_id not in self.accounts:
                status[account_id] = "not_found"
                continue
            
            account = self.accounts[account_id]
            
            # Check if account is enabled
            if not account.enabled:
                status[account_id] = "disabled"
                continue
            
            # Check last signal time
            if current_time - account.last_signal_time < self.sync_cooldown_seconds:
                status[account_id] = "cooldown"
                continue
            
            # Check for errors
            if account.sync_status == "error":
                status[account_id] = "error"
                continue
            
            status[account_id] = "ready"
        
        return status
    
    async def synchronize_accounts(self, account_ids: List[str], signal_data: Dict[str, Any]) -> Dict[str, bool]:
        """Synchronize signal execution across multiple accounts"""
        results = {}
        
        # Check sync status
        sync_status = self.check_account_sync_status(account_ids)
        ready_accounts = [acc_id for acc_id, status in sync_status.items() if status == "ready"]
        
        if not ready_accounts:
            print("No accounts ready for synchronization")
            return results
        
        # Mark accounts as pending
        for account_id in ready_accounts:
            self.update_account_state(account_id, sync_status="pending", last_signal_time=time.time())
        
        try:
            # Execute signals in parallel for all ready accounts
            tasks = []
            for account_id in ready_accounts:
                task = self._execute_signal_for_account(account_id, signal_data)
                tasks.append(task)
            
            # Wait for all tasks to complete
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for i, account_id in enumerate(ready_accounts):
                result = task_results[i]
                if isinstance(result, Exception):
                    print(f"Error executing signal for {account_id}: {result}")
                    results[account_id] = False
                    self.update_account_state(account_id, sync_status="error")
                else:
                    results[account_id] = result
                    self.update_account_state(account_id, sync_status="synced")
        
        except Exception as e:
            print(f"Error in account synchronization: {e}")
            # Mark all accounts as error
            for account_id in ready_accounts:
                self.update_account_state(account_id, sync_status="error")
                results[account_id] = False
        
        return results
    
    async def _execute_signal_for_account(self, account_id: str, signal_data: Dict[str, Any]) -> bool:
        """Execute signal for a single account"""
        try:
            # This would integrate with the execution engine
            # For now, simulate the execution
            await asyncio.sleep(0.1)  # Simulate execution time
            
            print(f"Executed signal for account {account_id}: {signal_data.get('side', 'UNKNOWN')} {signal_data.get('symbol', 'UNKNOWN')}")
            return True
            
        except Exception as e:
            print(f"Error executing signal for account {account_id}: {e}")
            return False
    
    def get_sync_statistics(self) -> Dict[str, Any]:
        """Get synchronization statistics"""
        current_time = time.time()
        
        # Count accounts by status
        status_counts = {}
        for account in self.accounts.values():
            status = account.sync_status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Count accounts in cooldown
        cooldown_count = sum(1 for account in self.accounts.values() 
                           if current_time - account.last_signal_time < self.sync_cooldown_seconds)
        
        return {
            "total_accounts": len(self.accounts),
            "enabled_accounts": len(self.get_enabled_accounts()),
            "sync_groups": len(self.sync_groups),
            "status_counts": status_counts,
            "cooldown_count": cooldown_count,
            "sync_timeout_seconds": self.sync_timeout_seconds,
            "sync_cooldown_seconds": self.sync_cooldown_seconds
        }
    
    def reset_account_sync_status(self, account_id: Optional[str] = None) -> None:
        """Reset synchronization status for account(s)"""
        if account_id:
            if account_id in self.accounts:
                self.update_account_state(account_id, sync_status="unknown")
        else:
            # Reset all accounts
            for account in self.accounts.values():
                account.sync_status = "unknown"
    
    def get_account_positions_summary(self) -> Dict[str, Dict[str, Any]]:
        """Get summary of account positions for synchronization"""
        summary = {}
        
        for account_id, account in self.accounts.items():
            if not account.enabled:
                continue
            
            summary[account_id] = {
                "position_side": account.position_side,
                "position_qty": account.position_qty,
                "unrealized_pnl": account.unrealized_pnl,
                "daily_pnl": account.daily_pnl,
                "sync_status": account.sync_status,
                "last_signal_time": account.last_signal_time
            }
        
        return summary
    
    def validate_sync_groups(self) -> Dict[str, List[str]]:
        """Validate sync groups and return invalid accounts"""
        invalid_accounts = {}
        
        for group_name, account_ids in self.sync_groups.items():
            invalid_in_group = []
            
            for account_id in account_ids:
                if account_id not in self.accounts:
                    invalid_in_group.append(account_id)
                elif not self.accounts[account_id].enabled:
                    invalid_in_group.append(account_id)
            
            if invalid_in_group:
                invalid_accounts[group_name] = invalid_in_group
        
        return invalid_accounts


# Global sync manager instance
_sync_manager_instance: Optional[AccountSyncManager] = None

def get_sync_manager() -> AccountSyncManager:
    """Get global account sync manager instance"""
    global _sync_manager_instance
    if _sync_manager_instance is None:
        _sync_manager_instance = AccountSyncManager()
    return _sync_manager_instance
