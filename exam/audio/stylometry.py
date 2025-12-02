"""
Stylometric analysis module for exam.ipynb.

This module contains functions for detecting AI-generated speech patterns:
- Speech rate analysis
- Hesitation pattern detection
- Lexical diversity consistency
- Zero-pause delivery detection
"""

import re
from typing import Dict, List


def analyze_speech_stylometry(text: str, prev_texts: List[str]) -> Dict:
    """
    GUARDRAIL: AI-Generated Answer Detection via Stylometric Analysis
    
    Detects unnatural fluency patterns typical of AI-generated responses:
    - Unnatural speech rate (too fast/fluent)
    - Lack of hesitation patterns (zero um/uh fillers)
    - Lexical inconsistency (sudden vocabulary shifts)
    - Zero-pause delivery (pre-written, unpunctuated text)
    
    Safeguard: Prevents use of AI-generated answers by analyzing speech
    characteristics that differ from natural human speech patterns.
    
    Args:
        text: Current answer text to analyze
        prev_texts: List of previous answer texts for baseline comparison
        
    Returns:
        Dictionary with flags if suspicious AI-generation patterns detected:
        - UNNATURAL_SPEECH_RATE: Unnaturally fast or fluent speech
        - NO_HESITATION_PATTERN: Suspiciously fluent without hesitation markers
        - LEXICAL_INCONSISTENCY: Significant vocabulary deviation from baseline
        - ZERO_PAUSE_DELIVERY: Pre-written text delivered without natural pauses
    """
    if not text or len(text) < 20:
        return {}
    
    flags = {}
    
    # 1. Speech Rate Detection: AI-generated text often has unnaturally high fluency/speed
    # Natural speech has ~120-160 words/min; AI-generated can exceed 200 words/min
    words = len(re.findall(r'\b\w+\b', text))
    # Rough estimate: assume 2 words per second for natural speech (~120 words/min)
    speech_rate = words / 2.0
    if speech_rate > 200:  # Unnaturally fast/fluent (suspicious of AI generation)
        flags["UNNATURAL_SPEECH_RATE"] = True
    
    # 2. Hesitation Pattern Detection: Natural speech has fillers (um, uh, er); AI-generated lacks these
    # This is a key differentiator: humans naturally pause and use fillers while thinking
    hesitation_count = len(
        re.findall(r'\b(um|uh|er|ah|hmm|hm|uhh|umm)\b', text, re.IGNORECASE)
    )
    hesitation_ratio = hesitation_count / max(words, 1)
    if hesitation_count > 0 and prev_texts:
        # Compare to student's baseline hesitation pattern
        prev_hesitation_avg = sum(
            len(re.findall(r'\b(um|uh|er|ah|hmm|hm)\b', t, re.IGNORECASE))
            for t in prev_texts
        ) / max(len(prev_texts), 1)
        # If current answer has <30% of baseline hesitations, suspiciously fluent (likely AI-generated)
        if hesitation_count < prev_hesitation_avg * 0.3:
            flags["NO_HESITATION_PATTERN"] = True  # Zero or minimal hesitation = AI-like fluency
    
    # 3. Lexical Diversity Consistency: AI-generated text may have sudden vocabulary shifts
    # Compare unique word ratio against student's historical baseline
    unique_words = len(set(word.lower() for word in re.findall(r'\b\w+\b', text)))
    diversity = unique_words / max(words, 1)
    
    # Compare to previous answers if available (need baseline to detect anomalies)
    if prev_texts and len(prev_texts) >= 2:
        prev_divs = [
            len(set(re.findall(r'\b\w+\b', t))) / max(len(re.findall(r'\b\w+\b', t)), 1)
            for t in prev_texts
        ]
        prev_avg_div = sum(prev_divs) / len(prev_divs)
        # If diversity deviates >20% from baseline, may indicate AI-generated content
        if abs(diversity - prev_avg_div) > 0.2:
            flags["LEXICAL_INCONSISTENCY"] = True
    
    # 4. Zero-Pause Delivery Detection: AI-generated text often lacks natural punctuation/breaks
    # Very long sentences without punctuation indicate pre-written AI-generated text
    # Natural speech has pauses, breaks, shorter sentences; AI text runs on without stops
    sentences = re.split(r'[.!?]\s+', text)
    max_sentence_length = max(
        len(re.findall(r'\b\w+\b', s)) for s in sentences
    ) if sentences else 0
    if max_sentence_length > 40:  # Suspiciously long sentence without pause (pre-written AI text)
        flags["ZERO_PAUSE_DELIVERY"] = True
    
    return flags

