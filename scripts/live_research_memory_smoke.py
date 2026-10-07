from __future__ import annotations

import sys
import uuid
import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from app.agents.evidence_verifier import EvidenceVerifier
from app.agents.research_agent import ResearchAgent
from app.agents.research_draft_generator import ResearchDraftGenerator
from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.core.bootstrap import create_schema
from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.models.entities import ChatMessage, ChatSession, ResearchLongTermMemory, UserAccount
from app.services.memory import RedisShortTermMemoryStore
from app.services.research_memory import ResearchMemoryService
from app.services.research_runtime import ResearchEventDrivenRuntime
from scripts.demo_research_agent import build_local_knowledge_service
from scripts.demo_research_draft import DemoEvidenceVerifierClient, DemoGroundedDraftClient
from scripts.demo_task_analyzer import DemoMockAiClient


def _runtime(settings, memory, knowledge):
    return ResearchEventDrivenRuntime(
        TaskAnalyzerAgent(DemoMockAiClient()),
        ResearchAgent(
            knowledge,
            top_k=settings.research_retrieval_top_k,
            max_evidence_items=settings.research_max_evidence_items,
        ),
        ResearchDraftGenerator(DemoGroundedDraftClient()),
        EvidenceVerifier(DemoEvidenceVerifierClient()),
        settings,
        memory,
    )


