"""
Trial quota management service using Cloudflare KV storage.
Manages shared daily quota for trial users without API keys.
"""
import os
import json
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass
import streamlit as st


@dataclass
class QuotaConfig:
    """Configuration for quota limits per generation mode."""
    # Cost in quota points (1 point = 1 standard 1K/2K image)
    cost: int
    # Maximum count per day for this specific mode
    daily_limit: int
    # Display name for UI
    display_name: str


# ============ Load Configuration from Environment ============
# Global daily quota pool (in points, where 1 point = 1 standard image)
GLOBAL_DAILY_QUOTA = int(os.getenv("TRIAL_GLOBAL_QUOTA", "50"))

# Configuration mode: "auto" or "manual"
QUOTA_CONFIG_MODE = os.getenv("TRIAL_QUOTA_MODE", "manual")

# Cooldown between generations (seconds)
GENERATION_COOLDOWN = int(os.getenv("TRIAL_COOLDOWN_SECONDS", "3"))

# Base ratios for auto-scaling (when QUOTA_CONFIG_MODE = "auto")
# These ratios determine how the global quota is distributed across modes
BASE_QUOTA_RATIOS = {
    "basic_1k": 0.60,    # 60% of global quota for basic 1K/2K
    "basic_4k": 0.20,    # 20% for basic 4K (costs 3x, so fewer images)
    "chat": 0.40,        # 40% for chat
    "batch_1k": 0.30,    # 30% for batch 1K/2K
    "batch_4k": 0.10,    # 10% for batch 4K
    "search": 0.30,      # 30% for search (costs 2x)
    "blend": 0.20,       # 20% for blend/style (costs 2x)
}

# Manual configuration (used when QUOTA_CONFIG_MODE = "manual")
# Load from environment variables with defaults
MANUAL_QUOTA_CONFIGS = {
    "basic_1k": QuotaConfig(
        cost=int(os.getenv("TRIAL_BASIC_1K_COST", "1")),
        daily_limit=int(os.getenv("TRIAL_BASIC_1K_LIMIT", "30")),
        display_name="Basic (1K/2K)"
    ),
    "basic_4k": QuotaConfig(
        cost=int(os.getenv("TRIAL_BASIC_4K_COST", "3")),
        daily_limit=int(os.getenv("TRIAL_BASIC_4K_LIMIT", "10")),
        display_name="Basic (4K)"
    ),
    "chat": QuotaConfig(
        cost=int(os.getenv("TRIAL_CHAT_COST", "1")),
        daily_limit=int(os.getenv("TRIAL_CHAT_LIMIT", "20")),
        display_name="Chat"
    ),
    "batch_1k": QuotaConfig(
        cost=int(os.getenv("TRIAL_BATCH_1K_COST", "1")),
        daily_limit=int(os.getenv("TRIAL_BATCH_1K_LIMIT", "15")),
        display_name="Batch (1K/2K)"
    ),
    "batch_4k": QuotaConfig(
        cost=int(os.getenv("TRIAL_BATCH_4K_COST", "3")),
        daily_limit=int(os.getenv("TRIAL_BATCH_4K_LIMIT", "5")),
        display_name="Batch (4K)"
    ),
    "search": QuotaConfig(
        cost=int(os.getenv("TRIAL_SEARCH_COST", "2")),
        daily_limit=int(os.getenv("TRIAL_SEARCH_LIMIT", "15")),
        display_name="Search"
    ),
    "blend": QuotaConfig(
        cost=int(os.getenv("TRIAL_BLEND_COST", "2")),
        daily_limit=int(os.getenv("TRIAL_BLEND_LIMIT", "10")),
        display_name="Blend/Style"
    ),
}


