"""
Basic image generation component with prompt library integration.
"""
import time
from io import BytesIO
import streamlit as st
from i18n import Translator
from services import (
    ImageGenerator,
    GenerationStateManager,
    get_current_user_history_sync,
    get_friendly_error_message,
    get_current_user_prompt_storage,
    get_prompt_generator,
    is_trial_mode,
)
from .trial_quota_display import check_and_show_quota_warning, consume_quota_after_generation


def render_basic_generation(t: Translator, settings: dict, generator: ImageGenerator):
    """
    Render the basic image generation interface.

    Args:
        t: Translator instance
        settings: Current settings from sidebar
        generator: ImageGenerator instance
    """
    # Initialize generation state
    GenerationStateManager.init_session_state()

    st.header(t("basic.title"))

    # Prompt library integration
    _render_prompt_library_section(t, generator)

    # Prompt input
    prompt = st.text_area(
        t("basic.prompt_label"),
        placeholder=t("basic.prompt_placeholder"),
        height=100,
        key="prompt_input",
        value=st.session_state.get("prompt_input", "")
    )

    # Show hint when prompt is empty
    if not prompt.strip():
        st.caption(f"💡 {t('basic.empty_hint')}")

    # Check generation state
    is_generating = GenerationStateManager.is_generating()
    can_generate, block_reason = GenerationStateManager.can_start_generation()

    # Generate button
    button_disabled = not prompt.strip() or not can_generate

    generate_clicked = st.button(
        t("basic.generate_btn") if not is_generating else t("basic.generating"),
        type="primary",
        disabled=button_disabled
    )

    # Handle generation button click - start task and rerun to update UI
    if generate_clicked and prompt.strip() and can_generate:
        # Check trial quota if in trial mode
        if is_trial_mode():
            if not check_and_show_quota_warning(t, "basic", settings["resolution"], 1):
                return  # Quota exceeded, stop here
        
        # Save generation params to session state for use after rerun
        st.session_state._pending_generation = {
            "prompt": prompt,
            "settings": settings.copy(),
        }
        # Start generation task (sets is_generating = True)
        GenerationStateManager.start_generation(
            prompt=prompt,
            mode="basic",
            resolution=settings["resolution"]
        )
        # Rerun immediately to update button state (disable it)
        st.rerun()

    # Execute generation when is_generating is True
    if is_generating and "_pending_generation" in st.session_state:
        pending = st.session_state._pending_generation
        gen_prompt = pending["prompt"]
        gen_settings = pending["settings"]

        # Create a placeholder for progress
        progress_container = st.empty()
        status_container = st.empty()

        result = None
        with status_container.container():
            # Show progress indicator
            estimated_time = GenerationStateManager.ESTIMATED_TIMES.get(
                gen_settings["resolution"], 10.0
            )
            st.info(f"🎨 {t('generation.in_progress')} ({t('generation.estimated_time', seconds=f'{estimated_time:.0f}')})")

            # Progress bar
            progress_bar = st.progress(0, text=t("basic.generating"))

            try:
                # Run sync generation
                result = generator.generate(
                    prompt=gen_prompt,
                    aspect_ratio=gen_settings["aspect_ratio"],
                    resolution=gen_settings["resolution"],
                    enable_thinking=gen_settings["enable_thinking"],
                    enable_search=gen_settings["enable_search"],
                    safety_level=gen_settings.get("safety_level", "moderate"),
                )

                # Update progress to 100%
                progress_bar.progress(1.0, text=t("generation.complete"))

                # Complete the generation task
                GenerationStateManager.complete_generation(
                    result=result,
                    error=result.error if result.error else None
                )
                
                # Mark quota consumption needed (will be consumed after rerun)
                if not result.error and result.image:
                    st.session_state._quota_to_consume = {
                        "mode": "basic",
                        "resolution": gen_settings["resolution"],
                        "count": 1
                    }

            except Exception as e:
                GenerationStateManager.complete_generation(error=str(e))
                del st.session_state._pending_generation
                st.error(f"❌ {t('basic.error')}: {get_friendly_error_message(str(e), t)}")
                return

        # Clean up pending generation
        del st.session_state._pending_generation

        # Clear progress containers
        progress_container.empty()
        status_container.empty()

        # Handle result
        if result.error:
            icon = "🛡️" if result.safety_blocked else "❌"
            st.error(f"{icon} {t('basic.error')}: {get_friendly_error_message(result.error, t)}")
        elif result.image:
            # Save using history sync manager (user-specific)
            history_sync = get_current_user_history_sync()
            filename = history_sync.save_to_history(
                image=result.image,
                prompt=gen_prompt,
                settings=gen_settings,
                duration=result.duration,
                mode="basic",
                text_response=result.text,
                thinking=result.thinking,
            )

            # Toast notification for save success
            if filename:
                st.toast(t("toast.image_saved", filename=filename), icon="✅")

            # Store as last result for this mode
            st.session_state.basic_last_result = {
                "image": result.image,
                "text": result.text,
                "thinking": result.thinking,
                "duration": result.duration,
                "filename": filename,
            }

        # Rerun to update button state and show result
        st.rerun()

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

    # Show last generated image from current session (only for basic mode)
    if not is_generating and "basic_last_result" in st.session_state and st.session_state.basic_last_result:
        _display_history_item(t, st.session_state.basic_last_result)


