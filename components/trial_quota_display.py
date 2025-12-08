"""
Trial quota display component.
Shows quota status and limits for trial users.
"""
import streamlit as st
from i18n import Translator
from services.trial_quota import get_trial_quota_service, is_trial_mode


def render_quota_status_compact(t: Translator):
    """
    Render compact quota status in sidebar.
    
    Args:
        t: Translator instance
    """
    if not is_trial_mode():
        return
    
    quota_service = get_trial_quota_service()
    status = quota_service.get_quota_status()
    
    # Compact display
    global_used = status["global_used"]
    global_limit = status["global_limit"]
    global_remaining = status["global_remaining"]
    
    # Progress bar
    progress = min(1.0, global_used / global_limit)
    
    # Color based on remaining quota
    if global_remaining > 20:
        color = "🟢"
    elif global_remaining > 10:
        color = "🟡"
    else:
        color = "🔴"
    
    st.caption(f"{color} {t('trial.quota_title')}")
    st.progress(progress, text=f"{global_used}/{global_limit} {t('trial.quota_used')}")
    
    # Show warning if low
    if global_remaining <= 5:
        st.warning(t('trial.quota_low_warning'))


def render_quota_status_detailed(t: Translator):
    """
    Render detailed quota status page.
    
    Args:
        t: Translator instance
    """
    if not is_trial_mode():
        st.info(t('trial.not_in_trial_mode'))
        return
    
    quota_service = get_trial_quota_service()
    status = quota_service.get_quota_status()
    
    st.header(t('trial.quota_status_title'))
    st.caption(t('trial.quota_status_description'))
    
    # Global quota
    st.subheader(t('trial.global_quota'))
    
    global_used = status["global_used"]
    global_limit = status["global_limit"]
    global_remaining = status["global_remaining"]
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            t('trial.used'),
            f"{global_used}",
            delta=None
        )
    
    with col2:
        st.metric(
            t('trial.remaining'),
            f"{global_remaining}",
            delta=None,
            delta_color="off"
        )
    
    with col3:
        st.metric(
            t('trial.limit'),
            f"{global_limit}",
            delta=None,
            delta_color="off"
        )
    
    # Progress bar
    progress = min(1.0, global_used / global_limit) if global_limit > 0 else 0
    st.progress(progress)
    
    st.divider()
    
    # Mode-specific quotas
    st.subheader(t('trial.mode_quotas'))
    
    modes = status.get("modes", {})
    
    # Group modes for display
    mode_groups = [
        ["basic_1k", "basic_4k"],
        ["chat", "search"],
        ["batch_1k", "batch_4k"],
        ["blend"],
    ]
    
    for group in mode_groups:
        cols = st.columns(len(group))
        
        for idx, mode_key in enumerate(group):
            if mode_key not in modes:
                continue
            
            mode_info = modes[mode_key]
            
            with cols[idx]:
                with st.container(border=True):
                    st.markdown(f"**{mode_info['name']}**")
                    
                    # Usage bar
                    mode_progress = min(1.0, mode_info['used'] / mode_info['limit']) if mode_info['limit'] > 0 else 0
                    st.progress(mode_progress)
                    
                    st.caption(f"{mode_info['used']}/{mode_info['limit']} {t('trial.quota_used')}")
                    st.caption(f"💰 {t('trial.cost_per_image')}: {mode_info['cost']}")
    
    st.divider()
    
    # Info section
    with st.expander(t('trial.how_it_works')):
        st.markdown(t('trial.how_it_works_content'))
    
    with st.expander(t('trial.get_unlimited')):
        st.markdown(t('trial.get_unlimited_content'))
    
    # Storage info
    st.caption(f"📦 {t('trial.storage')}: {status.get('storage', 'Unknown')}")
    st.caption(f"📅 {t('trial.resets_daily')}")


def check_and_show_quota_warning(
    t: Translator,
    mode: str,
    resolution: str = "1K",
    count: int = 1
) -> bool:
    """
    Check quota and show warning if insufficient.
    
    Args:
        t: Translator instance
        mode: Generation mode
        resolution: Image resolution
        count: Number of images
    
    Returns:
        True if quota is available, False otherwise
    """
    if not is_trial_mode():
        return True  # Not in trial mode, no quota check needed
    
    quota_service = get_trial_quota_service()
    can_generate, reason, quota_info = quota_service.check_quota(mode, resolution, count)
    
    if not can_generate:
        # Show error with quota info
        st.error(f"❌ {t('trial.quota_exceeded')}: {reason}")
        
        # Show current status
        if quota_info:
            if "global_remaining" in quota_info:
                st.info(
                    f"📊 {t('trial.global_quota')}: "
                    f"{quota_info['global_used']}/{quota_info['global_limit']} {t('trial.quota_used')} "
                    f"({quota_info['global_remaining']} {t('trial.remaining')})"
                )
            
            if "mode_remaining" in quota_info:
                st.info(
                    f"🎨 {quota_info['mode']}: "
                    f"{quota_info['mode_used']}/{quota_info['mode_limit']} {t('trial.quota_used')} "
                    f"({quota_info['mode_remaining']} {t('trial.remaining')})"
                )
        
        # Show how to get more quota
        st.info(t('trial.get_more_quota_hint'))
        
        return False
    
    return True


def consume_quota_after_generation(
    mode: str,
    resolution: str = "1K",
    count: int = 1,
    success: bool = True
):
    """
    Consume quota after successful generation.

    Args:
        mode: Generation mode
        resolution: Image resolution
        count: Number of images generated
        success: Whether generation was successful
    """
    if not is_trial_mode():
        return

    if not success:
        return  # Don't consume quota if generation failed

    quota_service = get_trial_quota_service()
    quota_service.consume_quota(mode, resolution, count)
