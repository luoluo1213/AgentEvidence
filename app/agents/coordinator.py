from __future__ import annotations

from collections import defaultdict

from app.agents.events import (
    AgentEvent,
    AgentEventType,
    CollaborationBlackboard,
    PRIORITY_ORDER,
)
from app.agents.registry import AgentRegistry
from app.core.config import Settings


class EventDrivenCoordinator:
    """
    Generic event-driven coordinator.

    Responsibilities:
    - manage execution rounds
    - select open tasks
    - let agents claim tasks
    - enforce execution budgets
    - apply agent results to the shared Blackboard

    Domain-specific task creation and final acceptance are implemented
    by subclasses such as ResearchEventDrivenCoordinator.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        coordinator_agent,
        settings: Settings,
    ):
        self.registry = registry
        self.coordinator_agent = coordinator_agent
        self.settings = settings

        self.max_rounds = int(
            getattr(settings, "agent_max_rounds", 8)
        )
        self.max_claims_per_round = int(
            getattr(settings, "agent_max_claims_per_round", 4)
        )
        self.max_claims_per_agent = int(
            getattr(settings, "agent_max_claims_per_agent", 8)
        )
        self.final_min_confidence = float(
            getattr(
                settings,
                "agent_final_acceptance_min_confidence",
                0.6,
            )
        )

    def run(
        self,
        board: CollaborationBlackboard,
    ) -> CollaborationBlackboard:
        board = self._ensure_root_task(board)

        claim_counts: dict[str, int] = defaultdict(int)

        for round_number in range(1, self.max_rounds + 1):
            board = board.append_event(
                AgentEvent(
                    type=AgentEventType.ROUND_STARTED,
                    actor=self.coordinator_agent.name,
                    message=f"round={round_number}",
                    metadata={"round": round_number},
                )
            )

            # Release/create tasks whose dependencies are satisfied.
            board = self._derive_missing_work(board)

            # Check whether a final result can already be accepted.
            board = self._try_accept_final(board)
            if board.final_artifact_id:
                return board

            candidates = self._claim_candidates(
                board,
                claim_counts,
            )

            if not candidates:
                board = self._derive_missing_work(
                    board,
                    force_response=True,
                )
                candidates = self._claim_candidates(
                    board,
                    claim_counts,
                )

                if not candidates:
                    break

            for task, candidate in candidates:
                current_task = board.tasks.get(task.id, task)

                board = board.update_task(
                    current_task.claim(
                        candidate.agent.profile.name
                    )
                ).append_event(
                    AgentEvent(
                        type=AgentEventType.TASK_CLAIMED,
                        actor=candidate.agent.profile.name,
                        task_id=task.id,
                        message=candidate.decision.reason,
                        metadata={
                            "confidence":
                                candidate.decision.confidence
                        },
                    )
                )

                result = candidate.agent.act(
                    current_task,
                    board,
                )

                board = board.apply_turn_result(
                    current_task,
                    candidate.agent.profile.name,
                    result,
                )

                claim_counts[
                    candidate.agent.profile.name
                ] += 1

            board = self._derive_missing_work(board)
            board = self._try_accept_final(board)

            if board.final_artifact_id:
                return board

        return board.append_event(
            AgentEvent(
                type=AgentEventType.BUDGET_EXHAUSTED,
                actor=self.coordinator_agent.name,
                message=(
                    "event-driven agent budget exhausted "
                    "before final acceptance"
                ),
            )
        )

    def _ensure_root_task(
        self,
        board: CollaborationBlackboard,
    ) -> CollaborationBlackboard:
        """
        Default implementation.

        ResearchEventDrivenCoordinator overrides this method.
        """
        if board.tasks:
            return board

        root = self.coordinator_agent.root_task(board)

        return board.add_task(root).append_event(
            AgentEvent(
                type=AgentEventType.TASK_CREATED,
                actor=self.coordinator_agent.name,
                task_id=root.id,
                message=root.title,
            )
        )

    def _derive_missing_work(
        self,
        board: CollaborationBlackboard,
        force_response: bool = False,
    ) -> CollaborationBlackboard:
        """
        Domain-specific task dependency logic.

        Subclasses override this method.
        """
        return board

    def _try_accept_final(
        self,
        board: CollaborationBlackboard,
    ) -> CollaborationBlackboard:
        """
        Domain-specific final-result acceptance.

        Subclasses override this method.
        """
        return board

    def _claim_candidates(
        self,
        board: CollaborationBlackboard,
        claim_counts: dict[str, int],
    ):
        task_candidates = []

        for task in board.open_tasks():
            candidates = self.registry.candidate_decisions_for(
                task,
                board,
            )

            for candidate in candidates:
                agent_name = candidate.agent.profile.name

                if (
                    claim_counts[agent_name]
                    >= self.max_claims_per_agent
                ):
                    continue

                task_candidates.append(
                    (task, candidate)
                )

        task_candidates.sort(
            key=lambda item: (
                PRIORITY_ORDER[item[0].priority],
                item[1].decision.confidence,
                item[1].agent.profile.name,
            ),
            reverse=True,
        )

        selected = []
        selected_agents = set()
        seen = set()

        for task, candidate in task_candidates:
            agent_name = candidate.agent.profile.name
            key = (task.id, agent_name)

            if key in seen:
                continue

            # One task per agent per scheduling round.
            if agent_name in selected_agents:
                continue

            selected.append((task, candidate))
            seen.add(key)
            selected_agents.add(agent_name)

            if len(selected) >= self.max_claims_per_round:
                break

        return selected