def _require_live_redis(store: RedisShortTermMemoryStore) -> None:
    if store.client is None:
        raise RuntimeError("Redis client is unavailable; refusing to report fallback as live success")
    if not store.client.ping():
        raise RuntimeError("Redis PING did not return a successful response")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # Keep this integration smoke focused on live memory backends. Research
    # retrieval remains the existing deterministic local demo configuration.
    parser = argparse.ArgumentParser(description="Verify live Redis/MySQL research memory round trips.")
    parser.add_argument("--keep-data", action="store_true", help="Keep uniquely named smoke records and Redis keys.")
    args = parser.parse_args()
    settings = get_settings().model_copy(update={"knowledge_vector_enabled": False})
    token = uuid.uuid4().hex[:12]
    username = f"memory-smoke-{token}"
    session_a_id = f"memory-smoke-a-{token}"
    session_b_id = f"memory-smoke-b-{token}"
    redis_message_key = f"mindbridge:short-term-memory:{session_a_id}"
    redis_summary_key = f"mindbridge:research-session-summary:{session_a_id}"
    redis_session_b_key = f"mindbridge:short-term-memory:{session_b_id}"
    redis_session_b_summary_key = f"mindbridge:research-session-summary:{session_b_id}"
    first_query = "介绍 mini-SWE-agent 的 Agent loop"
    second_query = "那它怎么执行 action？"

    create_schema()
    with engine.connect() as connection:
        if connection.execute(text("SELECT 1")).scalar_one() != 1:
            raise RuntimeError("MySQL SELECT 1 failed")

    knowledge, knowledge_db = build_local_knowledge_service(settings)
    db1 = SessionLocal()
    db2 = None
    redis1 = RedisShortTermMemoryStore(settings)
    _require_live_redis(redis1)
    redis1.client.delete(redis_message_key, redis_summary_key)
    try:
        user = UserAccount(username=username, display_name="Research Memory Smoke", password_hash="smoke")
        db1.add(user)
        db1.commit()
        db1.refresh(user)
        user_id = user.id
        session_a = ChatSession(public_id=session_a_id, user_id=user_id, title="Live memory smoke A")
        db1.add(session_a)
        db1.commit()
        db1.refresh(session_a)

        memory1 = ResearchMemoryService(db1, settings, redis1)
        first = _runtime(settings, memory1, knowledge).run(
            first_query,
            user_id=user_id,
            session_id=session_a_id,
        )
        if first.final_result is None:
            raise RuntimeError("Turn 1 runtime did not produce FinalResearchResult")

        mysql_message_count = db1.query(ChatMessage).filter(ChatMessage.session_id == session_a.id).count()
        mysql_memory_count = db1.query(ResearchLongTermMemory).filter(
            ResearchLongTermMemory.user_id == user_id
        ).count()
        redis_message_count = int(redis1.client.llen(redis_message_key))
        redis_summary_exists = bool(redis1.client.exists(redis_summary_key))
        if mysql_message_count < 2 or mysql_memory_count < 1:
            raise RuntimeError("MySQL turn or long-term memory write/read round trip failed")
        if redis_message_count < 2 or not redis_summary_exists:
            raise RuntimeError("Redis session memory write/read round trip failed")

        db1.close()
        db2 = SessionLocal()
        persisted_user = db2.query(UserAccount).filter(UserAccount.username == username).one()
        persisted_session_a = db2.query(ChatSession).filter(ChatSession.public_id == session_a_id).one()
        persisted_messages = db2.query(ChatMessage).filter(
            ChatMessage.session_id == persisted_session_a.id
        ).count()
        if persisted_user.id != user_id or persisted_messages < 2:
            raise RuntimeError("MySQL data was not readable from a fresh SQLAlchemy session")

        session_b = ChatSession(public_id=session_b_id, user_id=user_id, title="Live memory smoke B")
        db2.add(session_b)
        db2.commit()
        redis2 = RedisShortTermMemoryStore(settings)
        _require_live_redis(redis2)
        memory2 = ResearchMemoryService(db2, settings, redis2)
        cross_session = memory2.build_context(user_id, session_b_id, "继续之前的项目分析")
        if not any("mini-SWE-agent" in item for item in cross_session.long_term_memories):
            raise RuntimeError("Long-term memory was not recovered from MySQL in Session B")

        # Remove the SQL L1 copy before Turn 2. A successful context read can now
        # only come from the real Redis key, not the ChatMessage fallback.
        db2.query(ChatMessage).filter(ChatMessage.session_id == persisted_session_a.id).delete()
        db2.commit()
        redis_context = memory2.build_context(user_id, session_a_id, second_query)
        if not redis_context.recent_messages or "mini-SWE-agent" not in redis_context.contextualized_query:
            raise RuntimeError("Turn 2 did not recover usable prior context from Redis")
        if db2.query(ChatMessage).filter(ChatMessage.session_id == persisted_session_a.id).count() != 0:
            raise RuntimeError("MySQL fallback isolation check failed")

        second = _runtime(settings, memory2, knowledge).run(
            second_query,
            user_id=user_id,
            session_id=session_a_id,
        )
        if second.final_result is None:
            raise RuntimeError("Turn 2 runtime did not produce FinalResearchResult")
        runtime_context = second.board.latest_artifact("conversation_context").payload["value"]
        if "mini-SWE-agent" not in runtime_context.contextualized_query:
            raise RuntimeError("MemoryAgent did not receive usable prior-session context")

        print("Redis: LIVE VERIFIED")
        print(f"  endpoint: {settings.redis_url}")
        print(f"  key: {redis_message_key}")
        print(f"  turn-1 messages read from Redis: {redis_message_count}")
        print("  MySQL L1 rows were removed before the successful Turn 2 context read")
        print("MySQL: LIVE VERIFIED")
        print("  connection: existing DATABASE_URL configuration")
        print(f"  fresh-session ChatMessage rows read: {persisted_messages}")
        print(f"  long-term records read in Session B: {len(cross_session.long_term_memories)}")
        print("Runtime: LIVE VERIFIED")
        print(f"  Turn 1: {first_query}")
        print(f"  Turn 2: {second_query}")
        print(f"  contextualized query contains prior entity: {'mini-SWE-agent' in runtime_context.contextualized_query}")
        print(f"  final answer: {second.final_result.answer}")
        return 0
    finally:
        if db2 is not None:
            db2.close()
        else:
            db1.close()
        knowledge_db.close()
        if not args.keep_data:
            cleanup_db = SessionLocal()
            try:
                cleanup_user = cleanup_db.query(UserAccount).filter(UserAccount.username == username).first()
                if cleanup_user is not None:
                    cleanup_db.query(ChatMessage).filter(ChatMessage.user_id == cleanup_user.id).delete()
                    cleanup_db.query(ResearchLongTermMemory).filter(
                        ResearchLongTermMemory.user_id == cleanup_user.id
                    ).delete()
                    cleanup_db.query(ChatSession).filter(ChatSession.user_id == cleanup_user.id).delete()
                    cleanup_db.delete(cleanup_user)
                    cleanup_db.commit()
            finally:
                cleanup_db.close()
            if redis1.client is not None:
                redis1.client.delete(
                    redis_message_key,
                    redis_summary_key,
                    redis_session_b_key,
                    redis_session_b_summary_key,
                )


if __name__ == "__main__":
    raise SystemExit(main())
