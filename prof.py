# -*- coding: utf-8 -*-
# VivaAI Secure — URL Generator
# Railway deployment entry point

from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import gradio as gr

# Load environment variables BEFORE importing modules that use VIVA_HMAC_SECRET
# This ensures .env file is loaded before prof.url_generator and other modules
# try to read VIVA_HMAC_SECRET at import time
load_dotenv()

# =========================
# Startup Validation
# =========================
# Validate required environment variables (fail fast in production)
environment = os.getenv("ENVIRONMENT", "development").lower()
if environment == "production":
    from shared.config_validation import validate_required_env_vars
    is_valid, error = validate_required_env_vars(["VIVA_HMAC_SECRET", "OPENAI_API_KEY"])
    if not is_valid:
        print(f"❌ Configuration Error: {error}")
        print("   Set required environment variables in .env file or environment variables.")
        import sys
        sys.exit(1)
else:
    # Warn in development if critical vars are missing
    missing = []
    if not os.getenv("VIVA_HMAC_SECRET"):
        missing.append("VIVA_HMAC_SECRET")
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if missing:
        print(f"⚠️  Warning: Missing environment variables: {', '.join(missing)}")
        print("   Set them in .env file for full functionality.")
        print("   See .env.example for a template.")

# =========================
# Module Imports
# =========================
# Import business logic modules
from prof.pdf_validator import validate_pdf_and_calculate_chunks
from prof.url_generator import encode_config_to_url_v2
from prof.cryptography import generate_secure_passphrase
from prof.utils import calculate_max_duration

# Import UI helpers and handlers
from prof.ui.helpers import (
    combine_date_time,
    update_end_date,
    format_duration_display,
    format_pdf_status_message,
)
from prof.ui.handlers import (
    handle_step1_checkbox_change,
    handle_validate_pdf_and_show_step3,
    handle_calculate_duration_and_show_generate,
    handle_generate_url,
    handle_copy_url_to_clipboard,
)

# =========================
# Dependency Injection System
# =========================

def _build_prof_dependencies():
    """
    Build dependencies dictionary for prof UI handlers.
    This function collects all dependencies needed by the extracted handler functions.
    """
    return {
        # Core business logic functions
        "validate_pdf_and_calculate_chunks": validate_pdf_and_calculate_chunks,
        "encode_config_to_url": encode_config_to_url_v2,
        "generate_secure_passphrase": generate_secure_passphrase,
        "calculate_max_duration": calculate_max_duration,
        
        # Helper functions
        "combine_date_time": combine_date_time,
        "format_duration_display": format_duration_display,
        "format_pdf_status_message": format_pdf_status_message,
    }

# =========================
# Wrapper Functions (Dependency Injection)
# =========================

def handle_step1_checkbox_wrapper(checked: bool, state: dict) -> tuple:
    """Wrapper for handle_step1_checkbox_change with dependency injection."""
    dependencies = _build_prof_dependencies()
    return handle_step1_checkbox_change(gr, dependencies, checked, state)

def handle_validate_pdf_wrapper(pdf_url: str, state: dict) -> tuple:
    """Wrapper for handle_validate_pdf_and_show_step3 with dependency injection."""
    dependencies = _build_prof_dependencies()
    return handle_validate_pdf_and_show_step3(gr, dependencies, pdf_url, state)

def handle_calculate_duration_wrapper(num_questions: int, min_followups: int, max_followups: int, time_per_question: int, state: dict) -> tuple:
    """Wrapper for handle_calculate_duration_and_show_generate with dependency injection."""
    dependencies = _build_prof_dependencies()
    return handle_calculate_duration_and_show_generate(gr, dependencies, num_questions, min_followups, max_followups, time_per_question, state)

def handle_generate_url_wrapper(pdf_url: str, base_url: str, course_id: str, exam_id: str, section_id: str, num_questions: int, min_followups: int, max_followups: int, time_per_question: int, start_date: str, start_time: str, end_date: str, end_time: str, state: dict):
    """Wrapper for handle_generate_url with dependency injection."""
    dependencies = _build_prof_dependencies()
    yield from handle_generate_url(gr, dependencies, pdf_url, base_url, course_id, exam_id, section_id, num_questions, min_followups, max_followups, time_per_question, start_date, start_time, end_date, end_time, state)

