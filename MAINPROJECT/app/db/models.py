from sqlalchemy import (
    create_engine,
    func,
    Integer,
    Boolean,
    String,
    DateTime,
    Column,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone
import os

ERR_MAX_LEN = 512

Base = declarative_base()


class Service(Base):
    __tablename__ = "service"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    url = Column(String(2048), nullable=False)
    interval_s = Column(Integer, CheckConstraint("interval_s >= 60"), nullable=False)
    timeout_s = Column(Integer, CheckConstraint("timeout_s >= 1"), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    check_results = relationship(
        "CheckResult", back_populates="service", cascade="all, delete-orphan"
    )
    incidents = relationship(
        "Incident", back_populates="service", cascade="all, delete-orphan"
    )


class CheckResult(Base):
    __tablename__ = "check_result"
    id = Column(Integer, primary_key=True)
    service_id = Column(
        Integer, ForeignKey("service.id", ondelete="CASCADE"), nullable=False
    )
    ts = Column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False
    )
    ok = Column(Boolean, nullable=False)
    status_code = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    error_text = Column(String(ERR_MAX_LEN), nullable=True)

    service = relationship("Service", back_populates="check_results")

    __table_args__ = (Index("idx_check_results_service_ts", "service_id", "ts"),)


class Incident(Base):
    __tablename__ = "incident"
    id = Column(Integer, primary_key=True)
    service_id = Column(
        Integer, ForeignKey("service.id", ondelete="CASCADE"), nullable=False
    )
    opened_at = Column(DateTime(timezone=True), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    fail_count = Column(Integer, nullable=False)
    is_open = Column(Boolean, nullable=False)

    service = relationship("Service", back_populates="incidents")


# По умолчанию используем Postgres (compose), если не переопределён переменной окружения
DB_URL = os.getenv(
    "DB_URL", "postgresql+psycopg://user:password@postgres:5432/fastapi_db"
)
engine = create_engine(DB_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
