"""Future intention must not become provider Work before typed readiness (Issue #58)."""
from __future__ import annotations

import asyncio
import copy
from datetime import datetime
from unittest.mock import patch

import pytest

from benchmarks.datasets.fast_planner_daily_life.qualification import load_cases, materialize_catalog
from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts import CognitiveWorkRequest
from tests.capability_runtime_test_support import submit_and_wait_terminal
from tests.test_planner_staged_progress import episode_runtime, read_reply, resolve, status


def future_case(language='en'):
    case = next(c for c in load_cases() if c['id'].endswith(f'34_supported_{language}'))
    return CognitiveWorkRequest.model_validate(copy.deepcopy(case['input']['request'])), materialize_catalog(case['input'])


def waiting_reply(request):
    raw = read_reply(request)
    gid = next(iter(raw['goal_outcomes']))
    raw.update(disposition='respond', steps=[], response_text=(
        'I will revisit the weather request at the specified time.'
        if request.language.startswith('en') else '我会在指定时间再处理这项天气查询。'),
        time_conditions=[{'goal_id':gid, 'due_at_ms':4092202800000, 'reason_code':'future_goal_readiness'}])
    sat = {'score':0.0,'status':'unsatisfied','satisfied_goal_ids':[], 'unmet_goal_ids':[gid],
        'unmet_requirements':['Wait until readiness, then acquire and deliver trusted weather evidence.'],
        'rationale':'The acknowledgement does not perform the future request.'}
    raw['goal_outcomes'][gid].update(disposition='respond',step_ids=[],response_text=raw['response_text'],satisfaction=sat)
    raw['goal_satisfaction'] = sat
    return raw


@pytest.mark.parametrize('tier', ['fast', 'deep'])
@pytest.mark.parametrize('language', ['en', 'zh'])
def test_waiting_acknowledgement_keeps_goal_open_without_provider_work(tier, language):
    async def run():
        request,catalog=future_case(language)
        plan=await resolve(request,catalog,waiting_reply(request),tier)
        assert plan.disposition=='respond', plan.metadata
        runtime,provider=episode_runtime(catalog,False)
        response=await CanonicalPlanRuntimeAdapter(runtime).build_planner_owned_response(
            plan=plan,session_id=request.sid,language=request.language)
        response.metadata.update(turn_id=request.sid,goal_association=request.context['goal_association_resolution'],
            goal_interpretation={'responsibilities':[r.model_dump(mode='json') for r in request.responsibilities]},
            user_turn_envelope={'turn_id':request.sid,'original_input':{'text':request.text},
                'normalized_input':{'text':request.text,'language':request.language}})
        manager=ConversationStateManager(task_store_enabled=False)
        manager.apply_goal_association_resolution(request.context['goal_association_resolution'],sid=request.sid,user_text=request.text,atomic=True)
        manager.record_interaction_response(request.sid,response)
        result=await submit_and_wait_terminal(runtime.runtime,response)
        assert result.status == 'completed'
        # Ordinary response_text uses the existing pending-speech delivery owner,
        # rather than fabricating a canonical executable step for the receipt.
        for speech in response.speech:
            manager.update_pending_task_status_for_request_id(request_id=speech.id,status='completed')
        assert not provider.calls and status(manager,plan.goal_ids[0])=='open'
        due=plan.time_conditions[0].due_at_ms
        assert manager.due_time_condition_opportunities(now_ms=due-1)==[]
        items=manager.due_time_condition_opportunities(now_ms=due)
        assert len(items)==1 and items[0]['condition']['goal_id']==plan.goal_ids[0]
        assert items[0]['responsibilities'] and items[0]['source_text']
        assert manager.due_time_condition_opportunities(now_ms=due+1)==[]
    asyncio.run(run())


@pytest.mark.parametrize('tier', ['fast', 'deep'])
def test_future_goal_cannot_dispatch_even_with_exact_time_condition(tier):
    async def run():
        request,catalog=future_case()
        raw=read_reply(request)
        raw['steps'][0]['args']={'location':'Hangzhou','date':'2099-09-04','period':'night'}
        raw['time_conditions']=waiting_reply(request)['time_conditions']
        # Deliberately bypass Schema in this check: the Host must reject early Work too.
        from agent.app.fast_planner import FastPlannerResolver
        from agent.app.deep_planner import DeepPlannerResolver
        from benchmarks.datasets.fast_planner_daily_life.qualification import ReplayModel,StaticCatalog
        import json
        model=ReplayModel(json.dumps(raw))
        cls=FastPlannerResolver if tier=='fast' else DeepPlannerResolver
        plan=await cls(model,StaticCatalog(catalog)).resolve(request)
        assert not plan.steps and plan.metadata.get('failure_class'), plan
        assert model.calls==1
    asyncio.run(run())


