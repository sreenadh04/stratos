import uuid
import datetime
from sqlalchemy import Column, String, Boolean, Float, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.dialects.postgresql import UUID

class Base(DeclarativeBase):
    pass

class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    website_url = Column(String(500), nullable=False)
    blog_url = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    snapshots = relationship("RawSnapshot", back_populates="competitor")
    signals = relationship("Signal", back_populates="competitor")

class Run(Base):
    __tablename__ = "runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String(50), default="pending")
    trigger_type = Column(String(50), default="scheduled")
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    signal_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    langsmith_run_id = Column(String(255), nullable=True)

    snapshots = relationship("RawSnapshot", back_populates="run")
    signals = relationship("Signal", back_populates="run")

class RawSnapshot(Base):
    __tablename__ = "raw_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id"), nullable=False)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False)
    source_url = Column(String(500), nullable=False)
    content_hash = Column(String(64), nullable=False)
    raw_content = Column(Text, nullable=False)
    captured_at = Column(DateTime, default=datetime.datetime.utcnow)

    competitor = relationship("Competitor", back_populates="snapshots")
    run = relationship("Run", back_populates="snapshots")
    signals = relationship("Signal", back_populates="raw_snapshot")

class Signal(Base):
    __tablename__ = "signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id"), nullable=False)
    raw_snapshot_id = Column(UUID(as_uuid=True), ForeignKey("raw_snapshots.id"), nullable=True)
    impact_level = Column(String(10), nullable=True)
    summary = Column(Text, nullable=True)
    evidence = Column(Text, nullable=True)
    hypothesis = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    is_duplicate = Column(Boolean, default=False)
    evaluated_accurate = Column(Boolean, nullable=True)
    evaluator_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    run = relationship("Run", back_populates="signals")
    competitor = relationship("Competitor", back_populates="signals")
    raw_snapshot = relationship("RawSnapshot", back_populates="signals")