def _calculate_auto_quota_configs() -> Dict[str, QuotaConfig]:
    """
    Calculate quota configs automatically based on global quota and ratios.
    
    Returns:
        Dictionary of quota configurations
    """
    configs = {}
    
    # Define costs (same as manual)
    costs = {
        "basic_1k": 1,
        "basic_4k": 3,
        "chat": 1,
        "batch_1k": 1,
        "batch_4k": 3,
        "search": 2,
        "blend": 2,
    }
    
    # Display names
    display_names = {
        "basic_1k": "Basic (1K/2K)",
        "basic_4k": "Basic (4K)",
        "chat": "Chat",
        "batch_1k": "Batch (1K/2K)",
        "batch_4k": "Batch (4K)",
        "search": "Search",
        "blend": "Blend/Style",
    }
    
    # Calculate limits based on ratios
    for mode_key, ratio in BASE_QUOTA_RATIOS.items():
        cost = costs[mode_key]
        # Calculate how many images can be generated with the allocated quota
        allocated_points = GLOBAL_DAILY_QUOTA * ratio
        daily_limit = int(allocated_points / cost)
        
        configs[mode_key] = QuotaConfig(
            cost=cost,
            daily_limit=max(1, daily_limit),  # At least 1
            display_name=display_names[mode_key]
        )
    
    return configs


def _validate_quota_config() -> Tuple[bool, List[str]]:
    """
    Validate quota configuration for potential issues.
    
    Returns:
        Tuple of (is_valid, list_of_warnings)
    """
    warnings = []
    
    # Calculate theoretical maximum usage per mode
    total_possible_points = 0
    for mode_key, config in QUOTA_CONFIGS.items():
        max_points = config.daily_limit * config.cost
        total_possible_points += max_points
        
        # Check if single mode can exceed global quota
        if max_points > GLOBAL_DAILY_QUOTA:
            warnings.append(
                f"⚠️ {config.display_name} can use {max_points} points "
                f"(limit: {config.daily_limit} × cost: {config.cost}), "
                f"which exceeds global quota ({GLOBAL_DAILY_QUOTA})"
            )
    
    # Check if total possible usage is reasonable
    if total_possible_points > GLOBAL_DAILY_QUOTA * 3:
        warnings.append(
            f"⚠️ Total possible usage ({total_possible_points} points) "
            f"is much higher than global quota ({GLOBAL_DAILY_QUOTA}). "
            f"Consider reducing mode limits or increasing global quota."
        )
    
    return len(warnings) == 0, warnings


# Select configuration based on mode
if QUOTA_CONFIG_MODE == "auto":
    QUOTA_CONFIGS = _calculate_auto_quota_configs()
    print(f"[TrialQuota] Using AUTO configuration (global quota: {GLOBAL_DAILY_QUOTA})")
else:
    QUOTA_CONFIGS = MANUAL_QUOTA_CONFIGS
    print(f"[TrialQuota] Using MANUAL configuration")

# Validate configuration on startup
_is_valid, _warnings = _validate_quota_config()
if not _is_valid:
    print("[TrialQuota] Configuration warnings:")
    for warning in _warnings:
        print(f"  {warning}")

# Cooldown is now loaded from environment (see above)


