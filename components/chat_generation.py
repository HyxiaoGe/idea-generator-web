"""
Chat-based image generation component for iterative refinement.
"""
import json
from io import BytesIO
from datetime import datetime
import streamlit as st
from i18n import Translator
from services import (
    ChatSession,
    GenerationStateManager,
    get_current_user_history_sync,
    get_friendly_error_message,
    is_trial_mode,
    get_content_filter,
)
from .trial_quota_display import check_and_show_quota_warning, consume_quota_after_generation


def render_chat_generation(t: Translator, settings: dict, chat_session: ChatSession):
    """
    Render the chat-based image generation interface.

    Args:
        t: Translator instance
        settings: Current settings from sidebar
        chat_session: ChatSession instance
    """
    # Initialize generation state
    GenerationStateManager.init_session_state()

    st.header(t("chat.title"))
    st.caption(t("chat.description"))

    # Consume quota if needed (after rerun)
    if "_quota_to_consume" in st.session_state:
        quota_info = st.session_state._quota_to_consume
        consume_quota_after_generation(
            quota_info["mode"],
            quota_info["resolution"],
            quota_info["count"],
            True
        )
        del st.session_state._quota_to_consume
        # Rerun to update quota display in sidebar
        st.rerun()
    
    # Initialize chat messages in session state
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # Control buttons
    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
    with col1:
        if st.button(t("chat.start_btn"), width="stretch"):
            chat_session.clear_session()
            chat_session.start_session(aspect_ratio=settings["aspect_ratio"])
            st.session_state.chat_messages = [{
                "role": "assistant",
                "content": t("chat.welcome"),
                "image": None
            }]
            st.session_state.show_chat_clear_confirm = False
            st.rerun()

    with col2:
        # Clear button with confirmation
        has_messages = bool(st.session_state.chat_messages)
        if st.button(t("chat.clear_btn"), width="stretch", disabled=not has_messages):
            st.session_state.show_chat_clear_confirm = True

    with col3:
        # Export chat functionality
        if has_messages:
            export_data = _export_chat_data(st.session_state.chat_messages)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                f"📤 {t('chat.export_btn')}",
                data=export_data,
                file_name=f"chat_export_{timestamp}.json",
                mime="application/json",
                width="stretch"
            )

    # Show message count
    if has_messages:
        msg_count = len(st.session_state.chat_messages)
        st.caption(f"💬 {t('chat.messages_count', count=msg_count)}")

    # Clear confirmation dialog
    if st.session_state.get("show_chat_clear_confirm"):
        with st.container():
            st.warning(t("chat.clear_confirm"))
            confirm_col1, confirm_col2, confirm_col3 = st.columns([1, 1, 3])
            with confirm_col1:
                if st.button(t("history.yes_btn"), type="primary", key="chat_clear_yes"):
                    chat_session.clear_session()
                    st.session_state.chat_messages = []
                    st.session_state.show_chat_clear_confirm = False
                    st.rerun()
            with confirm_col2:
                if st.button(t("history.no_btn"), key="chat_clear_no"):
                    st.session_state.show_chat_clear_confirm = False
                    st.rerun()

    st.divider()

    # Show enhanced empty state if no messages yet
    if not st.session_state.chat_messages:
        _render_chat_empty_state(t)
        return

    # Display chat messages
    for idx, message in enumerate(st.session_state.chat_messages):
        role = message["role"]
        avatar = "🤖" if role == "assistant" else "👤"

        with st.chat_message(role, avatar=avatar):
            # Show text content
            if message.get("content"):
                st.write(message["content"])

            # Show thinking if available
            if message.get("thinking"):
                with st.expander(t("chat.thinking_label"), expanded=False):
                    st.write(message["thinking"])

            # Show image if available
            if message.get("image"):
                st.image(message["image"], width="stretch")

                # Download button - compact style
                buf = BytesIO()
                message["image"].save(buf, format="PNG")
                st.download_button(
                    f"⬇️ {t('history.download_btn')}",
                    data=buf.getvalue(),
                    file_name=f"chat_{idx + 1}.png",
                    mime="image/png",
                    key=f"download_chat_{idx}",
                    width="content"
                )

    # Check generation state
    is_generating = GenerationStateManager.is_generating()
    can_generate, block_reason = GenerationStateManager.can_start_generation()

    # Chat input (disabled during generation)
    if prompt := st.chat_input(t("chat.input_placeholder"), disabled=is_generating):
        if not can_generate:
            st.warning(f"⚠️ {block_reason}")
            return

        # Check content safety first (two-layer: keywords + AI)
        content_filter = get_content_filter()
        is_safe, blocked_reason = content_filter.is_safe(prompt)
        if not is_safe:
            st.error(content_filter.get_blocked_message(t.language, blocked_reason))
            if blocked_reason.startswith("keyword:"):
                keyword = blocked_reason.split(":", 1)[1]
                st.caption(f"🚫 {t('errors.blocked_keyword')}: `{keyword}`")
            st.stop()

        # Check trial quota if in trial mode
        if is_trial_mode():
            if not check_and_show_quota_warning(t, "chat", settings.get("resolution", "1K"), 1):
                return  # Quota exceeded, stop here

        # Add user message
        st.session_state.chat_messages.append({
            "role": "user",
            "content": prompt,
            "image": None
        })

        # Display user message immediately
        with st.chat_message("user", avatar="👤"):
            st.write(prompt)

        # Start generation task
        task = GenerationStateManager.start_generation(
            prompt=prompt,
            mode="chat",
            resolution=settings.get("resolution", "1K")
        )

        # Generate response
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner(t("basic.generating")):
                # Ensure session is started
                if not chat_session.is_active():
                    chat_session.start_session(aspect_ratio=settings["aspect_ratio"])

                try:
                    # Send message
                    response = chat_session.send_message(
                        message=prompt,
                        aspect_ratio=settings["aspect_ratio"],
                        safety_level=settings.get("safety_level", "moderate"),
                    )
                    GenerationStateManager.complete_generation(result=response)
                except Exception as e:
                    GenerationStateManager.complete_generation(error=str(e))
                    st.error(f"❌ {t('basic.error')}: {get_friendly_error_message(str(e), t)}")
                    st.rerun()

            if response.error:
                icon = "🛡️" if response.safety_blocked else "❌"
                friendly_error = get_friendly_error_message(response.error, t)
                st.error(f"{icon} {t('basic.error')}: {friendly_error}")
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": f"Error: {friendly_error}",
                    "image": None
                })
            else:
                # Show response
                if response.text:
                    st.write(response.text)

                if response.thinking:
                    with st.expander(t("chat.thinking_label"), expanded=False):
                        st.write(response.thinking)

                if response.image:
                    st.image(response.image, width="stretch")

                    # Download button - compact style
                    buf = BytesIO()
                    response.image.save(buf, format="PNG")
                    st.download_button(
                        f"⬇️ {t('history.download_btn')}",
                        data=buf.getvalue(),
                        file_name=f"chat_{len(st.session_state.chat_messages) + 1}.png",
                        mime="image/png",
                        key=f"download_chat_new",
                        width="content"
                    )

                # Mark quota consumption needed (will be consumed after rerun)
                if response.image:
                    st.session_state._quota_to_consume = {
                        "mode": "chat",
                        "resolution": settings.get("resolution", "1K"),
                        "count": 1
                    }
                
                # Store in history using sync manager
                if response.image:
                    history_sync = get_current_user_history_sync()
                    
                    # Get session ID and calculate chat index
                    session_id = chat_session.get_session_id()
                    # Count images in current session
                    chat_index = sum(1 for msg in st.session_state.chat_messages if msg.get("image") is not None)
                    
                    filename = history_sync.save_to_history(
                        image=response.image,
                        prompt=prompt,
                        settings=settings,
                        duration=response.duration,
                        mode="chat",
                        text_response=response.text,
                        thinking=response.thinking,
                        session_id=session_id,
                        chat_index=chat_index,
                    )

                    # Toast notification for save success
                    if filename:
                        st.toast(t("toast.image_saved", filename=filename), icon="✅")

                # Add to chat messages
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": response.text or "",
                    "image": response.image,
                    "thinking": response.thinking
                })

        st.rerun()


