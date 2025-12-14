"""
Batch image generation component.
Generate multiple image variations from a single prompt.
"""
from io import BytesIO
from typing import List, Tuple, Dict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import zipfile
import io
import streamlit as st
from PIL import Image
from i18n import Translator
from services import (
    ImageGenerator,
    GenerationStateManager,
    get_current_user_history_sync,
    get_friendly_error_message,
    is_trial_mode,
    get_content_filter,
)
from services.cost_estimator import estimate_cost
from .trial_quota_display import check_and_show_quota_warning, consume_quota_after_generation


def generate_batch(
    generator: ImageGenerator,
    prompt: str,
    count: int,
    aspect_ratio: str,
    resolution: str,
    safety_level: str = "moderate",
    progress_callback=None,
    cancel_check=None,
    parallel: bool = True,
    max_workers: int = 3,
) -> Tuple[List, Dict[int, str]]:
    """
    Generate multiple images with optional parallel execution.
    
    Args:
        generator: ImageGenerator instance
        prompt: Text prompt for generation
        count: Number of images to generate
        aspect_ratio: Image aspect ratio
        resolution: Image resolution
        safety_level: Content safety level
        progress_callback: Callback for progress updates
        cancel_check: Callback to check if cancelled
        parallel: Whether to use parallel generation (default: True)
        max_workers: Maximum concurrent workers (default: 3)
    
    Returns:
        Tuple of (results_list, errors_dict)
    """
    if not parallel or count == 1:
        # Fall back to serial generation
        return _generate_batch_serial(
            generator, prompt, count, aspect_ratio, resolution,
            safety_level, progress_callback, cancel_check
        )
    
    return _generate_batch_parallel(
        generator, prompt, count, aspect_ratio, resolution,
        safety_level, progress_callback, cancel_check, max_workers
    )


def _generate_batch_serial(
    generator: ImageGenerator,
    prompt: str,
    count: int,
    aspect_ratio: str,
    resolution: str,
    safety_level: str,
    progress_callback,
    cancel_check,
) -> Tuple[List, Dict[int, str]]:
    """Generate images serially (original implementation)."""
    results = []
    errors = {}

    for i in range(count):
        # Check for cancellation
        if cancel_check and cancel_check():
            break

        try:
            result = generator.generate(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                enable_thinking=False,
                enable_search=False,
                safety_level=safety_level,
            )
            results.append(result)
        except Exception as e:
            # Create error result
            from services.generator import GenerationResult
            result = GenerationResult(error=str(e))
            results.append(result)
            errors[i] = str(e)

        if progress_callback:
            progress_callback(i + 1, count)

    return results, errors