class TrialQuotaService:
    """Service for managing trial user quotas."""

    def __init__(self):
        """Initialize the trial quota service."""
        # Check if R2/KV is available
        self._kv_available = self._check_kv_available()
        
        # Fallback to session state if KV not available
        self._use_session_fallback = not self._kv_available
        
        if self._use_session_fallback:
            self._init_session_fallback()

    def _check_kv_available(self) -> bool:
        """Check if Cloudflare KV storage is available."""
        # Check for R2 credentials (we'll use R2 as KV alternative)
        required_vars = [
            "R2_ACCOUNT_ID",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET_NAME"
        ]
        return all(os.getenv(var) for var in required_vars)

    def _init_session_fallback(self):
        """Initialize session state fallback storage."""
        if "trial_quota_data" not in st.session_state:
            st.session_state.trial_quota_data = {
                "date": self._get_current_date(),
                "global_used": 0,
                "mode_usage": {},
                "last_generation": 0,
            }

    def _get_current_date(self) -> str:
        """Get current date in UTC as string (YYYY-MM-DD)."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _get_quota_key(self) -> str:
        """Get the KV key for today's quota data."""
        return f"trial_quota_{self._get_current_date()}"

    def _load_quota_data(self) -> Dict:
        """Load quota data from storage."""
        if self._use_session_fallback:
            return self._load_from_session()
        else:
            return self._load_from_kv()

    def _load_from_session(self) -> Dict:
        """Load quota data from session state."""
        data = st.session_state.get("trial_quota_data", {})
        
        # Check if date has changed (new day)
        current_date = self._get_current_date()
        if data.get("date") != current_date:
            # Reset for new day
            data = {
                "date": current_date,
                "global_used": 0,
                "mode_usage": {},
                "last_generation": 0,
            }
            st.session_state.trial_quota_data = data
        
        return data

    def _load_from_kv(self) -> Dict:
        """Load quota data from Cloudflare KV (via R2 metadata)."""
        try:
            from .r2_storage import get_r2_storage
            r2 = get_r2_storage(user_id=None)
            
            if not r2.is_available:
                return self._get_empty_quota_data()
            
            key = f"quota/{self._get_quota_key()}.json"
            
            try:
                response = r2._client.get_object(
                    Bucket=r2.bucket_name,
                    Key=key
                )
                data = json.loads(response["Body"].read().decode("utf-8"))
                return data
            except r2._client.exceptions.NoSuchKey:
                # No data for today yet
                return self._get_empty_quota_data()
                
        except Exception as e:
            print(f"[TrialQuota] Failed to load from KV: {e}")
            return self._get_empty_quota_data()

    def _get_empty_quota_data(self) -> Dict:
        """Get empty quota data structure."""
        return {
            "date": self._get_current_date(),
            "global_used": 0,
            "mode_usage": {},
            "last_generation": 0,
        }

    def _save_quota_data(self, data: Dict) -> bool:
        """Save quota data to storage."""
        if self._use_session_fallback:
            return self._save_to_session(data)
        else:
            return self._save_to_kv(data)

    def _save_to_session(self, data: Dict) -> bool:
        """Save quota data to session state."""
        st.session_state.trial_quota_data = data
        return True

    def _save_to_kv(self, data: Dict) -> bool:
        """Save quota data to Cloudflare KV (via R2)."""
        try:
            from .r2_storage import get_r2_storage
            r2 = get_r2_storage(user_id=None)
            
            if not r2.is_available:
                return False
            
            key = f"quota/{self._get_quota_key()}.json"
            
            r2._client.put_object(
                Bucket=r2.bucket_name,
                Key=key,
                Body=json.dumps(data, indent=2),
                ContentType="application/json",
                # Expire after 2 days (cleanup old data)
                Expires=datetime.now(timezone.utc).replace(hour=0, minute=0, second=0) + \
                        __import__('datetime').timedelta(days=2)
            )
            return True
            
        except Exception as e:
            print(f"[TrialQuota] Failed to save to KV: {e}")
            return False

    def get_mode_key(self, mode: str, resolution: str = "1K") -> str:
        """
        Get the quota config key for a generation mode.
        
        Args:
            mode: Generation mode (basic, chat, batch, search, blend, style)
            resolution: Resolution (1K, 2K, 4K)
        
        Returns:
            Config key string
        """
        if mode == "basic":
            return "basic_4k" if resolution == "4K" else "basic_1k"
        elif mode == "batch":
            return "batch_4k" if resolution == "4K" else "batch_1k"
        elif mode in ["blend", "style"]:
            return "blend"
        else:
            return mode  # chat, search

    def check_quota(
        self,
        mode: str,
        resolution: str = "1K",
        count: int = 1
    ) -> Tuple[bool, str, Dict]:
        """
        Check if quota is available for a generation request.
        
        Args:
            mode: Generation mode
            resolution: Image resolution
            count: Number of images to generate
        
        Returns:
            Tuple of (can_generate, reason, quota_info)
        """
        mode_key = self.get_mode_key(mode, resolution)
        config = QUOTA_CONFIGS.get(mode_key)
        
        if not config:
            return False, "Invalid generation mode", {}
        
        # Load current quota data
        data = self._load_quota_data()
        
        # Calculate cost
        total_cost = config.cost * count
        
        # Check cooldown
        current_time = time.time()
        last_gen = data.get("last_generation", 0)
        if current_time - last_gen < GENERATION_COOLDOWN:
            remaining = int(GENERATION_COOLDOWN - (current_time - last_gen))
            return False, f"Please wait {remaining}s before next generation", {}
        
        # Check global quota
        global_used = data.get("global_used", 0)
        global_remaining = GLOBAL_DAILY_QUOTA - global_used
        
        if total_cost > global_remaining:
            return False, f"Daily global quota exceeded ({global_used}/{GLOBAL_DAILY_QUOTA} used)", {
                "global_used": global_used,
                "global_limit": GLOBAL_DAILY_QUOTA,
                "global_remaining": global_remaining,
            }
        
        # Check mode-specific quota
        mode_usage = data.get("mode_usage", {})
        mode_used = mode_usage.get(mode_key, 0)
        mode_remaining = config.daily_limit - mode_used
        
        if count > mode_remaining:
            return False, f"{config.display_name} daily limit exceeded ({mode_used}/{config.daily_limit} used)", {
                "mode": config.display_name,
                "mode_used": mode_used,
                "mode_limit": config.daily_limit,
                "mode_remaining": mode_remaining,
            }
        
        # All checks passed
        quota_info = {
            "global_used": global_used,
            "global_limit": GLOBAL_DAILY_QUOTA,
            "global_remaining": global_remaining,
            "mode": config.display_name,
            "mode_used": mode_used,
            "mode_limit": config.daily_limit,
            "mode_remaining": mode_remaining,
            "cost": total_cost,
        }
        
        return True, "OK", quota_info

    def consume_quota(
        self,
        mode: str,
        resolution: str = "1K",
        count: int = 1
    ) -> bool:
        """
        Consume quota for a generation.
        
        Args:
            mode: Generation mode
            resolution: Image resolution
            count: Number of images generated
        
        Returns:
            True if quota was consumed successfully
        """
        mode_key = self.get_mode_key(mode, resolution)
        config = QUOTA_CONFIGS.get(mode_key)
        
        if not config:
            return False
        
        # Load current data
        data = self._load_quota_data()
        
        # Calculate cost
        total_cost = config.cost * count
        
        # Update usage
        data["global_used"] = data.get("global_used", 0) + total_cost
        
        mode_usage = data.get("mode_usage", {})
        mode_usage[mode_key] = mode_usage.get(mode_key, 0) + count
        data["mode_usage"] = mode_usage
        
        # Update last generation time
        data["last_generation"] = time.time()
        
        # Save
        return self._save_quota_data(data)

    def get_quota_status(self) -> Dict:
        """
        Get current quota status for display.
        
        Returns:
            Dictionary with quota information
        """
        data = self._load_quota_data()
        
        global_used = data.get("global_used", 0)
        global_remaining = GLOBAL_DAILY_QUOTA - global_used
        
        mode_usage = data.get("mode_usage", {})
        
        # Build mode status
        mode_status = {}
        for mode_key, config in QUOTA_CONFIGS.items():
            used = mode_usage.get(mode_key, 0)
            mode_status[mode_key] = {
                "name": config.display_name,
                "used": used,
                "limit": config.daily_limit,
                "remaining": config.daily_limit - used,
                "cost": config.cost,
            }
        
        return {
            "date": data.get("date"),
            "global_used": global_used,
            "global_limit": GLOBAL_DAILY_QUOTA,
            "global_remaining": global_remaining,
            "modes": mode_status,
            "storage": "Cloudflare KV" if not self._use_session_fallback else "Session (Fallback)",
        }

    def reset_quota(self) -> bool:
        """
        Manually reset quota (admin function).
        
        Returns:
            True if reset successful
        """
        data = self._get_empty_quota_data()
        return self._save_quota_data(data)


# Global instance
_trial_quota_service: Optional[TrialQuotaService] = None


def get_trial_quota_service() -> TrialQuotaService:
    """Get or create the global trial quota service instance."""
    global _trial_quota_service
    if _trial_quota_service is None:
        _trial_quota_service = TrialQuotaService()
    return _trial_quota_service


def is_trial_mode() -> bool:
    """
    Check if current user is in trial mode (no API key configured).
    
    Returns:
        True if user is using trial mode
    """
    # Force trial mode for testing (set to True to always show quota)
    FORCE_TRIAL_MODE = os.getenv("FORCE_TRIAL_MODE", "false").lower() == "true"
    
    if FORCE_TRIAL_MODE:
        return True
    
    # Check if user has their own API key
    user_api_key = st.session_state.get("user_api_key", "")
    env_api_key = os.getenv("GOOGLE_API_KEY", "")
    
    # Trial mode if no API key is configured
    return not (user_api_key or env_api_key)
