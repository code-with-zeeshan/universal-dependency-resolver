# backend/api/routes/system.py
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, Request
from typing import Optional, Dict, List, Tuple, Any
from pydantic import BaseModel, Field
import json
import tempfile
import subprocess
import re
import logging

from backend.core.system_scanner import SystemScanner
from backend.api.dependencies import get_system_scanner, limiter
from backend.api.auth import get_current_user
from backend.database.models import User

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize system scanner
system_scanner = SystemScanner()

# Keep all your existing models
class SystemRequirement(BaseModel):
    type: str  # 'gpu', 'cpu', 'os', 'memory', 'disk', 'python', 'compiler'
    minimum: Optional[Dict[str, Any]] = Field(default_factory=dict)
    recommended: Optional[Dict[str, Any]] = Field(default_factory=dict)
    required: bool = True

class SystemCheckRequest(BaseModel):
    requirements: List[SystemRequirement]
    packages: Optional[List[str]] = None

class EnvironmentAnalysis(BaseModel):
    filename: str
    type: str
    packages: List[Dict[str, Any]]
    system_requirements: Dict[str, Any]
    potential_conflicts: List[Dict[str, Any]]
    estimated_size: Optional[int] = None
    python_version_required: Optional[str] = None

# MOVED FROM main.py - System info endpoint (renamed from /api/system-info)
@router.get("/info")
@limiter.limit("30/minute")
async def get_system_info(
    request: Request,
    scanner: SystemScanner = Depends(get_system_scanner),
    detailed: bool = False,
    current_user: User = Depends(get_current_user)) -> dict:
    """Get current system information"""
    try:
        info = scanner.scan_all()
        
        if not detailed:
            # Return simplified version
            return {
                "status": "success",
                "system": {
                    "os": f"{info['os']['system']} {info['os']['release']}",
                    "cpu": info['cpu']['brand'],
                    "gpu": info['gpu']['devices'][0]['name'] if info['gpu']['available'] else None,
                    "cuda": info['gpu'].get('cuda'),
                    "python": info['runtime_versions']['python']['version']
                }
            }
        
        return {"status": "success", "data": info}
    except ValueError as e:
        logger.error(f"Invalid system scan data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"System scan failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Keep all your existing endpoints exactly as they were
@router.post("/check-compatibility")
@limiter.limit("10/minute")
async def check_system_compatibility(
    request: Request,
    check_request: SystemCheckRequest,
    current_user: User = Depends(get_current_user)) -> dict:
    """Check if system meets specified requirements"""
    try:
        system_info = system_scanner.scan_all()  # Uses the module-level system_scanner
        results = {
            "compatible": True,
            "checks": [],
            "warnings": [],
            "errors": [],
            "recommendations": []
        }
        
        for req in check_request.requirements:
            check_result = _check_requirement_comprehensive(system_info, req)
            results["checks"].append(check_result)
            
            if check_result["status"] == "fail":
                results["compatible"] = False
                results["errors"].append(check_result["message"])
            elif check_result["status"] == "warning":
                results["warnings"].append(check_result["message"])
            
            # Add recommendations
            if "recommendation" in check_result:
                results["recommendations"].append(check_result["recommendation"])
        
        # Check package-specific requirements if provided
        if check_request.packages:
            package_checks = await _check_package_requirements(request.packages, system_info)
            results["package_compatibility"] = package_checks
        
        return {"status": "success", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/gpu/info")
@limiter.limit("30/minute")
async def get_gpu_info(
    request: Request,
    current_user: User = Depends(get_current_user)) -> dict:
    """Get detailed GPU information"""
    try:
        gpu_info = system_scanner.detect_gpu_info()  # Uses the module-level system_scanner
        
        # Add additional GPU details if available
        if gpu_info['available']:
            # Enhanced GPU information gathering
            gpu_info['detailed_info'] = await _get_detailed_gpu_info()
            
            # Check for GPU compute capabilities
            gpu_info['compute_capabilities'] = _check_gpu_compute_capabilities()
            
            # Check for deep learning framework support
            gpu_info['framework_support'] = _check_gpu_framework_support()
        
        return {"status": "success", "gpu": gpu_info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/runtime/{runtime}")
@limiter.limit("30/minute")
async def get_runtime_info(
    request: Request,
    runtime: str,
    current_user: User = Depends(get_current_user)) -> dict:
    """Get information about a specific runtime (python, node, java, etc.)"""
    try:
        runtime_versions = system_scanner.detect_runtime_versions()  # Uses the module-level system_scanner
        
        # Comprehensive runtime detection
        runtime_checkers = {
            'docker': _check_docker,
            'rust': _check_rust,
            'go': _check_go,
            'julia': _check_julia,
            'r': _check_r,
            'dotnet': _check_dotnet,
            'ruby': _check_ruby,
            'php': _check_php,
            'kotlin': _check_kotlin,
            'scala': _check_scala
        }
        
        if runtime not in runtime_versions and runtime in runtime_checkers:
            runtime_info = await runtime_checkers[runtime]()
        elif runtime in runtime_versions:
            runtime_info = runtime_versions[runtime]
            
            # Add additional runtime-specific info
            if runtime == 'python':
                runtime_info['packages'] = await _get_python_packages()
                runtime_info['virtual_env'] = _detect_virtual_env()
            elif runtime == 'node':
                runtime_info['npm_version'] = _get_npm_version()
                runtime_info['global_packages'] = await _get_npm_global_packages()
        else:
            raise HTTPException(status_code=404, detail=f"Runtime {runtime} not found")
        
        return {"status": "success", "runtime": runtime, "info": runtime_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze-environment")
@limiter.limit("5/minute")
async def analyze_environment_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)) -> dict:
    """Analyze an environment file (requirements.txt, package.json, etc.)"""
    try:
        content = await file.read()
        filename = file.filename.lower()
        
        analysis = EnvironmentAnalysis(
            filename=file.filename,
            type="unknown",
            packages=[],
            system_requirements={},
            potential_conflicts=[]
        )
        
        # Route to appropriate parser
        if filename.endswith(('requirements.txt', 'requirements.in', 'requirements-dev.txt')):
            analysis.type = "python"
            analysis.packages = _parse_requirements_txt_comprehensive(content.decode())
            analysis.python_version_required = _extract_python_version_requirement(content.decode())
        elif filename.endswith('pipfile'):
            analysis.type = "python-pipenv"
            analysis.packages = _parse_pipfile(content.decode())
        elif filename.endswith('pipfile.lock'):
            analysis.type = "python-pipenv-lock"
            analysis.packages = _parse_pipfile_lock(content.decode())
        elif filename.endswith('pyproject.toml'):
            analysis.type = "python-poetry"
            analysis.packages = _parse_pyproject_toml(content.decode())
        elif filename.endswith('package.json'):
            analysis.type = "nodejs"
            analysis.packages = _parse_package_json_comprehensive(content.decode())
        elif filename.endswith('package-lock.json'):
            analysis.type = "nodejs-lock"
            analysis.packages = _parse_package_lock_json(content.decode())
        elif filename.endswith('yarn.lock'):
            analysis.type = "nodejs-yarn"
            analysis.packages = _parse_yarn_lock(content.decode())
        elif filename.endswith(('environment.yml', 'environment.yaml')):
            analysis.type = "conda"
            analysis.packages = _parse_conda_env_comprehensive(content.decode())
        elif filename.endswith('cargo.toml'):
            analysis.type = "rust"
            analysis.packages = _parse_cargo_toml_comprehensive(content.decode())
        elif filename.endswith('cargo.lock'):
            analysis.type = "rust-lock"
            analysis.packages = _parse_cargo_lock(content.decode())
        elif filename.endswith('go.mod'):
            analysis.type = "go"
            analysis.packages = _parse_go_mod(content.decode())
        elif filename.endswith('composer.json'):
            analysis.type = "php"
            analysis.packages = _parse_composer_json(content.decode())
        elif filename.endswith('gemfile'):
            analysis.type = "ruby"
            analysis.packages = _parse_gemfile(content.decode())
        
        # Analyze system requirements and conflicts
        analysis = await _analyze_package_requirements(analysis)
        
        # Estimate total installation size
        analysis.estimated_size = await _estimate_installation_size(analysis.packages)
        
        return {"status": "success", "analysis": analysis.dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/benchmarks")
@limiter.limit("30/minute")
async def run_system_benchmarks(
    request: Request,
    comprehensive: bool = False,
    current_user: User = Depends(get_current_user)) -> dict:
    """Run system benchmarks"""
    try:
        benchmarks = {}
        
        # Basic benchmarks
        benchmarks['cpu'] = await _benchmark_cpu()
        benchmarks['memory'] = _benchmark_memory()
        benchmarks['disk'] = await _benchmark_disk()
        
        # GPU benchmark if available
        system_info = system_scanner.scan_all()
        if system_info['gpu']['available']:
            benchmarks['gpu'] = await _benchmark_gpu()
        
        if comprehensive:
            # Additional comprehensive benchmarks
            benchmarks['network'] = await _benchmark_network()
            benchmarks['python'] = await _benchmark_python()
            
            # Multi-core CPU benchmark
            benchmarks['cpu_multicore'] = await _benchmark_cpu_multicore()
        
        # Compare with typical values
        benchmarks['comparison'] = _compare_benchmark_results(benchmarks)
        
        return {"status": "success", "benchmarks": benchmarks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _check_requirement_comprehensive(system_info: Dict[str, Any], requirement: SystemRequirement) -> Dict[str, Any]:
    """Comprehensively check if system meets a specific requirement"""
    result = {
        "type": requirement.type,
        "status": "pass",
        "message": "",
        "details": {}
    }
    
    if requirement.type == "gpu":
        result.update(_check_gpu_requirement(system_info, requirement))
    
    elif requirement.type == "cpu":
        result.update(_check_cpu_requirement(system_info, requirement))
    
    elif requirement.type == "memory":
        result.update(_check_memory_requirement(system_info, requirement))
    
    elif requirement.type == "disk":
        result.update(_check_disk_requirement(system_info, requirement))
    
    elif requirement.type == "os":
        result.update(_check_os_requirement(system_info, requirement))
    
    elif requirement.type == "python":
        result.update(_check_python_requirement(system_info, requirement))
    
    elif requirement.type == "compiler":
        result.update(_check_compiler_requirement(system_info, requirement))
    
    return result

def _check_gpu_requirement(system_info: Dict[str, Any], requirement: SystemRequirement) -> Dict[str, Any]:
    """Check GPU requirements"""
    result = {"details": {}}
    
    if not system_info['gpu']['available']:
        if requirement.required:
            result["status"] = "fail"
            result["message"] = "GPU required but not available"
        else:
            result["status"] = "warning"
            result["message"] = "GPU recommended but not available"
        return result
    
    # Check CUDA version
    if requirement.minimum and "cuda" in requirement.minimum:
        required_cuda = requirement.minimum['cuda']
        system_cuda = system_info['gpu'].get('cuda')
        
        if not system_cuda:
            result["status"] = "fail"
            result["message"] = f"CUDA {required_cuda} required but not installed"
            result["recommendation"] = f"Install CUDA {required_cuda} or later"
        else:
            from packaging import version
            if version.parse(system_cuda) < version.parse(required_cuda):
                result["status"] = "fail"
                result["message"] = f"CUDA {required_cuda} required, but {system_cuda} found"
                result["recommendation"] = f"Update CUDA to version {required_cuda} or later"
    
    # Check GPU memory
    if requirement.minimum and "memory_gb" in requirement.minimum:
        required_memory = requirement.minimum['memory_gb']
        # Get GPU memory from devices
        min_gpu_memory = min(
            device.get('memory_mb', 0) / 1024 
            for device in system_info['gpu'].get('devices', [])
        )
        
        if min_gpu_memory < required_memory:
            result["status"] = "fail"
            result["message"] = f"GPU with {required_memory}GB memory required, but only {min_gpu_memory:.1f}GB available"
    
    # Check compute capability
    if requirement.minimum and "compute_capability" in requirement.minimum:
        required_cc = requirement.minimum['compute_capability']
        # This would need to be extracted from GPU info
        result["details"]["compute_capability_check"] = "pending"
    
    return result

def _check_cpu_requirement(system_info: Dict[str, Any], requirement: SystemRequirement) -> Dict[str, Any]:
    """Check CPU requirements"""
    result = {"details": {}}
    
    cpu_info = system_info['cpu']
    
    # Check core count
    if requirement.minimum and "cores" in requirement.minimum:
        required_cores = requirement.minimum['cores']
        available_cores = cpu_info.get('physical_cores', 0)
        
        if available_cores < required_cores:
            result["status"] = "fail"
            result["message"] = f"Requires {required_cores} CPU cores, but only {available_cores} available"
    
    # Check CPU features
    if requirement.minimum and "features" in requirement.minimum:
        required_features = requirement.minimum['features']
        cpu_flags = cpu_info.get('flags', [])
        
        missing_features = [f for f in required_features if f not in cpu_flags]
        if missing_features:
            result["status"] = "fail"
            result["message"] = f"CPU missing required features: {', '.join(missing_features)}"
    
    # Check architecture
    if requirement.minimum and "architecture" in requirement.minimum:
        required_arch = requirement.minimum['architecture']
        system_arch = cpu_info.get('architecture')
        
        if not _is_compatible_architecture(system_arch, required_arch):
            result["status"] = "fail"
            result["message"] = f"Requires {required_arch} architecture, but system is {system_arch}"
    
    return result

def _check_memory_requirement(system_info: Dict[str, Any], requirement: SystemRequirement) -> Dict[str, Any]:
    """Check memory requirements"""
    import psutil
    result = {"details": {}}
    
    memory = psutil.virtual_memory()
    available_gb = memory.total / (1024**3)
    
    if requirement.minimum and "gb" in requirement.minimum:
        required_gb = requirement.minimum['gb']
        
        if available_gb < required_gb:
            result["status"] = "fail"
            result["message"] = f"Requires {required_gb}GB RAM, but only {available_gb:.1f}GB available"
            result["recommendation"] = "Consider closing other applications or upgrading system memory"
    
    if requirement.recommended and "gb" in requirement.recommended:
        recommended_gb = requirement.recommended['gb']
        
        if available_gb < recommended_gb:
            result["status"] = "warning"
            result["message"] = f"Recommended {recommended_gb}GB RAM, but only {available_gb:.1f}GB available"
    
    # Check available memory
    available_free_gb = memory.available / (1024**3)
    if available_free_gb < 2:  # Less than 2GB free
        result["status"] = "warning"
        result["message"] = f"Low available memory: {available_free_gb:.1f}GB free"
    
    return result

def _check_disk_requirement(system_info: Dict[str, Any], requirement: SystemRequirement) -> Dict[str, Any]:
    """Check disk space requirements"""
    import psutil
    result = {"details": {}}
    
    disk = psutil.disk_usage('/')
    available_gb = disk.free / (1024**3)
    
    if requirement.minimum and "gb" in requirement.minimum:
        required_gb = requirement.minimum['gb']
        
        if available_gb < required_gb:
            result["status"] = "fail"
            result["message"] = f"Requires {required_gb}GB disk space, but only {available_gb:.1f}GB available"
    
    # Check disk type (SSD vs HDD)
    if requirement.minimum and "type" in requirement.minimum:
        required_type = requirement.minimum['type']
        # This would need platform-specific implementation
        result["details"]["disk_type_check"] = "pending"
    
    return result

def _check_os_requirement(system_info: Dict[str, Any], requirement: SystemRequirement) -> Dict[str, Any]:
    """Check OS requirements"""
    result = {"details": {}}
    
    os_info = system_info['os']
    
    if requirement.minimum and "name" in requirement.minimum:
        required_os = requirement.minimum['name'].lower()
        system_os = os_info['system'].lower()
        
        if not _is_compatible_os(system_os, required_os):
            result["status"] = "fail"
            result["message"] = f"Requires {required_os}, but system is {system_os}"
    
    if requirement.minimum and "version" in requirement.minimum:
        required_version = requirement.minimum['version']
        system_version = os_info.get('release', '')
        
        if not _is_compatible_os_version(system_os, system_version, required_version):
            result["status"] = "fail"
            result["message"] = f"Requires {system_os} {required_version}, but system is {system_version}"
    
    return result

def _check_python_requirement(system_info: Dict[str, Any], requirement: SystemRequirement) -> Dict[str, Any]:
    """Check Python requirements"""
    result = {"details": {}}
    
    python_info = system_info['runtime_versions'].get('python', {})
    
    if requirement.minimum and "version" in requirement.minimum:
        required_version = requirement.minimum['version']
        system_version = python_info.get('version', '')
        
        from packaging import version
        if not system_version or version.parse(system_version) < version.parse(required_version):
            result["status"] = "fail"
            result["message"] = f"Requires Python {required_version}, but system has {system_version}"
    
    return result

def _check_compiler_requirement(system_info: Dict[str, Any], requirement: SystemRequirement) -> Dict[str, Any]:
    """Check compiler requirements"""
    result = {"details": {}}
    
    if requirement.minimum:
        for compiler, version in requirement.minimum.items():
            installed_version = _get_compiler_version(compiler)
            
            if not installed_version:
                result["status"] = "fail"
                result["message"] = f"{compiler} compiler required but not found"
                result["recommendation"] = f"Install {compiler} {version} or later"
            elif version and not _is_compatible_version(installed_version, version):
                result["status"] = "fail"
                result["message"] = f"{compiler} {version} required, but {installed_version} found"
    
    return result

def _parse_requirements_txt_comprehensive(content: str) -> List[Dict[str, Any]]:
    """Comprehensive parsing of requirements.txt"""
    packages = []
    current_line_num = 0
    
    try:
        from packaging.requirements import Requirement
        from packaging.markers import Marker
    except ImportError:
        # Fallback to basic parsing
        return _parse_requirements_txt_basic(content)
    
    for line in content.split('\n'):
        current_line_num += 1
        line = line.strip()
        
        # Skip comments and empty lines
        if not line or line.startswith('#'):
            continue
        
        # Handle -r (include another requirements file)
        if line.startswith('-r '):
            packages.append({
                "type": "include",
                "file": line[3:].strip(),
                "line": current_line_num
            })
            continue
        
        # Handle -e (editable installs)
        if line.startswith('-e '):
            packages.append({
                "type": "editable",
                "path": line[3:].strip(),
                "line": current_line_num
            })
            continue
        
        # Handle index URLs
        if line.startswith(('-i ', '--index-url', '-f', '--find-links')):
            continue
        
        try:
            # Parse with packaging library
            req = Requirement(line)
            
            package_info = {
                "name": req.name,
                "version": str(req.specifier) if req.specifier else "*",
                "line": current_line_num
            }
            
            # Parse extras
            if req.extras:
                package_info["extras"] = list(req.extras)
            
            # Parse markers (environment markers)
            if req.marker:
                package_info["marker"] = str(req.marker)
                package_info["conditional"] = True
            
            # Parse URL requirements
            if req.url:
                package_info["url"] = req.url
            
            packages.append(package_info)
            
        except Exception as e:
            # Fallback parsing for non-standard formats
            packages.append({
                "name": line,
                "version": "*",
                "line": current_line_num,
                "parse_error": str(e)
            })
    
    return packages

def _parse_requirements_txt_basic(content: str) -> List[Dict[str, Any]]:
    """Basic requirements.txt parsing fallback"""
    packages = []
    
    for line in content.split('\n'):
        line = line.strip()
        if line and not line.startswith('#'):
            # Handle different operators
            for op in ['==', '>=', '<=', '>', '<', '~=', '!=']:
                if op in line:
                    name, version = line.split(op, 1)
                    packages.append({
                        "name": name.strip(),
                        "version": f"{op}{version.strip()}"
                    })
                    break
            else:
                # No version specifier
                packages.append({"name": line, "version": "*"})
    
    return packages

def _parse_pipfile(content: str) -> List[Dict[str, Any]]:
    """Parse Pipfile"""
    try:
        import toml
        data = toml.loads(content)
        packages = []
        
        for section in ['packages', 'dev-packages']:
            if section in data:
                for name, spec in data[section].items():
                    package_info = {"name": name, "dev": section == 'dev-packages'}
                    
                    if isinstance(spec, str):
                        package_info["version"] = spec
                    elif isinstance(spec, dict):
                        if 'version' in spec:
                            package_info["version"] = spec['version']
                        if 'git' in spec:
                            package_info["git"] = spec['git']
                        if 'path' in spec:
                            package_info["path"] = spec['path']
                        if 'editable' in spec:
                            package_info["editable"] = spec['editable']
                    
                    packages.append(package_info)
        
        return packages
    except Exception:
        return []

def _parse_pipfile_lock(content: str) -> List[Dict[str, Any]]:
    """Parse Pipfile.lock"""
    try:
        data = json.loads(content)
        packages = []
        
        for section in ['default', 'develop']:
            if section in data:
                for name, info in data[section].items():
                    package_info = {
                        "name": name,
                        "version": info.get('version', '*'),
                        "dev": section == 'develop'
                    }
                    
                    if 'hashes' in info:
                        package_info["hashes"] = info['hashes']
                    
                    packages.append(package_info)
        
        return packages
    except Exception:
        return []

def _parse_pyproject_toml(content: str) -> List[Dict[str, Any]]:
    """Parse pyproject.toml (Poetry/PEP 517)"""
    try:
        import toml
        data = toml.loads(content)
        packages = []
        
        # Poetry format
        if 'tool' in data and 'poetry' in data['tool']:
            poetry = data['tool']['poetry']
            
            for section in ['dependencies', 'dev-dependencies']:
                if section in poetry:
                    for name, spec in poetry[section].items():
                        if name == 'python':  # Skip Python version constraint
                            continue
                        
                        package_info = {"name": name, "dev": 'dev' in section}
                        
                        if isinstance(spec, str):
                            package_info["version"] = spec
                        elif isinstance(spec, dict):
                            if 'version' in spec:
                                package_info["version"] = spec['version']
                            if 'git' in spec:
                                package_info["git"] = spec['git']
                            if 'extras' in spec:
                                package_info["extras"] = spec['extras']
                        
                        packages.append(package_info)
        
        # PEP 517 format
        elif 'project' in data:
            project = data['project']
            
            if 'dependencies' in project:
                for dep in project['dependencies']:
                    # Parse PEP 508 dependency specification
                    packages.append(_parse_pep508_dependency(dep))
            
            if 'optional-dependencies' in project:
                for extra, deps in project['optional-dependencies'].items():
                    for dep in deps:
                        pkg = _parse_pep508_dependency(dep)
                        pkg['extra'] = extra
                        packages.append(pkg)
        
        return packages
    except Exception:
        return []

def _parse_pep508_dependency(dep_str: str) -> Dict[str, Any]:
    """Parse PEP 508 dependency specification"""
    try:
        from packaging.requirements import Requirement
        req = Requirement(dep_str)
        
        return {
            "name": req.name,
            "version": str(req.specifier) if req.specifier else "*",
            "extras": list(req.extras) if req.extras else None,
            "marker": str(req.marker) if req.marker else None
        }
    except:
        # Basic fallback
        if '>' in dep_str or '<' in dep_str or '=' in dep_str:
            for op in ['>=', '<=', '==', '>', '<', '~=']:
                if op in dep_str:
                    name, version = dep_str.split(op, 1)
                    return {"name": name.strip(), "version": f"{op}{version.strip()}"}
        
        return {"name": dep_str, "version": "*"}

def _parse_package_json_comprehensive(content: str) -> List[Dict[str, Any]]:
    """Comprehensive package.json parsing"""
    try:
        data = json.loads(content)
        packages = []
        
        # Parse different dependency sections
        dep_sections = [
            ('dependencies', False, False),
            ('devDependencies', True, False),
            ('peerDependencies', False, True),
            ('optionalDependencies', False, False),
            ('bundledDependencies', False, False)
        ]
        
        for section, is_dev, is_peer in dep_sections:
            if section in data:
                deps = data[section]
                
                if isinstance(deps, dict):
                    for name, version in deps.items():
                        package_info = {
                            "name": name,
                            "version": version,
                            "dev": is_dev,
                            "peer": is_peer
                        }
                        
                        # Parse version types
                        if version.startswith('file:'):
                            package_info["type"] = "file"
                            package_info["path"] = version[5:]
                        elif version.startswith('git'):
                            package_info["type"] = "git"
                            package_info["url"] = version
                        elif version.startswith('npm:'):
                            package_info["type"] = "alias"
                            package_info["alias"] = version[4:]
                        
                        packages.append(package_info)
                
                elif isinstance(deps, list) and section == 'bundledDependencies':
                    for name in deps:
                        packages.append({
                            "name": name,
                            "bundled": True
                        })
        
        # Extract engines (Node.js version requirements)
        if 'engines' in data:
            for engine, version in data['engines'].items():
                packages.append({
                    "type": "engine",
                    "name": engine,
                    "version": version
                })
        
        return packages
    except Exception:
        return []

def _parse_package_lock_json(content: str) -> List[Dict[str, Any]]:
    """Parse package-lock.json"""
    try:
        data = json.loads(content)
        packages = []
        
        # npm v7+ format
        if 'packages' in data:
            for path, info in data['packages'].items():
                if path == "":  # Root package
                    continue
                
                name = path.split('node_modules/')[-1]
                packages.append({
                    "name": name,
                    "version": info.get('version', '*'),
                    "resolved": info.get('resolved'),
                    "integrity": info.get('integrity'),
                    "dev": info.get('dev', False),
                    "optional": info.get('optional', False)
                })
        
        # npm v6 format
        elif 'dependencies' in data:
            def parse_deps(deps, dev=False):
                for name, info in deps.items():
                    packages.append({
                        "name": name,
                        "version": info.get('version', '*'),
                        "resolved": info.get('resolved'),
                        "integrity": info.get('integrity'),
                        "dev": dev or info.get('dev', False)
                    })
                    
                    # Nested dependencies
                    if 'dependencies' in info:
                        parse_deps(info['dependencies'], dev)
            
            parse_deps(data['dependencies'])
        
        return packages
    except Exception:
        return []

def _parse_yarn_lock(content: str) -> List[Dict[str, Any]]:
    """Parse yarn.lock"""
    packages = []
    current_package = None
    
    for line in content.split('\n'):
        line = line.strip()
        
        # Package declaration
        if line and not line.startswith(' ') and '@' in line:
            # Extract package name and version constraint
            parts = line.rstrip(':').split(', ')
            for part in parts:
                if '@' in part:
                    # Handle scoped packages
                    if part.startswith('@'):
                        at_count = part.count('@')
                        if at_count == 2:
                            name, version = part.rsplit('@', 1)
                        else:
                            name = part
                            version = '*'
                    else:
                        name, version = part.rsplit('@', 1)
                    
                    current_package = {
                        "name": name.strip('"'),
                        "requested_version": version.strip('"')
                    }
        
        # Version line
        elif line.startswith('version') and current_package:
            version = line.split('"')[1]
            current_package["version"] = version
            packages.append(current_package)
            current_package = None
    
    return packages

def _parse_conda_env_comprehensive(content: str) -> List[Dict[str, Any]]:
    """Comprehensive conda environment.yml parsing"""
    try:
        import yaml
        data = yaml.safe_load(content)
        packages = []
        
        if 'dependencies' in data:
            for dep in data['dependencies']:
                if isinstance(dep, str):
                    # Conda package
                    package_info = _parse_conda_dependency(dep)
                    package_info["manager"] = "conda"
                    packages.append(package_info)
                
                elif isinstance(dep, dict):
                    # Can contain pip dependencies
                    if 'pip' in dep:
                        for pip_dep in dep['pip']:
                            package_info = _parse_pip_dependency(pip_dep)
                            package_info["manager"] = "pip"
                            packages.append(package_info)
                    
                    # Other package managers (rare but possible)
                    for manager, deps in dep.items():
                        if manager != 'pip' and isinstance(deps, list):
                            for d in deps:
                                packages.append({
                                    "name": d,
                                    "manager": manager
                                })
        
        # Extract channels
        if 'channels' in data:
            channels = data['channels']
            # Add channel info to packages if needed
        
        # Extract other metadata
        if 'prefix' in data:
            # Environment location
            pass
        
        return packages
    except Exception:
        return []

def _parse_conda_dependency(dep: str) -> Dict[str, Any]:
    """Parse conda dependency string"""
    # Handle different conda dependency formats
    # package
    # package=version
    # package=version=build
    # package>=version
    
    if '=' in dep:
        if dep.count('=') == 2:
            # package=version=build
            name, version, build = dep.split('=')
            return {"name": name, "version": version, "build": build}
        elif '>' in dep or '<' in dep or '!' in dep:
            # Handle >=, <=, etc.
            for op in ['>=', '<=', '==', '!=', '>', '<']:
                if op in dep:
                    name, version = dep.split(op)
                    return {"name": name, "version": f"{op}{version}"}
        else:
            # package=version
            name, version = dep.split('=', 1)
            return {"name": name, "version": version}
    else:
        return {"name": dep, "version": "*"}

def _parse_pip_dependency(dep: str) -> Dict[str, Any]:
    """Parse pip dependency from conda env"""
    # Reuse the PEP 508 parser
    return _parse_pep508_dependency(dep)

def _parse_cargo_toml_comprehensive(content: str) -> List[Dict[str, Any]]:
    """Comprehensive Cargo.toml parsing"""
    try:
        import toml
        data = toml.loads(content)
        packages = []
        
        # Parse different dependency sections
        dep_sections = ['dependencies', 'dev-dependencies', 'build-dependencies']
        
        for section in dep_sections:
            if section in data:
                for name, spec in data[section].items():
                    package_info = {
                        "name": name,
                        "dev": 'dev' in section,
                        "build": 'build' in section
                    }
                    
                    if isinstance(spec, str):
                        package_info["version"] = spec
                    elif isinstance(spec, dict):
                        if 'version' in spec:
                            package_info["version"] = spec['version']
                        if 'git' in spec:
                            package_info["git"] = spec['git']
                            if 'branch' in spec:
                                package_info["branch"] = spec['branch']
                            if 'tag' in spec:
                                package_info["tag"] = spec['tag']
                        if 'path' in spec:
                            package_info["path"] = spec['path']
                        if 'features' in spec:
                            package_info["features"] = spec['features']
                        if 'optional' in spec:
                            package_info["optional"] = spec['optional']
                    
                    packages.append(package_info)
        
        # Parse target-specific dependencies
        if 'target' in data:
            for target, target_data in data['target'].items():
                for section in dep_sections:
                    if section in target_data:
                        for name, spec in target_data[section].items():
                            package_info = {
                                "name": name,
                                "target": target,
                                "dev": 'dev' in section
                            }
                            
                            if isinstance(spec, str):
                                package_info["version"] = spec
                            elif isinstance(spec, dict):
                                package_info["version"] = spec.get('version', '*')
                            
                            packages.append(package_info)
        
        return packages
    except Exception:
        return []

def _parse_cargo_lock(content: str) -> List[Dict[str, Any]]:
    """Parse Cargo.lock"""
    try:
        import toml
        data = toml.loads(content)
        packages = []
        
        if 'package' in data:
            for pkg in data['package']:
                package_info = {
                    "name": pkg.get('name'),
                    "version": pkg.get('version'),
                    "source": pkg.get('source'),
                    "checksum": pkg.get('checksum')
                }
                
                if 'dependencies' in pkg:
                    package_info["dependencies"] = pkg['dependencies']
                
                packages.append(package_info)
        
        return packages
    except Exception:
        return []

def _parse_go_mod(content: str) -> List[Dict[str, Any]]:
    """Parse go.mod"""
    packages = []
    
    for line in content.split('\n'):
        line = line.strip()
        
        if line.startswith('require'):
            # Start of require block
            in_require_block = True
        elif line.startswith('replace'):
            # Handle replace directives
            pass
        elif line and not line.startswith('//'):
            # Parse module lines
            parts = line.split()
            if len(parts) >= 2 and '.' in parts[0]:
                packages.append({
                    "name": parts[0],
                    "version": parts[1],
                    "indirect": 'indirect' in line
                })
    
    return packages

def _parse_composer_json(content: str) -> List[Dict[str, Any]]:
    """Parse composer.json (PHP)"""
    try:
        data = json.loads(content)
        packages = []
        
        for section in ['require', 'require-dev']:
            if section in data:
                for name, version in data[section].items():
                    if name == 'php':  # PHP version constraint
                        continue
                    
                    packages.append({
                        "name": name,
                        "version": version,
                        "dev": 'dev' in section
                    })
        
        return packages
    except Exception:
        return []

def _parse_gemfile(content: str) -> List[Dict[str, Any]]:
    """Parse Gemfile (Ruby)"""
    packages = []
    
    for line in content.split('\n'):
        line = line.strip()
        
        if line.startswith('gem '):
            # Parse gem declaration
            parts = re.findall(r'["\']([^"\']+)["\']', line)
            if parts:
                package_info = {"name": parts[0]}
                
                if len(parts) > 1:
                    package_info["version"] = parts[1]
                
                # Check for groups
                group_match = re.search(r':group\s*=>\s*:(\w+)', line)
                if group_match:
                    package_info["group"] = group_match.group(1)
                
                packages.append(package_info)
    
    return packages

def _extract_python_version_requirement(content: str) -> Optional[str]:
    """Extract Python version requirement from requirements.txt"""
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('#') and 'python' in line.lower():
            # Look for patterns like "# Requires Python >= 3.8"
            match = re.search(r'python\s*([><=]+)\s*([\d.]+)', line, re.I)
            if match:
                return f"{match.group(1)}{match.group(2)}"
    
    return None

async def _analyze_package_requirements(analysis: EnvironmentAnalysis) -> EnvironmentAnalysis:
    """Analyze packages for system requirements and conflicts"""
    
    # Known packages with special requirements
    gpu_packages = {
        'tensorflow-gpu', 'torch', 'pytorch', 'jax', 'cupy',
        'mxnet', 'paddle', 'tensorrt', 'onnxruntime-gpu'
    }
    
    large_memory_packages = {
        'tensorflow', 'pytorch', 'scipy', 'pandas', 'dask',
        'ray', 'spark', 'h2o'
    }
    
    compiler_packages = {
        'numpy', 'scipy', 'scikit-learn', 'matplotlib',
        'pillow', 'opencv-python'
    }
    
    # Analyze packages
    for package in analysis.packages:
        pkg_name = package.get('name', '').lower()
        
        # Check for GPU requirements
        if any(gpu_pkg in pkg_name for gpu_pkg in gpu_packages):
            analysis.system_requirements['gpu'] = {
                'required': True,
                'cuda': 'recommended'
            }
        
        # Check for memory requirements
        if pkg_name in large_memory_packages:
            current_mem = analysis.system_requirements.get('memory', {}).get('minimum_gb', 4)
            analysis.system_requirements['memory'] = {
                'minimum_gb': max(current_mem, 8),
                'recommended_gb': max(current_mem * 1.5, 16)
            }
        
        # Check for compiler requirements
        if pkg_name in compiler_packages:
            analysis.system_requirements['compiler'] = {
                'c': True,
                'cpp': True
            }
    
    # Check for known conflicts
    analysis.potential_conflicts = _detect_package_conflicts(analysis.packages)
    
    return analysis

def _detect_package_conflicts(packages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect potential package conflicts"""
    conflicts = []
    
    # Known conflicting packages
    conflict_groups = [
        ['tensorflow', 'tensorflow-gpu'],
        ['pillow', 'pil'],
        ['opencv-python', 'opencv-contrib-python'],
    ]
    
    package_names = {pkg['name'].lower() for pkg in packages}
    
    for group in conflict_groups:
        found = [pkg for pkg in group if pkg in package_names]
        if len(found) > 1:
            conflicts.append({
                "packages": found,
                "reason": "These packages may conflict with each other"
            })
    
    return conflicts

async def _estimate_installation_size(packages: List[Dict[str, Any]]) -> int:
    """Estimate total installation size in MB"""
    # This would ideally fetch actual package sizes
    # For now, use rough estimates
    
    size_estimates = {
        'tensorflow': 500,
        'pytorch': 750,
        'torch': 750,
        'scipy': 150,
        'numpy': 50,
        'pandas': 100,
        'matplotlib': 200,
        'opencv': 300,
        'scikit-learn': 100
    }
    
    total_size = 0
    
    for package in packages:
        pkg_name = package.get('name', '').lower()
        
        # Check for known packages
        for known_pkg, size in size_estimates.items():
            if known_pkg in pkg_name:
                total_size += size
                break
        else:
            # Default estimate
            total_size += 10
    
    return total_size

async def _get_detailed_gpu_info() -> List[Dict[str, Any]]:
    """Get detailed GPU information using nvidia-smi"""
    gpu_details = []
    
    try:
        # Query multiple GPU properties
        result = subprocess.run(
            [
                'nvidia-smi', 
                '--query-gpu=index,name,driver_version,vbios_version,memory.total,'
                'memory.free,memory.used,temperature.gpu,utilization.gpu,'
                'utilization.memory,power.draw,power.limit,compute_mode,compute_cap',
                '--format=csv,noheader,nounits'
            ],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 14:
                    gpu_details.append({
                        'index': int(parts[0]),
                        'name': parts[1],
                        'driver_version': parts[2],
                        'vbios_version': parts[3],
                        'memory': {
                            'total_mb': int(float(parts[4])),
                            'free_mb': int(float(parts[5])),
                            'used_mb': int(float(parts[6]))
                        },
                        'temperature_celsius': int(parts[7]) if parts[7] != 'N/A' else None,
                        'utilization': {
                            'gpu_percent': int(parts[8]) if parts[8] != 'N/A' else 0,
                            'memory_percent': int(parts[9]) if parts[9] != 'N/A' else 0
                        },
                        'power': {
                            'draw_watts': float(parts[10]) if parts[10] != 'N/A' else None,
                            'limit_watts': float(parts[11]) if parts[11] != 'N/A' else None
                        },
                        'compute_mode': parts[12],
                        'compute_capability': parts[13]
                    })
    except Exception as e:
        pass
    
    return gpu_details

def _check_gpu_compute_capabilities() -> Dict[str, Any]:
    """Check GPU compute capabilities for various frameworks"""
    capabilities = {}
    
    try:
        import torch
        if torch.cuda.is_available():
            capabilities['pytorch'] = {
                'available': True,
                'cuda_version': torch.version.cuda,
                'cudnn_version': torch.backends.cudnn.version(),
                'device_count': torch.cuda.device_count()
            }
    except ImportError:
        capabilities['pytorch'] = {'available': False}
    
    try:
        import tensorflow as tf
        gpus = tf.config.list_physical_devices('GPU')
        capabilities['tensorflow'] = {
            'available': len(gpus) > 0,
            'device_count': len(gpus)
        }
    except ImportError:
        capabilities['tensorflow'] = {'available': False}
    
    return capabilities

def _check_gpu_framework_support() -> Dict[str, Any]:
    """Check which deep learning frameworks can use the GPU"""
    support = {}
    
    frameworks = {
        'pytorch': 'torch',
        'tensorflow': 'tensorflow',
        'jax': 'jax',
        'mxnet': 'mxnet',
        'paddlepaddle': 'paddle'
    }
    
    for name, module in frameworks.items():
        try:
            __import__(module)
            support[name] = True
        except ImportError:
            support[name] = False
    
    return support

async def _check_docker() -> Dict[str, Any]:
    """Check Docker installation and version"""
    try:
        result = subprocess.run(
            ['docker', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            version_output = result.stdout.strip()
            
            # Get more Docker info
            info_result = subprocess.run(
                ['docker', 'info', '--format', '{{json .}}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            docker_info = {'version': version_output, 'available': True}
            
            if info_result.returncode == 0:
                import json
                info_data = json.loads(info_result.stdout)
                docker_info.update({
                    'server_version': info_data.get('ServerVersion'),
                    'storage_driver': info_data.get('Driver'),
                    'containers': info_data.get('Containers', 0),
                    'images': info_data.get('Images', 0)
                })
            
            return docker_info
    except Exception:
        pass
    
    return {'available': False}

async def _check_rust() -> Dict[str, Any]:
    """Check Rust installation"""
    rust_info = {'available': False}
    
    try:
        # Check rustc
        rustc_result = subprocess.run(
            ['rustc', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if rustc_result.returncode == 0:
            rust_info['rustc'] = rustc_result.stdout.strip()
            rust_info['available'] = True
        
        # Check cargo
        cargo_result = subprocess.run(
            ['cargo', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if cargo_result.returncode == 0:
            rust_info['cargo'] = cargo_result.stdout.strip()
        
        # Check installed toolchains
        toolchain_result = subprocess.run(
            ['rustup', 'toolchain', 'list'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if toolchain_result.returncode == 0:
            rust_info['toolchains'] = toolchain_result.stdout.strip().split('\n')
        
    except Exception:
        pass
    
    return rust_info

async def _check_go() -> Dict[str, Any]:
    """Check Go installation"""
    try:
        result = subprocess.run(
            ['go', 'version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            version_output = result.stdout.strip()
            
            # Get GOPATH and GOROOT
            env_result = subprocess.run(
                ['go', 'env', 'GOPATH', 'GOROOT'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            go_info = {'version': version_output, 'available': True}
            
            if env_result.returncode == 0:
                lines = env_result.stdout.strip().split('\n')
                if len(lines) >= 2:
                    go_info['GOPATH'] = lines[0]
                    go_info['GOROOT'] = lines[1]
            
            return go_info
    except Exception:
        pass
    
    return {'available': False}

async def _check_julia() -> Dict[str, Any]:
    """Check Julia installation"""
    try:
        result = subprocess.run(
            ['julia', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            return {
                'version': result.stdout.strip(),
                'available': True
            }
    except Exception:
        pass
    
    return {'available': False}

async def _check_r() -> Dict[str, Any]:
    """Check R installation"""
    try:
        result = subprocess.run(
            ['R', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # Extract version from output
            lines = result.stdout.strip().split('\n')
            version_line = lines[0] if lines else ''
            
            return {
                'version': version_line,
                'available': True
            }
    except Exception:
        pass
    
    return {'available': False}

async def _check_dotnet() -> Dict[str, Any]:
    """Check .NET installation"""
    try:
        result = subprocess.run(
            ['dotnet', '--info'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            info = {'available': True}
            
            # Parse .NET info
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if 'Version:' in line:
                    info['version'] = line.split('Version:')[1].strip()
                    break
            
            # List SDKs
            sdk_result = subprocess.run(
                ['dotnet', '--list-sdks'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if sdk_result.returncode == 0:
                info['sdks'] = sdk_result.stdout.strip().split('\n')
            
            return info
    except Exception:
        pass
    
    return {'available': False}

async def _check_ruby() -> Dict[str, Any]:
    """Check Ruby installation"""
    try:
        result = subprocess.run(
            ['ruby', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            ruby_info = {
                'version': result.stdout.strip(),
                'available': True
            }
            
            # Check gem
            gem_result = subprocess.run(
                ['gem', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if gem_result.returncode == 0:
                ruby_info['gem_version'] = gem_result.stdout.strip()
            
            return ruby_info
    except Exception:
        pass
    
    return {'available': False}

async def _check_php() -> Dict[str, Any]:
    """Check PHP installation"""
    try:
        result = subprocess.run(
            ['php', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            php_info = {
                'version': result.stdout.strip().split('\n')[0],
                'available': True
            }
            
            # Check composer
            composer_result = subprocess.run(
                ['composer', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if composer_result.returncode == 0:
                php_info['composer_version'] = composer_result.stdout.strip()
            
            return php_info
    except Exception:
        pass
    
    return {'available': False}

async def _check_kotlin() -> Dict[str, Any]:
    """Check Kotlin installation"""
    try:
        result = subprocess.run(
            ['kotlin', '-version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            return {
                'version': result.stdout.strip(),
                'available': True
            }
    except Exception:
        pass
    
    return {'available': False}

async def _check_scala() -> Dict[str, Any]:
    """Check Scala installation"""
    try:
        result = subprocess.run(
            ['scala', '-version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            return {
                'version': result.stderr.strip(),  # Scala outputs version to stderr
                'available': True
            }
    except Exception:
        pass
    
    return {'available': False}

def _get_npm_version() -> Optional[str]:
    """Get npm version"""
    try:
        result = subprocess.run(
            ['npm', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    
    return None

async def _get_python_packages() -> List[Dict[str, Any]]:
    """Get list of installed Python packages"""
    try:
        result = subprocess.run(
            ['pip', 'list', '--format=json'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    
    return []

async def _get_npm_global_packages() -> List[str]:
    """Get list of globally installed npm packages"""
    try:
        result = subprocess.run(
            ['npm', 'list', '-g', '--depth=0'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')[1:]  # Skip first line
            return [line.strip() for line in lines if line.strip()]
    except Exception:
        pass
    
    return []

def _detect_virtual_env() -> Dict[str, Any]:
    """Detect if running in a virtual environment"""
    import sys
    import os
    
    venv_info = {
        'active': False,
        'type': None,
        'path': None
    }
    
    # Check for virtualenv/venv
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        venv_info['active'] = True
        venv_info['type'] = 'venv'
        venv_info['path'] = sys.prefix
    
    # Check for conda
    if 'CONDA_DEFAULT_ENV' in os.environ:
        venv_info['active'] = True
        venv_info['type'] = 'conda'
        venv_info['name'] = os.environ.get('CONDA_DEFAULT_ENV')
        venv_info['path'] = os.environ.get('CONDA_PREFIX')
    
    # Check for poetry
    if 'POETRY_ACTIVE' in os.environ:
        venv_info['active'] = True
        venv_info['type'] = 'poetry'
    
    return venv_info

async def _check_package_requirements(packages: List[str], system_info: Dict[str, Any]) -> Dict[str, Any]:
    """Check system requirements for specific packages"""
    results = {}
    
    # This would ideally query package metadata
    # For now, use known requirements
    package_requirements = {
        'tensorflow': {
            'gpu': {'cuda': '11.2', 'cudnn': '8.1'},
            'memory': {'minimum_gb': 8}
        },
        'pytorch': {
            'gpu': {'cuda': '11.7', 'optional': True},
            'memory': {'minimum_gb': 4}
        },
        'opencv': {
            'compiler': {'cpp': True}
        }
    }
    
    for package in packages:
        if package in package_requirements:
            reqs = package_requirements[package]
            check_results = []
            
            for req_type, req_spec in reqs.items():
                requirement = SystemRequirement(
                    type=req_type,
                    minimum=req_spec if not isinstance(req_spec, dict) or 'optional' not in req_spec else {k: v for k, v in req_spec.items() if k != 'optional'},
                    required=not (isinstance(req_spec, dict) and req_spec.get('optional', False))
                )
                
                result = _check_requirement_comprehensive(system_info, requirement)
                check_results.append(result)
            
            results[package] = check_results
    
    return results

def _is_compatible_architecture(system_arch: str, required_arch: str) -> bool:
    """Check if architectures are compatible"""
    arch_aliases = {
        'x86_64': ['x86_64', 'amd64', 'x64'],
        'i386': ['i386', 'i686', 'x86'],
        'arm64': ['arm64', 'aarch64'],
        'armv7': ['armv7', 'armv7l']
    }
    
    system_arch_lower = system_arch.lower()
    required_arch_lower = required_arch.lower()
    
    # Direct match
    if system_arch_lower == required_arch_lower:
        return True
    
    # Check aliases
    for arch, aliases in arch_aliases.items():
        if system_arch_lower in aliases and required_arch_lower in aliases:
            return True
    
    return False

def _is_compatible_os(system_os: str, required_os: str) -> bool:
    """Check if OS is compatible"""
    os_aliases = {
        'linux': ['linux', 'gnu/linux'],
        'darwin': ['darwin', 'macos', 'osx'],
        'windows': ['windows', 'win32', 'win64']
    }
    
    system_os_lower = system_os.lower()
    required_os_lower = required_os.lower()
    
    # Direct match
    if system_os_lower == required_os_lower:
        return True
    
    # Check aliases
    for os_name, aliases in os_aliases.items():
        if system_os_lower in aliases and required_os_lower in aliases:
            return True
    
    return False

def _is_compatible_os_version(os_name: str, system_version: str, required_version: str) -> bool:
    """Check if OS version is compatible"""
    try:
        if os_name.lower() == 'darwin':  # macOS
            # Convert macOS version format
            sys_parts = system_version.split('.')
            req_parts = required_version.split('.')
            
            for i in range(min(len(sys_parts), len(req_parts))):
                if int(sys_parts[i]) < int(req_parts[i]):
                    return False
                elif int(sys_parts[i]) > int(req_parts[i]):
                    return True
            
            return True
        else:
            # Generic version comparison
            from packaging import version
            return version.parse(system_version) >= version.parse(required_version)
    except:
        return True  # Assume compatible if can't parse

def _is_compatible_version(installed: str, required: str) -> bool:
    """Check if installed version satisfies requirement"""
    try:
        from packaging import version
        from packaging.specifiers import SpecifierSet
        
        if any(op in required for op in ['>=', '<=', '>', '<', '==', '~=']):
            spec = SpecifierSet(required)
            return version.parse(installed) in spec
        else:
            return version.parse(installed) >= version.parse(required)
    except:
        return True

def _get_compiler_version(compiler: str) -> Optional[str]:
    """Get compiler version"""
    try:
        if compiler == 'gcc':
            result = subprocess.run(['gcc', '--version'], capture_output=True, text=True)
        elif compiler == 'g++':
            result = subprocess.run(['g++', '--version'], capture_output=True, text=True)
        elif compiler == 'clang':
            result = subprocess.run(['clang', '--version'], capture_output=True, text=True)
        elif compiler == 'msvc':
            result = subprocess.run(['cl'], capture_output=True, text=True)
        else:
            return None
        
        if result.returncode == 0:
            # Extract version from first line
            first_line = result.stdout.strip().split('\n')[0]
            # Use regex to find version number
            match = re.search(r'(\d+\.\d+(?:\.\d+)?)', first_line)
            if match:
                return match.group(1)
    except:
        pass
    
    return None

async def _benchmark_cpu() -> Dict[str, Any]:
    """Run CPU benchmark"""
    import time
    import numpy as np
    
    results = {}
    
    # Single-threaded benchmark
    start = time.time()
    size = 2000
    a = np.random.rand(size, size)
    b = np.random.rand(size, size)
    c = np.dot(a, b)
    single_thread_time = time.time() - start
    
    results['matrix_multiply_single'] = {
        'time_seconds': round(single_thread_time, 3),
        'size': f"{size}x{size}",
        'gflops': round((2 * size**3) / (single_thread_time * 1e9), 2)
    }
    
    # Integer operations benchmark
    start = time.time()
    count = 10000000
    total = sum(i for i in range(count))
    int_time = time.time() - start
    
    results['integer_operations'] = {
        'time_seconds': round(int_time, 3),
        'operations': count,
        'ops_per_second': round(count / int_time)
    }
    
    return results

def _benchmark_memory() -> Dict[str, Any]:
    """Run memory benchmark"""
    import psutil
    
    memory = psutil.virtual_memory()
    
    return {
        'total_gb': round(memory.total / (1024**3), 2),
        'available_gb': round(memory.available / (1024**3), 2),
        'used_gb': round(memory.used / (1024**3), 2),
        'percent_used': memory.percent,
        'swap': {
            'total_gb': round(psutil.swap_memory().total / (1024**3), 2),
            'used_gb': round(psutil.swap_memory().used / (1024**3), 2),
            'percent_used': psutil.swap_memory().percent
        }
    }

async def _benchmark_disk() -> Dict[str, Any]:
    """Run disk benchmark"""
    import psutil
    import tempfile
    import time
    import os
    
    results = {}
    
    # Disk usage
    disk = psutil.disk_usage('/')
    results['usage'] = {
        'total_gb': round(disk.total / (1024**3), 2),
        'free_gb': round(disk.free / (1024**3), 2),
        'percent_used': disk.percent
    }
    
    # Simple write/read benchmark
    try:
        test_size = 100 * 1024 * 1024  # 100MB
        test_data = os.urandom(test_size)
        
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            # Write test
            start = time.time()
            tmp.write(test_data)
            tmp.flush()
            os.fsync(tmp.fileno())
            write_time = time.time() - start
            
            results['write_speed_mbps'] = round((test_size / (1024**2)) / write_time, 2)
            
            # Read test
            tmp.seek(0)
            start = time.time()
            data = tmp.read()
            read_time = time.time() - start
            
            results['read_speed_mbps'] = round((test_size / (1024**2)) / read_time, 2)
            
            os.unlink(tmp.name)
    except Exception as e:
        results['benchmark_error'] = str(e)
    
    return results

async def _benchmark_gpu() -> Dict[str, Any]:
    """Run GPU benchmark"""
    results = {}
    
    try:
        import torch
        
        if torch.cuda.is_available():
            device = torch.device('cuda:0')
            
            # Warm up
            a = torch.randn(1000, 1000).to(device)
            b = torch.randn(1000, 1000).to(device)
            c = torch.matmul(a, b)
            torch.cuda.synchronize()
            
            # Matrix multiplication benchmark
            sizes = [2000, 4000, 8000]
            for size in sizes:
                a = torch.randn(size, size).to(device)
                b = torch.randn(size, size).to(device)
                
                torch.cuda.synchronize()
                start = time.time()
                
                c = torch.matmul(a, b)
                
                torch.cuda.synchronize()
                elapsed = time.time() - start
                
                results[f'matrix_multiply_{size}'] = {
                    'time_seconds': round(elapsed, 3),
                    'size': f"{size}x{size}",
                    'tflops': round((2 * size**3) / (elapsed * 1e12), 2)
                }
            
            # Memory transfer benchmark
            size_mb = 1000
            data = torch.randn(size_mb * 1024 * 1024 // 4).cpu()  # float32
            
            # Host to device
            start = time.time()
            data_gpu = data.to(device)
            torch.cuda.synchronize()
            h2d_time = time.time() - start
            
            results['memory_transfer'] = {
                'host_to_device_gbps': round(size_mb / 1024 / h2d_time, 2)
            }
            
            # Device to host
            start = time.time()
            data_cpu = data_gpu.cpu()
            torch.cuda.synchronize()
            d2h_time = time.time() - start
            
            results['memory_transfer']['device_to_host_gbps'] = round(size_mb / 1024 / d2h_time, 2)
            
        else:
            results['error'] = 'CUDA not available'
            
    except ImportError:
        results['error'] = 'PyTorch not installed'
    except Exception as e:
        results['error'] = str(e)
    
    return results

async def _benchmark_cpu_multicore() -> Dict[str, Any]:
    """Run multi-core CPU benchmark"""
    import concurrent.futures
    import time
    import numpy as np
    import multiprocessing
    
    def cpu_task(size=1000):
        a = np.random.rand(size, size)
        b = np.random.rand(size, size)
        c = np.dot(a, b)
        return c.sum()
    
    results = {}
    num_cores = multiprocessing.cpu_count()
    
    # Test scaling with different thread counts
    for num_threads in [1, num_cores // 2, num_cores]:
        start = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(cpu_task) for _ in range(num_threads)]
            results_list = [f.result() for f in futures]
        
        elapsed = time.time() - start
        
        results[f'threads_{num_threads}'] = {
            'time_seconds': round(elapsed, 3),
            'speedup': round(1 / elapsed if num_threads == 1 else results['threads_1']['time_seconds'] / elapsed, 2)
        }
    
    return results

async def _benchmark_network() -> Dict[str, Any]:
    """Run network benchmark"""
    import aiohttp
    import time
    
    results = {}
    
    # DNS lookup benchmark
    start = time.time()
    try:
        import socket
        socket.gethostbyname('www.google.com')
        dns_time = time.time() - start
        results['dns_lookup_ms'] = round(dns_time * 1000, 2)
    except Exception as e:
        results['dns_error'] = str(e)
    
    # HTTP request benchmark
    test_urls = [
        ('google', 'https://www.google.com'),
        ('cloudflare', 'https://1.1.1.1')
    ]
    
    async with aiohttp.ClientSession() as session:
        for name, url in test_urls:
            try:
                start = time.time()
                async with session.get(url, timeout=5) as response:
                    await response.read()
                    latency = time.time() - start
                    
                    results[f'{name}_latency_ms'] = round(latency * 1000, 2)
            except Exception as e:
                results[f'{name}_error'] = str(e)
    
    return results

async def _benchmark_python() -> Dict[str, Any]:
    """Run Python-specific benchmarks"""
    import time
    
    results = {}
    
    # Import time benchmark
    packages = ['numpy', 'pandas', 'matplotlib']
    for package in packages:
        try:
            start = time.time()
            __import__(package)
            import_time = time.time() - start
            results[f'import_{package}_ms'] = round(import_time * 1000, 2)
        except ImportError:
            results[f'import_{package}_ms'] = 'not installed'
    
    # List comprehension benchmark
    start = time.time()
    result = [i**2 for i in range(1000000)]
    list_comp_time = time.time() - start
    results['list_comprehension_ms'] = round(list_comp_time * 1000, 2)
    
    # Dictionary operations
    start = time.time()
    d = {}
    for i in range(100000):
        d[i] = i**2
    for i in range(100000):
        _ = d[i]
    dict_time = time.time() - start
    results['dict_operations_ms'] = round(dict_time * 1000, 2)
    
    return results

def _compare_benchmark_results(benchmarks: Dict[str, Any]) -> Dict[str, Any]:
    """Compare benchmark results with typical values"""
    typical_values = {
        'cpu': {
            'matrix_multiply_single': {
                'gflops': {'poor': 1, 'average': 5, 'good': 10, 'excellent': 20}
            }
        },
        'gpu': {
            'matrix_multiply_4000': {
                'tflops': {'poor': 0.5, 'average': 2, 'good': 5, 'excellent': 10}
            }
        },
        'disk': {
            'write_speed_mbps': {'poor': 50, 'average': 200, 'good': 500, 'excellent': 1000},
            'read_speed_mbps': {'poor': 100, 'average': 300, 'good': 800, 'excellent': 2000}
        }
    }
    
    comparison = {}
    
    for category, tests in typical_values.items():
        if category in benchmarks:
            comparison[category] = {}
            
            for test, metrics in tests.items():
                if test in benchmarks[category]:
                    for metric, ranges in metrics.items():
                        if metric in benchmarks[category][test]:
                            value = benchmarks[category][test][metric]
                            
                            rating = 'poor'
                            for level in ['poor', 'average', 'good', 'excellent']:
                                if value >= ranges[level]:
                                    rating = level
                            
                            comparison[category][f'{test}_{metric}_rating'] = rating
    
    return comparison