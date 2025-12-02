#!/usr/bin/env python3
"""
Load testing script for VivaAI Secure Exam Proctoring System.

This script provides basic load testing capabilities for the system.
For more advanced load testing, consider using locust or k6.

Usage:
    python scripts/load_test.py --endpoint <url> --requests <count> --concurrent <workers>
"""

import argparse
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any
import statistics

try:
    import httpx
except ImportError:
    print("Error: httpx is required for load testing")
    print("Install it with: uv pip install httpx")
    exit(1)


class LoadTestResult:
    """Results from a load test run."""
    
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.response_times: List[float] = []
        self.errors: List[str] = []
        self.start_time: float = 0
        self.end_time: float = 0
    
    def add_result(self, response_time: float, success: bool, error: str = ""):
        """Add a request result."""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
            self.response_times.append(response_time)
        else:
            self.failed_requests += 1
            if error:
                self.errors.append(error)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics from results."""
        if not self.response_times:
            return {
                "total_requests": self.total_requests,
                "successful": self.successful_requests,
                "failed": self.failed_requests,
                "success_rate": 0.0,
                "duration": self.end_time - self.start_time,
            }
        
        return {
            "total_requests": self.total_requests,
            "successful": self.successful_requests,
            "failed": self.failed_requests,
            "success_rate": self.successful_requests / self.total_requests * 100,
            "duration": self.end_time - self.start_time,
            "requests_per_second": self.total_requests / (self.end_time - self.start_time),
            "response_time_min": min(self.response_times),
            "response_time_max": max(self.response_times),
            "response_time_mean": statistics.mean(self.response_times),
            "response_time_median": statistics.median(self.response_times),
            "response_time_p95": self._percentile(self.response_times, 95),
            "response_time_p99": self._percentile(self.response_times, 99),
        }
    
    @staticmethod
    def _percentile(data: List[float], percentile: int) -> float:
        """Calculate percentile."""
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]


def make_request(url: str, method: str = "GET", headers: Dict[str, str] = None) -> tuple:
    """Make a single HTTP request."""
    start_time = time.time()
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.request(method, url, headers=headers or {})
            elapsed = time.time() - start_time
            
            if response.status_code < 400:
                return elapsed, True, ""
            else:
                return elapsed, False, f"HTTP {response.status_code}"
    except Exception as e:
        elapsed = time.time() - start_time
        return elapsed, False, str(e)


def run_load_test(
    url: str,
    num_requests: int,
    concurrent_workers: int,
    method: str = "GET",
    headers: Dict[str, str] = None
) -> LoadTestResult:
    """Run load test."""
    result = LoadTestResult()
    result.start_time = time.time()
    
    print(f"🚀 Starting load test:")
    print(f"   URL: {url}")
    print(f"   Requests: {num_requests}")
    print(f"   Concurrent workers: {concurrent_workers}")
    print(f"   Method: {method}")
    print()
    
    with ThreadPoolExecutor(max_workers=concurrent_workers) as executor:
        futures = [
            executor.submit(make_request, url, method, headers)
            for _ in range(num_requests)
        ]
        
        completed = 0
        for future in futures:
            response_time, success, error = future.result()
            result.add_result(response_time, success, error)
            completed += 1
            if completed % 10 == 0:
                print(f"   Progress: {completed}/{num_requests} requests", end="\r")
    
    result.end_time = time.time()
    print()  # New line after progress
    
    return result


def print_results(result: LoadTestResult):
    """Print load test results."""
    stats = result.get_stats()
    
    print("\n" + "=" * 60)
    print("LOAD TEST RESULTS")
    print("=" * 60)
    print(f"Total Requests:     {stats['total_requests']}")
    print(f"Successful:         {stats['successful']}")
    print(f"Failed:             {stats['failed']}")
    print(f"Success Rate:       {stats['success_rate']:.2f}%")
    print(f"Duration:           {stats['duration']:.2f}s")
    print(f"Requests/Second:    {stats['requests_per_second']:.2f}")
    print()
    
    if stats['successful'] > 0:
        print("Response Times:")
        print(f"  Min:              {stats['response_time_min']:.3f}s")
        print(f"  Max:              {stats['response_time_max']:.3f}s")
        print(f"  Mean:             {stats['response_time_mean']:.3f}s")
        print(f"  Median:           {stats['response_time_median']:.3f}s")
        print(f"  P95:              {stats['response_time_p95']:.3f}s")
        print(f"  P99:              {stats['response_time_p99']:.3f}s")
    
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        error_counts = {}
        for error in result.errors:
            error_counts[error] = error_counts.get(error, 0) + 1
        for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {error}: {count}")
    
    print("=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Load test VivaAI endpoints")
    parser.add_argument("--endpoint", required=True, help="Endpoint URL to test")
    parser.add_argument("--requests", type=int, default=100, help="Number of requests")
    parser.add_argument("--concurrent", type=int, default=10, help="Concurrent workers")
    parser.add_argument("--method", default="GET", help="HTTP method")
    parser.add_argument("--header", action="append", help="HTTP header (key:value)")
    
    args = parser.parse_args()
    
    headers = {}
    if args.header:
        for header in args.header:
            if ":" in header:
                key, value = header.split(":", 1)
                headers[key.strip()] = value.strip()
    
    result = run_load_test(
        args.endpoint,
        args.requests,
        args.concurrent,
        args.method,
        headers
    )
    
    print_results(result)


if __name__ == "__main__":
    main()

