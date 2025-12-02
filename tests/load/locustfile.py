"""
Load testing with Locust for VivaAI Assessment API.

Phase 4.1: Load testing infrastructure for performance validation.

Usage:
    locust -f tests/load/locustfile.py --host=http://localhost:8000
    locust -f tests/load/locustfile.py --host=http://localhost:8000 --users=100 --spawn-rate=10
"""

from locust import HttpUser, task, between, events
import json
import random
import string
import base64
from io import BytesIO
from PIL import Image


class APIUser(HttpUser):
    """
    Simulated user for load testing API endpoints.
    
    Simulates realistic exam flow:
    1. Health check
    2. Generate question
    3. Grade answer
    4. Process audio
    5. Generate TTS
    6. Generate follow-up question
    """
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    
    def on_start(self):
        """Called when a simulated user starts."""
        # Get API key from environment or use default
        import os
        self.api_key = os.getenv("LOAD_TEST_API_KEY", "test-api-key")
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        self.session_id = self._generate_session_id()
    
    def _generate_session_id(self) -> str:
        """Generate a random session ID."""
        return f"load_test_{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}"
    
    @task(3)
    def health_check(self):
        """Health check endpoint (most frequent)."""
        self.client.get("/health", name="Health Check")
    
    @task(2)
    def get_metrics(self):
        """Metrics endpoint."""
        self.client.get("/metrics", name="Metrics")
    
    @task(1)
    def generate_question_direct(self):
        """Generate question directly."""
        payload = {
            "context_text": "This is a test context for load testing. " * 10,
            "previous_questions": [],
            "session_id": self.session_id
        }
        self.client.post(
            "/api/v1/assessments/generate-question-direct",
            json=payload,
            headers=self.headers,
            name="Generate Question Direct"
        )
    
    @task(1)
    def grade_answer_direct(self):
        """Grade answer directly."""
        payload = {
            "messages": [
                {"role": "system", "content": "You are a grader."},
                {"role": "user", "content": "This is a test answer for load testing."}
            ],
            "chat_model": "gpt-4o-mini",
            "session_id": self.session_id
        }
        self.client.post(
            "/api/v1/assessments/grade-answer-direct",
            json=payload,
            headers=self.headers,
            name="Grade Answer Direct"
        )
    
    @task(1)
    def generate_tts(self):
        """Generate TTS audio."""
        payload = {
            "text": "This is a test question for load testing.",
            "session_id": self.session_id,
            "model": "tts-1",
            "voice": "alloy"
        }
        self.client.post(
            "/api/v1/assessments/generate-tts",
            json=payload,
            headers=self.headers,
            name="Generate TTS"
        )
    
    @task(1)
    def generate_followup_question(self):
        """Generate follow-up question."""
        payload = {
            "main_question": "What is the main idea?",
            "student_answer": "The main idea is about testing.",
            "context_text": "This is test context.",
            "previous_followups": [],
            "session_id": self.session_id
        }
        self.client.post(
            "/api/v1/assessments/generate-followup-question-direct",
            json=payload,
            headers=self.headers,
            name="Generate Follow-up Question"
        )
    
    @task(1)
    def process_audio(self):
        """Process audio file."""
        # Create a dummy audio file (WAV format)
        try:
            # Generate a small dummy WAV file
            audio_data = self._generate_dummy_audio()
            
            files = {
                "audio_file": ("test_audio.wav", audio_data, "audio/wav")
            }
            data = {
                "session_id": self.session_id
            }
            
            # Remove Content-Type header for multipart
            headers = {k: v for k, v in self.headers.items() if k.lower() != 'content-type'}
            
            self.client.post(
                "/api/v1/assessments/process-audio",
                files=files,
                data=data,
                headers=headers,
                name="Process Audio"
            )
        except Exception as e:
            # Skip if audio generation fails
            pass
    
    def _generate_dummy_audio(self) -> bytes:
        """Generate a dummy WAV file for testing."""
        # Create a minimal WAV file (1 second of silence)
        # WAV header + 1 second of silence at 16kHz, 16-bit mono
        sample_rate = 16000
        duration = 1
        num_samples = sample_rate * duration
        
        # WAV header
        wav_header = b'RIFF'
        wav_header += (36 + num_samples * 2).to_bytes(4, 'little')  # File size
        wav_header += b'WAVE'
        wav_header += b'fmt '
        wav_header += (16).to_bytes(4, 'little')  # fmt chunk size
        wav_header += (1).to_bytes(2, 'little')  # Audio format (PCM)
        wav_header += (1).to_bytes(2, 'little')  # Number of channels (mono)
        wav_header += sample_rate.to_bytes(4, 'little')  # Sample rate
        wav_header += (sample_rate * 2).to_bytes(4, 'little')  # Byte rate
        wav_header += (2).to_bytes(2, 'little')  # Block align
        wav_header += (16).to_bytes(2, 'little')  # Bits per sample
        wav_header += b'data'
        wav_header += (num_samples * 2).to_bytes(4, 'little')  # Data chunk size
        
        # Generate silence (zeros)
        audio_data = b'\x00' * (num_samples * 2)
        
        return wav_header + audio_data


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    print("=" * 80)
    print("Load Test Starting")
    print(f"Target Host: {environment.host}")
    print("=" * 80)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    print("=" * 80)
    print("Load Test Complete")
    print("=" * 80)
    
    # Print summary statistics
    stats = environment.stats
    print("\nRequest Statistics:")
    print("-" * 80)
    print(f"{'Name':<40} {'Requests':<12} {'Failures':<12} {'Avg (ms)':<12} {'Max (ms)':<12}")
    print("-" * 80)
    
    for name, stat in stats.entries.items():
        if stat.num_requests > 0:
            print(f"{name:<40} {stat.num_requests:<12} {stat.num_failures:<12} "
                  f"{stat.avg_response_time:<12.2f} {stat.max_response_time:<12.2f}")
    
    print("-" * 80)
    print(f"Total Requests: {stats.total.num_requests}")
    print(f"Total Failures: {stats.total.num_failures}")
    print(f"Failure Rate: {stats.total.fail_ratio * 100:.2f}%")
    print(f"Average Response Time: {stats.total.avg_response_time:.2f}ms")
    print(f"95th Percentile: {stats.total.get_response_time_percentile(0.95):.2f}ms")
    print(f"99th Percentile: {stats.total.get_response_time_percentile(0.99):.2f}ms")

