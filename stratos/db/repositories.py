# stratos/db/repositories.py
"""
Database repository pattern for all database operations.
Encapsulates all SQL queries in one place for maintainability.
"""
import uuid
import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_, desc, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from stratos.db.models import (
    Competitor, Run, RawSnapshot, Signal, 
    RunLog, ProductContext, UserAction, AuditLog
)


# ============================================================
# COMPETITOR REPOSITORY
# ============================================================
class CompetitorRepository:
    """Repository for competitor operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_all(self) -> List[Competitor]:
        """Get all competitors."""
        result = await self.session.execute(
            select(Competitor).where(Competitor.is_active == True).order_by(Competitor.name)
        )
        return result.scalars().all()
    
    async def get_all_including_inactive(self) -> List[Competitor]:
        """Get all competitors including inactive ones."""
        result = await self.session.execute(
            select(Competitor).order_by(Competitor.name)
        )
        return result.scalars().all()
    
    async def get_by_id(self, competitor_id: str) -> Optional[Competitor]:
        """Get competitor by ID."""
        result = await self.session.execute(
            select(Competitor).where(Competitor.id == competitor_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_name(self, name: str) -> Optional[Competitor]:
        """Get competitor by name."""
        result = await self.session.execute(
            select(Competitor).where(Competitor.name == name)
        )
        return result.scalar_one_or_none()
    
    async def create(self, name: str, website_url: str, blog_url: str) -> Competitor:
        """Create a new competitor."""
        competitor = Competitor(
            id=str(uuid.uuid4()),
            name=name,
            website_url=website_url,
            blog_url=blog_url,
            is_active=True,
            created_at=datetime.datetime.utcnow()
        )
        self.session.add(competitor)
        await self.session.flush()
        return competitor
    
    # #6: Source Health Monitoring
    async def update_health_status(self, competitor_id: str, success: bool) -> None:
        """Update competitor's health status based on scrape success/failure."""
        competitor = await self.get_by_id(competitor_id)
        if not competitor:
            return
        
        if success:
            competitor.last_successful_scrape = datetime.datetime.utcnow()
            competitor.consecutive_failures = 0
            competitor.is_active = True
        else:
            competitor.consecutive_failures += 1
            # Mark as inactive after 3 consecutive failures
            if competitor.consecutive_failures >= 3:
                competitor.is_active = False
        
        await self.session.flush()
    
    async def get_inactive_competitors(self) -> List[Competitor]:
        """Get all inactive competitors (for alerting)."""
        result = await self.session.execute(
            select(Competitor).where(Competitor.is_active == False)
        )
        return result.scalars().all()
    
    async def get_name_mapping(self) -> Dict[str, str]:
        """Get mapping of competitor_id -> name."""
        competitors = await self.get_all()
        return {str(c.id): c.name for c in competitors}


