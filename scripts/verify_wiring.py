#!/usr/bin/env python3
"""
Comprehensive wiring verification script for VivaAI Assessment API.

This script verifies that all components are properly wired:
- All imports work correctly
- All endpoints are registered
- Middleware is configured
- Dependencies are properly connected
- FastAPI app can be instantiated
"""

import os
import sys
import importlib
import inspect
from pathlib import Path
from typing import List, Dict, Tuple, Any
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class WiringVerifier:
    """Verify all wiring in the FastAPI application."""
    
    def __init__(self):
        self.results = {
            "imports": {"passed": [], "failed": []},
            "endpoints": {"registered": [], "missing": []},
            "middleware": {"configured": [], "missing": []},
            "dependencies": {"available": [], "missing": []},
            "app_creation": {"status": None, "error": None},
            "schemas": {"valid": [], "invalid": []}
        }
        self.errors = []
    
    def verify_imports(self) -> Dict[str, Any]:
        """Verify all critical imports work."""
        print("\n" + "="*60)
        print("1. VERIFYING IMPORTS")
        print("="*60)
        
        imports_to_check = [
            # Core FastAPI
            ("fastapi", "FastAPI"),
            ("fastapi", "Request"),
            ("fastapi", "HTTPException"),
            ("fastapi.middleware.cors", "CORSMiddleware"),
            
            # App modules
            ("app.schemas", "GenerateQuestionRequest"),
            ("app.schemas", "GenerateQuestionResponse"),
            ("app.schemas", "GradeAnswerRequest"),
            ("app.schemas", "GradeAnswerResponse"),
            ("app.schemas", "ProcessAudioRequest"),
            ("app.schemas", "ProcessAudioResponse"),
            ("app.schemas", "AnalyzeProctorRequest"),
            ("app.schemas", "AnalyzeProctorResponse"),
            ("app.schemas", "ParseLinkRequest"),
            ("app.schemas", "ParseLinkResponse"),
            ("app.schemas", "ErrorResponse"),
            
            # Shared modules
            ("shared.rate_limiting", "RateLimiter"),
            ("shared.rate_limiting", "RateLimitConfig"),
            ("shared.circuit_breaker", "CircuitBreaker"),
            ("shared.circuit_breaker", "CircuitBreakerConfig"),
            ("shared.logging_config", "setup_structlog"),
            ("shared.logging_config", "get_logger"),
            ("shared.security_config", "get_hmac_secret"),
            ("shared.constants", "MAX_FILE_SIZE"),
            ("shared.config_validation", "validate_config_at_startup"),
            ("shared.config_validation", "ConfigValidationError"),
            ("shared.url_encoding", "decode_config_from_url"),
            ("shared.config_parsing", "validate_config_params"),
            
            # Exam config (used in root endpoint)
            ("exam.config", "APP_VERSION"),
        ]
        
        for module_name, item_name in imports_to_check:
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, item_name):
                    self.results["imports"]["passed"].append(f"{module_name}.{item_name}")
                    print(f"  ✅ {module_name}.{item_name}")
                else:
                    self.results["imports"]["failed"].append(f"{module_name}.{item_name}")
                    print(f"  ❌ {module_name}.{item_name} - not found in module")
            except ImportError as e:
                self.results["imports"]["failed"].append(f"{module_name}.{item_name}")
                self.errors.append(f"Import error: {module_name}.{item_name} - {str(e)}")
                print(f"  ❌ {module_name}.{item_name} - {str(e)}")
            except Exception as e:
                self.results["imports"]["failed"].append(f"{module_name}.{item_name}")
                self.errors.append(f"Error importing {module_name}.{item_name}: {str(e)}")
                print(f"  ❌ {module_name}.{item_name} - {str(e)}")
        
        return self.results["imports"]
    
    def verify_app_creation(self) -> Dict[str, Any]:
        """Verify FastAPI app can be created."""
        print("\n" + "="*60)
        print("2. VERIFYING APP CREATION")
        print("="*60)
        
        try:
            # Set minimal environment if not set
            if not os.getenv("VIVA_HMAC_SECRET"):
                os.environ["VIVA_HMAC_SECRET"] = "DEVELOPMENT-ONLY-CHANGE-ME-min-32-chars-for-testing"
            if not os.getenv("ENVIRONMENT"):
                os.environ["ENVIRONMENT"] = "development"
            
            # Import app (this will execute all initialization code)
            from app.main import app
            
            # Verify app is FastAPI instance
            from fastapi import FastAPI
            if isinstance(app, FastAPI):
                self.results["app_creation"]["status"] = "success"
                print(f"  ✅ FastAPI app created successfully")
                print(f"     Title: {app.title}")
                print(f"     Version: {app.version}")
                print(f"     Docs URL: {app.docs_url}")
            else:
                self.results["app_creation"]["status"] = "failed"
                self.results["app_creation"]["error"] = "App is not a FastAPI instance"
                print(f"  ❌ App is not a FastAPI instance")
        except Exception as e:
            self.results["app_creation"]["status"] = "failed"
            self.results["app_creation"]["error"] = str(e)
            self.errors.append(f"App creation error: {str(e)}")
            print(f"  ❌ Failed to create app: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return self.results["app_creation"]
    
    def verify_endpoints(self) -> Dict[str, Any]:
        """Verify all expected endpoints are registered."""
        print("\n" + "="*60)
        print("3. VERIFYING ENDPOINTS")
        print("="*60)
        
        try:
            from app.main import app
            
            # Expected endpoints
            expected_endpoints = [
                ("GET", "/"),
                ("GET", "/health"),
                ("GET", "/metrics"),
                ("POST", "/api/v1/assessments/generate-question"),
                ("POST", "/api/v1/assessments/grade"),
                ("POST", "/api/v1/assessments/process-audio"),
                ("POST", "/api/v1/assessments/analyze-proctor"),
                ("POST", "/api/v1/assessments/parse-link"),
            ]
            
            # Get registered routes
            registered_routes = {}
            for route in app.routes:
                if hasattr(route, "path") and hasattr(route, "methods"):
                    for method in route.methods:
                        if method != "HEAD" and method != "OPTIONS":  # Skip auto-generated
                            key = (method, route.path)
                            registered_routes[key] = route
            
            # Check each expected endpoint
            for method, path in expected_endpoints:
                key = (method, path)
                if key in registered_routes:
                    route = registered_routes[key]
                    self.results["endpoints"]["registered"].append(f"{method} {path}")
                    print(f"  ✅ {method} {path}")
                    
                    # Check if it has a response model
                    if hasattr(route, "response_model") and route.response_model:
                        print(f"     Response model: {route.response_model.__name__}")
                else:
                    self.results["endpoints"]["missing"].append(f"{method} {path}")
                    print(f"  ❌ {method} {path} - NOT REGISTERED")
            
            # List any unexpected endpoints
            print(f"\n  Total registered routes: {len(registered_routes)}")
            
        except Exception as e:
            self.errors.append(f"Endpoint verification error: {str(e)}")
            print(f"  ❌ Error verifying endpoints: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return self.results["endpoints"]
    
    def verify_middleware(self) -> Dict[str, Any]:
        """Verify middleware is configured."""
        print("\n" + "="*60)
        print("4. VERIFYING MIDDLEWARE")
        print("="*60)
        
        try:
            from app.main import app
            
            # Expected middleware
            expected_middleware = [
                "CORSMiddleware",
                "request_id_middleware",
                "api_version_middleware",
                "request_limits_middleware"
            ]
            
            # Check middleware stack
            middleware_types = []
            for middleware in app.user_middleware:
                middleware_name = str(middleware.cls) if hasattr(middleware, 'cls') else str(middleware)
                middleware_types.append(middleware_name)
                if any(expected in middleware_name for expected in expected_middleware):
                    self.results["middleware"]["configured"].append(middleware_name)
                    print(f"  ✅ {middleware_name}")
            
            # Check for specific middleware functions
            middleware_functions = []
            for route in app.routes:
                if hasattr(route, "dependant") and route.dependant:
                    # Check dependencies
                    pass
            
            # Check if middleware functions exist in app.main
            import app.main as main_module
            if hasattr(main_module, "request_id_middleware"):
                if "request_id_middleware" not in self.results["middleware"]["configured"]:
                    self.results["middleware"]["configured"].append("request_id_middleware")
                    print(f"  ✅ request_id_middleware (function)")
            
            if hasattr(main_module, "api_version_middleware"):
                if "api_version_middleware" not in self.results["middleware"]["configured"]:
                    self.results["middleware"]["configured"].append("api_version_middleware")
                    print(f"  ✅ api_version_middleware (function)")
            
            if hasattr(main_module, "request_limits_middleware"):
                if "request_limits_middleware" not in self.results["middleware"]["configured"]:
                    self.results["middleware"]["configured"].append("request_limits_middleware")
                    print(f"  ✅ request_limits_middleware (function)")
            
            # Check CORS
            cors_found = any("CORS" in str(m) for m in middleware_types)
            if cors_found:
                print(f"  ✅ CORSMiddleware configured")
            else:
                self.results["middleware"]["missing"].append("CORSMiddleware")
                print(f"  ❌ CORSMiddleware not found")
            
        except Exception as e:
            self.errors.append(f"Middleware verification error: {str(e)}")
            print(f"  ❌ Error verifying middleware: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return self.results["middleware"]
    
    def verify_dependencies(self) -> Dict[str, Any]:
        """Verify dependencies are available."""
        print("\n" + "="*60)
        print("5. VERIFYING DEPENDENCIES")
        print("="*60)
        
        try:
            from app.main import app
            
            # Check for dependency functions
            import app.main as main_module
            
            dependencies_to_check = [
                "verify_api_key",
                "check_rate_limit",
                "require_auth",
                "rate_limiter",
                "circuit_breaker",
                "logger"
            ]
            
            for dep_name in dependencies_to_check:
                if hasattr(main_module, dep_name):
                    dep = getattr(main_module, dep_name)
                    self.results["dependencies"]["available"].append(dep_name)
                    print(f"  ✅ {dep_name}")
                    
                    # Check type if applicable
                    if dep_name == "rate_limiter":
                        from shared.rate_limiting import RateLimiter
                        if isinstance(dep, RateLimiter):
                            print(f"     Type: RateLimiter ✓")
                    
                    elif dep_name == "circuit_breaker":
                        from shared.circuit_breaker import CircuitBreaker
                        if isinstance(dep, CircuitBreaker):
                            print(f"     Type: CircuitBreaker ✓")
                    
                    elif dep_name == "logger":
                        import structlog
                        if isinstance(dep, structlog.BoundLogger):
                            print(f"     Type: BoundLogger ✓")
                else:
                    self.results["dependencies"]["missing"].append(dep_name)
                    print(f"  ❌ {dep_name} - NOT FOUND")
            
        except Exception as e:
            self.errors.append(f"Dependency verification error: {str(e)}")
            print(f"  ❌ Error verifying dependencies: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return self.results["dependencies"]
    
    def verify_schemas(self) -> Dict[str, Any]:
        """Verify Pydantic schemas are valid."""
        print("\n" + "="*60)
        print("6. VERIFYING SCHEMAS")
        print("="*60)
        
        try:
            from app.schemas import (
                GenerateQuestionRequest, GenerateQuestionResponse,
                GradeAnswerRequest, GradeAnswerResponse,
                ProcessAudioRequest, ProcessAudioResponse,
                AnalyzeProctorRequest, AnalyzeProctorResponse,
                ParseLinkRequest, ParseLinkResponse,
                ErrorResponse
            )
            
            schemas_to_check = [
                ("GenerateQuestionRequest", GenerateQuestionRequest),
                ("GenerateQuestionResponse", GenerateQuestionResponse),
                ("GradeAnswerRequest", GradeAnswerRequest),
                ("GradeAnswerResponse", GradeAnswerResponse),
                ("ProcessAudioRequest", ProcessAudioRequest),
                ("ProcessAudioResponse", ProcessAudioResponse),
                ("AnalyzeProctorRequest", AnalyzeProctorRequest),
                ("AnalyzeProctorResponse", AnalyzeProctorResponse),
                ("ParseLinkRequest", ParseLinkRequest),
                ("ParseLinkResponse", ParseLinkResponse),
                ("ErrorResponse", ErrorResponse),
            ]
            
            for name, schema_class in schemas_to_check:
                try:
                    # Try to get schema JSON
                    schema_json = schema_class.schema()
                    self.results["schemas"]["valid"].append(name)
                    print(f"  ✅ {name}")
                    if "properties" in schema_json:
                        print(f"     Fields: {', '.join(schema_json['properties'].keys())}")
                except Exception as e:
                    self.results["schemas"]["invalid"].append(name)
                    print(f"  ❌ {name} - {str(e)}")
                    self.errors.append(f"Schema error: {name} - {str(e)}")
        
        except Exception as e:
            self.errors.append(f"Schema verification error: {str(e)}")
            print(f"  ❌ Error verifying schemas: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return self.results["schemas"]
    
    def verify_lifespan(self) -> Dict[str, Any]:
        """Verify lifespan context manager is configured."""
        print("\n" + "="*60)
        print("7. VERIFYING LIFESPAN")
        print("="*60)
        
        try:
            from app.main import app
            
            if hasattr(app, "router") and hasattr(app.router, "lifespan_context"):
                print(f"  ✅ Lifespan context manager configured")
                return {"status": "configured"}
            else:
                # Check if lifespan is passed to FastAPI constructor
                import inspect
                import app.main as main_module
                if hasattr(main_module, "lifespan"):
                    print(f"  ✅ Lifespan function exists")
                    return {"status": "exists"}
                else:
                    print(f"  ⚠️  Lifespan not found (may be optional)")
                    return {"status": "not_found"}
        except Exception as e:
            print(f"  ❌ Error verifying lifespan: {str(e)}")
            return {"status": "error", "error": str(e)}
    
    def run_all_checks(self) -> Dict[str, Any]:
        """Run all verification checks."""
        print("="*60)
        print("VIVAAI ASSESSMENT API - WIRING VERIFICATION")
        print("="*60)
        
        # Run all checks
        self.verify_imports()
        self.verify_app_creation()
        self.verify_endpoints()
        self.verify_middleware()
        self.verify_dependencies()
        self.verify_schemas()
        self.verify_lifespan()
        
        return self.generate_summary()
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate summary report."""
        print("\n" + "="*60)
        print("VERIFICATION SUMMARY")
        print("="*60)
        
        # Calculate statistics
        total_imports = len(self.results["imports"]["passed"]) + len(self.results["imports"]["failed"])
        import_success_rate = (len(self.results["imports"]["passed"]) / total_imports * 100) if total_imports > 0 else 0
        
        total_endpoints = len(self.results["endpoints"]["registered"]) + len(self.results["endpoints"]["missing"])
        endpoint_success_rate = (len(self.results["endpoints"]["registered"]) / total_endpoints * 100) if total_endpoints > 0 else 0
        
        print(f"\n📦 IMPORTS:")
        print(f"   ✅ Passed: {len(self.results['imports']['passed'])}/{total_imports} ({import_success_rate:.1f}%)")
        if self.results["imports"]["failed"]:
            print(f"   ❌ Failed: {len(self.results['imports']['failed'])}")
            for failed in self.results["imports"]["failed"][:5]:
                print(f"      - {failed}")
        
        print(f"\n🔌 ENDPOINTS:")
        print(f"   ✅ Registered: {len(self.results['endpoints']['registered'])}/{total_endpoints} ({endpoint_success_rate:.1f}%)")
        if self.results["endpoints"]["missing"]:
            print(f"   ❌ Missing: {len(self.results['endpoints']['missing'])}")
            for missing in self.results["endpoints"]["missing"]:
                print(f"      - {missing}")
        
        print(f"\n🔧 MIDDLEWARE:")
        print(f"   ✅ Configured: {len(self.results['middleware']['configured'])}")
        if self.results["middleware"]["missing"]:
            print(f"   ❌ Missing: {len(self.results['middleware']['missing'])}")
            for missing in self.results["middleware"]["missing"]:
                print(f"      - {missing}")
        
        print(f"\n🔗 DEPENDENCIES:")
        print(f"   ✅ Available: {len(self.results['dependencies']['available'])}")
        if self.results["dependencies"]["missing"]:
            print(f"   ❌ Missing: {len(self.results['dependencies']['missing'])}")
            for missing in self.results["dependencies"]["missing"]:
                print(f"      - {missing}")
        
        print(f"\n📋 SCHEMAS:")
        print(f"   ✅ Valid: {len(self.results['schemas']['valid'])}")
        if self.results["schemas"]["invalid"]:
            print(f"   ❌ Invalid: {len(self.results['schemas']['invalid'])}")
            for invalid in self.results["schemas"]["invalid"]:
                print(f"      - {invalid}")
        
        print(f"\n🚀 APP CREATION:")
        if self.results["app_creation"]["status"] == "success":
            print(f"   ✅ App created successfully")
        else:
            print(f"   ❌ App creation failed")
            if self.results["app_creation"]["error"]:
                print(f"      Error: {self.results['app_creation']['error']}")
        
        # Overall status
        print("\n" + "="*60)
        has_critical_errors = (
            len(self.results["imports"]["failed"]) > 0 or
            len(self.results["endpoints"]["missing"]) > 0 or
            self.results["app_creation"]["status"] != "success"
        )
        
        if has_critical_errors:
            print("❌ VERIFICATION FAILED - Critical issues found")
            print("\nNext steps:")
            print("1. Fix import errors")
            print("2. Ensure all endpoints are registered")
            print("3. Verify app can be created")
            print("4. Run this script again")
        else:
            print("✅ VERIFICATION PASSED - All critical wiring is correct")
            print("\nNext steps:")
            print("1. Run the API server: uvicorn app.main:app --reload")
            print("2. Test endpoints using: python test_api.py")
            print("3. Check API docs at: http://localhost:8000/docs")
        
        print("="*60)
        
        return {
            "results": self.results,
            "errors": self.errors,
            "has_critical_errors": has_critical_errors
        }


def main():
    """Run wiring verification."""
    verifier = WiringVerifier()
    summary = verifier.run_all_checks()
    
    # Exit with error code if critical issues found
    if summary["has_critical_errors"]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

























