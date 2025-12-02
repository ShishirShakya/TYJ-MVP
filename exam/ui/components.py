"""
UI components for exam interface.

This module contains functions to create Gradio UI components:
- Professor link input and parse button
- Verification status display
- Consent checkboxes and disclaimers
- Student ID input and verification
- Webcam consent checkbox
- Chatbot for exam dialogue
- Proctor camera and status displays
- Connection and progress status
- Audio components (examiner and microphone)
- File output and integrity checkbox

Note: This module uses dependency injection for Gradio to ensure compatibility
across different environments (Railway, Hugging Face, local). Gradio is passed
as a parameter rather than imported directly.
"""

from typing import Dict, Any, TYPE_CHECKING
import os

# Type hints only - no runtime import
if TYPE_CHECKING:
    import gradio as gr


def create_ui_components(gr_module) -> Dict[str, Any]:
    """
    Create all Gradio UI components for the exam interface.
    
    Args:
        gr_module: Gradio module (passed as dependency for version compatibility)
        
    Returns:
        Dictionary containing all UI components with their names as keys
    """
    components = {}
    
    # Professor's Link Section
    components["professor_link_input"] = gr_module.Textbox(
        label="Professor's Link",
        placeholder="Paste exam configuration URL here...",
        lines=2,
        value=""
    )
    
    components["parse_link_btn"] = gr_module.Button(
        "🔗 Parse & Setup",
        variant="primary",
        size="lg"
    )
    
    # Verification Section
    components["verification_status"] = gr_module.Markdown(
        value="",
        elem_classes=["verification-status"]
    )
    
    # Informed Consent Section
    components["consent_disclaimer"] = gr_module.Markdown(
        value=(
            "### **⚠️ Informed Consent:** By proceeding, you acknowledge that "
            "this examination is conducted using AI and may include audio recording "
            "and proctoring for academic integrity purposes. You agree to complete "
            "this examination independently without unauthorized assistance."
        ),
        elem_classes=["consent-disclaimer"]
    )
    
    components["consent_checkbox"] = gr_module.Checkbox(
        label="I acknowledge and consent.",
        value=False,
        interactive=True
    )
    
    # Student ID Section
    components["student_id_input"] = gr_module.Textbox(
        label="Student ID",
        placeholder="Enter your Student ID (numeric/integer only)...",
        interactive=True
    )
    
    components["student_id_status"] = gr_module.Markdown(
        value="",
        visible=False,
        elem_classes=["student-id-status"]
    )
    
    components["student_id_verify_checkbox"] = gr_module.Checkbox(
        label="I verify my Student ID is correct, once I check this, student ID section will be hidden.",
        value=False,
        interactive=True
    )
    
    # Webcam Consent Section
    # Get violation thresholds for display (use same defaults as config.py)
    tab_blur_threshold = int(os.getenv("EXAM_TAB_BLUR_THRESHOLD", "3"))
    clipboard_paste_threshold = int(os.getenv("EXAM_CLIPBOARD_PASTE_THRESHOLD", "2"))
    clipboard_copy_threshold = int(os.getenv("EXAM_CLIPBOARD_COPY_THRESHOLD", "5"))
    answer_reuse_threshold = int(os.getenv("EXAM_ANSWER_REUSE_THRESHOLD", "2"))
    
    components["webcam_consent_disclaimer"] = gr_module.Markdown(
        value=(
            "### **⚠️ Webcam & Recording Consent:**\n\n"
            "**Important:** Once you click the **Webcam** and **Record** button, the examination will start.\n\n"
            "**Critical Rules:**\n"
            "- Once the webcam is started, **DO NOT stop or disable the webcam** during the examination.\n"
            "- Stopping or disabling the webcam **will be flagged** and the examination **will be terminated**.\n"
            "- The webcam must remain active throughout the entire examination.\n"
            "- You must keep your face visible to the webcam at all times.\n\n"
            "**Exam Rules & Violation Thresholds:**\n"
            "- **Tab switches:** {tab_blur} violations = exam termination\n"
            "- **Copy operations:** {clipboard_copy} violations = exam termination\n"
            "- **Paste operations:** {clipboard_paste} violations = exam termination\n"
            "- **Answer reuse:** {answer_reuse} violations = exam termination\n"
            "- **Critical violations** (immediate termination): Multiple faces detected, voiceprint mismatch, profanity\n"
            "- **Time limits:** You will have a limited time per question (timer will be shown)\n\n"
            "**By proceeding, you acknowledge that you understand these rules and agree to keep the webcam active throughout the examination.**"
        ).format(
            tab_blur=tab_blur_threshold,
            clipboard_copy=clipboard_copy_threshold,
            clipboard_paste=clipboard_paste_threshold,
            answer_reuse=answer_reuse_threshold
        ),
        elem_classes=["webcam-consent-disclaimer"]
    )
    
    components["webcam_consent_checkbox"] = gr_module.Checkbox(
        label="I understand and agree to keep the webcam active throughout the examination.",
        value=False,
        interactive=True
    )
    
    # Chatbot for exam dialogue
    components["chatbot"] = gr_module.Chatbot(
        label="Viva Dialogue",
        height=500,
        type="messages",
        show_copy_button=True,
        avatar_images=(None, "👨‍🏫"),
        value=[{"role": "assistant", "content": "Ready to begin... Webcam activation will start the exam."}]
    )
    
    # Proctor camera
    components["proctor_cam"] = gr_module.Image(
        sources=["webcam"],
        label="Webcam Proctoring (local only, not recorded)",
        visible=True,
        interactive=True
    )
    
    # Proctor status display
    components["proctor_status"] = gr_module.Markdown(
        value="💤 Inactive",
        visible=True
    )
    
    # Connection status indicator
    components["connection_status"] = gr_module.Markdown(
        value="🌐 Online",
        visible=True,
        elem_classes=["connection-status"]
    )
    
    # Progress tracking display
    components["progress_info"] = gr_module.Markdown(
        value="",
        visible=False,
        elem_classes=["progress-info"]
    )
    
    # Unified status component
    components["unified_status"] = gr_module.HTML(
        value="",
        visible=False,
        elem_classes=["unified-status"]
    )
    
    # Timeout countdown display
    components["timeout_countdown"] = gr_module.Markdown(
        value="",
        visible=False,
        elem_classes=["timeout-countdown"]
    )
    
    # Finish button
    components["finish_btn"] = gr_module.Button(
        "✅ Finish & Download",
        variant="primary",
        visible=False,
        interactive=False
    )
    
    # File integrity checkbox
    components["file_integrity_checkbox"] = gr_module.Checkbox(
        label="I acknowledge that I will not change the file name or attempt to tamper with the encrypted file.",
        value=False,
        interactive=True,
        visible=False,
        elem_classes=["file-integrity-checkbox"]
    )
    
    # File output
    components["file_out"] = gr_module.File(
        label="Transcript",
        interactive=False,
        visible=False,
        height=60
    )
    
    # Examiner audio component
    # Note: In Gradio 5.x, waveforms are shown by default, no need for show_waveform parameter
    components["examiner_audio"] = gr_module.Audio(
        label="Examiner (spoken)",
        type="filepath",
        autoplay=True,
        visible=True
    )
    
    # Microphone component
    components["mic"] = gr_module.Microphone(
        label="🎤 Record",
        type="filepath",
        format="wav",
        interactive=False,
        show_label=True,
        visible=True,
        elem_classes=["exam-microphone"]  # CSS class for hiding controls
    )
    
    # State component
    from exam.state import ensure_state
    components["s"] = gr_module.State(ensure_state({}))
    
    # Hidden audio output (prevents users from seeing/editing recorded audio)
    components["audio_out"] = gr_module.Audio(visible=False)
    
    return components


__all__ = ["create_ui_components"]