@pytest.mark.parametrize('tier', ['fast', 'deep'])
@pytest.mark.parametrize('offset', [-1, 0, 1])
def test_exact_readiness_boundary_admits_work_only_at_or_after_due(tier, offset):
    async def run():
        request,catalog=future_case()
        due=4092202800000
        class Clock:
            fromisoformat=staticmethod(datetime.fromisoformat)
            @staticmethod
            def now(tz): return datetime.fromtimestamp((due+offset)/1000,tz)
        with patch('agent.app.planner_context.datetime',Clock):
            raw=waiting_reply(request) if offset<0 else read_reply(request)
            if offset>=0:
                raw['steps'][0]['args']={'location':'Hangzhou','date':'2099-09-04','period':'night'}
            plan=await resolve(request,catalog,raw,tier)
        assert plan.disposition==('respond' if offset<0 else 'execute'),plan.metadata
        assert bool(plan.steps)==(offset>=0)
    asyncio.run(run())


@pytest.mark.parametrize('invalid', ['wrong_time','wrong_goal','fake_fulfillment','missing_condition'])
def test_host_rejects_waiting_response_with_invalid_readiness_or_fulfillment(invalid):
    async def run():
        request,catalog=future_case();raw=waiting_reply(request)
        if invalid=='wrong_time':raw['time_conditions'][0]['due_at_ms']+=1
        elif invalid=='wrong_goal':raw['time_conditions'][0]['goal_id']='unrelated-goal'
        elif invalid=='missing_condition':raw['time_conditions']=[]
        else:
            sat=raw['goal_satisfaction']
            sat.update(score=1.0,status='exact',satisfied_goal_ids=sat['unmet_goal_ids'],unmet_goal_ids=[],unmet_requirements=[])
        from agent.app.fast_planner import FastPlannerResolver
        from benchmarks.datasets.fast_planner_daily_life.qualification import ReplayModel,StaticCatalog
        import json
        model=ReplayModel(json.dumps(raw));plan=await FastPlannerResolver(model,StaticCatalog(catalog)).resolve(request)
        assert plan.metadata.get('failure_class') and not plan.steps,plan
        assert model.calls==1
    asyncio.run(run())


@pytest.mark.parametrize('terminal', ['cancelled','superseded','replaced_plan'])
def test_old_future_condition_cannot_wake_cancelled_or_replaced_intention(terminal):
    async def run():
        request,catalog=future_case();plan=await resolve(request,catalog,waiting_reply(request),'fast')
        runtime,_=episode_runtime(catalog,False)
        response=await CanonicalPlanRuntimeAdapter(runtime).build_planner_owned_response(plan=plan,session_id=request.sid,language=request.language)
        response.metadata['goal_interpretation']={'responsibilities':[r.model_dump(mode='json') for r in request.responsibilities]}
        manager=ConversationStateManager(task_store_enabled=False)
        manager.apply_goal_association_resolution(request.context['goal_association_resolution'],sid=request.sid,user_text=request.text,atomic=True)
        manager.record_interaction_response(request.sid,response)
        goal=manager._task_context_by_goal_id(plan.goal_ids[0])
        if terminal=='replaced_plan':goal['metadata']['canonical_plan_id']='replacement-plan'
        else:manager._set_goal_responsibility_status(goal,terminal,source='trusted_control')
        assert manager.due_time_condition_opportunities(now_ms=4092202800001)==[]
    asyncio.run(run())


@pytest.mark.parametrize('tier', ['fast','deep'])
@pytest.mark.parametrize('mode', ['body_action','stateful_effect','singing','media_playback'])
def test_future_provider_goal_waits_without_becoming_a_speech_goal(tier,mode):
    async def run():
        request,catalog=future_case()
        goal=request.context['goal_association_resolution']['new_goals'][0]
        ready=goal.pop('resource_responsibility')['resource']['attributes']['ready_at']
        goal.update(metadata={'output_mode':mode},object={'bindings':{'ready_at':ready}},
            description=f'Perform the requested {mode} only at the future time.',
            source_text=f'At 19:00 on September 4, 2099, perform the requested {mode}; never early.')
        if mode=='media_playback':
            goal['metadata']['media_operation']='pause'
            goal['object']['bindings']['media_operation']={'name':'media_operation','entity_type':'media_operation','value':'pause','confidence':1.0}
            goal['object']['bindings']['playback_id']={'name':'playback_id','entity_type':'playback_id','value':'playback-established','confidence':1.0}
        request=request.model_copy(update={'text':goal['source_text']},deep=True)
        before=copy.deepcopy(request.context['goal_association_resolution']['new_goals'])
        raw=waiting_reply(request);raw['response_text']='I will revisit your request at the specified time.'
        next(iter(raw['goal_outcomes'].values()))['response_text']=raw['response_text']
        plan=await resolve(request,catalog,raw,tier)
        assert plan.disposition=='respond' and not plan.steps,plan.metadata
        assert request.context['goal_association_resolution']['new_goals']==before
    asyncio.run(run())


