#!/usr/bin/env python3
"""
Health check script for VivaAI Assessment services.

Checks if all services are running and responding correctly.
Enhanced with response time tracking and detailed status information.
"""

import sys
import time
import requests
from typing import Dict, Tuple, Optional

# Service configuration
SERVICES: Dict[str, Dict[str, str]] = {
    "API": {
        "url": "http://localhost:8000/health",
        "name": "API Server",
        "port": "8000"
    },
    "Exam": {
        "url": "http://localhost:7860/",
        "name": "Exam Interface",
        "port": "7860"
    },
    "Prof": {
        "url": "http://localhost:7861/",
        "name": "Professor URL Generator",
        "port": "7861"
    },
    "Dash": {
        "url": "http://localhost:7862/",
        "name": "Dashboard",
        "port": "7862"
    }
}


def check_service(name: str, config: Dict[str, str]) -> Tuple[bool, str, Optional[float]]:
    """
    Check if a service is running and responding.
    
    Args:
        name: Service identifier
        config: Service configuration with url, name, port
        
    Returns:
        Tuple of (is_ok, message, response_time_seconds)
        - is_ok: True if service is healthy, False otherwise
        - message: Human-readable status message
        - response_time_seconds: Response time in seconds (None if failed)
    """
    url = config["url"]
    service_name = config["name"]
    
    try:
        start_time = time.time()
        response = requests.get(url, timeout=5)  # Increased timeout for better reliability
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            # Try to extract additional info from API health endpoint
            extra_info = ""
            if name == "API" and response.headers.get("content-type", "").startswith("application/json"):
                try:
                    health_data = response.json()
                    status = health_data.get("status", "unknown")
                    extra_info = f" (status: {status})"
                except:
                    pass
            
            time_str = f"{elapsed:.3f}s" if elapsed < 1.0 else f"{elapsed:.2f}s"
            return True, f"✓ {service_name}: OK (port {config['port']}, {time_str}{extra_info})", elapsed
        else:
            return False, f"✗ {service_name}: Status {response.status_code} (port {config['port']})", None
    except requests.exceptions.ConnectionError:
        return False, f"✗ {service_name}: Connection refused (port {config['port']} - service not running?)", None
    except requests.exceptions.Timeout:
        return False, f"✗ {service_name}: Timeout (port {config['port']} - service not responding?)", None
    except Exception as e:
        return False, f"✗ {service_name}: {type(e).__name__} - {str(e)[:100]} (port {config['port']})", None


def main():
    """Main function to check all services."""
    print("🔍 Checking VivaAI Assessment Services...")
    print("=" * 70)
    print()
    
    all_ok = True
    results = []
    total_time = 0.0
    
    for service_id, config in SERVICES.items():
        is_ok, message, response_time = check_service(service_id, config)
        results.append((is_ok, message, response_time))
        if not is_ok:
            all_ok = False
        if response_time is not None:
            total_time += response_time
    
    # Print results
    for is_ok, message, response_time in results:
        print(f"  {message}")
    
    print()
    print("=" * 70)
    
    # Summary statistics
    healthy_count = sum(1 for is_ok, _, _ in results if is_ok)
    total_count = len(results)
    
    if all_ok:
        print(f"✅ All {healthy_count}/{total_count} services are running correctly!")
        if total_time > 0:
            avg_time = total_time / healthy_count
            print(f"   Average response time: {avg_time:.3f}s")
        return 0
    else:
        print(f"❌ {healthy_count}/{total_count} services are healthy. Some services are not running or not responding.")
        print()
        print("Troubleshooting:")
        print("  1. Check if services are started:")
        print("     - API:    uvicorn app.main:app --host 0.0.0.0 --port 8000")
        print("     - Exam:   python exam.py")
        print("     - Prof:   python prof.py")
        print("     - Dash:   python dash.py")
        print()
        print("  2. Or use the startup script:")
        print("     bash scripts/start_all.sh")
        print()
        print("  3. Check environment variables:")
        print("     - Ensure .env file exists (see .env.example)")
        print("     - Verify VIVA_HMAC_SECRET and OPENAI_API_KEY are set")
        print("     - If using API mode, verify API_BASE_URL and API_KEY are set")
        print("     - (Alternative: EXAM_API_URL and EXAM_API_KEY)")
        print()
        print("  4. Check logs for errors")
        return 1


if __name__ == "__main__":
    sys.exit(main())

