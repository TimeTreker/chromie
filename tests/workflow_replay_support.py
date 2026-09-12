"""Architecture episodes using frozen model HTTP replies and controlled providers.

Initial admission and role scheduling are explicit test drivers. Real GI/GA/Planner
resolvers, contract checks, state, Runtime, result re-entry and due wake are exercised.
"""
from __future__ import annotations

import asyncio
import copy
import itertools
import json
import sys
import time
import uuid
from contextlib import ExitStack, contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent.app.clients.ollama_client import OllamaClient
from agent.app.cognitive_core.goal_interpreter.model_interpreter import OllamaGoalInterpreter
from agent.app.cognitive_core.goal_interpreter.schema import GoalInterpretationRequest
from agent.app.deep_planner import DeepPlannerResolver
from agent.app.fast_planner import FastPlannerResolver
from agent.app.goal_association import GoalAssociationResolver
from agent.app.settings import AgentServiceSettings
from benchmarks.datasets.fast_planner_daily_life.qualification import StaticCatalog
from benchmarks.integration.model_replay import ModelReplay, ReplayServer
from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.capability_runtime import (
    CapabilityDefinition, LocalSpeechCapabilityProvider, MockCapabilityProvider,
    local_speech_definition,
)
from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter, CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.outcome_reconciliation import ExecutionOutcomeReconciler
from orchestrator.runtime.situation import drain_due_time_conditions_once
from shared.chromie_contracts import CognitiveWorkRequest
from shared.chromie_contracts.reflex import CancellationDirective
from shared.chromie_contracts.interaction import CapabilityResult
from tests.capability_runtime_test_support import submit_and_wait_terminal
from tests.test_cognitive_runtime_pr7 import FakeRuntime


@contextmanager
def controlled_runtime():
    """Fix only wall time/UUID sources, preserving real async cancellation/scheduling."""
    original = uuid.uuid4
    counter = itertools.count(1)
    def next_id():
        return uuid.uuid5(uuid.NAMESPACE_URL, f'chromie-workflow-fixture:{next(counter)}')
    class Clock:
        fromisoformat = staticmethod(datetime.fromisoformat)
        milliseconds = 1788480000000
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(cls.milliseconds / 1000, tz)
    with ExitStack() as stack:
        for name, module in list(sys.modules.items()):
            if name.startswith(('agent.', 'orchestrator.', 'shared.', 'chromie_')) and getattr(module, 'uuid4', None) is original:
                stack.enter_context(patch.object(module, 'uuid4', next_id))
        stack.enter_context(patch('uuid.uuid4', next_id))
        stack.enter_context(patch('time.time', lambda: Clock.milliseconds / 1000))
        stack.enter_context(patch('agent.app.planner_context.datetime', Clock))
        yield Clock


class Provider(MockCapabilityProvider):
    def __init__(self, case):
        super().__init__('workflow-fixture')
        self.case = case
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def execute(self, request, definition, context):
        self.calls.append(request)
        self.started.set()
        if self.case['family'] == 'cancellation':
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
        output = self.case['provider_outputs'][request.capability_id]
        return CapabilityResult(request_id=request.request_id, capability_id=request.capability_id,
            provider_id=self.provider_id, status='completed', output=copy.deepcopy(output))