@pytest.mark.parametrize('tier', ['fast','deep'])
def test_future_wait_preserves_an_independent_ready_action(tier):
    async def run():
        request,catalog=future_case()
        other=next(c for c in load_cases() if c['id'].endswith('08_supported_en'))
        sibling=copy.deepcopy(other['input']['request']['context']['goal_association_resolution']['new_goals'][0])
        sibling.update(goal_id='ready-blink',source_responsibility_refs=['r2'],source_text='Blink exactly three times now.')
        request.context['goal_association_resolution']['new_goals'].append(sibling)
        current=CognitiveWorkRequest.model_validate(other['input']['request']).responsibilities[0]
        request.responsibilities.append(current.model_copy(update={'local_ref':'r2'}))
        raw=waiting_reply(request);raw['disposition']='mixed'
        raw['steps']=[{'step_id':'blink-now','capability_id':'soridormi.blink_eyes','args':{'count':3},
            'timing':'sequential','source_goal_ids':['ready-blink'],'step_purpose':'achieve_effect'}]
        raw['parameter_resolutions']=[{'step_id':'blink-now','parameter':'count','strategy':'user_supplied','value':3,
            'confidence':1.0,'blocking':False,'rationale':'Exact independent Goal binding.','source_goal_ids':['ready-blink']}]
        raw['goal_outcomes']['ready-blink']={'disposition':'execute','coverage':'complete','step_ids':['blink-now'],
            'satisfaction':{'score':1,'status':'exact','satisfied_goal_ids':['ready-blink'],'unmet_goal_ids':[],
                'unmet_requirements':[],'rationale':'Successful execution satisfies the independent action.'}}
        raw['goal_satisfaction']=copy.deepcopy(raw['goal_satisfaction'])
        raw['goal_satisfaction'].update(score=0.5,status='partial',satisfied_goal_ids=['ready-blink'])
        from agent.app.planner_model_contract import PlannerModelOutput
        raw=PlannerModelOutput.model_validate(raw).model_dump(mode='json')
        plan=await resolve(request,catalog,raw,tier)
        assert plan.disposition=='mixed',plan.metadata
        assert len(plan.steps)==1 and plan.steps[0].source_goal_ids==['ready-blink']
        assert len(plan.time_conditions)==1 and plan.time_conditions[0].goal_id!= 'ready-blink'
    asyncio.run(run())


@pytest.mark.parametrize('tier',['fast','deep'])
def test_time_crossing_during_inference_preserves_the_primary_waiting_decision(tier):
    async def run():
        from tests.test_planner_staged_progress import CheckedReply
        from agent.app.fast_planner import FastPlannerResolver
        from agent.app.deep_planner import DeepPlannerResolver
        from benchmarks.datasets.fast_planner_daily_life.qualification import StaticCatalog
        import json
        request,catalog=future_case();due=4092202800000
        class Clock:
            current=due-1
            fromisoformat=staticmethod(datetime.fromisoformat)
            @staticmethod
            def now(tz):return datetime.fromtimestamp(Clock.current/1000,tz)
        class SlowReply(CheckedReply):
            async def generate(self,prompt,**kwargs):
                answer=await super().generate(prompt,**kwargs)
                Clock.current=due+1
                return answer
        model=SlowReply(json.dumps(waiting_reply(request)))
        with patch('agent.app.planner_context.datetime',Clock):
            cls=FastPlannerResolver if tier=='fast' else DeepPlannerResolver
            plan=await cls(model,StaticCatalog(catalog)).resolve(request)
        assert model.calls==1 and plan.disposition=='respond' and not plan.steps,plan.metadata
        assert plan.time_conditions[0].due_at_ms==due
    asyncio.run(run())


