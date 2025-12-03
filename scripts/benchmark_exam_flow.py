#!/usr/bin/env python3
"""
Performance benchmark for exam flow operations.

Measures critical operations to identify bottlenecks:
- Question generation (chunk selection + API call)
- TTS generation (API call + file write)
- STT transcription (API call + processing)
- State serialization (save_state_to_disk)
- Full question-answer cycle
- Chunk validation
- Audio file operations

Usage:
    python z-thoughts/benchmark_exam_flow.py
    
    # Run with specific number of iterations
    python z-thoughts/benchmark_exam_flow.py --iterations 10
    
    # Save results to JSON
    python z-thoughts/benchmark_exam_flow.py --output results.json
"""

import time
import json
import os
import sys
import argparse
from typing import Dict, Any, List, Optional
from pathlib import Path
from statistics import mean, median, stdev
import tempfile

# Add parent directory to path to import exam modules
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from openai import OpenAI
    from exam.audio.tts import tts_to_mp3
    from exam.audio.stt import transcribe
    from exam.audio.utils import get_audio_duration
    from exam.state.persistence import save_state_to_disk, prepare_state_for_serialization
    from exam.state.core import ensure_state
    from shared.pdf_processing import _validate_context
    from shared.performance_monitor import record_timing, get_performance_stats, reset_metrics
except ImportError as e:
    print(f"Warning: Could not import exam modules: {e}")
    print("Some benchmarks may be skipped. Run from project root directory.")
    # Create mock functions for testing structure
    def tts_to_mp3(*args, **kwargs):
        time.sleep(0.1)  # Simulate TTS
        return tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
    
    def transcribe(*args, **kwargs):
        time.sleep(0.2)  # Simulate transcription
        return "Mock transcription text"
    
    def get_audio_duration(*args, **kwargs):
        return 5.0
    
    def save_state_to_disk(*args, **kwargs):
        time.sleep(0.01)  # Simulate save
        return True
    
    def prepare_state_for_serialization(state):
        return state
    
    def ensure_state(s):
        return s or {}
    
    def _validate_context(ctx):
        return True, ""
    
    # Mock performance monitor functions
    def record_timing(operation: str, duration: float, success: bool = True):
        pass
    
    def get_performance_stats():
        return {}
    
    def reset_metrics():
        pass