# ============================================================
# RUN REPOSITORY
# ============================================================
class RunRepository:
    """Repository for run operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, run_id: str, trigger_type: str = "manual") -> Run:
        """Create a new run."""
        # #28: Set retention expiry
        retention_days = 180
        from stratos.config import settings
        if hasattr(settings, 'data_retention_days'):
            retention_days = settings.data_retention_days
        
        run = Run(
            id=run_id,
            status="running",
            trigger_type=trigger_type,
            started_at=datetime.datetime.utcnow(),
            signal_count=0,
            retention_expiry=datetime.datetime.utcnow() + datetime.timedelta(days=retention_days),
            tokens_used=0,
            estimated_cost=0.0,
        )
        self.session.add(run)
        await self.session.flush()
        return run
    
    async def get_by_id(self, run_id: str) -> Optional[Run]:
        """Get run by ID."""
        result = await self.session.execute(
            select(Run).where(Run.id == run_id)
        )
        return result.scalar_one_or_none()
    
    async def get_latest(self, limit: int = 10, offset: int = 0) -> List[Run]:
        """Get most recent runs with pagination (#30)."""
        result = await self.session.execute(
            select(Run)
            .order_by(desc(Run.started_at))
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()
    
    async def get_latest_with_signals(self, limit: int = 10) -> List[Run]:
        """Get most recent runs with their signals preloaded."""
        result = await self.session.execute(
            select(Run)
            .options(selectinload(Run.signals))
            .order_by(desc(Run.started_at))
            .limit(limit)
        )
        return result.scalars().all()
    
    async def complete_run(self, run_id: str, signal_count: int = 0) -> None:
        """Mark a run as complete."""
        await self.session.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(
                status="complete",
                completed_at=datetime.datetime.utcnow(),
                signal_count=signal_count
            )
        )
        await self.session.flush()
    
    async def fail_run(self, run_id: str, error_message: str) -> None:
        """Mark a run as failed."""
        await self.session.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(
                status="failed",
                completed_at=datetime.datetime.utcnow(),
                error_message=error_message
            )
        )
        await self.session.flush()
    
    # #22: Run Timeout
    async def timeout_run(self, run_id: str) -> None:
        """Mark a run as timed out."""
        await self.session.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(
                status="failed",
                completed_at=datetime.datetime.utcnow(),
                error_message="Run timed out after 5 minutes"
            )
        )
        await self.session.flush()
    
    # #24: Run Priority
    async def get_running_count(self) -> int:
        """Get count of currently running runs."""
        result = await self.session.execute(
            select(func.count()).where(Run.status == "running")
        )
        return result.scalar_one()
    
    # #40: Cost Tracking
    async def update_cost(self, run_id: str, tokens_used: int, estimated_cost: float) -> None:
        """Update token usage and cost for a run."""
        await self.session.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(
                tokens_used=tokens_used,
                estimated_cost=estimated_cost
            )
        )
        await self.session.flush()
    
    # #28: Data Retention
    async def get_expired_runs(self) -> List[Run]:
        """Get runs that have exceeded retention period."""
        result = await self.session.execute(
            select(Run)
            .where(
                and_(
                    Run.retention_expiry.isnot(None),
                    Run.retention_expiry < datetime.datetime.utcnow(),
                    Run.status.in_(["complete", "failed", "cancelled"])
                )
            )
        )
        return result.scalars().all()
    
    async def archive_run(self, run_id: str) -> None:
        """Mark a run as archived (#28)."""
        await self.session.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(archived_at=datetime.datetime.utcnow())
        )
        await self.session.flush()