def _display_result(t: Translator, image, text: str, thinking: str,
                   duration: float, filename: str):
    """Display the generation result."""
    st.subheader(t("basic.result"))

    # Show thinking if available
    if thinking:
        with st.expander(t("basic.thinking_label"), expanded=False):
            st.write(thinking)

    # Show image
    st.image(image, width="stretch")

    # Action bar: timing info and download button
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"⏱️ {t('basic.time_label')}: {duration:.2f} {t('basic.seconds')}")
    with col2:
        buf = BytesIO()
        image.save(buf, format="PNG")
        download_name = filename.split("/")[-1] if "/" in filename else filename
        st.download_button(
            f"⬇️ {t('basic.download_btn')}",
            data=buf.getvalue(),
            file_name=download_name,
            mime="image/png",
            width="stretch"
        )

    # Show text response
    if text:
        with st.expander(t("basic.response_label"), expanded=False):
            st.write(text)


def _display_history_item(t: Translator, item: dict):
    """Display a history item."""
    st.subheader(t("basic.result"))

    if item.get("thinking"):
        with st.expander(t("basic.thinking_label"), expanded=False):
            st.write(item["thinking"])

    # Show image
    st.image(item["image"], width="stretch")

    # Action bar
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"⏱️ {t('basic.time_label')}: {item['duration']:.2f} {t('basic.seconds')}")
    with col2:
        buf = BytesIO()
        item["image"].save(buf, format="PNG")
        download_name = item.get("filename", "generated_image.png")
        if "/" in download_name:
            download_name = download_name.split("/")[-1]
        st.download_button(
            f"⬇️ {t('basic.download_btn')}",
            data=buf.getvalue(),
            file_name=download_name,
            mime="image/png",
            width="stretch"
        )

    if item.get("text"):
        with st.expander(t("basic.response_label"), expanded=False):
            st.write(item["text"])


def _render_prompt_library_section(t: Translator, generator: ImageGenerator):
    """Render the prompt library integration section."""
    # Initialize services
    prompt_storage = get_current_user_prompt_storage()
    prompt_gen = get_prompt_generator(generator._api_key)

    # Tabs for different prompt sources
    tab1, tab2 = st.tabs([
        "📚 " + t("basic.library_tab", default="Prompt Library"),
        "✨ " + t("basic.ai_tools_tab", default="AI Tools")
    ])

    # Tab 1: Prompt Library (includes favorites)
    with tab1:
        _render_library_with_favorites(t, prompt_storage)

    # Tab 2: AI Tools (enhance + generate)
    with tab2:
        _render_ai_tools(t, prompt_gen, prompt_storage)


def _render_library_with_favorites(t: Translator, storage):
    """Render prompt library with favorites toggle."""
    import random
    
    # Get current language
    current_lang = st.session_state.get("language", "en")
    
    # Toggle between Library and Favorites
    view_mode = st.radio(
        "View",
        options=["library", "favorites"],
        format_func=lambda x: {"library": "📚 " + t("basic.library_view", default="Library"), 
                               "favorites": "⭐ " + t("basic.favorites_view", default="Favorites")}[x],
        horizontal=True,
        label_visibility="collapsed"
    )
    
    if view_mode == "library":
        _render_library_view(t, storage, current_lang)
    else:
        _render_favorites_view(t, storage)