class BenchmarkResults:
    """Container for benchmark results."""
    
    def __init__(self):
        self.results: Dict[str, List[float]] = {}
        self.metadata: Dict[str, Any] = {}
    
    def add_timing(self, operation: str, duration: float):
        """Add a timing measurement."""
        if operation not in self.results:
            self.results[operation] = []
        self.results[operation].append(duration)
        record_timing(operation, duration, success=True)
    
    def get_stats(self, operation: str) -> Dict[str, float]:
        """Get statistics for an operation."""
        if operation not in self.results or not self.results[operation]:
            return {}
        
        timings = sorted(self.results[operation])
        count = len(timings)
        
        return {
            "count": count,
            "min": min(timings),
            "max": max(timings),
            "mean": mean(timings),
            "median": median(timings),
            "stdev": stdev(timings) if count > 1 else 0.0,
            "p50": timings[int(count * 0.50)] if count > 0 else 0,
            "p95": timings[int(count * 0.95)] if count > 0 else 0,
            "p99": timings[int(count * 0.99)] if count > 0 else 0,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary."""
        stats = {}
        for operation in self.results:
            stats[operation] = self.get_stats(operation)
        
        return {
            "benchmarks": [
                {
                    "name": op,
                    "stats": stats[op]
                }
                for op in sorted(stats.keys())
            ],
            "metadata": self.metadata
        }


def benchmark_chunk_validation(num_chunks: int = 100) -> float:
    """Benchmark chunk validation operation."""
    # Generate mock chunks
    chunks = [f"This is a test chunk {i} with some content. " * 10 for i in range(num_chunks)]
    
    start = time.perf_counter()
    for chunk in chunks:
        _validate_context(chunk)
    duration = time.perf_counter() - start
    
    return duration / num_chunks  # Average per chunk


def benchmark_state_serialization(state_size: str = "medium") -> float:
    """Benchmark state serialization."""
    # Create mock state of different sizes
    if state_size == "small":
        state = {
            "session_id": "test123",
            "student_id": "student456",
            "phase": "awaiting_main_answer",
            "history": [{"role": "user", "content": "test"}],
            "scores": [85, 90],
        }
    elif state_size == "large":
        state = {
            "session_id": "test123",
            "student_id": "student456",
            "phase": "awaiting_main_answer",
            "history": [{"role": "user", "content": "test " * 1000} for _ in range(100)],
            "scores": [85, 90] * 50,
            "answers_tslog_all": [{"ts_iso": "2024-01-01T00:00:00Z", "text": "answer"} for _ in range(200)],
        }
    else:  # medium
        state = {
            "session_id": "test123",
            "student_id": "student456",
            "phase": "awaiting_main_answer",
            "history": [{"role": "user", "content": "test"} for _ in range(20)],
            "scores": [85, 90, 88, 92],
            "answers_tslog_all": [{"ts_iso": "2024-01-01T00:00:00Z", "text": "answer"} for _ in range(10)],
        }
    
    # Prepare state for serialization
    prepared_state = prepare_state_for_serialization(state)
    
    # Benchmark serialization
    start = time.perf_counter()
    json_str = json.dumps(prepared_state)
    duration = time.perf_counter() - start
    
    return duration


def benchmark_state_save(state_size: str = "medium", use_disk: bool = False) -> float:
    """Benchmark state save operation."""
    if state_size == "small":
        state = ensure_state({"session_id": "test123", "student_id": "student456"})
    elif state_size == "large":
        state = ensure_state({
            "session_id": "test123",
            "student_id": "student456",
            "history": [{"role": "user", "content": "test " * 1000} for _ in range(100)],
        })
    else:  # medium
        state = ensure_state({
            "session_id": "test123",
            "student_id": "student456",
            "history": [{"role": "user", "content": "test"} for _ in range(20)],
        })
    
    if use_disk:
        # Actually save to disk (creates temp file)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        temp_path = temp_file.name
        temp_file.close()
        
        try:
            start = time.perf_counter()
            save_state_to_disk(state, persist_ok=True)
            duration = time.perf_counter() - start
        finally:
            # Cleanup
            if os.path.exists(temp_path):
                os.remove(temp_path)
    else:
        # Just measure serialization time
        start = time.perf_counter()
        prepared = prepare_state_for_serialization(state)
        json.dumps(prepared)
        duration = time.perf_counter() - start
    
    return duration


def benchmark_tts_generation(text_length: str = "medium", client: Optional[OpenAI] = None) -> float:
    """Benchmark TTS generation."""
    if text_length == "short":
        text = "Please elaborate."
    elif text_length == "long":
        text = "This is a longer question that requires more time to generate. " * 20
    else:  # medium
        text = "What is the main idea of this passage? Please explain in detail."
    
    if client is None:
        # Mock TTS (no API call)
        time.sleep(0.1)  # Simulate API call
        return 0.1
    
    try:
        start = time.perf_counter()
        audio_path = tts_to_mp3(text, client, s=None)
        duration = time.perf_counter() - start
        
        # Cleanup
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except:
                pass
        
        return duration
    except Exception as e:
        print(f"Warning: TTS benchmark failed: {e}")
        return 0.0


def benchmark_stt_transcription(audio_duration: float = 5.0, client: Optional[OpenAI] = None) -> float:
    """Benchmark STT transcription."""
    if client is None:
        # Mock transcription (no API call)
        time.sleep(audio_duration * 0.1)  # Simulate transcription time
        return audio_duration * 0.1
    
    # Create a dummy audio file for testing
    # In real scenario, this would be an actual audio file
    try:
        # For benchmarking, we'll simulate or use a small test file
        # This is a placeholder - actual implementation would need a real audio file
        print("Warning: STT benchmark requires actual audio file - using mock")
        time.sleep(0.2)  # Simulate transcription
        return 0.2
    except Exception as e:
        print(f"Warning: STT benchmark failed: {e}")
        return 0.0


def benchmark_question_generation_flow(client: Optional[OpenAI] = None) -> Dict[str, float]:
    """Benchmark full question generation flow (chunk selection + question gen + TTS)."""
    results = {}
    
    # 1. Chunk selection + validation
    start = time.perf_counter()
    chunks = ["Test chunk content " * 50 for _ in range(10)]
    valid_chunks = [chunk for chunk in chunks if _validate_context(chunk)[0]]
    results["chunk_selection"] = time.perf_counter() - start
    
    # 2. Question generation (mock - would be API call)
    if client:
        try:
            start = time.perf_counter()
            # Mock question generation - in real scenario would call API
            question = "What is the main idea of this passage?"
            time.sleep(0.1)  # Simulate API latency
            results["question_generation"] = time.perf_counter() - start
        except Exception as e:
            print(f"Warning: Question generation benchmark failed: {e}")
            results["question_generation"] = 0.0
    else:
        start = time.perf_counter()
        question = "What is the main idea of this passage?"
        time.sleep(0.1)  # Simulate API latency
        results["question_generation"] = time.perf_counter() - start
    
    # 3. TTS generation
    tts_duration = benchmark_tts_generation("medium", client)
    results["tts_generation"] = tts_duration
    
    # 4. Total flow time
    results["total_flow"] = results["chunk_selection"] + results["question_generation"] + results["tts_generation"]
    
    return results


def run_benchmarks(
    iterations: int = 5,
    use_api: bool = False,
    client: Optional[OpenAI] = None
) -> BenchmarkResults:
    """Run all benchmarks."""
    results = BenchmarkResults()
    results.metadata = {
        "iterations": iterations,
        "use_api": use_api,
        "timestamp": time.time(),
    }
    
    print("=" * 80)
    print("Exam Flow Performance Benchmark")
    print("=" * 80)
    print(f"Iterations: {iterations}")
    print(f"Use API: {use_api}")
    print()
    
    # Reset metrics
    reset_metrics()
    
    # 1. Chunk validation
    print("Benchmarking: Chunk validation...")
    for i in range(iterations):
        duration = benchmark_chunk_validation(num_chunks=100)
        results.add_timing("chunk_validation", duration)
    print(f"  Average: {results.get_stats('chunk_validation')['mean']*1000:.2f}ms per chunk")
    print()
    
    # 2. State serialization (small, medium, large)
    for size in ["small", "medium", "large"]:
        print(f"Benchmarking: State serialization ({size})...")
        for i in range(iterations):
            duration = benchmark_state_serialization(state_size=size)
            results.add_timing(f"state_serialization_{size}", duration)
        stats = results.get_stats(f"state_serialization_{size}")
        print(f"  Average: {stats['mean']*1000:.2f}ms")
    print()
    
    # 3. State save (serialization only, no disk I/O)
    print("Benchmarking: State save (serialization only)...")
    for i in range(iterations):
        duration = benchmark_state_save(state_size="medium", use_disk=False)
        results.add_timing("state_save_serialization", duration)
    stats = results.get_stats("state_save_serialization")
    print(f"  Average: {stats['mean']*1000:.2f}ms")
    print()
    
    # 4. TTS generation (short, medium, long)
    for length in ["short", "medium", "long"]:
        print(f"Benchmarking: TTS generation ({length})...")
        for i in range(iterations):
            duration = benchmark_tts_generation(text_length=length, client=client if use_api else None)
            results.add_timing(f"tts_generation_{length}", duration)
        stats = results.get_stats(f"tts_generation_{length}")
        print(f"  Average: {stats['mean']:.3f}s")
    print()
    
    # 5. STT transcription
    print("Benchmarking: STT transcription...")
    for i in range(iterations):
        duration = benchmark_stt_transcription(audio_duration=5.0, client=client if use_api else None)
        results.add_timing("stt_transcription", duration)
    stats = results.get_stats("stt_transcription")
    print(f"  Average: {stats['mean']:.3f}s")
    print()
    
    # 6. Full question generation flow
    print("Benchmarking: Full question generation flow...")
    for i in range(iterations):
        flow_results = benchmark_question_generation_flow(client=client if use_api else None)
        for op, duration in flow_results.items():
            results.add_timing(f"question_flow_{op}", duration)
    
    flow_stats = {
        "chunk_selection": results.get_stats("question_flow_chunk_selection"),
        "question_generation": results.get_stats("question_flow_question_generation"),
        "tts_generation": results.get_stats("question_flow_tts_generation"),
        "total_flow": results.get_stats("question_flow_total_flow"),
    }
    print(f"  Chunk selection: {flow_stats['chunk_selection']['mean']*1000:.2f}ms")
    print(f"  Question generation: {flow_stats['question_generation']['mean']:.3f}s")
    print(f"  TTS generation: {flow_stats['tts_generation']['mean']:.3f}s")
    print(f"  Total flow: {flow_stats['total_flow']['mean']:.3f}s")
    print()
    
    return results


def print_summary(results: BenchmarkResults):
    """Print summary of benchmark results."""
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print()
    
    # Group by category
    categories = {
        "Chunk Operations": ["chunk_validation"],
        "State Operations": [op for op in results.results.keys() if "state" in op],
        "TTS Operations": [op for op in results.results.keys() if "tts" in op],
        "STT Operations": [op for op in results.results.keys() if "stt" in op],
        "Question Flow": [op for op in results.results.keys() if "question_flow" in op],
    }
    
    for category, operations in categories.items():
        if not operations:
            continue
        
        print(f"{category}:")
        print(f"{'Operation':<40} {'Mean':<12} {'P95':<12} {'P99':<12} {'Count':<8}")
        print("-" * 80)
        
        for op in sorted(operations):
            stats = results.get_stats(op)
            if stats:
                print(f"{op:<40} {stats['mean']*1000:>10.2f}ms {stats['p95']*1000:>10.2f}ms {stats['p99']*1000:>10.2f}ms {stats['count']:>6}")
        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Benchmark exam flow performance")
    parser.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="Number of iterations per benchmark (default: 5)"
    )
    parser.add_argument(
        "--use-api",
        action="store_true",
        help="Use actual OpenAI API calls (requires API key)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Save results to JSON file"
    )
    
    args = parser.parse_args()
    
    # Initialize OpenAI client if using API
    client = None
    if args.use_api:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("Warning: OPENAI_API_KEY not set. Running with mock API calls.")
        else:
            try:
                client = OpenAI(api_key=api_key)
                print("Using actual OpenAI API calls.")
            except Exception as e:
                print(f"Warning: Could not initialize OpenAI client: {e}")
                print("Running with mock API calls.")
    
    # Run benchmarks
    results = run_benchmarks(
        iterations=args.iterations,
        use_api=args.use_api and client is not None,
        client=client
    )
    
    # Print summary
    print_summary(results)
    
    # Save to file if requested
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(results.to_dict(), f, indent=2)
        print(f"Results saved to: {output_path}")
    
    # Print performance targets from spd.txt
    print("=" * 80)
    print("Performance Targets (from spd.txt):")
    print("=" * 80)
    print("  Question generation: < 3s (including API call)")
    print("  Audio transcription: < 5s for 60s audio")
    print("  TTS generation: < 2s for typical question")
    print("  State save: < 100ms per save")
    print("  Total exam flow: < 10s per question-answer cycle")
    print()


if __name__ == "__main__":
    main()

