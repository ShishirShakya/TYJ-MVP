"""
UI layout for exam interface.

This module contains the Gradio Blocks layout structure for the exam interface.
The layout uses components from exam.ui.components and structures them into
a cohesive interface.

Note: This module uses dependency injection for Gradio to ensure compatibility
across different environments.
"""

from typing import Dict, Any, Callable, Optional, TYPE_CHECKING

# Type hints only - no runtime import
if TYPE_CHECKING:
    import gradio as gr

from exam.ui.components import create_ui_components
from exam.ui.security_js import get_security_javascript
from exam.state import ensure_state


def create_ui_layout(
    gr_module,
    components: Dict[str, Any] = None,
    handlers: Optional[Dict[str, Callable]] = None
) -> tuple:
    """
    Create and return the Gradio Blocks layout for the exam interface.
    
    Args:
        gr_module: The Gradio module (passed as a dependency).
        components: Optional dictionary of components. If None, components will be created.
        
    Returns:
        Tuple of (demo, components_dict) where:
        - demo: Gradio Blocks instance with the exam interface layout
        - components_dict: Dictionary of all components and section containers for event wiring
    """
    # Dictionary to store all components and section containers for event wiring
    layout_components = {}
    
    # Create Blocks instance
    with gr_module.Blocks(title="VivaAI Secure - Exam") as demo:
        # Add custom JavaScript for security detection using HTML component
        security_js = gr_module.HTML(
            value=get_security_javascript(),
            visible=False
        )
        layout_components["security_js"] = security_js
        
        # Add CSS to hide pause, redo, rewind, and scissor controls on microphone component
        # Scoped to .exam-microphone class only for safety
        microphone_css = gr_module.HTML(
            value="""
            <style>
            /* Hide pause, redo, rewind, and scissor/trim controls on microphone component */
            /* Scoped to .exam-microphone class only - very safe, won't affect other components */
            .exam-microphone button[aria-label*="pause" i],
            .exam-microphone button[aria-label*="Pause"],
            .exam-microphone button[aria-label*="redo" i],
            .exam-microphone button[aria-label*="Redo"],
            .exam-microphone button[aria-label*="rewind" i],
            .exam-microphone button[aria-label*="Rewind"],
            .exam-microphone button[aria-label*="scissor" i],
            .exam-microphone button[aria-label*="Scissor"],
            .exam-microphone button[aria-label*="trim" i],
            .exam-microphone button[aria-label*="Trim"],
            .exam-microphone button[aria-label*="edit" i],
            .exam-microphone button[aria-label*="Edit"] {
                display: none !important;
                pointer-events: none !important; /* Extra safety - disable interaction */
            }
            </style>
            """,
            visible=False
        )
        layout_components["microphone_css"] = microphone_css
        
        with gr_module.Tab("Exam"):
            # Create components inside Tab context if not provided
            # This ensures components are properly nested in the Tab
            if components is None:
                components = create_ui_components(gr_module)
            
            # Step Indicator (always visible at top) - Compact progress bar
            step_indicator = gr_module.HTML(
                value="""
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                    <div style="flex: 1; background: #e0e0e0; height: 8px; border-radius: 4px; overflow: hidden;">
                        <div style="background: #4CAF50; height: 100%; width: 16.67%; border-radius: 4px; transition: width 0.3s;"></div>
                    </div>
                    <span style="font-size: 12px; color: #666; white-space: nowrap;">Step 1/6</span>
                </div>
                """,
                elem_classes=["step-indicator"]
            )
            layout_components["step_indicator"] = step_indicator
            
            # Professor's Link Section (visible by default)
            # Components must be created/referenced inside the Column for proper nesting
            with gr_module.Column(visible=True) as professor_link_section:
                with gr_module.Row():
                    with gr_module.Column(scale=5):
                        # Create component directly inside Column for proper nesting
                        professor_link_input = gr_module.Textbox(
                            label="Professor's Link",
                            placeholder="Paste exam configuration URL here...",
                            lines=2,
                            value=""
                        )
                    with gr_module.Column(scale=1):
                        parse_link_btn = gr_module.Button(
                            "🔗 Parse & Setup",
                            variant="primary",
                            size="lg"
                        )
            layout_components["professor_link_section"] = professor_link_section
            layout_components["professor_link_input"] = professor_link_input
            layout_components["parse_link_btn"] = parse_link_btn
            
            # Verification Section (hidden by default, shown after parsing)
            with gr_module.Column(visible=False) as verification_section:
                with gr_module.Row():
                    with gr_module.Column(scale=5):
                        verification_status = gr_module.Markdown(
                            value="",
                            elem_classes=["verification-status"]
                        )
            layout_components["verification_section"] = verification_section
            layout_components["verification_status"] = verification_status
            
            # Informed Consent Section (hidden by default, shown after verification)
            with gr_module.Column(visible=False) as consent_section:
                with gr_module.Row():
                    with gr_module.Column(scale=5):
                        consent_disclaimer = gr_module.Markdown(
                            value=(
                                "### **⚠️ Informed Consent:** By proceeding, you acknowledge that "
                                "this examination is conducted using AI and may include audio recording "
                                "and proctoring for academic integrity purposes. You agree to complete "
                                "this examination independently without unauthorized assistance."
                            ),
                            elem_classes=["consent-disclaimer"]
                        )
                    with gr_module.Column(scale=1):
                        consent_checkbox = gr_module.Checkbox(
                            label="I acknowledge and consent.",
                            value=False,
                            interactive=True
                        )
            layout_components["consent_section"] = consent_section
            layout_components["consent_disclaimer"] = consent_disclaimer
            layout_components["consent_checkbox"] = consent_checkbox
            
            # Student ID Section (hidden by default, shown after consent)
            with gr_module.Column(visible=False) as student_id_section:
                # FERPA COMPLIANCE: Privacy disclosure for student ID collection
                student_id_disclosure = gr_module.Markdown(
                    value="""
**📋 Privacy Notice**: 
- Your Student ID will be used for grading purposes and shared with your instructor
- This is permitted under FERPA (Family Educational Rights and Privacy Act) for legitimate educational purposes
- Your data is encrypted and stored securely
- You can request data deletion per your FERPA rights
                    """,
                    visible=True
                )
                layout_components["student_id_disclosure"] = student_id_disclosure
                
                with gr_module.Row():
                    with gr_module.Column(scale=5):
                        student_id_input = gr_module.Textbox(
                            label="Student ID",
                            placeholder="Enter your Student ID (numeric/integer only)...",
                            interactive=True
                        )
                        student_id_status = gr_module.Markdown(
                            value="",
                            visible=False,
                            elem_classes=["student-id-status"]
                        )
                    with gr_module.Column(scale=1):
                        student_id_verify_checkbox = gr_module.Checkbox(
                            label="I verify my Student ID is correct, once I check this, student ID section will be hidden.",
                            value=False,
                            interactive=True
                        )
            layout_components["student_id_section"] = student_id_section
            layout_components["student_id_input"] = student_id_input
            layout_components["student_id_status"] = student_id_status
            layout_components["student_id_verify_checkbox"] = student_id_verify_checkbox
            
            # Webcam Consent Section (hidden by default, shown after Student ID)
            with gr_module.Column(visible=False) as webcam_consent_section:
                with gr_module.Row():
                    with gr_module.Column(scale=5):
                        webcam_consent_disclaimer = gr_module.Markdown(
                            value=(
                                "### **⚠️ Webcam & Recording Consent:**\n\n"
                                "**Important:** Once you click the **Webcam** and **Record** button, the examination will start.\n\n"
                                "**Critical Rules:**\n"
                                "- Once the webcam is started, **DO NOT stop or disable the webcam** during the examination.\n"
                                "- Stopping or disabling the webcam **will be flagged** and the examination **will be terminated**.\n"
                                "- The webcam must remain active throughout the entire examination.\n"
                                "- You must keep your face visible to the webcam at all times.\n\n"
                                "**By proceeding, you acknowledge that you understand these rules and agree to keep the webcam active throughout the examination.**"
                            ),
                            elem_classes=["webcam-consent-disclaimer"]
                        )
                    with gr_module.Column(scale=1):
                        webcam_consent_checkbox = gr_module.Checkbox(
                            label="I understand and agree to keep the webcam active throughout the examination.",
                            value=False,
                            interactive=True
                        )
            layout_components["webcam_consent_section"] = webcam_consent_section
            layout_components["webcam_consent_disclaimer"] = webcam_consent_disclaimer
            layout_components["webcam_consent_checkbox"] = webcam_consent_checkbox
            
            # Split Layout (shown after Webcam Consent)
            # Components must be created directly inside Column for proper nesting
            with gr_module.Column(visible=False) as exam_layout:
                with gr_module.Row():
                    # Left side: Chatbot (60%)
                    with gr_module.Column(scale=3):
                        chatbot = gr_module.Chatbot(
                            label="Viva Dialogue",
                            height=500,
                            type="messages",
                            show_copy_button=True,
                            avatar_images=(None, "👨‍🏫"),
                            value=[{"role": "assistant", "content": "Ready to begin... Webcam activation will start the exam."}]
                        )
                    # Right side: Exam Setup (40%)
                    with gr_module.Column(scale=2):
                        proctor_cam = gr_module.Image(
                            sources=["webcam"],
                            label="Webcam Proctoring (local only, not recorded)",
                            visible=True,
                            interactive=True
                        )
                        # Video statistics directly below camera
                        proctor_status = gr_module.Markdown(
                            value="💤 Inactive",
                            visible=True
                        )
                        # Connection status indicator (real-time)
                        connection_status = gr_module.Markdown(
                            value="🌐 Online",
                            visible=True,
                            elem_classes=["connection-status"]
                        )
                        # Progress tracking display (real-time)
                        progress_info = gr_module.Markdown(
                            value="",
                            visible=False,
                            elem_classes=["progress-info"]
                        )
                        # Status component below proctor status
                        unified_status = gr_module.HTML(
                            value="",
                            visible=False,
                            elem_classes=["unified-status"]
                        )
                        # Timeout countdown display (real-time)
                        timeout_countdown = gr_module.Markdown(
                            value="",
                            visible=False,
                            elem_classes=["timeout-countdown"]
                        )
                        # Finish button below status (only shown after exam completion)
                        finish_btn = gr_module.Button(
                            "✅ Finish & Download",
                            variant="primary",
                            visible=False,
                            interactive=False
                        )
                        # File integrity acknowledgment checkbox (shown after file download)
                        file_integrity_checkbox = gr_module.Checkbox(
                            label="I acknowledge that I will not change the file name or attempt to tamper with the encrypted file.",
                            value=False,
                            interactive=True,
                            visible=False,
                            elem_classes=["file-integrity-checkbox"]
                        )
                        # File output - Hidden initially, shown after exam completion
                        file_out = gr_module.File(
                            label="Encrypted Transcript (.enc)",
                            interactive=False,
                            visible=False,
                            height=60
                        )
                
                # Audio components row (60/40 split matching main layout)
                with gr_module.Row():
                    # Left side: Examiner audio (60%)
                    with gr_module.Column(scale=3):
                        # Note: In Gradio 5.x, waveforms are shown by default
                        examiner_audio = gr_module.Audio(
                            label="Examiner (spoken)",
                            type="filepath",
                            autoplay=True,
                            visible=True
                        )
                    # Right side: Record button (40%)
                    with gr_module.Column(scale=2):
                        mic = gr_module.Microphone(
                            label="🎤 Record",
                            type="filepath",
                            format="wav",
                            interactive=False,
                            show_label=True,
                            visible=True,
                            elem_classes=["exam-microphone"]  # CSS class for hiding controls
                        )
            
            layout_components["exam_layout"] = exam_layout
            layout_components["chatbot"] = chatbot
            layout_components["proctor_cam"] = proctor_cam
            layout_components["proctor_status"] = proctor_status
            layout_components["connection_status"] = connection_status
            layout_components["progress_info"] = progress_info
            layout_components["unified_status"] = unified_status
            layout_components["timeout_countdown"] = timeout_countdown
            layout_components["finish_btn"] = finish_btn
            layout_components["file_integrity_checkbox"] = file_integrity_checkbox
            layout_components["file_out"] = file_out
            layout_components["examiner_audio"] = examiner_audio
            layout_components["mic"] = mic
            
            # State component (created at Tab level)
            s = gr_module.State(ensure_state({}))
            layout_components["s"] = s
            
            # Hidden audio output component (for internal state management)
            # Created at Tab level since it's hidden and doesn't need container nesting
            audio_out = gr_module.Audio(visible=False)
            layout_components["audio_out"] = audio_out
            
            # Wire events inside Blocks context if handlers provided
            if handlers:
                _wire_ui_events(layout_components, handlers, gr_module)
    
    return demo, layout_components


