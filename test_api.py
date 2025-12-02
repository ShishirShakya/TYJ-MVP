#!/usr/bin/env python3
"""
Manual API testing script for VivaAI Assessment API.

This script helps test all endpoints and verify the API works correctly.
"""

import os
import sys
import hmac
import hashlib
import requests
import json
from typing import Optional

# Configuration
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_SECRET = os.getenv("VIVA_HMAC_SECRET", "DEVELOPMENT-ONLY-CHANGE-ME-min-32-chars")


def generate_api_key(secret: str) -> str:
    """Generate a valid API key using HMAC."""
    known_token = "vivaai-api-key"
    return hmac.new(
        secret.encode("utf-8"),
        known_token.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def print_response(response: requests.Response, title: str):
    """Print formatted response."""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    print(f"Status: {response.status_code}")
    print(f"Headers:")
    for key, value in response.headers.items():
        if key.lower() in ['x-request-id', 'x-api-version', 'content-type']:
            print(f"  {key}: {value}")
    print(f"\nBody:")
    try:
        print(json.dumps(response.json(), indent=2))
    except:
        print(response.text)
    print()


def test_root():
    """Test root endpoint."""
    print("\n🔍 Testing Root Endpoint...")
    response = requests.get(f"{BASE_URL}/")
    print_response(response, "Root Endpoint")
    return response.status_code == 200


def test_health():
    """Test health check endpoint."""
    print("\n🔍 Testing Health Check...")
    response = requests.get(f"{BASE_URL}/health")
    print_response(response, "Health Check")
    return response.status_code == 200


def test_metrics():
    """Test metrics endpoint."""
    print("\n🔍 Testing Metrics Endpoint...")
    response = requests.get(f"{BASE_URL}/metrics")
    print_response(response, "Metrics")
    return response.status_code == 200


def test_parse_link(api_key: str):
    """Test parse link endpoint."""
    print("\n🔍 Testing Parse Link Endpoint...")
    
    # Test with valid URL
    url = "https://example.com/exam?pdf_url=https://example.com/test.pdf&config=CS101/EXAM001/5/2/decryption_key"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key
    }
    data = {"url": url}
    
    response = requests.post(
        f"{BASE_URL}/api/v1/assessments/parse-link",
        headers=headers,
        json=data
    )
    print_response(response, "Parse Link (Valid URL)")
    
    # Test with invalid API key
    print("\n🔍 Testing Parse Link with Invalid API Key...")
    headers["X-API-Key"] = "invalid-key"
    response = requests.post(
        f"{BASE_URL}/api/v1/assessments/parse-link",
        headers=headers,
        json=data
    )
    print_response(response, "Parse Link (Invalid API Key)")
    
    return response.status_code == 401  # Should fail with invalid key


def test_generate_question(api_key: str):
    """Test generate question endpoint (placeholder)."""
    print("\n🔍 Testing Generate Question Endpoint...")
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key
    }
    data = {
        "session_id": "test_session_123",
        "course_id": "CS101",
        "exam_id": "EXAM001"
    }
    
    response = requests.post(
        f"{BASE_URL}/api/v1/assessments/generate-question",
        headers=headers,
        json=data
    )
    print_response(response, "Generate Question (Placeholder)")
    return response.status_code == 501  # Expected: Not Implemented


def test_grade_answer(api_key: str):
    """Test grade answer endpoint (placeholder)."""
    print("\n🔍 Testing Grade Answer Endpoint...")
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key
    }
    data = {
        "session_id": "test_session_123",
        "answer": "This is a test answer",
        "question_id": "q_123"
    }
    
    response = requests.post(
        f"{BASE_URL}/api/v1/assessments/grade",
        headers=headers,
        json=data
    )
    print_response(response, "Grade Answer (Placeholder)")
    return response.status_code == 501  # Expected: Not Implemented


def test_rate_limiting(api_key: str):
    """Test rate limiting."""
    print("\n🔍 Testing Rate Limiting...")
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key
    }
    data = {"url": "https://example.com"}
    
    # Make multiple requests
    success_count = 0
    rate_limited_count = 0
    
    print("Making 70 requests to test rate limiting...")
    for i in range(70):
        response = requests.post(
            f"{BASE_URL}/api/v1/assessments/parse-link",
            headers=headers,
            json=data
        )
        if response.status_code == 200 or response.status_code == 400:
            success_count += 1
        elif response.status_code == 429:
            rate_limited_count += 1
            if rate_limited_count == 1:
                print(f"\n⚠️  Rate limit hit at request #{i+1}")
                print_response(response, "Rate Limit Response")
    
    print(f"\nResults: {success_count} successful, {rate_limited_count} rate limited")
    return rate_limited_count > 0


def test_request_id():
    """Test request ID correlation."""
    print("\n🔍 Testing Request ID Correlation...")
    custom_id = "test-request-12345"
    headers = {"X-Request-ID": custom_id}
    
    response = requests.get(f"{BASE_URL}/health", headers=headers)
    print_response(response, "Request ID Test")
    
    returned_id = response.headers.get("X-Request-ID")
    if returned_id == custom_id:
        print("✅ Request ID correlation works!")
        return True
    else:
        print(f"❌ Request ID mismatch: sent {custom_id}, got {returned_id}")
        return False


def main():
    """Run all tests."""
    print("="*60)
    print("VivaAI Assessment API - Manual Testing Script")
    print("="*60)
    print(f"Base URL: {BASE_URL}")
    
    # Generate API key
    api_key = generate_api_key(API_SECRET)
    print(f"\nGenerated API Key: {api_key[:20]}...")
    
    results = {}
    
    # Run tests
    print("\n" + "="*60)
    print("Running Tests...")
    print("="*60)
    
    results["root"] = test_root()
    results["health"] = test_health()
    results["metrics"] = test_metrics()
    results["parse_link"] = test_parse_link(api_key)
    results["generate_question"] = test_generate_question(api_key)
    results["grade_answer"] = test_grade_answer(api_key)
    results["request_id"] = test_request_id()
    
    # Rate limiting test (optional, takes time)
    print("\n" + "="*60)
    user_input = input("Run rate limiting test? (takes ~10 seconds) [y/N]: ")
    if user_input.lower() == 'y':
        results["rate_limiting"] = test_rate_limiting(api_key)
    else:
        print("Skipping rate limiting test")
        results["rate_limiting"] = None
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    for test_name, result in results.items():
        if result is None:
            status = "⏭️  SKIPPED"
        elif result:
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
        print(f"{test_name:20} {status}")
    
    print("\n" + "="*60)
    print("Testing Complete!")
    print("="*60)
    print("\nNote: Some endpoints return 501 (Not Implemented) - this is expected.")
    print("These endpoints need to be wired up to the business logic.")
    print("\nNext steps:")
    print("1. Review the test results above")
    print("2. Check server logs for any errors")
    print("3. Verify API documentation at http://localhost:8000/docs")
    print("4. Implement adapter layer for placeholder endpoints")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Error: Could not connect to {BASE_URL}")
        print("Make sure the server is running: uvicorn app.main:app --reload")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

