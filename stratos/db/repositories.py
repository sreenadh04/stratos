# stratos/db/repositories.py
"""
Database repository pattern for all database operations.
Encapsulates all SQL queries in one place for maintainability.
"""
import uuid
import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_, desc, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from stratos.db.models import Competitor, Run, RawSnapshot, Signal


class CompetitorRepository:
    """Repository for competitor operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_all(self) -> List[Competitor]:
        """Get all competitors."""
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
            created_at=datetime.datetime.utcnow()
        )
        self.session.add(competitor)
        await self.session.flush()
        return competitor
    
    async def get_name_mapping(self) -> Dict[str, str]:
        """Get mapping of competitor_id -> name."""
        competitors = await self.get_all()
        return {str(c.id): c.name for c in competitors}


class RunRepository:
    """Repository for run operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, run_id: str, trigger_type: str = "manual") -> Run:
        """Create a new run."""
        run = Run(
            id=run_id,
            status="running",
            trigger_type=trigger_type,
            started_at=datetime.datetime.utcnow(),
            signal_count=0,
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
    
    async def get_latest(self, limit: int = 10) -> List[Run]:
        """Get most recent runs."""
        result = await self.session.execute(
            select(Run)
            .order_by(desc(Run.started_at))
            .limit(limit)
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
    ) -> RawSnapshot:
        """Create a new raw snapshot."""
        snapshot = RawSnapshot(
            id=str(uuid.uuid4()),
            competitor_id=competitor_id,
            run_id=run_id,
            source_url=source_url,
            content_hash=content_hash,
            raw_content=raw_content,
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
            }
            for snapshot, name in rows
        ]


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
                recommendation=recommendation
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