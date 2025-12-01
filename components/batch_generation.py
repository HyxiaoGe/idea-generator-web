"""
Batch image generation component.
Generate multiple image variations from a single prompt.
"""
from io import BytesIO
from typing import List
from datetime import datetime
import zipfile
import io
import streamlit as st
from PIL import Image
from i18n import Translator
from services import (
    ImageGenerator,
    GenerationStateManager,
    get_history_sync,
    get_friendly_error_message,
)
from services.cost_estimator import estimate_cost


def generate_batch(
    generator: ImageGenerator,
    prompt: str,
    count: int,
    aspect_ratio: str,
    resolution: str,
    safety_level: str = "moderate",
    progress_callback=None,
    cancel_check=None
) -> List:
    """Generate multiple images synchronously."""
    results = []

    for i in range(count):
        # Check for cancellation
        if cancel_check and cancel_check():
            break

        result = generator.generate(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            enable_thinking=False,
            enable_search=False,
            safety_level=safety_level,
        )
        results.append(result)

        if progress_callback:
            progress_callback(i + 1, count)

    return results


def render_batch_generation(t: Translator, settings: dict, generator: ImageGenerator):
    """
    Render the batch image generation interface.

    Args:
        t: Translator instance
        settings: Current settings from sidebar
        generator: ImageGenerator instance
    """
    # Initialize generation state
    GenerationStateManager.init_session_state()

    st.header(t("batch.title"))
    st.caption(t("batch.description"))

    # Prompt input
    prompt = st.text_area(
        t("batch.prompt_label"),
        placeholder=t("batch.prompt_placeholder"),
        height=100,
        key="batch_prompt"
    )

    # Batch settings
    col1, col2 = st.columns(2)

    with col1:
        count = st.slider(
            t("batch.count_label"),
            min_value=2,
            max_value=8,
            value=4,
            step=1,
            key="batch_count"
        )

    with col2:
        # Show cost estimate
        estimate = estimate_cost(settings["resolution"], count)
        st.metric(
            t("batch.cost_label"),
            f"${estimate.total_cost:.2f}",
            delta=f"{count} {t('batch.images')}",
            delta_color="off"
        )

    # Variation mode hint
    st.info(t("batch.variation_hint"))

    # Check generation state
    is_generating = GenerationStateManager.is_generating()
    can_generate, block_reason = GenerationStateManager.can_start_generation()

    # Generate button row
    col1, col2, col3 = st.columns([1, 1, 3])

    with col1:
        button_disabled = not prompt.strip() or not can_generate
        generate_clicked = st.button(
            t("basic.generate_btn") if not is_generating else t("basic.generating"),
            type="primary",
            disabled=button_disabled,
            width="stretch"
        )

    with col2:
        if is_generating:
            if st.button(t("generation.cancel_btn"), width="stretch"):
                GenerationStateManager.cancel_generation()
                st.toast(t("generation.cancelled"), icon="⚠️")
                st.rerun()

    if generate_clicked and prompt.strip() and can_generate:
        # Start generation task
        task = GenerationStateManager.start_generation(
            prompt=prompt,
            mode="batch",
            resolution=settings["resolution"]
        )

        if task:
            # Create status container for progress
            with st.status(t("batch.generating"), expanded=True) as status:
                progress_bar = st.progress(0, text=t("batch.progress_text", current=0, total=count))

                # Progress callback
                def update_progress(current, total):
                    progress = current / total
                    progress_bar.progress(progress, text=t("batch.progress_text", current=current, total=total))

                # Cancel check callback
                def check_cancelled():
                    return GenerationStateManager.is_cancelled()

                try:
                    # Run batch generation
                    results = generate_batch(
                        generator=generator,
                        prompt=prompt,
                        count=count,
                        aspect_ratio=settings["aspect_ratio"],
                        resolution=settings["resolution"],
                        safety_level=settings.get("safety_level", "moderate"),
                        progress_callback=update_progress,
                        cancel_check=check_cancelled
                    )

                    # Complete the generation task
                    GenerationStateManager.complete_generation(result=results)
                    status.update(label=t("batch.complete"), state="complete", expanded=True)

                except Exception as e:
                    GenerationStateManager.complete_generation(error=str(e))
                    st.error(f"❌ {t('basic.error')}: {get_friendly_error_message(str(e), t)}")
                    return

            # Calculate statistics
            successful = [r for r in results if r.image is not None]
            failed = [r for r in results if r.error is not None]
            total_time = sum(r.duration for r in results)

            # Save to history using sync manager
            history_sync = get_history_sync()
            for idx, result in enumerate(successful):
                history_sync.save_to_history(
                    image=result.image,
                    prompt=f"[Batch {idx + 1}/{len(successful)}] {prompt}",
                    settings=settings,
                    duration=result.duration,
                    mode="batch",
                    text_response=result.text,
                )

            # Store as last result for this mode
            st.session_state.batch_last_results = {
                "images": [r.image for r in successful],
                "total_time": total_time,
                "successful_count": len(successful),
                "failed_count": len(failed),
                "failed_errors": [r.error for r in failed if r.error],
                "prompt": prompt,
            }

            st.toast(t("toast.batch_saved", count=len(successful)), icon="✅")

            if failed:
                st.toast(t("toast.batch_failed", count=len(failed)), icon="⚠️")

            # Display results
            _display_batch_results(t, st.session_state.batch_last_results)

    # Show last generated results from current session
    elif not is_generating and "batch_last_results" in st.session_state and st.session_state.batch_last_results:
        _display_batch_results(t, st.session_state.batch_last_results)


def _display_batch_results(t: Translator, data: dict):
    """Display batch generation results."""
    st.subheader(t("batch.results"))

    # Show stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(t("batch.successful"), data["successful_count"])
    with col2:
        st.metric(t("batch.failed"), data["failed_count"])
    with col3:
        st.metric(t("batch.total_time"), f"{data['total_time']:.1f}s")

    st.divider()

    # Display images in grid
    images = data.get("images", [])
    if images:
        cols = st.columns(min(len(images), 4))

        for idx, image in enumerate(images):
            col_idx = idx % 4
            with cols[col_idx]:
                st.image(image, width="stretch")

                buf = BytesIO()
                image.save(buf, format="PNG")
                st.download_button(
                    f"⬇️ #{idx + 1}",
                    data=buf.getvalue(),
                    file_name=f"batch_{idx + 1}.png",
                    mime="image/png",
                    key=f"download_batch_{idx}",
                    width="stretch"
                )

    # Show errors if any
    failed_errors = data.get("failed_errors", [])
    if failed_errors:
        with st.expander(t("batch.errors"), expanded=False):
            for idx, error in enumerate(failed_errors):
                st.write(f"{t('batch.error_item', num=idx + 1)}: {error}")

    # Download all as ZIP
    if len(images) > 1:
        st.divider()

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            prompt = data.get("prompt", "batch")
            for idx, image in enumerate(images):
                img_buffer = BytesIO()
                image.save(img_buffer, format="PNG")
                prompt_slug = "".join(c if c.isalnum() or c == " " else "" for c in prompt[:20])
                prompt_slug = "_".join(prompt_slug.split())
                zip_file.writestr(f"batch_{idx + 1}_{prompt_slug}.png", img_buffer.getvalue())

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            f"📦 {t('batch.download_all')} ({len(images)} {t('batch.images')})",
            data=zip_buffer.getvalue(),
            file_name=f"batch_{timestamp}.zip",
            mime="application/zip",
            key="download_batch_zip",
            width="stretch"
        )
