"""
TinyIntent Helper Generator

AI-powered generation of custom helper packages from natural language descriptions.
"""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich import box

console = Console()

class HelperGenerator:
    """Generate helper packages using AI assistance."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.templates_dir = self.project_root / "templates" / "helpers"
        self.output_dir = Path.home() / ".tinyintent" / "packages"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def interactive_generate(self) -> Optional[str]:
        """Interactive helper generation process."""
        console.print("🎯 [bold cyan]TinyIntent Helper Generator[/bold cyan]")
        console.print("Generate a custom helper package using AI assistance.\n")
        
        # Get basic information
        helper_spec = self._collect_helper_specification()
        if not helper_spec:
            return None
        
        # Generate the helper
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
            task = progress.add_task("Generating helper package...", total=None)
            
            try:
                package_dir = self._generate_helper_package(helper_spec)
                progress.remove_task(task)
            except Exception as e:
                progress.remove_task(task)
                console.print(f"[red]❌ Generation failed: {e}[/red]")
                return None
        
        if package_dir:
            console.print(f"[green]✅ Helper package generated successfully![/green]")
            console.print(f"📁 Package location: {package_dir}")
            
            # Show next steps
            self._show_next_steps(helper_spec["id"])
            
            return str(package_dir)
        else:
            console.print("[red]❌ Failed to generate helper package[/red]")
            return None
    
    def _collect_helper_specification(self) -> Optional[Dict[str, Any]]:
        """Collect helper specification from user interactively."""
        spec = {}
        
        # Helper ID
        while True:
            helper_id = Prompt.ask("Helper ID (lowercase, underscore-separated)")
            if self._validate_helper_id(helper_id):
                spec["id"] = helper_id
                break
            console.print("[red]❌ Invalid helper ID. Use lowercase letters, numbers, and underscores (3-40 chars).[/red]")
        
        # Description
        spec["description"] = Prompt.ask("Helper description (what does it do?)")
        
        # Language
        language = Prompt.ask(
            "Programming language",
            choices=["python", "node"],
            default="python"
        )
        spec["language"] = language
        
        # Category
        category = Prompt.ask(
            "Helper category",
            choices=["information", "automation", "communication", "entertainment", "productivity", "other"],
            default="other"
        )
        spec["category"] = category
        
        # Risk level
        risk_level = Prompt.ask(
            "Risk level",
            choices=["low", "medium", "high"],
            default="low"
        )
        spec["risk_level"] = risk_level
        
        # Capabilities
        console.print("\n[bold]Select required capabilities:[/bold]")
        capabilities = []
        
        if Confirm.ask("Does your helper need network access? (API calls, web scraping, etc.)"):
            capabilities.append("network")
        
        if Confirm.ask("Does your helper need filesystem access? (read/write files)"):
            capabilities.append("filesystem")
        
        if Confirm.ask("Does your helper need database access?"):
            capabilities.append("database")
        
        spec["capabilities"] = capabilities
        
        # Advanced options
        if Confirm.ask("Configure advanced options?"):
            spec["can_execute"] = Confirm.ask("Allow direct execution? (false = preview-only)", default=False)
            spec["requires_approval"] = Confirm.ask("Require manual approval?", default=True)
        else:
            spec["can_execute"] = False  # Safe default
            spec["requires_approval"] = True  # Safe default
        
        # Generate input/output schemas
        console.print("\n[bold]Define helper inputs and outputs:[/bold]")
        spec["inputs"] = self._design_input_schema(spec)
        spec["outputs"] = self._design_output_schema(spec)
        
        # Show summary
        self._show_specification_summary(spec)
        
        if Confirm.ask("Generate helper with this specification?"):
            return spec
        else:
            return None
    
    def _validate_helper_id(self, helper_id: str) -> bool:
        """Validate helper ID format."""
        pattern = r'^[a-z0-9_]{3,40}$'
        return bool(re.match(pattern, helper_id))
    
    def _design_input_schema(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Design input JSON schema based on helper description."""
        # Basic schema based on helper type and description
        schema = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        # Add common fields based on capabilities
        if "network" in spec["capabilities"]:
            schema["properties"]["url"] = {
                "type": "string",
                "format": "uri",
                "description": "URL to process or fetch data from"
            }
        
        if "filesystem" in spec["capabilities"]:
            schema["properties"]["file_path"] = {
                "type": "string",
                "description": "Path to file to process"
            }
        
        # Add operation field for most helpers
        schema["properties"]["operation"] = {
            "type": "string",
            "enum": ["process", "analyze", "fetch", "convert"],
            "default": "process",
            "description": "Operation to perform"
        }
        schema["required"].append("operation")
        
        # Add text input for text processing helpers
        if any(word in spec["description"].lower() for word in ["text", "analyze", "process", "parse"]):
            schema["properties"]["text"] = {
                "type": "string",
                "description": "Text input to process"
            }
        
        return schema
    
    def _design_output_schema(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Design output JSON schema based on helper description."""
        schema = {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["success", "error"],
                    "description": "Operation status"
                },
                "message": {
                    "type": "string",
                    "description": "Human-readable result message"
                },
                "result": {
                    "type": "object",
                    "description": "Processed result data"
                }
            },
            "required": ["status", "message"]
        }
        
        return schema
    
    def _show_specification_summary(self, spec: Dict[str, Any]) -> None:
        """Show helper specification summary."""
        console.print("\n[bold]Helper Specification Summary:[/bold]")
        
        info_table = [
            ("ID", spec["id"]),
            ("Description", spec["description"]),
            ("Language", spec["language"]),
            ("Category", spec["category"]),
            ("Risk Level", spec["risk_level"]),
            ("Capabilities", ", ".join(spec["capabilities"]) or "None"),
            ("Can Execute", "✅ Yes" if spec.get("can_execute") else "❌ Preview only"),
            ("Requires Approval", "✅ Yes" if spec.get("requires_approval") else "❌ No")
        ]
        
        for label, value in info_table:
            console.print(f"  [dim]{label}:[/dim] {value}")
    
    def _generate_helper_package(self, spec: Dict[str, Any]) -> Optional[Path]:
        """Generate the actual helper package."""
        helper_id = spec["id"]
        package_dir = self.output_dir / helper_id
        
        # Check if package already exists
        if package_dir.exists():
            if not Confirm.ask(f"Package '{helper_id}' already exists. Overwrite?"):
                return None
            shutil.rmtree(package_dir)
        
        package_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Generate package.json
            self._generate_package_json(spec, package_dir)
            
            # Generate helper.yaml
            self._generate_helper_yaml(spec, package_dir)
            
            # Generate schema files
            self._generate_schema_files(spec, package_dir)
            
            # Generate main script
            self._generate_main_script(spec, package_dir)
            
            # Generate README
            self._generate_readme(spec, package_dir)
            
            # Generate health check (optional)
            if spec["language"] == "python":
                self._generate_health_check(spec, package_dir)
            
            return package_dir
            
        except Exception as e:
            # Clean up on failure
            if package_dir.exists():
                shutil.rmtree(package_dir)
            raise e
    
    def _generate_package_json(self, spec: Dict[str, Any], package_dir: Path) -> None:
        """Generate package.json file."""
        package_json = {
            "name": spec["id"],
            "version": "1.0.0",
            "description": spec["description"],
            "author": "Generated by TinyIntent",
            "license": "MIT",
            "keywords": [spec["category"], "generated", "ai"],
            "tinyintent": {
                "spec_version": "1.0",
                "category": spec["category"],
                "risk_level": spec["risk_level"],
                "capabilities": spec["capabilities"],
                "supported_versions": [">=2.0.0"],
                "entry_point": "./main.py" if spec["language"] == "python" else "./main.js",
                "language": spec["language"],
                "requires_approval": spec.get("requires_approval", True),
                "can_execute": spec.get("can_execute", False),
                "lifecycle": {
                    "state": "draft",
                    "since": datetime.now().strftime("%Y-%m-%d"),
                    "notes": "Generated helper - requires testing and validation"
                },
                "limits": {
                    "preview_per_min": 60,
                    "exec_per_min": 10,
                    "daily_exec_budget": 100
                },
                "generated": True,
                "generator": "tinyintent-helper-generator-v1.0",
                "generated_at": datetime.now().isoformat()
            },
            "engines": {
                "tinyintent": ">=2.0.0"
            }
        }
        
        if spec["language"] == "python":
            package_json["engines"]["python"] = ">=3.8"
            package_json["dependencies"] = {"requests": ">=2.25.0"}
        else:
            package_json["engines"]["node"] = ">=16.0.0"
            package_json["dependencies"] = {"axios": ">=0.27.0"}
        
        with open(package_dir / "package.json", 'w') as f:
            json.dump(package_json, f, indent=2)
    
    def _generate_helper_yaml(self, spec: Dict[str, Any], package_dir: Path) -> None:
        """Generate helper.yaml file."""
        helper_yaml = {
            "purpose": spec["description"],
            "schema": {
                "input": "./input.schema.json",
                "output": "./output.schema.json"
            },
            "capabilities": {
                "preview": True,
                "execute": spec.get("can_execute", False),
                "emergency_close": False
            },
            "sandbox": {
                "commands": [
                    "/usr/bin/python3" if spec["language"] == "python" else "/usr/bin/node",
                    "./main.py" if spec["language"] == "python" else "./main.js"
                ],
                "timeouts": [
                    {"name": "default", "seconds": 10},
                    {"name": "execute", "seconds": 30}
                ],
                "cpu": {"max_ms": 5000},
                "mem": {"max_mb": 128}
            },
            "environment": {
                "required": [],
                "optional": []
            },
            "metadata": {
                "version": "1.0.0",
                "author": "Generated by TinyIntent",
                "risk_level": spec["risk_level"],
                "audit_required": True,
                "generated": True
            }
        }
        
        # Add network access if needed
        if "network" in spec["capabilities"]:
            helper_yaml["sandbox"]["network"] = "enabled"
        
        # Add filesystem access if needed
        if "filesystem" in spec["capabilities"]:
            helper_yaml["sandbox"]["filesystem"] = "restricted"
        
        with open(package_dir / "helper.yaml", 'w') as f:
            import yaml
            yaml.dump(helper_yaml, f, default_flow_style=False, indent=2)
    
    def _generate_schema_files(self, spec: Dict[str, Any], package_dir: Path) -> None:
        """Generate input and output schema files."""
        # Input schema
        with open(package_dir / "input.schema.json", 'w') as f:
            json.dump(spec["inputs"], f, indent=2)
        
        # Output schema
        with open(package_dir / "output.schema.json", 'w') as f:
            json.dump(spec["outputs"], f, indent=2)
    
    def _generate_main_script(self, spec: Dict[str, Any], package_dir: Path) -> None:
        """Generate main script file."""
        if spec["language"] == "python":
            self._generate_python_script(spec, package_dir)
        else:
            self._generate_node_script(spec, package_dir)
    
    def _generate_python_script(self, spec: Dict[str, Any], package_dir: Path) -> None:
        """Generate Python main script."""
        script_content = f'''#!/usr/bin/env python3
"""
{spec["id"].title().replace('_', ' ')} Helper

{spec["description"]}

Generated by TinyIntent Helper Generator
"""

import sys
import json
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_request(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process the helper request.
    
    Args:
        input_data: Input data matching input.schema.json
        
    Returns:
        Output data matching output.schema.json
    """
    try:
        operation = input_data.get("operation", "process")
        
        # TODO: Implement your helper logic here
        logger.info(f"Processing {{operation}} operation")
        
        # Example implementation
        if operation == "process":
            result = {{
                "processed": True,
                "data": input_data,
                "helper_id": "{spec["id"]}"
            }}
        else:
            return {{
                "status": "error",
                "message": f"Unsupported operation: {{operation}}"
            }}
        
        return {{
            "status": "success",
            "message": f"{spec["description"]} completed successfully",
            "result": result
        }}
        
    except Exception as e:
        logger.error(f"Error processing request: {{e}}")
        return {{
            "status": "error",
            "message": f"Processing failed: {{str(e)}}"
        }}

def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python main.py <input_json>")
        sys.exit(1)
    
    try:
        # Parse input JSON
        input_json = sys.argv[1]
        input_data = json.loads(input_json)
        
        # Process request
        result = process_request(input_data)
        
        # Output result as JSON
        print(json.dumps(result))
        
    except json.JSONDecodeError as e:
        error_result = {{
            "status": "error",
            "message": f"Invalid JSON input: {{e}}"
        }}
        print(json.dumps(error_result))
        sys.exit(1)
    except Exception as e:
        error_result = {{
            "status": "error", 
            "message": f"Unexpected error: {{e}}"
        }}
        print(json.dumps(error_result))
        sys.exit(1)

if __name__ == "__main__":
    main()
'''
        
        with open(package_dir / "main.py", 'w') as f:
            f.write(script_content)
        
        # Make executable
        os.chmod(package_dir / "main.py", 0o755)
    
    def _generate_node_script(self, spec: Dict[str, Any], package_dir: Path) -> None:
        """Generate Node.js main script."""
        script_content = f'''#!/usr/bin/env node
/**
 * {spec["id"].title().replace('_', ' ')} Helper
 * 
 * {spec["description"]}
 * 
 * Generated by TinyIntent Helper Generator
 */

function processRequest(inputData) {{
    try {{
        const operation = inputData.operation || 'process';
        
        // TODO: Implement your helper logic here
        console.error(`Processing ${{operation}} operation`);
        
        // Example implementation
        let result;
        if (operation === 'process') {{
            result = {{
                processed: true,
                data: inputData,
                helper_id: '{spec["id"]}'
            }};
        }} else {{
            return {{
                status: 'error',
                message: `Unsupported operation: ${{operation}}`
            }};
        }}
        
        return {{
            status: 'success',
            message: '{spec["description"]} completed successfully',
            result: result
        }};
        
    }} catch (error) {{
        console.error('Error processing request:', error);
        return {{
            status: 'error',
            message: `Processing failed: ${{error.message}}`
        }};
    }}
}}

function main() {{
    if (process.argv.length !== 3) {{
        console.log('Usage: node main.js <input_json>');
        process.exit(1);
    }}
    
    try {{
        // Parse input JSON
        const inputJson = process.argv[2];
        const inputData = JSON.parse(inputJson);
        
        // Process request
        const result = processRequest(inputData);
        
        // Output result as JSON
        console.log(JSON.stringify(result));
        
    }} catch (error) {{
        const errorResult = {{
            status: 'error',
            message: `Invalid JSON input: ${{error.message}}`
        }};
        console.log(JSON.stringify(errorResult));
        process.exit(1);
    }}
}}

if (require.main === module) {{
    main();
}}
'''
        
        with open(package_dir / "main.js", 'w') as f:
            f.write(script_content)
        
        # Make executable
        os.chmod(package_dir / "main.js", 0o755)
    
    def _generate_readme(self, spec: Dict[str, Any], package_dir: Path) -> None:
        """Generate README.md file."""
        readme_content = f'''# {spec["id"].title().replace('_', ' ')} Helper

{spec["description"]}

## Overview

This helper was generated using the TinyIntent Helper Generator. It provides a starting template that you can customize for your specific needs.

## Configuration

- **Language**: {spec["language"].title()}
- **Category**: {spec["category"].title()}
- **Risk Level**: {spec["risk_level"].title()}
- **Capabilities**: {", ".join(spec["capabilities"]) or "None"}
- **Execution**: {"Enabled" if spec.get("can_execute") else "Preview only"}
- **Approval**: {"Required" if spec.get("requires_approval") else "Not required"}

## Usage

### Input Schema

The helper accepts input matching the schema in `input.schema.json`:

```json
{json.dumps(spec["inputs"], indent=2)}
```

### Output Schema

The helper returns output matching the schema in `output.schema.json`:

```json
{json.dumps(spec["outputs"], indent=2)}
```

## Development

### Testing

You can test the helper directly:

```bash
# Example test
{"python3 main.py" if spec["language"] == "python" else "node main.js"} '{{"operation": "process"}}'
```

### Installation

Install this helper package:

```bash
tinyintent helper install ./
```

## Customization

This is a generated template. To customize:

1. Modify `main.{"py" if spec["language"] == "python" else "js"}` to implement your specific logic
2. Update input/output schemas as needed
3. Adjust capabilities and risk levels in `package.json` and `helper.yaml`
4. Add dependencies to `package.json`
5. Test thoroughly before enabling execution

## Generated Information

- **Generated At**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- **Generator**: TinyIntent Helper Generator v1.0
- **Initial State**: Draft (requires validation)

## Next Steps

1. Implement your custom logic in the main script
2. Test the helper thoroughly
3. Install and test with TinyIntent
4. Update lifecycle state to "trusted" when ready for production
'''
        
        with open(package_dir / "README.md", 'w') as f:
            f.write(readme_content)
    
    def _generate_health_check(self, spec: Dict[str, Any], package_dir: Path) -> None:
        """Generate health check script for Python helpers."""
        health_content = f'''#!/usr/bin/env python3
"""
Health check for {spec["id"]} helper.
"""

import json
import sys

def health_check():
    """Perform health check."""
    try:
        # TODO: Add specific health checks for your helper
        # Examples:
        # - Check API endpoints are accessible
        # - Verify required files exist
        # - Test database connections
        # - Validate environment variables
        
        return {{
            "status": "healthy",
            "helper_id": "{spec["id"]}",
            "version": "1.0.0",
            "checks": {{
                "basic": "pass"
            }}
        }}
        
    except Exception as e:
        return {{
            "status": "unhealthy",
            "helper_id": "{spec["id"]}",
            "error": str(e)
        }}

if __name__ == "__main__":
    result = health_check()
    print(json.dumps(result))
    sys.exit(0 if result["status"] == "healthy" else 1)
'''
        
        with open(package_dir / "health.py", 'w') as f:
            f.write(health_content)
        
        os.chmod(package_dir / "health.py", 0o755)
    
    def _show_next_steps(self, helper_id: str) -> None:
        """Show next steps after generation."""
        steps = [
            f"📝 Edit the main script to implement your custom logic",
            f"🧪 Test the helper: cd ~/.tinyintent/packages/{helper_id} && python main.py '{{\"operation\": \"process\"}}'",
            f"📦 Install the helper: tinyintent helper install ~/.tinyintent/packages/{helper_id}",
            f"✅ Test with TinyIntent: tinyintent helper info {helper_id}",
            f"🚀 Update lifecycle to 'trusted' when ready for production"
        ]
        
        panel = Panel(
            "\n".join(f"  {i+1}. {step}" for i, step in enumerate(steps)),
            title="Next Steps",
            border_style="green",
            box=box.ROUNDED
        )
        
        console.print("\n", panel)

def generate_helper_interactive() -> Optional[str]:
    """Interactive helper generation entry point."""
    generator = HelperGenerator()
    return generator.interactive_generate()

if __name__ == "__main__":
    generate_helper_interactive()