# ============================================================
# RAW SNAPSHOT REPOSITORY
# ============================================================
class RawSnapshotRepository:
    """Repository for raw snapshot operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        competitor_id: str,
        run_id: str,
        source_url: str,
        content_hash: str,
        raw_content: str,
        source_type: str = "blog",
    ) -> RawSnapshot:
        """Create a new raw snapshot."""
        snapshot = RawSnapshot(
            id=str(uuid.uuid4()),
            competitor_id=competitor_id,
            run_id=run_id,
            source_url=source_url,
            source_type=source_type,
            content_hash=content_hash,
            raw_content=raw_content,
            is_successful=True,
            captured_at=datetime.datetime.utcnow(),
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot
    
    async def exists_for_hash(self, competitor_id: str, content_hash: str) -> bool:
        """Check if a snapshot with this hash exists for a competitor."""
        result = await self.session.execute(
            select(RawSnapshot.id)
            .where(
                and_(
                    RawSnapshot.competitor_id == competitor_id,
                    RawSnapshot.content_hash == content_hash
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
    
    async def get_by_run(self, run_id: str) -> List[RawSnapshot]:
        """Get all snapshots for a run."""
        result = await self.session.execute(
            select(RawSnapshot)
            .where(RawSnapshot.run_id == run_id)
            .options(selectinload(RawSnapshot.competitor))
        )
        return result.scalars().all()
    
    async def get_by_run_with_content(self, run_id: str) -> List[Dict[str, Any]]:
        """Get snapshots with competitor names for a run."""
        result = await self.session.execute(
            select(RawSnapshot, Competitor.name)
            .join(Competitor, RawSnapshot.competitor_id == Competitor.id)
            .where(RawSnapshot.run_id == run_id)
        )
        rows = result.all()
        return [
            {
                "snapshot_id": str(snapshot.id),
                "competitor_id": str(snapshot.competitor_id),
                "competitor_name": name,
                "content": snapshot.raw_content,
                "blog_url": snapshot.source_url,
                "content_hash": snapshot.content_hash,
                "source_type": snapshot.source_type,
                "is_successful": snapshot.is_successful,
            }
            for snapshot, name in rows
        ]


# ============================================================
# SIGNAL REPOSITORY
# ============================================================
class SignalRepository:
    """Repository for signal operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        run_id: str,
        competitor_id: str,
        impact_level: str,
        summary: str,
        evidence: str,
        confidence: float,
        raw_snapshot_id: str = None,
        is_duplicate: bool = False,
        prompt_version: str = None,
        llm_provider_used: str = None,
    ) -> Signal:
        """Create a new signal."""
        signal = Signal(
            id=str(uuid.uuid4()),
            run_id=run_id,
            competitor_id=competitor_id,
            raw_snapshot_id=raw_snapshot_id,
            impact_level=impact_level,
            summary=summary,
            evidence=evidence,
            confidence=confidence,
            is_duplicate=is_duplicate,
            prompt_version=prompt_version,
            llm_provider_used=llm_provider_used,
            created_at=datetime.datetime.utcnow(),
        )
        self.session.add(signal)
        await self.session.flush()
        return signal
    
    async def get_by_run(self, run_id: str, include_duplicates: bool = False) -> List[Signal]:
        """Get all signals for a run."""
        query = select(Signal).where(Signal.run_id == run_id)
        if not include_duplicates:
            query = query.where(Signal.is_duplicate == False)
        query = query.options(selectinload(Signal.competitor))
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_by_run_with_competitor(self, run_id: str) -> List[Dict[str, Any]]:
        """Get signals with competitor names for a run."""
        result = await self.session.execute(
            select(Signal, Competitor.name)
            .join(Competitor, Signal.competitor_id == Competitor.id)
            .where(
                and_(
                    Signal.run_id == run_id,
                    Signal.is_duplicate == False
                )
            )
            .order_by(desc(Signal.created_at))
        )
        rows = result.all()
        return [
            {
                "signal_id": str(signal.id),
                "competitor_id": str(signal.competitor_id),
                "competitor_name": name,
                "impact_level": signal.impact_level,
                "summary": signal.summary,
                "evidence": signal.evidence,
                "is_duplicate": signal.is_duplicate,
                "hypothesis": signal.hypothesis,
                "recommendation": signal.recommendation,
                "confidence": signal.confidence,
                "prompt_version": signal.prompt_version,
                "llm_provider_used": signal.llm_provider_used,
            }
            for signal, name in rows
        ]
    
    async def get_latest_for_competitor(self, competitor_id: str, limit: int = 5) -> List[Signal]:
        """Get latest signals for a competitor."""
        result = await self.session.execute(
            select(Signal)
            .where(
                and_(
                    Signal.competitor_id == competitor_id,
                    Signal.is_duplicate == False
                )
            )
            .order_by(desc(Signal.created_at))
            .limit(limit)
        )
        return result.scalars().all()
    
    # #14: Historical Memory
    async def get_history_for_competitor(self, competitor_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get historical signals/hypotheses for a competitor."""
        result = await self.session.execute(
            select(Signal)
            .where(
                and_(
                    Signal.competitor_id == competitor_id,
                    Signal.is_duplicate == False,
                    Signal.hypothesis.isnot(None)
                )
            )
            .order_by(desc(Signal.created_at))
            .limit(limit)
        )
        signals = result.scalars().all()
        return [
            {
                "run_id": str(s.run_id),
                "created_at": s.created_at.isoformat(),
                "hypothesis": s.hypothesis,
                "recommendation": s.recommendation,
                "summary": s.summary,
                "impact_level": s.impact_level,
            }
            for s in signals
        ]
    
    async def update_strategy(
        self,
        competitor_id: str,
        run_id: str,
        hypothesis: str,
        recommendation: str,
    ) -> None:
        """Update hypothesis and recommendation for all signals in a run for a competitor."""
        await self.session.execute(
            update(Signal)
            .where(
                and_(
                    Signal.competitor_id == competitor_id,
                    Signal.run_id == run_id,
                    Signal.is_duplicate == False
                )
            )
            .values(
                hypothesis=hypothesis,
                recommendation=recommendation,
                updated_at=datetime.datetime.utcnow()
            )
        )
        await self.session.flush()
    
    async def evaluate_signal(
        self,
        signal_id: str,
        accurate: bool,
        note: str,
    ) -> bool:
        """Mark a signal as evaluated."""
        result = await self.session.execute(
            update(Signal)
            .where(Signal.id == signal_id)
            .values(
                evaluated_accurate=accurate,
                evaluator_note=note
            )
            .returning(Signal.id)
        )
        await self.session.flush()
        return result.scalar_one_or_none() is not None
    
    async def get_unique_signals_by_competitor(self, run_id: str) -> Dict[str, List[Signal]]:
        """Group unique signals by competitor for a run."""
        result = await self.session.execute(
            select(Signal)
            .options(selectinload(Signal.competitor))
            .where(
                and_(
                    Signal.run_id == run_id,
                    Signal.is_duplicate == False
                )
            )
        )
        signals = result.scalars().all()
        
        grouped = {}
        for signal in signals:
            comp_id = str(signal.competitor_id)
            if comp_id not in grouped:
                grouped[comp_id] = []
            grouped[comp_id].append(signal)
        
        return grouped
    
    async def get_count(self) -> int:
        """Get total count of unique signals."""
        result = await self.session.execute(
            select(func.count()).where(Signal.is_duplicate == False)
        )
        return result.scalar_one()
    
    async def get_high_impact_count(self) -> int:
        """Get count of HIGH impact signals."""
        result = await self.session.execute(
            select(func.count()).where(
                and_(
                    Signal.is_duplicate == False,
                    Signal.impact_level == "HIGH"
                )
            )
        )
        return result.scalar_one()


# ============================================================
# PRODUCT CONTEXT REPOSITORY (#13)
# ============================================================
class ProductContextRepository:
    """Repository for product context operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_active(self) -> Optional[ProductContext]:
        """Get the active product context."""
        result = await self.session.execute(
            select(ProductContext)
            .where(ProductContext.is_active == True)
            .order_by(desc(ProductContext.version))
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def create(self, context: Dict[str, Any]) -> ProductContext:
        """Create a new product context version."""
        latest = await self.get_active()
        version = (latest.version + 1) if latest else 1
        
        # Deactivate old version
        if latest:
            latest.is_active = False
        
        new_context = ProductContext(
            id=str(uuid.uuid4()),
            version=version,
            context_text=context.get("context_text", ""),
            product_goal=context.get("product_goal"),
            current_priority=context.get("current_priority"),
            competitive_advantage=context.get("competitive_advantage"),
            target_customer=context.get("target_customer"),
            key_weakness=context.get("key_weakness"),
            is_active=True,
            created_at=datetime.datetime.utcnow(),
        )
        self.session.add(new_context)
        await self.session.flush()
        return new_context
    
    async def get_all_versions(self) -> List[ProductContext]:
        """Get all product context versions."""
        result = await self.session.execute(
            select(ProductContext).order_by(desc(ProductContext.version))
        )
        return result.scalars().all()


# ============================================================
# USER ACTION REPOSITORY (#15)
# ============================================================
class UserActionRepository:
    """Repository for user action operations (feedback loop)."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        signal_id: str,
        action_taken: str,
        action_category: str = None,
        impact_notes: str = None,
        user_id: str = None,
    ) -> UserAction:
        """Create a new user action."""
        action = UserAction(
            id=str(uuid.uuid4()),
            signal_id=signal_id,
            action_taken=action_taken,
            action_category=action_category,
            impact_notes=impact_notes,
            user_id=user_id,
            taken_at=datetime.datetime.utcnow(),
        )
        self.session.add(action)
        await self.session.flush()
        return action
    
    async def get_by_signal(self, signal_id: str) -> List[UserAction]:
        """Get all actions taken for a signal."""
        result = await self.session.execute(
            select(UserAction).where(UserAction.signal_id == signal_id)
        )
        return result.scalars().all()


# ============================================================
# AUDIT LOG REPOSITORY (#36)
# ============================================================
class AuditLogRepository:
    """Repository for audit log operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        action: str,
        user_id: str = None,
        resource_id: str = None,
        resource_type: str = None,
        ip_address: str = None,
        user_agent: str = None,
        details: Dict[str, Any] = None,
        success: bool = True,
        error_message: str = None,
    ) -> AuditLog:
        """Create a new audit log entry."""
        log = AuditLog(
            id=str(uuid.uuid4()),
            user_id=user_id,
            action=action,
            resource_id=resource_id,
            resource_type=resource_type,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
            success=success,
            error_message=error_message,
            created_at=datetime.datetime.utcnow(),
        )
        self.session.add(log)
        await self.session.flush()
        return log


# ============================================================
# RUN LOG REPOSITORY (#26)
# ============================================================
class RunLogRepository:
    """Repository for run log operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        run_id: str,
        agent: str,
        message: str,
        level: str = "INFO",
    ) -> RunLog:
        """Create a new run log entry."""
        log = RunLog(
            id=str(uuid.uuid4()),
            run_id=run_id,
            agent=agent,
            level=level,
            message=message,
            timestamp=datetime.datetime.utcnow(),
        )
        self.session.add(log)
        await self.session.flush()
        return log
    
    async def get_by_run(self, run_id: str, limit: int = 100) -> List[RunLog]:
        """Get logs for a specific run."""
        result = await self.session.execute(
            select(RunLog)
            .where(RunLog.run_id == run_id)
            .order_by(RunLog.timestamp)
            .limit(limit)
        )
        return result.scalars().all()