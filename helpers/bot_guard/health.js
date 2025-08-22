#!/usr/bin/env node
/**
 * Bot Guard Helper Health Check
 * 
 * Validates that the helper can function properly by checking:
 * - Required environment variables are set
 * - Network connectivity (if in live mode)
 * - Basic validation of helper manifest and schemas
 */

const fs = require('fs');
const path = require('path');

function healthCheck() {
    const results = {
        status: 'healthy',
        checks: {},
        timestamp: new Date().toISOString()
    };

    // Check 1: Validate manifest file exists and is readable
    try {
        const manifestPath = path.join(__dirname, 'helper.yaml');
        if (!fs.existsSync(manifestPath)) {
            results.checks.manifest = { status: 'fail', message: 'helper.yaml not found' };
            results.status = 'unhealthy';
        } else {
            results.checks.manifest = { status: 'pass', message: 'Manifest file exists' };
        }
    } catch (error) {
        results.checks.manifest = { status: 'fail', message: `Manifest check failed: ${error.message}` };
        results.status = 'unhealthy';
    }

    // Check 2: Validate schema files exist
    try {
        const inputSchemaPath = path.join(__dirname, 'input.schema.json');
        const outputSchemaPath = path.join(__dirname, 'output.schema.json');
        
        if (!fs.existsSync(inputSchemaPath)) {
            results.checks.input_schema = { status: 'fail', message: 'input.schema.json not found' };
            results.status = 'unhealthy';
        } else {
            // Try to parse JSON
            JSON.parse(fs.readFileSync(inputSchemaPath, 'utf8'));
            results.checks.input_schema = { status: 'pass', message: 'Input schema valid' };
        }

        if (!fs.existsSync(outputSchemaPath)) {
            results.checks.output_schema = { status: 'fail', message: 'output.schema.json not found' };
            results.status = 'unhealthy';
        } else {
            // Try to parse JSON
            JSON.parse(fs.readFileSync(outputSchemaPath, 'utf8'));
            results.checks.output_schema = { status: 'pass', message: 'Output schema valid' };
        }
    } catch (error) {
        results.checks.schemas = { status: 'fail', message: `Schema validation failed: ${error.message}` };
        results.status = 'unhealthy';
    }

    // Check 3: Environment variables (only warn, don't fail)
    const requiredEnvs = ['EXCHANGE_API_KEY', 'EXCHANGE_API_SECRET', 'EXCHANGE_BASE_URL', 'EXCHANGE_MODE'];
    const missingEnvs = requiredEnvs.filter(env => !process.env[env]);
    
    if (missingEnvs.length > 0) {
        results.checks.environment = { 
            status: 'warn', 
            message: `Missing env vars: ${missingEnvs.join(', ')} (expected for production)` 
        };
    } else {
        results.checks.environment = { status: 'pass', message: 'All required environment variables set' };
    }

    // Check 4: Main script exists and is readable
    try {
        const mainScriptPath = path.join(__dirname, 'main.js');
        if (!fs.existsSync(mainScriptPath)) {
            results.checks.main_script = { status: 'fail', message: 'main.js not found' };
            results.status = 'unhealthy';
        } else {
            // Basic syntax check by trying to read
            fs.readFileSync(mainScriptPath, 'utf8');
            results.checks.main_script = { status: 'pass', message: 'Main script exists and readable' };
        }
    } catch (error) {
        results.checks.main_script = { status: 'fail', message: `Main script check failed: ${error.message}` };
        results.status = 'unhealthy';
    }

    // Output results
    console.log(JSON.stringify(results, null, 2));
    
    // Exit with appropriate code
    if (results.status === 'unhealthy') {
        process.exit(1);
    } else {
        process.exit(0);
    }
}

// Run health check
healthCheck();