"""
TinyIntent Agent Generator

Scaffolds new helpers from natural-language specifications.
Generates helper folders with manifests, schemas, and stub implementations.

M10.0: Self-Replicating Agent Generator
"""

import json
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

from tinyintent.helpers.manifest import validate_agent_spec
from tinyintent.bridge.logs.audit import get_audit_logger


class AgentGenerator:
    """Generates new helper agents from specifications."""
    
    def __init__(self, helpers_dir: Optional[Path] = None):
        """Initialize generator with helpers directory."""
        if helpers_dir is None:
            # Default to helpers/ directory relative to project root
            self.helpers_dir = Path(__file__).parent.parent / "helpers"
        else:
            self.helpers_dir = Path(helpers_dir)
        
        self.audit_logger = get_audit_logger()
    
    def create_agent(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new agent from specification.
        
        Args:
            spec: Agent specification dictionary
            
        Returns:
            dict: Creation result with status and details
        """
        # Validate specification
        is_valid, errors = validate_agent_spec(spec)
        if not is_valid:
            result = {
                "created": False,
                "helper_id": spec.get("id", "unknown"),
                "errors": errors,
                "validation": {"passed": False, "errors": errors}
            }
            
            # Log validation failure
            self.audit_logger.log_entry({
                "action": "agent_create",
                "helper_id": spec.get("id", "unknown"),
                "success": False,
                "errors": errors,
                "validation_passed": False
            })
            
            return result
        
        helper_id = spec["id"]
        
        # Check if helper already exists
        helper_dir = self.helpers_dir / helper_id
        if helper_dir.exists():
            result = {
                "created": False,
                "helper_id": helper_id,
                "errors": [f"Helper '{helper_id}' already exists"],
                "validation": {"passed": True, "errors": []}
            }
            
            self.audit_logger.log_entry({
                "action": "agent_create",
                "helper_id": helper_id,
                "success": False,
                "errors": [f"Helper '{helper_id}' already exists"],
                "validation_passed": True
            })
            
            return result
        
        try:
            # Create helper directory
            helper_dir.mkdir(parents=True, exist_ok=True)
            
            # Apply safe defaults
            safe_spec = self._apply_safe_defaults(spec)
            
            # Generate helper files
            self._generate_helper_yaml(helper_dir, safe_spec)
            self._generate_schemas(helper_dir, safe_spec)
            self._generate_main_script(helper_dir, safe_spec)
            
            # Validate generated files
            validation_result = self._validate_generated_helper(helper_dir)
            
            # M10.5: Generate provenance after files are created
            provenance_result = self._generate_provenance(helper_dir, helper_id, "agent_generator")
            
            result = {
                "created": True,
                "helper_id": helper_id,
                "enabled": True,  # Helper is registered but can_execute=false
                "validation": validation_result,
                "files_created": [
                    f"{helper_id}/helper.yaml",
                    f"{helper_id}/input.schema.json",
                    f"{helper_id}/output.schema.json",
                    f"{helper_id}/main.{self._get_file_extension(safe_spec['language'])}"
                ] + (["provenance.json"] if provenance_result["ok"] else []),
                "provenance": provenance_result  # M10.5: Include provenance result
            }
            
            # Log successful creation
            self.audit_logger.log_entry({
                "action": "agent_create",
                "helper_id": helper_id,
                "language": safe_spec["language"],
                "capabilities": safe_spec.get("capabilities", []),
                "success": True,
                "validation_passed": validation_result["passed"],
                "files_created": result["files_created"]
            })
            
            return result
            
        except Exception as e:
            # Clean up on failure
            if helper_dir.exists():
                import shutil
                shutil.rmtree(helper_dir, ignore_errors=True)
            
            result = {
                "created": False,
                "helper_id": helper_id,
                "errors": [f"Failed to create helper: {str(e)}"],
                "validation": {"passed": False, "errors": [str(e)]}
            }
            
            self.audit_logger.log_entry({
                "action": "agent_create",
                "helper_id": helper_id,
                "success": False,
                "errors": [str(e)],
                "validation_passed": False
            })
            
            return result
    
    def _apply_safe_defaults(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Apply safe defaults to agent specification."""
        safe_spec = spec.copy()
        
        # Safe-by-default settings
        safe_spec.setdefault("can_execute", False)
        safe_spec.setdefault("risk_level", "high")
        safe_spec.setdefault("capabilities", [])
        safe_spec.setdefault("requires_approval", True)
        
        # Force safety overrides
        safe_spec["can_execute"] = False  # Always disable execution for generated agents
        
        # Add safety notes
        safety_notes = "Generated by Agent Generator. Disabled execute by default."
        if "safety_notes" in safe_spec:
            safe_spec["safety_notes"] = f"{safe_spec['safety_notes']} {safety_notes}"
        else:
            safe_spec["safety_notes"] = safety_notes
        
        return safe_spec
    
    def _generate_helper_yaml(self, helper_dir: Path, spec: Dict[str, Any]) -> None:
        """Generate helper.yaml manifest."""
        manifest = {
            "id": spec["id"],
            "name": spec["id"].replace("_", " ").title(),
            "description": spec["description"],
            "version": "1.0.0",
            "purpose": spec["description"],
            
            # Schema paths
            "schema": {
                "input": "input.schema.json",
                "output": "output.schema.json"
            },
            
            # Capabilities and safety
            "capabilities": {
                "preview": True,
                "execute": spec["can_execute"],
                "emergency_close": False
            },
            
            # Sandbox configuration
            "sandbox": {
                "commands": [
                    {
                        "name": f"main.{self._get_file_extension(spec['language'])}",
                        "timeout": 30
                    }
                ],
                "timeouts": [
                    {"name": "default", "seconds": 30}
                ]
            },
            
            # M10.0: Agent generation metadata
            "generated": {
                "by": "TinyIntent Agent Generator",
                "language": spec["language"],
                "capabilities_requested": spec.get("capabilities", []),
                "risk_level": spec["risk_level"],
                "safety_notes": spec["safety_notes"]
            }
        }
        
        # Add capabilities if specified
        if spec.get("capabilities"):
            manifest["required_capabilities"] = spec["capabilities"]
        
        manifest_path = helper_dir / "helper.yaml"
        with open(manifest_path, 'w') as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)
    
    def _generate_schemas(self, helper_dir: Path, spec: Dict[str, Any]) -> None:
        """Generate input and output JSON schemas."""
        # Input schema
        input_schema_path = helper_dir / "input.schema.json"
        with open(input_schema_path, 'w') as f:
            json.dump(spec["inputs"], f, indent=2)
        
        # Output schema
        output_schema_path = helper_dir / "output.schema.json"
        with open(output_schema_path, 'w') as f:
            json.dump(spec["outputs"], f, indent=2)
    
    def _generate_main_script(self, helper_dir: Path, spec: Dict[str, Any]) -> None:
        """Generate main script based on language."""
        language = spec["language"]
        
        if language == "python":
            self._generate_python_script(helper_dir, spec)
        elif language == "node":
            self._generate_node_script(helper_dir, spec)
        else:
            raise ValueError(f"Unsupported language: {language}")
    
    def _generate_python_script(self, helper_dir: Path, spec: Dict[str, Any]) -> None:
        """Generate Python main.py script."""
        template = f'''#!/usr/bin/env python3
"""
{spec["id"].replace("_", " ").title()} Helper

{spec["description"]}

Generated by TinyIntent Agent Generator.
M10.0: Self-Replicating Agent Generator
"""

import json
import sys
from pathlib import Path


def validate_input(input_data, schema_path):
    """Validate input against schema if jsonschema is available."""
    try:
        import jsonschema
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        jsonschema.validate(input_data, schema)
        return True, None
    except ImportError:
        # jsonschema not available - validation handled by bridge
        return True, None
    except Exception as e:
        return False, str(e)


def generate_output(action, input_data, dry_run=False):
    """Generate output conforming to output schema."""
    # This is a stub implementation
    # TODO: Implement actual helper logic here
    
    result = {{
        "status": "success",
        "action": action,
        "input_received": input_data,
        "dry_run": dry_run,
        "result": "ok (stub implementation)",
        "message": f"Helper {{action}} completed successfully (stub)",
        "generated_by": "TinyIntent Agent Generator"
    }}
    
    if dry_run:
        result["message"] = f"Helper {{action}} would execute (dry run)"
        result["result"] = "ok (dry run)"
    
    return result


def main():
    """Main entry point."""
    try:
        # Read input from stdin
        input_text = sys.stdin.read().strip()
        if not input_text:
            raise ValueError("No input provided")
        
        request_data = json.loads(input_text)
        
        # Extract fields
        action = request_data.get("action", "execute")
        input_data = request_data.get("input", {{}})
        dry_run = request_data.get("dry_run", False)
        
        # Validate input schema
        schema_path = Path(__file__).parent / "input.schema.json"
        is_valid, error = validate_input(input_data, schema_path)
        if not is_valid:
            result = {{
                "status": "error",
                "error": f"Input validation failed: {{error}}",
                "action": action
            }}
            print(json.dumps(result, indent=2))
            sys.exit(1)
        
        # Generate output
        output = generate_output(action, input_data, dry_run)
        
        # Return result
        print(json.dumps(output, indent=2))
        sys.exit(0)
        
    except json.JSONDecodeError as e:
        result = {{
            "status": "error",
            "error": f"Invalid JSON input: {{e}}",
            "action": "unknown"
        }}
        print(json.dumps(result, indent=2))
        sys.exit(1)
        
    except Exception as e:
        result = {{
            "status": "error", 
            "error": str(e),
            "action": request_data.get("action", "unknown") if 'request_data' in locals() else "unknown"
        }}
        print(json.dumps(result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
'''
        
        script_path = helper_dir / "main.py"
        with open(script_path, 'w') as f:
            f.write(template)
        
        # Make executable
        script_path.chmod(0o755)
    
    def _generate_node_script(self, helper_dir: Path, spec: Dict[str, Any]) -> None:
        """Generate Node.js main.js script."""
        template = f'''#!/usr/bin/env node
/**
 * {spec["id"].replace("_", " ").title()} Helper
 * 
 * {spec["description"]}
 * 
 * Generated by TinyIntent Agent Generator.
 * M10.0: Self-Replicating Agent Generator
 */

const fs = require('fs');
const path = require('path');

/**
 * Validate input against schema if available
 */
function validateInput(inputData, schemaPath) {{
    try {{
        // Basic validation - full JSON Schema validation would require additional libraries
        if (!fs.existsSync(schemaPath)) {{
            return [true, null];
        }}
        
        const schema = JSON.parse(fs.readFileSync(schemaPath, 'utf8'));
        
        // Basic type checking
        if (schema.type && typeof inputData !== schema.type) {{
            return [false, `Expected type ${{schema.type}}, got ${{typeof inputData}}`];
        }}
        
        return [true, null];
    }} catch (error) {{
        return [false, error.message];
    }}
}}

/**
 * Generate output conforming to output schema
 */
function generateOutput(action, inputData, dryRun = false) {{
    // This is a stub implementation
    // TODO: Implement actual helper logic here
    
    const result = {{
        status: 'success',
        action: action,
        input_received: inputData,
        dry_run: dryRun,
        result: 'ok (stub implementation)',
        message: `Helper ${{action}} completed successfully (stub)`,
        generated_by: 'TinyIntent Agent Generator'
    }};
    
    if (dryRun) {{
        result.message = `Helper ${{action}} would execute (dry run)`;
        result.result = 'ok (dry run)';
    }}
    
    return result;
}}

/**
 * Main entry point
 */
function main() {{
    try {{
        // Read input from stdin
        let inputText = '';
        
        process.stdin.setEncoding('utf8');
        process.stdin.on('data', (chunk) => {{
            inputText += chunk;
        }});
        
        process.stdin.on('end', () => {{
            try {{
                if (!inputText.trim()) {{
                    throw new Error('No input provided');
                }}
                
                const requestData = JSON.parse(inputText);
                
                // Extract fields
                const action = requestData.action || 'execute';
                const inputData = requestData.input || {{}};
                const dryRun = requestData.dry_run || false;
                
                // Validate input schema
                const schemaPath = path.join(__dirname, 'input.schema.json');
                const [isValid, error] = validateInput(inputData, schemaPath);
                
                if (!isValid) {{
                    const result = {{
                        status: 'error',
                        error: `Input validation failed: ${{error}}`,
                        action: action
                    }};
                    console.log(JSON.stringify(result, null, 2));
                    process.exit(1);
                }}
                
                // Generate output
                const output = generateOutput(action, inputData, dryRun);
                
                // Return result
                console.log(JSON.stringify(output, null, 2));
                process.exit(0);
                
            }} catch (parseError) {{
                if (parseError instanceof SyntaxError) {{
                    const result = {{
                        status: 'error',
                        error: `Invalid JSON input: ${{parseError.message}}`,
                        action: 'unknown'
                    }};
                    console.log(JSON.stringify(result, null, 2));
                }} else {{
                    const result = {{
                        status: 'error',
                        error: parseError.message,
                        action: requestData ? (requestData.action || 'unknown') : 'unknown'
                    }};
                    console.log(JSON.stringify(result, null, 2));
                }}
                process.exit(1);
            }}
        }});
        
    }} catch (error) {{
        const result = {{
            status: 'error',
            error: error.message,
            action: 'unknown'
        }};
        console.log(JSON.stringify(result, null, 2));
        process.exit(1);
    }}
}}

// Start the helper
main();
'''
        
        script_path = helper_dir / "main.js"
        with open(script_path, 'w') as f:
            f.write(template)
        
        # Make executable
        script_path.chmod(0o755)
    
    def _get_file_extension(self, language: str) -> str:
        """Get file extension for language."""
        extensions = {
            "python": "py",
            "node": "js"
        }
        return extensions.get(language, "txt")
    
    def _validate_generated_helper(self, helper_dir: Path) -> Dict[str, Any]:
        """Validate generated helper files."""
        try:
            from tinyintent.helpers.manifest import validate_helper_manifest
            return validate_helper_manifest(helper_dir)
        except Exception as e:
            return {
                "passed": False,
                "errors": [f"Validation failed: {str(e)}"],
                "warnings": []
            }
    
    def _generate_provenance(self, helper_dir: Path, helper_id: str, generator: str) -> Dict[str, Any]:
        """
        M10.5: Generate provenance record for newly created agent.
        
        Args:
            helper_dir: Path to helper directory
            helper_id: Helper identifier
            generator: Source that generated the helper
            
        Returns:
            dict: Provenance generation result
        """
        try:
            # Import provenance module
            from tinyintent.bridge.provenance import generate_and_save_provenance
            
            # Generate and save provenance
            ok, reason, provenance_data = generate_and_save_provenance(
                helper_id, helper_dir, generator
            )
            
            return {
                "ok": ok,
                "reason": reason,
                "data": provenance_data if ok else None
            }
            
        except ImportError:
            # Provenance module not available (e.g., during development)
            return {
                "ok": False,
                "reason": "Provenance module not available",
                "data": None
            }
            
        except Exception as e:
            # Handle any unexpected errors gracefully
            return {
                "ok": False,
                "reason": f"Provenance generation failed: {str(e)}",
                "data": None
            }


# Global generator instance
agent_generator = AgentGenerator()