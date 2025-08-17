#!/usr/bin/env node

/**
 * TinyIntent Bot Guard Helper - M4 Framework
 * 
 * Crypto bot risk management and emergency controls.
 * This is a stub implementation for the Helpers Framework v1.
 */

const fs = require('fs');
const crypto = require('crypto');

// Read input from stdin
let inputData = '';
process.stdin.setEncoding('utf8');

process.stdin.on('readable', () => {
    let chunk;
    while ((chunk = process.stdin.read()) !== null) {
        inputData += chunk;
    }
});

process.stdin.on('end', () => {
    try {
        const input = JSON.parse(inputData);
        const result = processOperation(input);
        console.log(JSON.stringify(result, null, 2));
        process.exit(0);
    } catch (error) {
        const errorResult = {
            status: "error",
            operation: "unknown",
            action_type: "preview",
            message: `Bot Guard Error: ${error.message}`,
            timestamp: new Date().toISOString(),
            warnings: ["This is a stub implementation for M4 Framework"],
            execution_id: generateExecutionId()
        };
        console.log(JSON.stringify(errorResult, null, 2));
        process.exit(1);
    }
});

function processOperation(input) {
    const { operation, symbol, dry_run = true } = input;
    
    // Generate execution ID
    const executionId = generateExecutionId();
    
    // Base response structure
    const response = {
        status: "success",
        operation: operation,
        action_type: dry_run ? "preview" : "execute",
        timestamp: new Date().toISOString(),
        execution_id: executionId,
        warnings: ["This is a stub implementation for M4 Framework"]
    };
    
    // Handle different operations
    switch (operation) {
        case 'close_position':
            return handleClosePosition(input, response);
        
        case 'close_all_positions':
            return handleCloseAllPositions(input, response);
        
        case 'emergency_stop':
            return handleEmergencyStop(input, response);
        
        case 'get_positions':
            return handleGetPositions(input, response);
        
        case 'get_balance':
            return handleGetBalance(input, response);
        
        case 'set_stop_loss':
            return handleSetStopLoss(input, response);
        
        case 'cancel_orders':
            return handleCancelOrders(input, response);
        
        default:
            throw new Error(`Unknown operation: ${operation}`);
    }
}

function handleClosePosition(input, response) {
    const { symbol, amount, side = "both" } = input;
    
    // Simulate position data
    const mockPosition = {
        id: "pos_" + generateId(),
        symbol: symbol,
        side: side === "both" ? "long" : side,
        size: amount || 0.5,
        entry_price: 45000.0,
        current_price: 46500.0,
        pnl: 750.0,
        action: "close"
    };
    
    response.symbol = symbol;
    response.positions = [mockPosition];
    response.message = `Preview: Close ${side} position for ${symbol}`;
    
    // Simulate order to close position
    response.orders = [{
        id: "order_" + generateId(),
        symbol: symbol,
        type: "market",
        side: mockPosition.side === "long" ? "sell" : "buy",
        amount: mockPosition.size,
        price: mockPosition.current_price,
        status: "pending"
    }];
    
    return response;
}

function handleCloseAllPositions(input, response) {
    // Simulate multiple positions
    const mockPositions = [
        {
            id: "pos_" + generateId(),
            symbol: "BTC/USDT",
            side: "long",
            size: 0.25,
            entry_price: 45000.0,
            current_price: 46500.0,
            pnl: 375.0,
            action: "close"
        },
        {
            id: "pos_" + generateId(),
            symbol: "ETH/USDT", 
            side: "short",
            size: 2.0,
            entry_price: 3200.0,
            current_price: 3150.0,
            pnl: 100.0,
            action: "close"
        }
    ];
    
    response.positions = mockPositions;
    response.message = "Preview: Close all open positions";
    
    // Generate orders for each position
    response.orders = mockPositions.map(pos => ({
        id: "order_" + generateId(),
        symbol: pos.symbol,
        type: "market",
        side: pos.side === "long" ? "sell" : "buy",
        amount: pos.size,
        price: pos.current_price,
        status: "pending"
    }));
    
    return response;
}

function handleEmergencyStop(input, response) {
    const { emergency_code, confirmation_phrase } = input;
    
    // Validate emergency authorization
    if (!emergency_code || !confirmation_phrase) {
        response.status = "error";
        response.message = "Emergency stop requires authorization code and confirmation phrase";
        return response;
    }
    
    if (confirmation_phrase !== "confirm emergency close") {
        response.status = "error";
        response.message = "Invalid confirmation phrase";
        return response;
    }
    
    // Simulate emergency stop
    response.message = "EMERGENCY STOP: All trading halted, positions will be closed at market";
    response.positions = [];
    response.orders = [];
    response.warnings.push("EMERGENCY STOP ACTIVATED");
    
    return response;
}

function handleGetPositions(input, response) {
    // Simulate current positions
    const mockPositions = [
        {
            id: "pos_" + generateId(),
            symbol: "BTC/USDT",
            side: "long",
            size: 0.25,
            entry_price: 45000.0,
            current_price: 46500.0,
            pnl: 375.0,
            action: "none"
        }
    ];
    
    response.positions = mockPositions;
    response.message = `Found ${mockPositions.length} open positions`;
    
    return response;
}

function handleGetBalance(input, response) {
    // Simulate account balances
    response.balances = {
        "USDT": {
            free: 10000.0,
            used: 2500.0,
            total: 12500.0
        },
        "BTC": {
            free: 0.1,
            used: 0.25,
            total: 0.35
        }
    };
    
    response.message = "Account balances retrieved";
    
    return response;
}

function handleSetStopLoss(input, response) {
    const { symbol, stop_loss_price } = input;
    
    response.symbol = symbol;
    response.orders = [{
        id: "order_" + generateId(),
        symbol: symbol,
        type: "stop",
        side: "sell",
        amount: 0.25,
        price: stop_loss_price,
        status: "pending"
    }];
    
    response.message = `Preview: Set stop loss at ${stop_loss_price} for ${symbol}`;
    
    return response;
}

function handleCancelOrders(input, response) {
    // Simulate cancelling orders
    response.orders = [
        {
            id: "order_123",
            symbol: "BTC/USDT",
            type: "limit",
            side: "buy",
            amount: 0.1,
            price: 44000.0,
            status: "cancelled"
        }
    ];
    
    response.message = "Preview: Cancel all pending orders";
    
    return response;
}

function generateId() {
    return Math.random().toString(36).substring(2, 10);
}

function generateExecutionId() {
    return crypto.randomBytes(8).toString('hex');
}