def _export_chat_data(messages: list) -> str:
    """
    Export chat messages to JSON format.

    Args:
        messages: List of chat messages

    Returns:
        JSON string of exportable chat data
    """
    export_messages = []
    for msg in messages:
        export_msg = {
            "role": msg.get("role", "unknown"),
            "content": msg.get("content", ""),
            "has_image": msg.get("image") is not None,
            "thinking": msg.get("thinking", ""),
        }
        export_messages.append(export_msg)

    export_data = {
        "exported_at": datetime.now().isoformat(),
        "message_count": len(export_messages),
        "messages": export_messages
    }

    return json.dumps(export_data, indent=2, ensure_ascii=False)


def _render_chat_empty_state(t: Translator):
    """Render enhanced empty state for chat mode."""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            f"""
            <div style="text-align: center; padding: 40px 20px;">
                <div style="font-size: 64px; margin-bottom: 16px;">💬</div>
                <h3 style="margin-bottom: 8px;">{t("chat.empty_title")}</h3>
                <p style="color: #888; margin-bottom: 16px;">{t("chat.empty_description")}</p>
                <p style="color: #666; font-size: 14px;">{t("chat.empty_cta")}</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Show refinement tips
    with st.expander(t("chat.refine_tips.title"), expanded=True):
        tips = t("chat.refine_tips.items")
        if isinstance(tips, list):
            for tip in tips:
                st.write(f"- {tip}")