def _render_library_view(t: Translator, storage, current_lang):
    """Render the library view."""
    import random
    
    st.caption(t("basic.library_caption", default="Browse prompts by category"))

    # Category selector and refresh button
    col1, col2 = st.columns([3, 1])
    
    with col1:
        categories = storage.get_all_categories(language=current_lang)
        if not categories:
            st.info(t("basic.library_empty", default="No prompts yet. Generate some in AI Tools!"))
            return

        # Category name translation mapping
        category_names = {
            "portrait": t("templates.categories.portrait", default="Portrait"),
            "product": t("templates.categories.product", default="Product"),
            "landscape": t("templates.categories.landscape", default="Landscape"),
            "art": t("templates.categories.art", default="Art"),
            "food": t("templates.categories.food", default="Food"),
            "architecture": t("templates.categories.architecture", default="Architecture"),
        }
        
        selected_category = st.selectbox(
            t("basic.select_category", default="Category"),
            options=categories,
            format_func=lambda x: category_names.get(x, x.title()),
            label_visibility="collapsed",
            key="lib_category_select"
        )
    
    with col2:
        if st.button("🔄", key="lib_refresh", help=t("basic.refresh_prompts", default="Refresh"), use_container_width=True):
            if "lib_shuffle_seed" not in st.session_state:
                st.session_state.lib_shuffle_seed = 0
            st.session_state.lib_shuffle_seed += 1
            st.rerun()

    # Load prompts
    prompts = storage.load_category_prompts(selected_category, language=current_lang)
    if not prompts:
        st.info(t("basic.category_empty", default="No prompts in this category"))
        return

    # Shuffle prompts based on seed
    seed = st.session_state.get("lib_shuffle_seed", 0)
    random.seed(seed)
    shuffled_prompts = prompts.copy()
    random.shuffle(shuffled_prompts)

    # Display prompts (show first 5)
    st.caption(f"📊 {len(prompts)} {t('basic.prompts_available', default='prompts available')}")
    
    for idx, prompt_data in enumerate(shuffled_prompts[:5]):
        prompt_text = prompt_data.get("prompt", "")
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.caption(f"{idx + 1}. {prompt_text[:80]}{'...' if len(prompt_text) > 80 else ''}")
        with col2:
            if st.button("✨", key=f"lib_use_{selected_category}_{seed}_{idx}", help=t("basic.use_prompt", default="Use")):
                st.session_state.prompt_input = prompt_text
                st.rerun()
        with col3:
            if st.button("⭐", key=f"lib_fav_{selected_category}_{seed}_{idx}", help=t("basic.add_favorite", default="Favorite")):
                if storage.add_to_favorites(prompt_data):
                    st.toast(t("basic.added_favorite", default="Added to favorites!"), icon="⭐")


def _render_favorites_view(t: Translator, storage):
    """Render the favorites view."""
    import random
    
    st.caption(t("basic.favorites_caption", default="Your favorite prompts"))

    # Refresh button
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption("")  # Spacer
    with col2:
        if st.button("🔄", key="fav_refresh", help=t("basic.refresh_prompts", default="Refresh"), use_container_width=True):
            if "fav_shuffle_seed" not in st.session_state:
                st.session_state.fav_shuffle_seed = 0
            st.session_state.fav_shuffle_seed += 1
            st.rerun()

    favorites = storage.get_favorites()
    if not favorites:
        st.info(t("basic.favorites_empty", default="No favorites yet. Star prompts in Library!"))
        return

    # Shuffle favorites
    seed = st.session_state.get("fav_shuffle_seed", 0)
    random.seed(seed)
    shuffled_favs = favorites.copy()
    random.shuffle(shuffled_favs)

    st.caption(f"⭐ {len(favorites)} {t('basic.favorites_count', default='favorites')}")
    
    for idx, fav in enumerate(shuffled_favs[:5]):
        prompt_text = fav.get("prompt", "")
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.caption(f"{idx + 1}. {prompt_text[:80]}{'...' if len(prompt_text) > 80 else ''}")
        with col2:
            if st.button("✨", key=f"fav_use_{seed}_{idx}", help=t("basic.use_prompt", default="Use")):
                st.session_state.prompt_input = prompt_text
                st.rerun()
        with col3:
            if st.button("🗑️", key=f"fav_del_{seed}_{idx}", help=t("basic.remove_favorite", default="Remove")):
                if storage.remove_from_favorites(prompt_text):
                    st.toast(t("basic.removed_favorite", default="Removed from favorites"), icon="🗑️")
                    st.rerun()


