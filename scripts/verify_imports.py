#!/usr/bin/env python3
"""
Script to verify import dependencies and detect circular imports
Referenced in CI workflow
"""

import ast
import os
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Set, Tuple


class ImportAnalyzer:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.backend_root = self.project_root / "backend"
        self.imports = defaultdict(set)
        self.errors = []
        
    def analyze_file(self, file_path: Path) -> Set[str]:
        """Analyze imports in a Python file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
        except Exception as e:
            self.errors.append(f"Failed to parse {file_path}: {e}")
            return set()
        
        imports = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
        
        return imports
    
    def get_local_imports(self, imports: Set[str]) -> Set[str]:
        """Filter to get only local project imports"""
        local_imports = set()
        
        for imp in imports:
            # Check if it's a backend module
            if imp.startswith('backend.'):
                local_imports.add(imp)
            elif imp.startswith('.'):
                # Relative import - need to resolve
                local_imports.add(imp)
        
        return local_imports
    
    def analyze_project(self):
        """Analyze all Python files in the project"""
        print("🔍 Analyzing project imports...")
        
        python_files = list(self.backend_root.rglob("*.py"))
        
        for file_path in python_files:
            # Skip __pycache__ and other non-source directories
            if "__pycache__" in str(file_path) or ".venv" in str(file_path):
                continue
            
            # Get relative module path
            try:
                rel_path = file_path.relative_to(self.backend_root)
                module_path = str(rel_path.with_suffix(''))
                module_name = f"backend.{module_path.replace(os.sep, '.')}"
                
                if module_name.endswith('.__init__'):
                    module_name = module_name[:-9]
                
                # Analyze imports
                file_imports = self.analyze_file(file_path)
                local_imports = self.get_local_imports(file_imports)
                
                self.imports[module_name] = local_imports
                
            except Exception as e:
                self.errors.append(f"Error processing {file_path}: {e}")
    
    def detect_circular_imports(self) -> List[List[str]]:
        """Detect circular import dependencies"""
        print("🔄 Detecting circular imports...")
        
        def has_path(graph, start, end, visited=None):
            if visited is None:
                visited = set()
            
            if start == end:
                return True
            
            if start in visited:
                return False
            
            visited.add(start)
            
            for neighbor in graph.get(start, set()):
                if has_path(graph, neighbor, end, visited.copy()):
                    return True
            
            return False
        
        cycles = []
        
        for module in self.imports:
            for imported in self.imports[module]:
                if imported in self.imports and has_path(self.imports, imported, module):
                    cycle = [module, imported]
                    if cycle not in cycles and list(reversed(cycle)) not in cycles:
                        cycles.append(cycle)
        
        return cycles
    
    def check_import_standards(self):
        """Check if imports follow project standards"""
        print("📋 Checking import standards...")
        
        violations = []
        
        for module, imports in self.imports.items():
            for imp in imports:
                # Check for absolute vs relative imports
                if imp.startswith('.'):
                    violations.append(f"{module}: Uses relative import '{imp}' - prefer absolute imports")
                
                # Check for wildcard imports (would need AST analysis)
                # This is a simplified check
                
        return violations
    
    def generate_dependency_graph(self) -> str:
        """Generate a visual dependency graph in DOT format"""
        print("📊 Generating dependency graph...")
        
        dot_content = ["digraph ImportGraph {"]
        dot_content.append("  rankdir=TB;")
        dot_content.append("  node [shape=box];")
        
        for module, imports in self.imports.items():
            for imp in imports:
                if imp in self.imports:  # Only show internal dependencies
                    dot_content.append(f'  "{module}" -> "{imp}";')
        
        dot_content.append("}")
        
        return "\n".join(dot_content)
    
    def run_analysis(self) -> bool:
        """Run complete import analysis"""
        print("🚀 Starting import analysis...")
        
        self.analyze_project()
        
        if self.errors:
            print(f"❌ Found {len(self.errors)} parsing errors:")
            for error in self.errors:
                print(f"  - {error}")
        
        # Check for circular imports
        cycles = self.detect_circular_imports()
        if cycles:
            print(f"❌ Found {len(cycles)} circular import(s):")
            for cycle in cycles:
                print(f"  - {' -> '.join(cycle)}")
        
        # Check import standards
        violations = self.check_import_standards()
        if violations:
            print(f"⚠️  Found {len(violations)} import standard violation(s):")
            for violation in violations:
                print(f"  - {violation}")
        
        # Generate dependency graph
        graph_dot = self.generate_dependency_graph()
        with open("import_graph.dot", "w") as f:
            f.write(graph_dot)
        print("📊 Dependency graph saved to import_graph.dot")
        
        # Summary
        total_modules = len(self.imports)
        total_imports = sum(len(imports) for imports in self.imports.values())
        
        print(f"\n📈 Analysis Summary:")
        print(f"  - Total modules analyzed: {total_modules}")
        print(f"  - Total imports found: {total_imports}")
        print(f"  - Parsing errors: {len(self.errors)}")
        print(f"  - Circular imports: {len(cycles)}")
        print(f"  - Standard violations: {len(violations)}")
        
        # Return True if no critical issues
        return len(cycles) == 0 and len(self.errors) == 0


def main():
    if len(sys.argv) > 1:
        project_root = sys.argv[1]
    else:
        project_root = os.getcwd()
    
    analyzer = ImportAnalyzer(project_root)
    success = analyzer.run_analysis()
    
    if success:
        print("✅ Import analysis completed successfully!")
        sys.exit(0)
    else:
        print("❌ Import analysis found critical issues!")
        sys.exit(1)


if __name__ == "__main__":
    main()