def _generate_batch_parallel(
    generator: ImageGenerator,
    prompt: str,
    count: int,
    aspect_ratio: str,
    resolution: str,
    safety_level: str,
    progress_callback,
    cancel_check,
    max_workers: int,
) -> Tuple[List, Dict[int, str]]:
    """Generate images in parallel using ThreadPoolExecutor."""
    results = [None] * count
    errors = {}
    completed = 0
    
    def generate_single(idx: int):
        """Generate a single image and return with its index."""
        try:
            result = generator.generate(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                enable_thinking=False,
                enable_search=False,
                safety_level=safety_level,
            )
            return idx, result, None
        except Exception as e:
            # Create error result
            from services.generator import GenerationResult
            result = GenerationResult(error=str(e))
            return idx, result, str(e)
    
    # Use ThreadPoolExecutor for parallel generation
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {executor.submit(generate_single, i): i for i in range(count)}
        
        # Process completed tasks as they finish
        for future in as_completed(futures):
            # Check for cancellation
            if cancel_check and cancel_check():
                # Cancel remaining tasks
                for f in futures:
                    f.cancel()
                executor.shutdown(wait=False)
                break
            
            try:
                idx, result, error = future.result()
                results[idx] = result
                
                if error:
                    errors[idx] = error
                
                completed += 1
                
                if progress_callback:
                    progress_callback(completed, count)
                    
            except Exception as e:
                # Handle unexpected errors
                idx = futures[future]
                from services.generator import GenerationResult
                results[idx] = GenerationResult(error=str(e))
                errors[idx] = str(e)
                completed += 1
                
                if progress_callback:
                    progress_callback(completed, count)
    
    # Filter out None results (from cancellation)
    results = [r for r in results if r is not None]
    
    return results, errors


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

    # Variation mode hint and parallel mode toggle
    col_hint, col_parallel = st.columns([3, 1])
    
    with col_hint:
        st.info(t("batch.variation_hint"))
    
    with col_parallel:
        parallel_mode = st.toggle(
            t("batch.parallel_mode"),
            value=True,
            help=t("batch.parallel_help"),
            key="batch_parallel_mode"
        )

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
        # Check content safety first (two-layer: keywords + AI)
        content_filter = get_content_filter()
        is_safe, blocked_reason = content_filter.is_safe(prompt)
        if not is_safe:
            st.error(content_filter.get_blocked_message(t.language, blocked_reason))
            if blocked_reason.startswith("keyword:"):
                keyword = blocked_reason.split(":", 1)[1]
                st.caption(f"🚫 {t('errors.blocked_keyword')}: `{keyword}`")
            return  # Blocked, stop here

        # Check trial quota if in trial mode
        if is_trial_mode():
            if not check_and_show_quota_warning(t, "batch", settings["resolution"], count):
                return  # Quota exceeded, stop here

        # Start generation task
        task = GenerationStateManager.start_generation(
            prompt=prompt,
            mode="batch",
            resolution=settings["resolution"]
        )

        if task:
            # Create status container for progress
            with st.status(t("batch.generating"), expanded=True) as status:
                progress_bar = st.progress(0, text=t("batch.progress_parallel", completed=0, total=count))

                # Progress callback
                def update_progress(completed, total):
                    progress = completed / total
                    progress_bar.progress(progress, text=t("batch.progress_parallel", completed=completed, total=total))

                # Cancel check callback
                def check_cancelled():
                    return GenerationStateManager.is_cancelled()

                try:
                    # Run batch generation (use user's parallel mode preference)
                    results, batch_errors = generate_batch(
                        generator=generator,
                        prompt=prompt,
                        count=count,
                        aspect_ratio=settings["aspect_ratio"],
                        resolution=settings["resolution"],
                        safety_level=settings.get("safety_level", "moderate"),
                        progress_callback=update_progress,
                        cancel_check=check_cancelled,
                        parallel=parallel_mode,  # Use user's preference
                        max_workers=3,  # Limit concurrent requests to avoid rate limiting
                    )

                    # Complete the generation task
                    GenerationStateManager.complete_generation(result=results)
                    status.update(label=t("batch.complete"), state="complete", expanded=True)
                    
                    # Mark quota consumption needed (will be consumed after rerun)
                    successful_count = len([r for r in results if r.image is not None])
                    if successful_count > 0:
                        st.session_state._quota_to_consume = {
                            "mode": "batch",
                            "resolution": settings["resolution"],
                            "count": successful_count
                        }

                except Exception as e:
                    GenerationStateManager.complete_generation(error=str(e))
                    st.error(f"❌ {t('basic.error')}: {get_friendly_error_message(str(e), t)}")
                    return

            # Calculate statistics
            successful = [r for r in results if r.image is not None]
            failed = [r for r in results if r.error is not None]
            total_time = sum(r.duration for r in results)
            
            # Merge batch_errors into failed list for display
            for idx, error_msg in batch_errors.items():
                if idx < len(results) and results[idx].error:
                    # Error already captured in result
                    pass

            # Generate batch_id for this batch
            import uuid
            batch_id = str(uuid.uuid4())
            
            # Save to history using sync manager
            history_sync = get_current_user_history_sync()
            for idx, result in enumerate(successful):
                history_sync.save_to_history(
                    image=result.image,
                    prompt=prompt,  # Use original prompt, not with [Batch X/Y] prefix
                    settings=settings,
                    duration=result.duration,
                    mode="batch",
                    text_response=result.text,
                    session_id=batch_id,  # Use batch_id as session_id for grouping
                    chat_index=idx,  # Index within batch
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
