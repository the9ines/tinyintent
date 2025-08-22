#!/usr/bin/env python3
"""
Log Tailer Helper Health Check

Validates that the helper can function properly by checking:
- Required files exist and are accessible
- Basic filesystem permissions for log reading
- Helper manifest and schemas are valid
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path


def health_check():
    """Run comprehensive health check for log_tailer helper."""
    results = {
        'status': 'healthy',
        'checks': {},
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }

    helper_dir = Path(__file__).parent

    # Check 1: Validate manifest file exists and is readable
    try:
        manifest_path = helper_dir / 'helper.yaml'
        if not manifest_path.exists():
            results['checks']['manifest'] = {
                'status': 'fail', 
                'message': 'helper.yaml not found'
            }
            results['status'] = 'unhealthy'
        else:
            results['checks']['manifest'] = {
                'status': 'pass', 
                'message': 'Manifest file exists'
            }
    except Exception as error:
        results['checks']['manifest'] = {
            'status': 'fail', 
            'message': f'Manifest check failed: {error}'
        }
        results['status'] = 'unhealthy'

    # Check 2: Validate schema files exist and are valid JSON
    try:
        input_schema_path = helper_dir / 'input.schema.json'
        output_schema_path = helper_dir / 'output.schema.json'
        
        if not input_schema_path.exists():
            results['checks']['input_schema'] = {
                'status': 'fail', 
                'message': 'input.schema.json not found'
            }
            results['status'] = 'unhealthy'
        else:
            # Try to parse JSON
            with open(input_schema_path, 'r') as f:
                json.load(f)
            results['checks']['input_schema'] = {
                'status': 'pass', 
                'message': 'Input schema valid'
            }

        if not output_schema_path.exists():
            results['checks']['output_schema'] = {
                'status': 'fail', 
                'message': 'output.schema.json not found'
            }
            results['status'] = 'unhealthy'
        else:
            # Try to parse JSON
            with open(output_schema_path, 'r') as f:
                json.load(f)
            results['checks']['output_schema'] = {
                'status': 'pass', 
                'message': 'Output schema valid'
            }
    except Exception as error:
        results['checks']['schemas'] = {
            'status': 'fail', 
            'message': f'Schema validation failed: {error}'
        }
        results['status'] = 'unhealthy'

    # Check 3: Main script exists and is readable
    try:
        main_script_path = helper_dir / 'main.py'
        if not main_script_path.exists():
            results['checks']['main_script'] = {
                'status': 'fail', 
                'message': 'main.py not found'
            }
            results['status'] = 'unhealthy'
        else:
            # Check if script is readable
            with open(main_script_path, 'r') as f:
                f.read(100)  # Just read first 100 chars to test
            results['checks']['main_script'] = {
                'status': 'pass', 
                'message': 'Main script exists and readable'
            }
    except Exception as error:
        results['checks']['main_script'] = {
            'status': 'fail', 
            'message': f'Main script check failed: {error}'
        }
        results['status'] = 'unhealthy'

    # Check 4: Test filesystem access (create and read a temp log file)
    try:
        import tempfile
        
        # Create a temporary log file to test reading capability
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as temp_log:
            temp_log.write('Test log entry\nAnother test entry\n')
            temp_log_path = temp_log.name

        # Try to read it back
        with open(temp_log_path, 'r') as f:
            lines = f.readlines()
            if len(lines) >= 2:
                results['checks']['filesystem'] = {
                    'status': 'pass', 
                    'message': 'Filesystem read/write test passed'
                }
            else:
                results['checks']['filesystem'] = {
                    'status': 'fail', 
                    'message': 'Could not read test log file properly'
                }
                results['status'] = 'unhealthy'
        
        # Clean up
        os.unlink(temp_log_path)
        
    except Exception as error:
        results['checks']['filesystem'] = {
            'status': 'fail', 
            'message': f'Filesystem test failed: {error}'
        }
        results['status'] = 'unhealthy'

    # Check 5: Python modules availability
    try:
        required_modules = ['json', 'os', 'sys', 'pathlib', 'datetime']
        missing_modules = []
        
        for module in required_modules:
            try:
                __import__(module)
            except ImportError:
                missing_modules.append(module)
        
        if missing_modules:
            results['checks']['dependencies'] = {
                'status': 'fail', 
                'message': f'Missing Python modules: {", ".join(missing_modules)}'
            }
            results['status'] = 'unhealthy'
        else:
            results['checks']['dependencies'] = {
                'status': 'pass', 
                'message': 'All required Python modules available'
            }
    except Exception as error:
        results['checks']['dependencies'] = {
            'status': 'fail', 
            'message': f'Dependency check failed: {error}'
        }
        results['status'] = 'unhealthy'

    # Output results as JSON
    print(json.dumps(results, indent=2))
    
    # Exit with appropriate code
    if results['status'] == 'unhealthy':
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    health_check()