def _render_library_quick_access_old(t: Translator, storage):
    """Render quick access to prompt library."""
    import random
    
    # Get current language
    current_lang = st.session_state.get("language", "en")
    
    st.caption(t("basic.library_caption", default="Browse prompts by category"))

    # Category selector and refresh button
    col1, col2 = st.columns([3, 1])
    
    with col1:
        categories = storage.get_all_categories(language=current_lang)
        if not categories:
            st.info(t("basic.library_empty", default="No prompts yet. Go to Templates to generate some!"))
            return

        # Category name translation mapping
        category_names = {
            "portrait": t("templates.categories.portrait", default="Portrait"),
            "product": t("templates.categories.product", default="Product"),
            "landscape": t("templates.categories.landscape", default="Landscape"),
            "art": t("templates.categories.art", default="Art"),
            "food": t("templates.categories.food", default="Food"),
            "architecture": t("templates.categories.architecture", default="Architecture"),
        }
        
        selected_category = st.selectbox(
            t("basic.select_category", default="Category"),
            options=categories,
            format_func=lambda x: category_names.get(x, x.title()),
            label_visibility="collapsed",
            key="lib_category_select"
        )
    
    with col2:
        if st.button("🔄", key="lib_refresh", help=t("basic.refresh_prompts", default="Refresh"), use_container_width=True):
            # Increment shuffle seed to get different prompts
            if "lib_shuffle_seed" not in st.session_state:
                st.session_state.lib_shuffle_seed = 0
            st.session_state.lib_shuffle_seed += 1
            st.rerun()

    # Load prompts
    prompts = storage.load_category_prompts(selected_category, language=current_lang)
    if not prompts:
        st.info(t("basic.category_empty", default="No prompts in this category"))
        return

    # Shuffle prompts based on seed
    seed = st.session_state.get("lib_shuffle_seed", 0)
    random.seed(seed)
    shuffled_prompts = prompts.copy()
    random.shuffle(shuffled_prompts)

    # Display prompts (show first 5)
    st.caption(f"📊 {len(prompts)} {t('basic.prompts_available', default='prompts available')}")
    
    for idx, prompt_data in enumerate(shuffled_prompts[:5]):
        prompt_text = prompt_data.get("prompt", "")
        col1, col2 = st.columns([4, 1])
        with col1:
            st.caption(f"{idx + 1}. {prompt_text[:80]}{'...' if len(prompt_text) > 80 else ''}")
        with col2:
            if st.button("✨", key=f"lib_use_{selected_category}_{seed}_{idx}", help=t("basic.use_prompt", default="Use")):
                st.session_state.prompt_input = prompt_text
                st.rerun()


def _render_ai_tools(t: Translator, prompt_gen, storage):
    """Render AI tools: enhance and generate."""
    # Get current language
    current_lang = st.session_state.get("language", "en")
    
    # Sub-tabs for AI tools
    ai_tab1, ai_tab2 = st.tabs([
        "✨ " + t("basic.enhance_tool", default="Enhance Prompt"),
        "🎲 " + t("basic.generate_tool", default="Generate New")
    ])
    
    with ai_tab1:
        _render_ai_enhance_section(t, prompt_gen)
    
    with ai_tab2:
        _render_generate_new_prompts(t, prompt_gen, storage, current_lang)