def _wire_ui_events(components: Dict[str, Any], handlers: Dict[str, Callable], gr_module):
    """
    Wire all UI events inside Blocks context.
    
    Args:
        components: Dictionary of all UI components
        handlers: Dictionary of event handler functions
        gr_module: Gradio module
    """
    # Shared concurrency bucket
    cpu_q = "cpu"
    
    # Extract components
    professor_link_input = components["professor_link_input"]
    parse_link_btn = components["parse_link_btn"]
    professor_link_section = components["professor_link_section"]
    verification_section = components["verification_section"]
    verification_status = components["verification_status"]
    consent_section = components["consent_section"]
    consent_checkbox = components["consent_checkbox"]
    student_id_section = components["student_id_section"]
    student_id_input = components["student_id_input"]
    student_id_status = components["student_id_status"]
    student_id_verify_checkbox = components["student_id_verify_checkbox"]
    webcam_consent_section = components["webcam_consent_section"]
    webcam_consent_checkbox = components["webcam_consent_checkbox"]
    exam_layout = components["exam_layout"]
    chatbot = components["chatbot"]
    proctor_cam = components["proctor_cam"]
    proctor_status = components["proctor_status"]
    connection_status = components["connection_status"]
    progress_info = components["progress_info"]
    unified_status = components["unified_status"]
    timeout_countdown = components["timeout_countdown"]
    finish_btn = components["finish_btn"]
    file_integrity_checkbox = components["file_integrity_checkbox"]
    file_out = components["file_out"]
    examiner_audio = components["examiner_audio"]
    mic = components["mic"]
    s = components["s"]
    audio_out = components["audio_out"]
    step_indicator = components.get("step_indicator")
    
    # Wire events using handler functions
    parse_link_btn.click(
        handlers["handle_parse_and_show_chatbot"],
        inputs=[professor_link_input, s],
        outputs=[s, chatbot, professor_link_input, parse_link_btn, professor_link_section,
                verification_section, verification_status, consent_section, student_id_section,
                webcam_consent_section, exam_layout, step_indicator],
        concurrency_limit=2,
        concurrency_id=cpu_q
    )
    
    consent_checkbox.change(
        handlers["handle_consent_checkbox"],
        inputs=[consent_checkbox, s],
        outputs=[consent_section, student_id_section, step_indicator, verification_section]
    )
    
    student_id_verify_checkbox.change(
        handlers["handle_student_id_verify"],
        inputs=[student_id_verify_checkbox, student_id_input, s],
        outputs=[s, student_id_input, student_id_verify_checkbox,
                student_id_section, webcam_consent_section, exam_layout, student_id_status, step_indicator]
    )
    
    # Wire webcam consent checkbox
    webcam_consent_checkbox.change(
        handlers["handle_webcam_consent_checkbox"],
        inputs=[webcam_consent_checkbox, s],
        outputs=[s, webcam_consent_section, exam_layout, step_indicator]
    )
    
    # Wire webcam stream
    proctor_cam.stream(
        handlers["_stream_proctor"],
        inputs=[proctor_cam, s],
        outputs=[s, proctor_cam, proctor_status, connection_status, chatbot, mic, examiner_audio, progress_info, timeout_countdown, unified_status]
    )
    
    # Wire microphone recording
    mic.stop_recording(
        handlers["handle_mic_wrapper"],
        inputs=[mic, s, unified_status],
        outputs=[
            s,
            audio_out,
            unified_status,
            mic,
            chatbot,
            proctor_cam,
            proctor_status,
            finish_btn,
            examiner_audio,
            timeout_countdown
        ],
        concurrency_limit=2,
        concurrency_id=cpu_q
    )
    
    # Finish & Download handler
    finish_btn.click(
        handlers["finalize_and_export_encrypted"],
        inputs=[s],
        outputs=[file_out, unified_status],
        concurrency_limit=4,
        concurrency_id=cpu_q
    ).then(
        handlers["_after_finish_ui"],
        inputs=[s, file_out, unified_status],
        outputs=[proctor_cam, proctor_status, file_out, unified_status, file_integrity_checkbox],
        concurrency_limit=2,
        concurrency_id=cpu_q
    )
    
    # Wire checkbox change event
    file_integrity_checkbox.change(
        handlers["handle_file_integrity_checkbox"],
        inputs=[file_integrity_checkbox, s],
        outputs=[s, file_out],
        concurrency_limit=1,
        concurrency_id=cpu_q
    )


def get_layout_components(gr_module) -> Dict[str, Any]:
    """
    Get all components used in the layout for event wiring.
    
    This function returns a dictionary of all components that need to be
    wired to event handlers. This is useful for event wiring in the notebook.
    
    Args:
        gr_module: The Gradio module (passed as a dependency).
        
    Returns:
        Dictionary of component names to component instances.
    """
    components = create_ui_components(gr_module)
    
    # Add layout-specific components that are created in the layout
    # These are the section containers that control visibility
    layout_components = {
        "professor_link_section": None,  # Created in layout
        "verification_section": None,  # Created in layout
        "consent_section": None,  # Created in layout
        "student_id_section": None,  # Created in layout
        "webcam_consent_section": None,  # Created in layout
        "exam_layout": None,  # Created in layout
    }
    
    # Merge with component dictionary
    components.update(layout_components)
    
    return components


__all__ = [
    "create_ui_layout",
    "get_layout_components",
]