def test_frozen_waiting_reference_rejects_the_original_early_dispatch_shape():
    from agent.app.planner_model_contract import PlannerModelOutput, materialize_planner_output
    from shared.chromie_contracts.plan import CanonicalPlan
    from benchmarks.datasets.fast_planner_daily_life.qualification import waiting_reference_errors
    request,_=future_case();raw=read_reply(request)
    raw['steps'][0]['args']={'location':'Hangzhou','date':'2099-09-04','period':'night'}
    raw['time_conditions']=waiting_reply(request)['time_conditions']
    old_plan=CanonicalPlan.model_validate(materialize_planner_output(PlannerModelOutput.model_validate(raw),
        planner_tier='fast',plan_id='old-accepted-temporal-plan',expected_goal_ids_for_turn=list(raw['goal_outcomes'])))
    expectation=next(c for c in load_cases() if c['id'].endswith('34_supported_en'))['target']['reference_region']
    assert 'waiting reference forbids current Work or confirmation' in waiting_reference_errors(expectation,old_plan)
    good=CanonicalPlan.model_validate(materialize_planner_output(PlannerModelOutput.model_validate(waiting_reply(request)),
        planner_tier='fast',plan_id='waiting-plan',expected_goal_ids_for_turn=list(raw['goal_outcomes'])))
    assert waiting_reference_errors(expectation,good)==[]


@pytest.mark.parametrize('language', ['en','zh'])
def test_future_intention_survives_restart_and_due_host_reentry_dispatches_once(tmp_path,language):
    from types import SimpleNamespace
    from orchestrator.orchestrator import VoiceAssistant
    from orchestrator.runtime.cognitive_runtime import CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator
    from orchestrator.runtime.situation import drain_due_time_conditions_once

    async def run():
        request,catalog=future_case(language)
        plan=await resolve(request,catalog,waiting_reply(request),'fast')
        runtime,provider=episode_runtime(catalog,False)
        adapter=CanonicalPlanRuntimeAdapter(runtime)
        response=await adapter.build_planner_owned_response(plan=plan,session_id=request.sid,language=request.language)
        response.metadata['goal_interpretation']={'responsibilities':[r.model_dump(mode='json') for r in request.responsibilities]}
        path=tmp_path/'future-goals.json'
        manager=ConversationStateManager(task_store_enabled=True,task_store_path=path)
        manager.apply_goal_association_resolution(request.context['goal_association_resolution'],sid=request.sid,user_text=request.text,atomic=True)
        manager.record_interaction_response(request.sid,response)
        assert manager.persist_task_contexts()
        restored=ConversationStateManager(task_store_enabled=True,task_store_path=path)
        assert status(restored,plan.goal_ids[0])=='open'
        due=plan.time_conditions[0].due_at_ms
        assert restored.next_time_condition_due_ms()==due
        raw=read_reply(request)
        bindings=request.context['goal_association_resolution']['new_goals'][0]['resource_responsibility']['resource']['attributes']
        raw['steps'][0]['args']={k:bindings[k]['value'] for k in ('location','date','period')}

        class Client:
            requests=[]
            async def resolve_fast_plan(self,_session,*,request,timeout_ms):
                self.requests.append(request)
                return await resolve(request,catalog,raw,'fast')

        client=Client()
        host=VoiceAssistant.__new__(VoiceAssistant)
        host.agent_client=client
        host.conversation_state=restored
        host.cognitive_runtime_policy=SimpleNamespace(fast_planner_timeout_ms=3000,deep_planner_timeout_ms=6000)
        host.cognitive_runtime=GoalDrivenRuntimeCoordinator(agent_client=client,adapter=adapter,policy=CognitiveRuntimePolicy(mode='apply'))
        logs=[]
        host.session_log=lambda *args,**kwargs: logs.append((args,kwargs))
        context=copy.deepcopy(request.context)
        context.pop('goal_association_resolution')
        context['active_goal_snapshots']=restored.active_goal_snapshots()
        host.build_context=lambda _sid: copy.deepcopy(context)
        host._cognitive_core_authority_context=lambda context,**_kwargs: context
        async def session():return object()
        host.get_http_session=session
        async def apply(response,*,session_id):
            result=await submit_and_wait_terminal(runtime.runtime,response)
            assert result.status=='completed'
            return 'planner_reentry_applied'
        host._apply_planner_reentry_response=apply
        class Clock:
            fromisoformat=staticmethod(datetime.fromisoformat)
            @staticmethod
            def now(tz):return datetime.fromtimestamp(due/1000,tz)
        assert await drain_due_time_conditions_once(host,now_ms=due-1)==[]
        assert not client.requests and not provider.calls
        with patch('agent.app.planner_context.datetime',Clock):
            assert await drain_due_time_conditions_once(host,now_ms=due)==['planner_reentry_applied'], logs
        assert len(client.requests)==1
        seen=client.requests[0]
        assert seen.responsibilities==request.responsibilities
        assert list(seen.planner_reentry_scope.goal_ids)==plan.goal_ids
        assert seen.planner_reentry_scope.trigger=='time_condition_reentry'
        assert seen.context['time_condition']['source_plan_id']==plan.plan_id
        assert [call.capability_id for call in provider.calls]==['chromie.weather.lookup']
        assert await drain_due_time_conditions_once(host,now_ms=due+1)==[]
        restarted_after_wake=ConversationStateManager(task_store_enabled=True,task_store_path=path)
        assert restarted_after_wake.due_time_condition_opportunities(now_ms=due+1)==[]
        assert status(restarted_after_wake,plan.goal_ids[0])=='open'
    asyncio.run(run())