class Episode:
    def __init__(self, case, replay, url, root):
        self.case, self.replay, self.root = case, replay, root
        self.events = []
        self.catalog = case['catalog']
        self.gi = OllamaGoalInterpreter(ollama_url=url, model='fixture-gi', deep_model='fixture-gi-deep', timeout_ms=5000, num_ctx=131072, num_predict=2048)
        settings = AgentServiceSettings(ollama_num_ctx=131072, ollama_num_predict=2048)
        def model(role):
            return OllamaClient(base_url=url, model='fixture-'+role, purpose=role, timeout_ms=5000, service_settings=settings)
        self.ga = GoalAssociationResolver(model('ga'), num_ctx=131072, num_predict=2048)
        self.planners = {
            'fast': FastPlannerResolver(model('fast'), StaticCatalog(self.catalog), num_ctx=131072, num_predict=2048),
            'deep': DeepPlannerResolver(model('deep'), StaticCatalog(self.catalog), num_ctx=131072, num_predict=2048),
        }
        definitions = [CapabilityDefinition(capability_id=c['capability_id'], provider_id='workflow-fixture',
            input_schema=c['input_schema'], output_schema=case['provider_schemas'][c['capability_id']],
            requires_confirmation=c.get('requires_confirmation', False),
            metadata={'safety_class':c['safety_class'], 'effects':c['effects']}) for c in self.catalog]
        definitions.append(local_speech_definition())
        self.runtime = FakeRuntime(definitions)
        self.provider = Provider(case)
        self.runtime.runtime.register_provider(self.provider)
        self.runtime.runtime.register_provider(LocalSpeechCapabilityProvider(lambda _args: {'played': True, 'playback_started': True, 'voice_released': True}))
        self.adapter = CanonicalPlanRuntimeAdapter(self.runtime)
        self.manager = ConversationStateManager(base_conversation_id=case['id'], task_store_enabled=True, task_store_path=root/'state.json')

    def goal_status(self):
        return self.manager._goal_responsibility_status(self.manager._task_context_by_goal_id(self.goal))

    async def resolve_fast_plan(self, _session, *, request, timeout_ms):
        self.last_request = request
        return await self.plan(request, 'fast')

    async def resolve_deep_plan(self, _session, *, request, timeout_ms):
        self.last_request = request
        return await self.plan(request, 'deep')

    async def plan(self, request, tier):
        result = await self.planners[tier].resolve(request)
        if result.metadata.get('failure_class'):
            raise AssertionError(f'{tier} contract failure: {result.metadata}')
        self.events.append({'boundary':tier, 'disposition':result.disposition, 'goal_ids':result.goal_ids})
        return result

    def host(self, request):
        host = VoiceAssistant.__new__(VoiceAssistant)
        host.agent_client = self
        host.conversation_state = self.manager
        host.cognitive_runtime_policy = SimpleNamespace(fast_planner_timeout_ms=5000, deep_planner_timeout_ms=5000)
        host.cognitive_runtime = GoalDrivenRuntimeCoordinator(agent_client=self, adapter=self.adapter, policy=CognitiveRuntimePolicy(mode='apply'))
        host.session_log = lambda *a, **kw: self.events.append({'host_log': str(a), 'fields': str(kw)})
        host.build_context = lambda _sid: copy.deepcopy(request.context)
        host._cognitive_core_authority_context = lambda context, **_kwargs: context
        async def session():
            return object()
        host.get_http_session = session
        return host

    async def begin(self):
        inp = self.case['input']
        context = copy.deepcopy(inp.get('context', {}))
        if self.case.get('initial_goal_resolution'):
            self.manager.apply_goal_association_resolution(self.case['initial_goal_resolution'], sid=inp['sid'], user_text='Prior scheduled request', atomic=True)
            context['active_goal_snapshots'] = self.manager.active_goal_snapshots()
        gi_request = GoalInterpretationRequest(sid=inp['sid'], text=inp['text'], language=inp['language'], context=context)
        interpreted = await self.gi.interpret_goal(gi_request)
        self.events.append({'boundary':'gi', 'responsibilities':interpreted.model_dump(mode='json')})
        request = CognitiveWorkRequest(sid=inp['sid'], text=inp['text'], language=inp['language'], context=context,
            responsibilities=interpreted.responsibilities, interpretation_confidence=interpreted.confidence,
            interpretation_unresolved=interpreted.unresolved)
        association = await self.ga.resolve(request)
        assert association.resolution_status == 'resolved', association.metadata
        self.manager.apply_goal_association_resolution(association, sid=request.sid, user_text=request.text, atomic=True)
        self.goal = association.new_goals[0].goal_id if association.new_goals else association.associations[0].target_goal_ids[0]
        self.replay.bind('goal', self.goal)
        self.events.append({'boundary':'ga', 'resolution':association.model_dump(mode='json')})
        request.context['goal_association_resolution'] = association.model_dump(mode='json')
        request.context['active_goal_snapshots'] = self.manager.active_goal_snapshots()
        self.request = request
        plan = await self.plan(request, self.case['initial_planner'])
        response = await self.adapter.build_planner_owned_response(plan=plan, session_id=request.sid, language=request.language)
        response.metadata.update(turn_id=request.sid, goal_association=association.model_dump(mode='json'),
            goal_interpretation=interpreted.model_dump(mode='json'),
            user_turn_envelope={'turn_id':request.sid, 'original_input':{'text':request.text}, 'normalized_input':{'text':request.text, 'language':request.language}})
        self.manager.record_interaction_response(request.sid, response)
        return plan, response

    def record_result(self, plan, response, result, sid=None):
        bundle = ExecutionOutcomeReconciler().build(turn_id=response.metadata['turn_id'], interaction_id=response.interaction_id,
            plan=plan, requests=response.capabilities, results=result.results,
            output_schemas={r.request_id:self.case['provider_schemas'][r.capability_id] for r in response.capabilities})
        self.manager.record_execution_outcome_bundle(bundle, sid=sid)
        self.manager.reconcile_execution_outcome_responsibilities(bundle, sid=sid)
        self.events.append({'boundary':'runtime_result', 'aggregate_status':bundle.aggregate_status, 'goal_status':self.goal_status()})
        return bundle

    async def execute(self, plan, response, sid=None):
        result = await submit_and_wait_terminal(self.runtime.runtime, response)
        assert result.status == 'completed', result
        if response.capabilities:
            return self.record_result(plan, response, result, sid)
        for speech in response.speech:
            self.manager.update_pending_task_status_for_request_id(request_id=speech.id, status='completed')
        return None

    async def run(self, clock):
        plan, response = await self.begin()
        if self.case['family'] == 'cancellation':
            receipt = await self.runtime.runtime.submit(response)
            await asyncio.wait_for(self.provider.started.wait(), 3)
            cancellation = await self.runtime.runtime.cancel_scope(CancellationDirective(source_turn_id='fixture-stop', requested_scope='current_interaction', foreground_interaction_id=response.interaction_id))
            self.manager.apply_reflex_cancellation_receipt(cancellation, revoked_confirmation=None, sid=self.request.sid, user_text='Stop.')
            result = await self.runtime.runtime.wait_terminal(receipt)
            assert self.provider.cancelled.is_set()
            assert result.status == 'cancelled', result
            assert self.goal_status() == 'open'
            assert self.manager._task_context_by_goal_id(self.goal)['status'] == 'cancelled'
            self.events.append({'boundary':'cancellation', 'goal_status':self.goal_status(), 'provider_cancelled':True})
        elif self.case['family'] == 'delayed':
            assert not response.capabilities and plan.time_conditions
            await self.execute(plan, response)
            assert not self.provider.calls and self.goal_status() == 'open'
            assert self.manager.persist_task_contexts()
            self.manager = ConversationStateManager(base_conversation_id=self.case['id'], task_store_enabled=True, task_store_path=self.root/'state.json')
            due = plan.time_conditions[0].due_at_ms
            self.events.append({'boundary':'restart', 'goal_status':self.goal_status(), 'due_at_ms':due})
            request = self.request.model_copy(deep=True)
            request.context.pop('goal_association_resolution')
            request.context['active_goal_snapshots'] = self.manager.active_goal_snapshots()
            host = self.host(request)
            async def apply(next_response, *, session_id):
                next_response.metadata['turn_id'] = self.request.sid
                next_plan = plan.model_validate(next_response.metadata['canonical_plan'])
                self.manager.record_interaction_response(session_id, next_response)
                await self.execute(next_plan, next_response, session_id)
                return 'applied'
            host._apply_planner_reentry_response = apply
            assert await drain_due_time_conditions_once(host, now_ms=due-1) == []
            assert not self.provider.calls
            clock.milliseconds = due
            wake = await drain_due_time_conditions_once(host, now_ms=due)
            assert wake == ['applied'], (wake, self.events[-4:])
            assert await drain_due_time_conditions_once(host, now_ms=due+1) == []
            assert self.last_request.context['time_condition']['source_plan_id'] == plan.plan_id
            assert list(self.last_request.planner_reentry_scope.goal_ids) == [self.goal]
            assert self.goal_status() == 'satisfied'
        else:
            bundle = await self.execute(plan, response)
            if self.case['family'] == 'conditional':
                assert self.goal_status() == 'open'
                assert [c.capability_id for c in self.provider.calls] == ['chromie.weather.lookup']
                host = self.host(self.request)
                next_response = await host._plan_evidence_bound_capability_result_response(source_response=response,
                    bundle=bundle, plan=plan, session_id=self.request.sid)
                assert next_response is not None
                assert self.last_request.planner_reentry_scope.source_plan_id == plan.plan_id
                assert self.last_request.context['trusted_terminal_evidence'][0]['data'] == self.case['provider_outputs']['chromie.weather.lookup']
                next_response.metadata['turn_id'] = self.request.sid
                next_plan = plan.model_validate(next_response.metadata['canonical_plan'])
                self.manager.record_interaction_response(self.request.sid, next_response)
                await self.execute(next_plan, next_response)
            assert self.goal_status() == 'satisfied', self.goal_status()
        calls = [{'capability':c.capability_id, 'args':c.args} for c in self.provider.calls]
        assert calls == self.case['expected_provider_calls'], calls
        assert self.goal_status() == self.case['expected_goal_status']
        self.replay.assert_finished()
        assert all(not r['schema_errors'] for r in self.replay.records)
        return {'case':self.case['id'], 'passed':True, 'evidence_level':'offline_architecture_replay',
            'model_ability_evaluated':False, 'events':self.replay.normalize(self.events), 'model_calls':len(self.replay.records),
            'provider_calls':calls, 'final_goal_status':self.goal_status(), 'model_records':self.replay.records}


async def run_case(case, root: Path, replay=None):
    replay = replay or ModelReplay(case)
    with ReplayServer(replay) as server, controlled_runtime() as clock:
        episode = Episode(case, replay, server.url, root)
        try:
            return await episode.run(clock)
        except Exception as exc:
            (root/'failure.json').write_text(json.dumps({
                'error': f'{type(exc).__name__}: {exc}',
                'events': replay.normalize(episode.events), 'model_records': replay.records,
                'mismatches': replay.mismatches, 'errors': replay.errors,
                'provider_calls': [{'capability':c.capability_id, 'args':c.args} for c in episode.provider.calls],
            }, ensure_ascii=False, indent=2)+'\n')
            raise