def handle_copy_url_wrapper(url: str) -> tuple:
    """Wrapper for handle_copy_url_to_clipboard with dependency injection."""
    dependencies = _build_prof_dependencies()
    return handle_copy_url_to_clipboard(gr, dependencies, url)

# =========================
# Gradio UI (Settings Tab - URL Generator)
# Sequential Accordion Flow: Step 1 → Step 2 → Step 3 (Generate URL)
# =========================

# Custom CSS for light green checkbox border
custom_css = """
.pdf-consent-checkbox {
    border: 2px solid #86efac !important;
    border-radius: 6px !important;
    padding: 10px 12px !important;
    margin: 10px 0 !important;
}
.pdf-consent-checkbox input[type="checkbox"] {
    accent-color: #86efac !important;
    width: 18px !important;
    height: 18px !important;
}
.pdf-consent-checkbox:hover {
    border-color: #4ade80 !important;
}
"""

with gr.Blocks(title="VivaAI Secure - Settings", css=custom_css) as demo:
    with gr.Tab("Settings"):
        # State management for chunk data
        chunk_state = gr.State({
            'num_valid_chunks': 0,
            'num_total_chunks': 0,
            'file_size_mb': 0.0
        })
        
        # Step 1: PDF Requirements Consent Accordion
        with gr.Accordion("⚠️ PDF Requirements - Consent", open=True, visible=True) as step1_accordion:
            gr.Markdown("""
            **📋 Requirements:**
            - **Cloud storage links** (Dropbox, Google Drive, OneDrive, Box, or direct URLs)
            - **Max:** 2MB file size, 50 pages (excess pages truncated)
            - **Format:** Text-based only (Word→PDF conversion recommended)
            
            **🚫 Avoid:**
            - Heavy images, scanned pages, complex tables, heavy math equations
            - **Confidential, private, or student data** (content sent to LLM)
            - Copyrighted material (ensure you have permission)
            
            **⚡ User Experience:**
            - Content quality directly affects exam question generation quality
            - Use clean, text-based PDFs for best results
            - Large files may take longer to process
            
            **🔒 Privacy & Processing:**
            - PDF content is processed by OpenAI's GPT models (GPT-4o-mini) for question generation
            - Content is chunked and sent to LLM during exam generation
            - Ensure compliance with data privacy regulations (FERPA, GDPR, etc.)
            - No long-term storage of PDF content (processed in real-time)
            """)
            step1_checkbox = gr.Checkbox(
                label=" I understand and agree to the PDF Requirements",
                value=False,
                info="I confirm that I have read and understood the PDF requirements, privacy implications, and processing details",
                elem_classes=["pdf-consent-checkbox"]
            )
        
        # Step 2: PDF URL Input Accordion
        with gr.Accordion("📄 Step 1: Upload PDF from Cloud Storage", open=False, visible=False) as step2_accordion:
            with gr.Row():
                generate_pdf_url_input = gr.Textbox(
                    label="PDF URL (Cloud Storage)",
                    placeholder="https://www.dropbox.com/s/... or https://drive.google.com/file/d/...",
                    lines=2,
                    info="Supports Dropbox, Google Drive, OneDrive, Box, or direct URLs. Auto-validates size (max 2MB).",
                    scale=3  # Takes 3/4 of the width
                )
                validate_pdf_btn = gr.Button("📄 Validate PDF", variant="primary", scale=1)  # Takes 1/4 of the width
        
        # Step 3: Exam Configuration Accordion
        with gr.Accordion("⚙️ Step 2: Exam Configuration", open=False, visible=False) as step3_accordion:
            # PDF validation status display at the top
            step3_pdf_status = gr.Markdown("", visible=False)
            
            # Date/Time picker using custom HTML components
            # Get today's date as default
            today_date = datetime.now().strftime("%Y-%m-%d")
            # Calculate default end date (+7 days)
            default_end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            
            # Row 1: Course ID, Exam ID, Section ID
            with gr.Row():
                generate_course_id_input = gr.Textbox(
                    label="Course ID",
                    placeholder="e.g., ECO2200, CS101",
                    lines=1,  # Explicitly set to single line to prevent scrollbar
                    scale=1,
                    info="Course code identifier",
                )
                generate_exam_id_input = gr.Textbox(
                    label="Exam ID",
                    placeholder="e.g., Midterm-A, Final-2024, Quiz-1, Chapter-1, etc",
                    lines=1,  # Explicitly set to single line to prevent scrollbar
                    scale=1,
                    info="Exam identifier",
                )
                generate_section_id_input = gr.Textbox(
                    label="Section ID",
                    placeholder="e.g., Fall2025-Section-A, Spring2024-Section-B, etc.",
                    value="",
                    lines=1,  # Explicitly set to single line to prevent scrollbar
                    info="Semester or session identifier",
                    scale=1
                )
            
            # Row 2: Exam Configuration - Compact Section
            with gr.Row():
                generate_n_questions_input = gr.Number(
                    label="Number of Questions",
                    value=1,
                    minimum=1,
                    maximum=10,
                    step=1,
                    precision=0,
                    scale=1,
                    info="Total questions (max based on PDF chunks)"
                )
                generate_min_followups_input = gr.Number(
                    label="Min Follow-ups",
                    value=0,
                    minimum=0,
                    maximum=2,
                    step=1,
                    precision=0,
                    scale=1,
                    info="Min follow-ups per question"
                )
                generate_max_followups_input = gr.Number(
                    label="Max Follow-ups",
                    value=1,
                    minimum=0,
                    maximum=5,
                    step=1,
                    precision=0,
                    scale=1,
                    info="Max follow-ups per question"
                )
                generate_time_per_question_input = gr.Dropdown(
                    label="Time per Question (seconds)",
                    choices=[45, 60, 75, 90],
                    value=60,
                    scale=1,
                    info="Recommended: 60 seconds"
                )
                max_duration_display = gr.Markdown(
                    value="⏱️ **Maximum Total Duration:** Calculating...",
                    visible=True
                )
            
            # Row 3: Start Date, Start Time, End Date, End Time
            with gr.Row():
                generate_start_date_picker = gr.Textbox(
                    label="Start Date",
                    placeholder="YYYY-MM-DD",
                    value=today_date,
                    info="Select start date (default: today)",
                    elem_classes="date-picker",
                    scale=1
                )
                generate_start_time_picker = gr.Textbox(
                    label="Start Time",
                    placeholder="HH:MM (default: 00:00)",
                    value="00:00",
                    info="Start time (24-hour format)",
                    elem_classes="time-picker",
                    scale=1
                )
                generate_end_date_picker = gr.Textbox(
                    label="End Date",
                    placeholder="YYYY-MM-DD (auto: +7 days)",
                    value=default_end_date,
                    info="Auto-updates to start date + 7 days",
                    elem_classes="date-picker",
                    scale=1
                )
                generate_end_time_picker = gr.Textbox(
                    label="End Time",
                    placeholder="HH:MM (default: 23:59)",
                    value="23:59",
                    info="End time (24-hour format)",
                    elem_classes="time-picker",
                    scale=1
                )
                
                # Custom JavaScript for date/time pickers with native HTML5 inputs
                date_picker_js = """
                <script>
                (function(){
                    const init = () => {
                        setTimeout(() => {
                            const dates = [...document.querySelectorAll('input[placeholder*="YYYY-MM-DD"]')];
                            const times = [...document.querySelectorAll('input[placeholder*="HH:MM"]')];
                            dates.forEach(d => d.type = 'date');
                            times.forEach(t => { t.type = 'time'; t.step = '60'; });
                            if(dates[0] && dates[1]) {
                                dates[0].addEventListener('change', e => {
                                    if(e.target.value) {
                                        const d = new Date(e.target.value);
                                        d.setDate(d.getDate() + 7);
                                        dates[1].value = d.toISOString().split('T')[0];
                                        dates[1].dispatchEvent(new Event('input', {bubbles: true}));
                                        dates[1].dispatchEvent(new Event('change', {bubbles: true}));
                                    }
                                });
                            }
                        }, 500);
                    };
                    if(document.readyState === 'loading') {
                        document.addEventListener('DOMContentLoaded', init);
                    } else {
                        init();
                    }
                    if(window.gradio) {
                        const orig = window.gradio.createInterface;
                        window.gradio.createInterface = function(...args) {
                            const result = orig.apply(this, args);
                            setTimeout(init, 1000);
                            return result;
                        };
                    }
                })();
                </script>
                """
                gr.HTML(date_picker_js)
            
            # Row 4: Base URL input (hidden in UI but kept functional)
            # Use empty string so handler always reads from EXAM_BASE_URL environment variable
            with gr.Row():
                generate_base_url_input = gr.Textbox(
                    label="Base URL",
                    value="",  # Empty - handler will read from EXAM_BASE_URL env var
                    placeholder="http://localhost:7860 or https://your-domain.com",
                    lines=1,
                    info="Base URL where the exam app will be hosted (reads from EXAM_BASE_URL env var)",
                    scale=1,
                    visible=False  # Hide in UI but keep functional
                )
        
        # Step 3: Generate URL Accordion
        with gr.Accordion("🔗 Step 3: Generate Exam URL", open=False, visible=False) as step3_generate_accordion:
            with gr.Row():
                generate_url_btn = gr.Button("🔗 Generate URL", variant="primary", scale=1)
                copy_url_btn = gr.Button("📋 Copy URL", variant="primary", scale=1, interactive=False)
            
            # Generated URL (read-only, can only be copied via Copy URL button)
            generated_url_output = gr.Textbox(
                label="Generated URL",
                placeholder="URL will appear here...",
                lines=2,
                interactive=False,  # Make it unclickable
                show_copy_button=False  # Remove built-in copy button
            )
            generate_url_status = gr.Markdown("")
        
        # =========================
        # Event Handlers and Wiring
        # =========================
        
        # Wire Step 1 → Step 2
        step1_checkbox.change(
            handle_step1_checkbox_wrapper,
            inputs=[step1_checkbox, chunk_state],
            outputs=[step1_accordion, step2_accordion, chunk_state]
        )
        
        # Wire Step 2 → Step 3 (using button click)
        validate_pdf_btn.click(
            handle_validate_pdf_wrapper,
            inputs=[generate_pdf_url_input, chunk_state],
            outputs=[step3_pdf_status, step1_accordion, step2_accordion, step3_accordion, chunk_state, generate_n_questions_input, max_duration_display]
        )
        
        # Wire Step 3 → Step 3 (Generate URL) (on field changes) - updated with time_per_question
        generate_n_questions_input.change(
            handle_calculate_duration_wrapper,
            inputs=[generate_n_questions_input, generate_min_followups_input, generate_max_followups_input, generate_time_per_question_input, chunk_state],
            outputs=[max_duration_display, step3_generate_accordion, chunk_state]
        )
        generate_min_followups_input.change(
            handle_calculate_duration_wrapper,
            inputs=[generate_n_questions_input, generate_min_followups_input, generate_max_followups_input, generate_time_per_question_input, chunk_state],
            outputs=[max_duration_display, step3_generate_accordion, chunk_state]
        )
        generate_max_followups_input.change(
            handle_calculate_duration_wrapper,
            inputs=[generate_n_questions_input, generate_min_followups_input, generate_max_followups_input, generate_time_per_question_input, chunk_state],
            outputs=[max_duration_display, step3_generate_accordion, chunk_state]
        )
        generate_time_per_question_input.change(
            handle_calculate_duration_wrapper,
            inputs=[generate_n_questions_input, generate_min_followups_input, generate_max_followups_input, generate_time_per_question_input, chunk_state],
            outputs=[max_duration_display, step3_generate_accordion, chunk_state]
        )
        
        # Auto-update end date when start date changes
        generate_start_date_picker.change(
            update_end_date,
            inputs=[generate_start_date_picker, generate_start_time_picker],
            outputs=[generate_end_date_picker, generate_end_time_picker]
        )
        
        # Generate URL button
        generate_url_btn.click(
            handle_generate_url_wrapper,
            inputs=[generate_pdf_url_input, generate_base_url_input, generate_course_id_input, 
                    generate_exam_id_input, generate_section_id_input, generate_n_questions_input, 
                    generate_min_followups_input, generate_max_followups_input, generate_time_per_question_input,
                    generate_start_date_picker, generate_start_time_picker, generate_end_date_picker, generate_end_time_picker,
                    chunk_state],
            outputs=[generated_url_output, generate_url_status, generate_url_btn, copy_url_btn, chunk_state]
        )
        
        # Copy URL button handler
        copy_url_btn.click(
            handle_copy_url_wrapper,
            inputs=[generated_url_output],
            outputs=[generated_url_output, generate_url_status],
            js="(url) => { if(url) { navigator.clipboard.writeText(url); } return url; }"
        )

# =========================
# Launch Configuration for Railway
# =========================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 7861))  # Default port 7861 for prof.py
    demo.queue(default_concurrency_limit=16, max_size=256)
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        show_error=True,
        pwa=True
    )

