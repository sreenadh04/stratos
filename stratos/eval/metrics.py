# stratos/eval/metrics.py
"""
Evaluation framework for measuring signal accuracy and quality.
Tracks precision, duplicate rates, and other performance metrics.
"""
import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from sqlalchemy import select, func, and_
from stratos.db.session import get_db_session_manual
from stratos.db.repositories import SignalRepository, RunRepository
from stratos.db.models import Signal


@dataclass
class EvaluationMetrics:
    """Container for evaluation metrics."""
    total_signals: int
    evaluated_count: int
    precision: float
    duplicate_rate: float
    high_impact_accuracy: float
    medium_impact_accuracy: float
    low_impact_accuracy: float
    last_evaluated: Optional[str]


class SignalEvaluator:
    """Evaluates signal accuracy and quality metrics."""
    
    def __init__(self):
        self.signal_repo = None
        self.run_repo = None
    
    async def _get_repos(self):
        """Get repository instances."""
        async with get_db_session_manual() as session:
            self.signal_repo = SignalRepository(session)
            self.run_repo = RunRepository(session)
    
    async def compute_metrics(self, run_id: Optional[str] = None) -> EvaluationMetrics:
        """
        Compute evaluation metrics for signals.
        
        Args:
            run_id: Optional run ID to filter by. If None, uses all runs.
        
        Returns:
            EvaluationMetrics dataclass
        """
        async with get_db_session_manual() as session:
            signal_repo = SignalRepository(session)
            
            # Get signals
            if run_id:
                signals = await signal_repo.get_by_run(run_id, include_duplicates=True)
            else:
                # Get all signals
                result = await session.execute(
                    select(Signal).order_by(Signal.created_at.desc())
                )
                signals = result.scalars().all()
            
            # Separate evaluated and total
            evaluated = [s for s in signals if s.evaluated_accurate is not None]
            total = len(signals)
            evaluated_count = len(evaluated)
            
            if evaluated_count == 0:
                return EvaluationMetrics(
                    total_signals=total,
                    evaluated_count=0,
                    precision=0.0,
                    duplicate_rate=0.0,
                    high_impact_accuracy=0.0,
                    medium_impact_accuracy=0.0,
                    low_impact_accuracy=0.0,
                    last_evaluated=None
                )
            
            # Calculate overall precision
            accurate_count = sum(1 for s in evaluated if s.evaluated_accurate)
            precision = accurate_count / evaluated_count if evaluated_count > 0 else 0
            
            # Calculate duplicate rate
            duplicate_count = sum(1 for s in signals if s.is_duplicate)
            duplicate_rate = duplicate_count / total if total > 0 else 0
            
            # Calculate accuracy by impact level
            high_impact = [s for s in evaluated if s.impact_level == "HIGH"]
            medium_impact = [s for s in evaluated if s.impact_level == "MEDIUM"]
            low_impact = [s for s in evaluated if s.impact_level == "LOW"]
            
            high_accuracy = sum(1 for s in high_impact if s.evaluated_accurate) / len(high_impact) if high_impact else 0
            medium_accuracy = sum(1 for s in medium_impact if s.evaluated_accurate) / len(medium_impact) if medium_impact else 0
            low_accuracy = sum(1 for s in low_impact if s.evaluated_accurate) / len(low_impact) if low_impact else 0
            
            # Get last evaluated timestamp
            last_eval = None
            if evaluated:
                last_eval = max(s.created_at for s in evaluated).isoformat()
            
            return EvaluationMetrics(
                total_signals=total,
                evaluated_count=evaluated_count,
                precision=precision,
                duplicate_rate=duplicate_rate,
                high_impact_accuracy=high_accuracy,
                medium_impact_accuracy=medium_accuracy,
                low_impact_accuracy=low_accuracy,
                last_evaluated=last_eval
            )
    
    async def get_run_metrics(self, run_id: str) -> Dict[str, Any]:
        """Get detailed metrics for a specific run."""
        async with get_db_session_manual() as session:
            signal_repo = SignalRepository(session)
            run_repo = RunRepository(session)
            
            # Get run
            run = await run_repo.get_by_id(run_id)
            if not run:
                return {"error": "Run not found"}
            
            # Get signals
            signals = await signal_repo.get_by_run(run_id, include_duplicates=True)
            evaluated = [s for s in signals if s.evaluated_accurate is not None]
            
            return {
                "run_id": run_id,
                "run_status": run.status,
                "started_at": run.started_at.isoformat(),
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "total_signals": len(signals),
                "unique_signals": len([s for s in signals if not s.is_duplicate]),
                "duplicates": len([s for s in signals if s.is_duplicate]),
                "evaluated_count": len(evaluated),
                "precision": sum(1 for s in evaluated if s.evaluated_accurate) / len(evaluated) if evaluated else 0,
            }
    
    async def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics for the dashboard."""
        async with get_db_session_manual() as session:
            signal_repo = SignalRepository(session)
            
            total_signals = await signal_repo.get_count()
            high_impact = await signal_repo.get_high_impact_count()
            
            # Get evaluated count
            result = await session.execute(
                select(func.count()).where(Signal.evaluated_accurate.isnot(None))
            )
            evaluated_count = result.scalar_one()
            
            # Get accurate count
            result = await session.execute(
                select(func.count()).where(Signal.evaluated_accurate == True)
            )
            accurate_count = result.scalar_one()
            
            precision = accurate_count / evaluated_count if evaluated_count > 0 else 0
            
            return {
                "total_signals": total_signals,
                "high_impact": high_impact,
                "evaluated_count": evaluated_count,
                "precision": precision,
                "accuracy": precision,  # Alias for simplicity
            }