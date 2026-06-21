#!/usr/bin/env python3
"""
Script to verify data flow between components
Referenced in CI workflow
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any
import yaml
import requests
import time


class DataFlowChecker:
    def __init__(self, config_path: str = None):
        self.config_path = config_path or "scripts/data_flow_config.yaml"
        self.base_url = "http://localhost:8000"
        self.test_results = []
        
    def load_config(self) -> Dict[str, Any]:
        """Load data flow test configuration"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            # Return default configuration
            return {
                "endpoints": [
                    {
                        "name": "health_check",
                        "path": "/api/v1/health",
                        "method": "GET",
                        "expected_status": 200,
                        "expected_fields": ["status", "timestamp"]
                    },
                    {
                        "name": "system_info",
                        "path": "/api/v1/system/info",
                        "method": "GET",
                        "expected_status": 200,
                        "expected_fields": ["status", "data"]
                    },
                    {
                        "name": "package_search",
                        "path": "/api/v1/packages/search",
                        "method": "GET",
                        "params": {"q": "numpy"},
                        "expected_status": 200,
                        "expected_fields": ["status", "results"]
                    }
                ],
                "data_flows": [
                    {
                        "name": "package_resolution_flow",
                        "steps": [
                            {
                                "endpoint": "package_search",
                                "extract_data": "results.pypi[0].name"
                            },
                            {
                                "endpoint": "package_resolve",
                                "use_data": {"packages": [{"name": "extracted_data", "ecosystem": "pypi"}]}
                            }
                        ]
                    }
                ]
            }
    
    def wait_for_service(self, max_wait: int = 60) -> bool:
        """Wait for the service to be available"""
        print("🔄 Waiting for service to be available...")
        
        for i in range(max_wait):
            try:
                response = requests.get(f"{self.base_url}/api/v1/health", timeout=5)
                if response.status_code == 200:
                    print("✅ Service is available!")
                    return True
            except requests.exceptions.RequestException:
                pass
            
            print(f"⏳ Waiting... ({i+1}/{max_wait})")
            time.sleep(1)
        
        print("❌ Service failed to become available")
        return False
    
    def test_endpoint(self, endpoint_config: Dict[str, Any]) -> Dict[str, Any]:
        """Test a single endpoint"""
        name = endpoint_config["name"]
        path = endpoint_config["path"]
        method = endpoint_config.get("method", "GET")
        params = endpoint_config.get("params", {})
        expected_status = endpoint_config.get("expected_status", 200)
        expected_fields = endpoint_config.get("expected_fields", [])
        
        print(f"🧪 Testing endpoint: {name}")
        
        result = {
            "name": name,
            "success": False,
            "response_time": 0,
            "errors": []
        }
        
        try:
            url = f"{self.base_url}{path}"
            start_time = time.time()
            
            if method.upper() == "GET":
                response = requests.get(url, params=params, timeout=10)
            elif method.upper() == "POST":
                response = requests.post(url, json=params, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            result["response_time"] = time.time() - start_time
            result["status_code"] = response.status_code
            
            # Check status code
            if response.status_code != expected_status:
                result["errors"].append(
                    f"Expected status {expected_status}, got {response.status_code}"
                )
            
            # Check response format
            try:
                response_data = response.json()
                result["response_data"] = response_data
                
                # Check expected fields
                for field in expected_fields:
                    if not self._check_field_exists(response_data, field):
                        result["errors"].append(f"Missing expected field: {field}")
                
            except json.JSONDecodeError:
                result["errors"].append("Response is not valid JSON")
            
            # Mark as successful if no errors
            if not result["errors"]:
                result["success"] = True
                print(f"  ✅ {name} passed ({result['response_time']:.3f}s)")
            else:
                print(f"  ❌ {name} failed: {', '.join(result['errors'])}")
        
        except Exception as e:
            result["errors"].append(f"Request failed: {str(e)}")
            print(f"  ❌ {name} failed: {str(e)}")
        
        return result
    
    def _check_field_exists(self, data: Any, field_path: str) -> bool:
        """Check if a nested field exists in the data"""
        fields = field_path.split('.')
        current = data
        
        for field in fields:
            if isinstance(current, dict) and field in current:
                current = current[field]
            elif isinstance(current, list) and field.isdigit():
                idx = int(field)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return False
            else:
                return False
        
        return True
    
    def test_data_flow(self, flow_config: Dict[str, Any]) -> Dict[str, Any]:
        """Test a complete data flow"""
        name = flow_config["name"]
        steps = flow_config["steps"]
        
        print(f"🔄 Testing data flow: {name}")
        
        result = {
            "name": name,
            "success": False,
            "steps_completed": 0,
            "errors": []
        }
        
        extracted_data = {}
        
        try:
            for i, step in enumerate(steps):
                print(f"  Step {i+1}: {step.get('description', 'Processing...')}")
                
                # Prepare request data
                endpoint_data = step.copy()
                
                # Replace extracted data
                if "use_data" in step:
                    use_data = step["use_data"]
                    for key, value in use_data.items():
                        if value == "extracted_data" and extracted_data:
                            use_data[key] = list(extracted_data.values())[0]
                    endpoint_data["params"] = use_data
                
                # Execute step
                step_result = self.test_endpoint(endpoint_data)
                
                if not step_result["success"]:
                    result["errors"].extend(step_result["errors"])
                    break
                
                # Extract data for next step
                if "extract_data" in step and step_result.get("response_data"):
                    extract_path = step["extract_data"]
                    try:
                        extracted_value = self._extract_data(step_result["response_data"], extract_path)
                        extracted_data[extract_path] = extracted_value
                    except Exception as e:
                        result["errors"].append(f"Failed to extract data: {e}")
                        break
                
                result["steps_completed"] += 1
            
            # Mark as successful if all steps completed
            if result["steps_completed"] == len(steps):
                result["success"] = True
                print(f"  ✅ {name} completed successfully")
            else:
                print(f"  ❌ {name} failed after {result['steps_completed']} steps")
        
        except Exception as e:
            result["errors"].append(f"Data flow failed: {str(e)}")
            print(f"  ❌ {name} failed: {str(e)}")
        
        return result
    
    def _extract_data(self, data: Any, path: str) -> Any:
        """Extract data from response using path notation"""
        fields = path.split('.')
        current = data
        
        for field in fields:
            if isinstance(current, dict):
                current = current[field]
            elif isinstance(current, list):
                if field.isdigit():
                    current = current[int(field)]
                else:
                    # Handle array field access like 'results.pypi[0]'
                    if '[' in field and ']' in field:
                        field_name = field[:field.index('[')]
                        index = int(field[field.index('[')+1:field.index(']')])
                        current = current[field_name][index]
                    else:
                        current = current[field]
            else:
                raise ValueError(f"Cannot access field '{field}' on {type(current)}")
        
        return current
    
    def run_checks(self) -> bool:
        """Run all data flow checks"""
        print("🚀 Starting data flow checks...")
        
        # Wait for service
        if not self.wait_for_service():
            return False
        
        # Load configuration
        config = self.load_config()
        
        # Test individual endpoints
        print("\n📡 Testing individual endpoints...")
        endpoint_results = []
        for endpoint in config.get("endpoints", []):
            result = self.test_endpoint(endpoint)
            endpoint_results.append(result)
            self.test_results.append(result)
        
        # Test data flows
        print("\n🔄 Testing data flows...")
        flow_results = []
        for flow in config.get("data_flows", []):
            result = self.test_data_flow(flow)
            flow_results.append(result)
            self.test_results.append(result)
        
        # Generate summary
        total_tests = len(endpoint_results) + len(flow_results)
        successful_tests = sum(1 for r in self.test_results if r["success"])
        
        print(f"\n📈 Data Flow Check Summary:")
        print(f"  - Total tests: {total_tests}")
        print(f"  - Successful: {successful_tests}")
        print(f"  - Failed: {total_tests - successful_tests}")
        
        # Save detailed results
        with open("data_flow_results.json", "w") as f:
            json.dump(self.test_results, f, indent=2)
        print(f"📄 Detailed results saved to data_flow_results.json")
        
        return successful_tests == total_tests


def main():
    checker = DataFlowChecker()
    success = checker.run_checks()
    
    if success:
        print("✅ All data flow checks passed!")
        sys.exit(0)
    else:
        print("❌ Some data flow checks failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()