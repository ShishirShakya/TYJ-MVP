"""
Compliance verification script - Checks codebase against coding philosophy.

This script verifies compliance with the principles in cp.txt:
- Single Source of Truth (no duplication)
- Error sanitization
- Security audit logging
- Rate limiting availability
- Consistent patterns
"""

import os
import re
import ast
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict


class ComplianceChecker:
    """Check codebase compliance with coding philosophy."""
    
    def __init__(self, root_dir: str = "."):
        self.root_dir = Path(root_dir)
        self.issues: List[Dict[str, any]] = []
        self.stats: Dict[str, int] = defaultdict(int)
    
    def check_ssot_compliance(self) -> List[Dict[str, any]]:
        """Check for code duplication (SSOT violations)."""
        issues = []
        
        # Check for duplicate function definitions
        functions = defaultdict(list)
        
        for py_file in self.root_dir.rglob("*.py"):
            if "test" in str(py_file) or "__pycache__" in str(py_file):
                continue
            
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    tree = ast.parse(content, filename=str(py_file))
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            func_name = node.name
                            if not func_name.startswith("_"):  # Only check public functions
                                functions[func_name].append(str(py_file))
            except Exception:
                pass
        
        # Report potential duplicates
        for func_name, files in functions.items():
            if len(files) > 1:
                # Check if it's a legitimate case (different modules)
                modules = [f.split(os.sep)[-2] if os.sep in f else "root" for f in files]
                if len(set(modules)) < len(files):
                    issues.append({
                        "type": "duplication",
                        "severity": "warning",
                        "message": f"Function '{func_name}' found in multiple files: {files}",
                        "files": files
                    })
        
        return issues
    
    def check_error_sanitization(self) -> List[Dict[str, any]]:
        """Check that error messages are sanitized."""
        issues = []
        error_patterns = [
            r'raise\s+\w+Error\([^)]*str\([^)]*\)',  # Direct error string conversion
            r'f["\'].*\{.*\}.*Error',  # F-strings in error messages
        ]
        
        for py_file in self.root_dir.rglob("*.py"):
            if "test" in str(py_file) or "__pycache__" in str(py_file):
                continue
            
            if "shared/errors.py" in str(py_file):  # Skip SSOT file
                continue
            
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for i, line in enumerate(lines, 1):
                        # Check for direct error exposure (simple heuristic)
                        if "get_sanitized_user_message" in line or "_get_sanitized_user_message" in line:
                            self.stats["sanitized_errors"] += 1
                        elif re.search(r'raise.*Error.*f?["\']', line) and "get_sanitized" not in "".join(lines[max(0, i-5):i+1]):
                            # Potential unsanitized error (needs manual review)
                            if "exam/flow" in str(py_file) or "exam/ui" in str(py_file):
                                issues.append({
                                    "type": "error_sanitization",
                                    "severity": "info",
                                    "message": f"Potential unsanitized error at line {i}",
                                    "file": str(py_file),
                                    "line": i
                                })
            except Exception:
                pass
        
        return issues
    
    def check_rate_limiting_available(self) -> List[Dict[str, any]]:
        """Check that rate limiting module exists and is properly exported."""
        issues = []
        
        rate_limiting_file = self.root_dir / "shared" / "rate_limiting.py"
        if not rate_limiting_file.exists():
            issues.append({
                "type": "rate_limiting",
                "severity": "error",
                "message": "Rate limiting module not found",
                "file": "shared/rate_limiting.py"
            })
        else:
            self.stats["rate_limiting_exists"] = 1
        
        # Check if exported in __init__.py
        init_file = self.root_dir / "shared" / "__init__.py"
        if init_file.exists():
            with open(init_file, "r", encoding="utf-8") as f:
                content = f.read()
                if "rate_limiting" in content or "check_rate_limit" in content:
                    self.stats["rate_limiting_exported"] = 1
                else:
                    issues.append({
                        "type": "rate_limiting",
                        "severity": "warning",
                        "message": "Rate limiting not exported in shared/__init__.py",
                        "file": "shared/__init__.py"
                    })
        
        return issues
    
    def check_security_audit_available(self) -> List[Dict[str, any]]:
        """Check that security audit logging exists."""
        issues = []
        
        security_audit_file = self.root_dir / "shared" / "security_audit.py"
        if not security_audit_file.exists():
            issues.append({
                "type": "security_audit",
                "severity": "error",
                "message": "Security audit module not found",
                "file": "shared/security_audit.py"
            })
        else:
            self.stats["security_audit_exists"] = 1
        
        return issues
    
    def check_todos(self) -> List[Dict[str, any]]:
        """Check for TODO/FIXME comments in production code."""
        issues = []
        
        for py_file in self.root_dir.rglob("*.py"):
            if "test" in str(py_file) or "__pycache__" in str(py_file):
                continue
            if "z-thoughts" in str(py_file):  # Skip docs
                continue
            
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for i, line in enumerate(lines, 1):
                        if re.search(r'\bTODO\b|\bFIXME\b', line, re.IGNORECASE):
                            # Allow "Future enhancement" comments
                            if "future enhancement" not in line.lower():
                                issues.append({
                                    "type": "todo",
                                    "severity": "info",
                                    "message": f"TODO/FIXME found at line {i}",
                                    "file": str(py_file),
                                    "line": i,
                                    "content": line.strip()
                                })
            except Exception:
                pass
        
        return issues
    
    def run_all_checks(self) -> Dict[str, any]:
        """Run all compliance checks."""
        print("Running compliance checks...")
        
        all_issues = []
        all_issues.extend(self.check_ssot_compliance())
        all_issues.extend(self.check_error_sanitization())
        all_issues.extend(self.check_rate_limiting_available())
        all_issues.extend(self.check_security_audit_available())
        all_issues.extend(self.check_todos())
        
        return {
            "issues": all_issues,
            "stats": dict(self.stats),
            "summary": {
                "total_issues": len(all_issues),
                "errors": len([i for i in all_issues if i["severity"] == "error"]),
                "warnings": len([i for i in all_issues if i["severity"] == "warning"]),
                "info": len([i for i in all_issues if i["severity"] == "info"]),
            }
        }


def main():
    """Run compliance verification."""
    checker = ComplianceChecker()
    results = checker.run_all_checks()
    
    print("\n" + "="*60)
    print("COMPLIANCE VERIFICATION RESULTS")
    print("="*60)
    print(f"\nTotal Issues: {results['summary']['total_issues']}")
    print(f"  Errors: {results['summary']['errors']}")
    print(f"  Warnings: {results['summary']['warnings']}")
    print(f"  Info: {results['summary']['info']}")
    
    print(f"\nStatistics:")
    for key, value in results['stats'].items():
        print(f"  {key}: {value}")
    
    if results['issues']:
        print(f"\nIssues Found:")
        for issue in results['issues'][:20]:  # Show first 20
            print(f"  [{issue['severity'].upper()}] {issue['type']}: {issue['message']}")
            if 'file' in issue:
                print(f"    File: {issue['file']}")
        if len(results['issues']) > 20:
            print(f"  ... and {len(results['issues']) - 20} more issues")
    else:
        print("\n✅ No compliance issues found!")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    main()