def _render_generate_new_prompts(t: Translator, prompt_gen, storage, current_lang):
    """Render the generate new prompts section."""
    st.caption(t("basic.generate_caption", default="Generate new prompts with AI"))
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Category name translation mapping
        category_names = {
            "portrait": t("templates.categories.portrait", default="Portrait"),
            "product": t("templates.categories.product", default="Product"),
            "landscape": t("templates.categories.landscape", default="Landscape"),
            "art": t("templates.categories.art", default="Art"),
            "food": t("templates.categories.food", default="Food"),
            "architecture": t("templates.categories.architecture", default="Architecture"),
        }
        
        categories = ["portrait", "product", "landscape", "art", "food", "architecture"]
        gen_category = st.selectbox(
            t("basic.generate_category", default="Category"),
            options=categories,
            format_func=lambda x: category_names.get(x, x.title())
        )
    
    with col2:
        gen_style = st.text_input(
            t("basic.generate_style", default="Style (optional)"),
            placeholder=t("basic.generate_style_placeholder", default="e.g., photorealistic, vintage")
        )
    
    gen_count = st.slider(
        t("basic.generate_count", default="Number of prompts"),
        min_value=5,
        max_value=20,
        value=10
    )
    
    if st.button("🚀 " + t("basic.generate_prompts_btn", default="Generate Prompts"), type="primary", use_container_width=True):
        with st.spinner(t("basic.generating_prompts", default="Generating prompts with AI...")):
            try:
                prompts = prompt_gen.generate_category_prompts(
                    category=gen_category,
                    style=gen_style if gen_style else None,
                    count=gen_count,
                    language=current_lang
                )
                
                if prompts:
                    st.session_state.generated_prompts_new = prompts
                    st.session_state.generated_category_new = gen_category
                    st.success(f"✅ {t('basic.generated_success', default='Generated')} {len(prompts)} {t('basic.prompts_available', default='prompts')}")
                else:
                    st.error(t("basic.generate_failed", default="Failed to generate prompts"))
                    
            except Exception as e:
                st.error(f"{t('basic.error', default='Error')}: {str(e)}")
    
    # Display generated prompts
    if "generated_prompts_new" in st.session_state and st.session_state.generated_prompts_new:
        st.divider()
        st.subheader(t("basic.generated_prompts", default="Generated Prompts"))
        
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("💾 " + t("basic.save_all_btn", default="Save All"), use_container_width=True):
                category = st.session_state.get("generated_category_new", "art")
                saved_count = 0
                for prompt in st.session_state.generated_prompts_new:
                    if storage.add_prompt_to_category(category, prompt, language=current_lang):
                        saved_count += 1
                st.success(f"💾 {t('basic.saved_prompts', default='Saved')} {saved_count} {t('basic.prompts_available', default='prompts')}")
                storage.clear_cache()
                del st.session_state.generated_prompts_new
                st.rerun()
        
        for idx, prompt_data in enumerate(st.session_state.generated_prompts_new):
            with st.container(border=True):
                prompt_text = prompt_data.get("prompt", "")
                st.write(prompt_text)
                
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    if st.button("✨", key=f"use_gen_new_{idx}", help=t("basic.use_prompt", default="Use"), use_container_width=True):
                        st.session_state.prompt_input = prompt_text
                        st.rerun()
                with col2:
                    if st.button("⭐", key=f"fav_gen_new_{idx}", help=t("basic.add_favorite", default="Favorite"), use_container_width=True):
                        if storage.add_to_favorites(prompt_data):
                            st.toast(t("basic.added_favorite", default="Added to favorites!"), icon="⭐")
                with col3:
                    if st.button("💾", key=f"save_gen_new_{idx}", help=t("basic.save_prompt", default="Save"), use_container_width=True):
                        category = st.session_state.get("generated_category_new", "art")
                        if storage.add_prompt_to_category(category, prompt_data, language=current_lang):
                            st.toast(t("basic.saved_prompt", default="Saved!"), icon="💾")
                            storage.clear_cache()


def _render_ai_enhance_section(t: Translator, prompt_gen):
    """Render AI prompt enhancement section."""
    st.caption(t("basic.enhance_caption", default="Enhance your prompt with AI"))

    # Get current prompt
    current_prompt = st.session_state.get("prompt_input", "")

    if not current_prompt.strip():
        st.info(t("basic.enhance_hint", default="Enter a prompt below, then come back here to enhance it!"))
        return

    # Show current prompt
    st.text_area(
        t("basic.current_prompt", default="Current prompt"),
        value=current_prompt,
        height=60,
        disabled=True,
        key="enhance_current"
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        if st.button("✨ " + t("basic.enhance_btn", default="Enhance with AI"), use_container_width=True):
            with st.spinner(t("basic.enhancing", default="Enhancing...")):
                try:
                    enhanced = prompt_gen.enhance_prompt(
                        current_prompt,
                        language=st.session_state.get("language", "en")
                    )
                    st.session_state.enhanced_prompt = enhanced
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    with col2:
        if st.button("🎲 " + t("basic.variations_btn", default="Generate Variations"), use_container_width=True):
            with st.spinner(t("basic.generating_variations", default="Generating...")):
                try:
                    variations = prompt_gen.generate_variations(
                        current_prompt,
                        count=3,
                        variation_type="style"
                    )
                    st.session_state.prompt_variations = variations
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    # Show enhanced prompt
    if "enhanced_prompt" in st.session_state and st.session_state.enhanced_prompt:
        st.divider()
        st.caption("✨ " + t("basic.enhanced_result", default="Enhanced prompt"))
        enhanced = st.session_state.enhanced_prompt

        col1, col2 = st.columns([4, 1])
        with col1:
            st.success(enhanced)
        with col2:
            if st.button("📋", key="use_enhanced", help="Use enhanced prompt"):
                st.session_state.prompt_input = enhanced
                del st.session_state.enhanced_prompt
                st.rerun()

    # Show variations
    if "prompt_variations" in st.session_state and st.session_state.prompt_variations:
        st.divider()
        st.caption("🎲 " + t("basic.variations_result", default="Variations"))
        for idx, variation in enumerate(st.session_state.prompt_variations):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.info(f"{idx + 1}. {variation}")
            with col2:
                if st.button("📋", key=f"use_var_{idx}", help="Use this variation"):
                    st.session_state.prompt_input = variation
                    del st.session_state.prompt_variations
                    st.rerun()
