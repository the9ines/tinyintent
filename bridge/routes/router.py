"""
Router management and monitoring routes.
"""

import sqlite3
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import json
from pathlib import Path

router = APIRouter(prefix="/router", tags=["router"])

# Path to episodes database
EPISODES_DB_PATH = Path(__file__).parent.parent.parent / "data" / "episodes" / "events.db"

class TrainingSummaryResponse(BaseModel):
    timestamp: str
    status: str
    model: Dict[str, Any]
    dataset: Dict[str, Any]
    training: Dict[str, Any]
    performance: Dict[str, Any]
    files: Dict[str, Any]
    sample_predictions: List[Dict[str, Any]]

class RouterMetricsResponse(BaseModel):
    total_requests: int
    avg_latency_ms: float
    accuracy: float
    confidence_avg: float
    model_status: str
    last_prediction: str

@router.get("/train_summary", response_model=TrainingSummaryResponse)
async def get_training_summary():
    """
    Get router training summary and model deployment status.
    
    Returns training metrics, model performance, and sample predictions
    from the last training run. This endpoint provides detailed insights
    into model accuracy, calibration, and deployment readiness.
    """
    train_summary_path = Path("router/train_summary.json")
    
    if not train_summary_path.exists():
        raise HTTPException(
            status_code=404, 
            detail="Training summary not found. Run 'make router-train' to generate model training data."
        )
    
    try:
        with open(train_summary_path, 'r') as f:
            train_summary = json.load(f)
        return TrainingSummaryResponse(**train_summary)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load training summary: {str(e)}"
        )

@router.get("/metrics", response_model=RouterMetricsResponse)
async def get_router_metrics():
    """
    Get router performance metrics from the last 24 hours.

    Returns real-time statistics including:
    - Total requests processed
    - Average latency in milliseconds
    - Prediction accuracy (route_pred == route_final)
    - Average confidence score
    - Model status
    - Last prediction timestamp
    """
    # Check if database exists
    if not EPISODES_DB_PATH.exists():
        return RouterMetricsResponse(
            total_requests=0,
            avg_latency_ms=0.0,
            accuracy=0.0,
            confidence_avg=0.0,
            model_status="no_data",
            last_prediction=""
        )

    try:
        # Query metrics from the last 24 hours
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat() + 'Z'

        with sqlite3.connect(EPISODES_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row

            # Get aggregate metrics
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    AVG(latency_ms) as avg_latency,
                    AVG(CASE WHEN route_pred = route_final THEN 1.0 ELSE 0.0 END) as accuracy,
                    AVG(confidence) as avg_confidence,
                    MAX(ts) as last_prediction
                FROM events
                WHERE ts >= ?
            """, (cutoff,))

            row = cursor.fetchone()

            # Determine model status based on data availability
            total_requests = row["total"] or 0
            if total_requests == 0:
                model_status = "no_recent_data"
            elif (row["accuracy"] or 0) < 0.5:
                model_status = "degraded"
            else:
                model_status = "healthy"

            return RouterMetricsResponse(
                total_requests=total_requests,
                avg_latency_ms=round(row["avg_latency"] or 0.0, 2),
                accuracy=round(row["accuracy"] or 0.0, 3),
                confidence_avg=round(row["avg_confidence"] or 0.0, 3),
                model_status=model_status,
                last_prediction=row["last_prediction"] or ""
            )

    except sqlite3.OperationalError as e:
        # Handle missing columns gracefully (schema may vary)
        if "no such column" in str(e):
            return RouterMetricsResponse(
                total_requests=0,
                avg_latency_ms=0.0,
                accuracy=0.0,
                confidence_avg=0.0,
                model_status="schema_mismatch",
                last_prediction=""
            )
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve metrics: {str(e)}")