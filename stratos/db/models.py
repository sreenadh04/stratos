# stratos/db/models.py
"""
SQLAlchemy models for StratOS database.
Includes all tables: competitors, runs, raw_snapshots, signals,
plus new tables for product_context, user_actions, audit_logs.
"""
import uuid
import datetime
from sqlalchemy import Column, String, Boolean, Float, Integer, Text, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.dialects.postgresql import UUID


class Base(DeclarativeBase):
    pass


# ============================================================
# 1. COMPETITORS TABLE
# ============================================================
class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    website_url = Column(String(500), nullable=False)
    blog_url = Column(String(500), nullable=False)
    
    # #6: Source Health Monitoring
    is_active = Column(Boolean, default=True)
    last_successful_scrape = Column(DateTime, nullable=True)
    consecutive_failures = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    snapshots = relationship("RawSnapshot", back_populates="competitor")
    signals = relationship("Signal", back_populates="competitor")

    # Indexes for #29
    __table_args__ = (
        Index("idx_competitors_name", "name"),
        Index("idx_competitors_is_active", "is_active"),
    )


# ============================================================
# 2. RUNS TABLE
# ============================================================
class Run(Base):
    __tablename__ = "runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String(50), default="pending")  # pending, running, complete, failed, cancelled
    trigger_type = Column(String(50), default="scheduled")  # manual, scheduled, startup
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    signal_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    langsmith_run_id = Column(String(255), nullable=True)
    
    # #40: Cost Tracking
    tokens_used = Column(Integer, default=0)
    estimated_cost = Column(Float, default=0.0)
    
    # #28: Data Retention
    archived_at = Column(DateTime, nullable=True)
    retention_expiry = Column(DateTime, nullable=True)

    # Relationships
    snapshots = relationship("RawSnapshot", back_populates="run")
    signals = relationship("Signal", back_populates="run")
    logs = relationship("RunLog", back_populates="run")

    # Indexes for #29
    __table_args__ = (
        Index("idx_runs_status", "status"),
        Index("idx_runs_started_at", "started_at"),
        Index("idx_runs_retention_expiry", "retention_expiry"),
    )


# ============================================================
# 3. RUN LOGS TABLE (#26)
# ============================================================
class RunLog(Base):
    __tablename__ = "run_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False)
    agent = Column(String(50), nullable=False)  # scout, analyst, strategist, writer
    level = Column(String(20), default="INFO")  # INFO, WARNING, ERROR
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationship
    run = relationship("Run", back_populates="logs")

    # Indexes for #29
    __table_args__ = (
        Index("idx_run_logs_run_id", "run_id"),
        Index("idx_run_logs_timestamp", "timestamp"),
    )


# ============================================================
# 4. RAW SNAPSHOTS TABLE
# ============================================================
class RawSnapshot(Base):
    __tablename__ = "raw_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id"), nullable=False)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False)
    source_url = Column(String(500), nullable=False)
    source_type = Column(String(50), default="blog")  # blog, github, linkedin, twitter
    content_hash = Column(String(64), nullable=False)
    raw_content = Column(Text, nullable=False)
    captured_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # #6: Source Health - track if this was a successful scrape
    is_successful = Column(Boolean, default=True)

    # Relationships
    competitor = relationship("Competitor", back_populates="snapshots")
    run = relationship("Run", back_populates="snapshots")
    signals = relationship("Signal", back_populates="raw_snapshot")

    # Indexes for #29
    __table_args__ = (
        Index("idx_raw_snapshots_competitor_hash", "competitor_id", "content_hash"),
        Index("idx_raw_snapshots_run_id", "run_id"),
        Index("idx_raw_snapshots_source_type", "source_type"),
    )


# ============================================================
# 5. SIGNALS TABLE
# ============================================================
class Signal(Base):
    __tablename__ = "signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id"), nullable=False)
    raw_snapshot_id = Column(UUID(as_uuid=True), ForeignKey("raw_snapshots.id"), nullable=True)
    
    # Signal data
    impact_level = Column(String(10), nullable=True)
    summary = Column(Text, nullable=True)
    evidence = Column(Text, nullable=True)
    
    # #15: Feedback Loop - Strategist output
    hypothesis = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    is_duplicate = Column(Boolean, default=False)
    
    # #17: A/B Testing support
    prompt_version = Column(String(50), nullable=True)
    llm_provider_used = Column(String(50), nullable=True)
    
    # Human evaluation
    evaluated_accurate = Column(Boolean, nullable=True)
    evaluator_note = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    run = relationship("Run", back_populates="signals")
    competitor = relationship("Competitor", back_populates="signals")
    raw_snapshot = relationship("RawSnapshot", back_populates="signals")
    user_actions = relationship("UserAction", back_populates="signal")

    # Indexes for #29
    __table_args__ = (
        Index("idx_signals_run_id", "run_id"),
        Index("idx_signals_competitor_id", "competitor_id"),
        Index("idx_signals_impact_level", "impact_level"),
        Index("idx_signals_is_duplicate", "is_duplicate"),
        Index("idx_signals_created_at", "created_at"),
    )


# ============================================================
# 6. PRODUCT CONTEXT TABLE (#13)
# ============================================================
class ProductContext(Base):
    __tablename__ = "product_context"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version = Column(Integer, default=1)
    context_text = Column(Text, nullable=False)
    
    # Structured fields for better prompting
    product_goal = Column(Text, nullable=True)
    current_priority = Column(Text, nullable=True)
    competitive_advantage = Column(Text, nullable=True)
    target_customer = Column(Text, nullable=True)
    key_weakness = Column(Text, nullable=True)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Indexes for #29
    __table_args__ = (
        Index("idx_product_context_is_active", "is_active"),
        Index("idx_product_context_updated_at", "updated_at"),
    )


# ============================================================
# 7. USER ACTIONS TABLE (#15)
# ============================================================
class UserAction(Base):
    __tablename__ = "user_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id = Column(UUID(as_uuid=True), ForeignKey("signals.id"), nullable=False)
    
    action_taken = Column(Text, nullable=False)  # e.g., "Implemented voice feature"
    action_category = Column(String(50), nullable=True)  # "feature", "pricing", "marketing"
    impact_notes = Column(Text, nullable=True)
    
    taken_at = Column(DateTime, default=datetime.datetime.utcnow)
    user_id = Column(String(255), nullable=True)  # For multi-user support

    # Relationship
    signal = relationship("Signal", back_populates="user_actions")

    # Indexes for #29
    __table_args__ = (
        Index("idx_user_actions_signal_id", "signal_id"),
        Index("idx_user_actions_taken_at", "taken_at"),
    )


# ============================================================
# 8. AUDIT LOGS TABLE (#36)
# ============================================================
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=True)  # For multi-user support
    action = Column(String(255), nullable=False)  # e.g., "TRIGGER_RUN", "EVALUATE_SIGNAL"
    resource_id = Column(String(255), nullable=True)  # e.g., run_id, signal_id
    resource_type = Column(String(50), nullable=True)  # e.g., "run", "signal"
    
    # Request context
    ip_address = Column(String(45), nullable=True)  # IPv6 support
    user_agent = Column(String(500), nullable=True)
    
    # Details
    details = Column(JSON, nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Indexes for #29
    __table_args__ = (
        Index("idx_audit_logs_user_id", "user_id"),
        Index("idx_audit_logs_action", "action"),
        Index("idx_audit_logs_created_at", "created_at"),
        Index("idx_audit_logs_resource_id", "resource_id"),
    )