@pytest.mark.parametrize('invalid', ['missing_opportunity','wrong_opportunity','wrong_scope','missing_snapshot','terminal_snapshot','wrong_snapshot_identity','duplicate_snapshot'])
@pytest.mark.parametrize('tier', ['fast','deep'])
def test_retained_goal_wake_rejects_unproven_or_stale_identity_before_inference(invalid,tier):
    import json
    from shared.chromie_contracts.core_interpretation import PlannerReentryScope
    from shared.chromie_contracts.situation import CognitiveOpportunity
    from benchmarks.datasets.fast_planner_daily_life.qualification import ReplayModel,StaticCatalog
    from agent.app.fast_planner import FastPlannerResolver
    from agent.app.deep_planner import DeepPlannerResolver

    async def run():
        request,catalog=future_case()
        manager=ConversationStateManager()
        manager.apply_goal_association_resolution(request.context['goal_association_resolution'],sid=request.sid,user_text=request.text,atomic=True)
        snapshot=manager.active_goal_snapshots()[0]
        gid=snapshot['goal_id']
        opportunity=CognitiveOpportunity.create(trigger='time_condition',goal_ids=[gid],reason_codes=['planner_time_condition'],recommended_cognition='fast')
        context=copy.deepcopy(request.context)
        context.pop('goal_association_resolution')
        context.update(active_goal_snapshots=[snapshot],cognitive_opportunity=opportunity.prompt_projection())
        scope=PlannerReentryScope(trigger='time_condition_reentry',goal_ids=[gid],opportunity_id=opportunity.opportunity_id)
        if invalid=='missing_opportunity':context.pop('cognitive_opportunity')
        elif invalid=='wrong_opportunity':context['cognitive_opportunity']['opportunity_id']='different-opportunity'
        elif invalid=='wrong_scope':context['cognitive_opportunity']['goal_ids']=['other-goal']
        elif invalid=='missing_snapshot':context['active_goal_snapshots']=[]
        elif invalid=='terminal_snapshot':snapshot['responsibility_status']='cancelled'
        elif invalid=='wrong_snapshot_identity':snapshot['goal']['goal_id']='other-goal'
        else:context['active_goal_snapshots'].append(copy.deepcopy(snapshot))
        incoming=request.model_copy(update={'context':context,'planner_reentry_scope':scope},deep=True)
        model=ReplayModel(json.dumps(waiting_reply(request)))
        resolver=(FastPlannerResolver if tier=='fast' else DeepPlannerResolver)(model,StaticCatalog(catalog))
        with pytest.raises(ValueError):await resolver.resolve(incoming)
        assert model.calls==0
    asyncio.run(run())


@pytest.mark.parametrize('tier', ['fast','deep'])
def test_primary_packet_exposes_the_same_host_clock_decision_as_validation(tier):
    from benchmarks.datasets.fast_planner_daily_life import qualification,deep_qualification
    async def run():
        module=qualification if tier=='fast' else deep_qualification
        case=copy.deepcopy(next(c for c in load_cases() if c['id'].endswith('34_supported_en')))
        case['input']['runtime_variant']='canonical_primary' if tier=='fast' else 'deep_primary'
        gid=case['input']['request']['context']['goal_association_resolution']['new_goals'][0]['goal_id']
        class Clock:
            offset=-1
            fromisoformat=staticmethod(datetime.fromisoformat)
            @staticmethod
            def now(tz):return datetime.fromtimestamp((4092202800000+Clock.offset)/1000,tz)
        with patch('agent.app.planner_context.datetime',Clock):
            before=await module.build_transaction(case)
            Clock.offset=0
            due=await module.build_transaction(case)
        binding=f'"{gid}":4092202800000'
        assert binding in before['user_prompt'] and binding in due['user_prompt']
        assert 'not yet ready' in before['user_prompt']
        assert 'ALREADY ARRIVED' not in before['user_prompt']
        assert 'ALREADY ARRIVED' in due['user_prompt']
        assert 'not yet ready' not in due['user_prompt']
    asyncio.run(run())
