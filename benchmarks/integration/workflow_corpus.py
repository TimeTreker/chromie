"""Astra-authored workflow contrasts; deterministic expansion is not model inference.

Each emitted JSON is an authoritative scenario. This authoring module never runs
inside production or strict replay, and may not infer an answer from observed behavior.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from agent.app.cognitive_core.goal_interpreter.model_interpreter import _source_tokens
from agent.app.goal_association_contract import GoalAssociationModelOutput
from benchmarks.integration.model_replay import encoded

ROOT = Path(__file__).resolve().parents[2]
SEEDS = ROOT/'benchmarks/integration/scenarios'
FAMILIES = (
    'normal_fast', 'normal_deep', 'conditional_rain', 'conditional_dry',
    'retained_timer', 'cancellation', 'provider_failed', 'provider_refused',
    'provider_invalid_output', 'duplicate_outcome', 'stale_outcome', 'foreign_goal_outcome',
    'cancel_timer', 'terminal_timer', 'early_work', 'ga_missing_source', 'ga_foreign_source',
    'ga_duplicate_mapping', 'gi_forbidden_how', 'gi_duplicate_ref', 'gi_bad_source',
    'gi_unknown_binding', 'plan_wrong_parameter', 'plan_missing_parameter',
    'plan_foreign_goal', 'plan_unknown_capability', 'acquisition_false_completion',
    'multi_goal', 'multi_goal_omission', 'new_readiness_gap',
    'relative_readiness', 'ambiguous_readiness', 'new_timer_cancellation', 'new_timer_terminal',
    'readiness_missing_zone', 'readiness_invalid_date', 'readiness_missing_clock', 'readiness_foreign_source',
    'gi_depth_resolved', 'gi_depth_unresolved', 'speech_fast', 'speech_deep',
    'mixed_action_speech', 'speech_exact_quote', 'provider_timed_out', 'provider_cancelled',
    'runtime_disabled_provider', 'confirmation_denied', 'confirmation_granted', 'plan_duplicate_step',
    'plan_missing_outcome', 'plan_false_satisfaction', 'plan_invalid_argument_type', 'plan_unknown_argument',
    'plan_missing_timing', 'plan_conflicting_resource', 'ga_binding_mutation', 'ga_forbidden_how',
    'ga_unknown_target', 'cancel_after_completion',
)
VALUES = {'blink':(1,2,3,5,10), 'walk':(0.1,1,2,15,30), 'nod':(2,3,4,6,8), 'shake':(2,3,4,6,8)}
CAPABILITIES = {'blink':'soridormi.blink_eyes', 'walk':'soridormi.walk_forward', 'nod':'soridormi.nod_yes', 'shake':'soridormi.shake_no'}
NEW_FAMILIES = set(FAMILIES[30:]) | {'new_readiness_gap'}


def source_evidence(text, start=0, end=None):
    tokens = [t for t in _source_tokens(text) if t['start'] >= start and t['end'] <= (end or len(text))]
    return {'source_start_token_ref':tokens[0]['ref'], 'source_end_token_ref':tokens[-1]['ref']}


def action_text(action, value, form):
    number = str(value)
    en = f'walk forward for {number} seconds' if action == 'walk' else f"{dict(blink='blink', nod='nod', shake='shake your head')[action]} {number} times"
    zh = f'向前走{number}秒' if action == 'walk' else f"{dict(blink='眨眼', nod='点头', shake='摇头')[action]}{number}次"
    return (en.capitalize()+'.', f'Please {en}.', zh+'。', '请'+zh+'。', '请 '+en+'。')[form]


def _separate_interaction(case):
    """Freeze authored SC words beside, never inside, a Work model reply."""
    words = case.setdefault("social_cognition", {})
    for step in case["model_steps"]:
        if step.get("role", step["name"].split("-")[0]) not in {"fast", "deep"}:
            continue
        raw = step["response"]
        if "social_fixture_text" in raw:
            words[step["name"]] = raw.pop("social_fixture_text") or "Fixture response."
        raw.pop("auxiliary_activities", None)
        for outcome in raw.get("goal_outcomes", {}).values():
            outcome.pop("social_fixture_text", None)
            if outcome.get("disposition") == "respond":
                outcome.setdefault("precedes_step_ids", [])
                outcome.setdefault("follows_step_ids", [])
    return case


def reference_case(family, action, value_index, form):
    """Assemble authored primary results, never fit an oracle to a runtime verdict."""
    if family in NEW_FAMILIES:
        return extended_case(family, action, value_index, form)
    delayed = family in {'retained_timer','cancel_timer','terminal_timer','early_work'}
    conditional = family in {'conditional_rain','conditional_dry','acquisition_false_completion'}
    seed = 'delayed' if delayed else 'conditional-dry' if family == 'conditional_dry' else 'conditional-rain' if conditional else 'cancellation' if family == 'cancellation' else 'normal'
    case = json.loads((SEEDS/f'workflow-{seed}.json').read_text())
    value = VALUES[action][value_index]
    zh = form in {2,3}
    language = 'zh-CN' if zh else 'en-US' if form in {0,1} else 'auto'
    capability = CAPABILITIES[action]
    argument = 'duration_s' if action == 'walk' else 'count'
    binding = 'duration' if action == 'walk' else 'count'
    bound_value = value if action != 'walk' else f'{value}秒' if zh else f'{value} seconds'
    original = action_text(action, value, form)
    text = original
    location = ('Hangzhou','Beijing','Shanghai','Shenzhen','Chengdu')[value_index]
    if conditional:
        text = f'如果{location}预报有雨，就{original}' if zh else f'If rain is forecast in {location}, {original}'
    if delayed:
        text = '继续之前安排的任务。' if zh else 'Continue the previously scheduled task.'
    sid = f'workflow-{family}-{action}-{value_index}-{form}'
    case.update(id=sid, input={'sid':sid,'text':text,'language':language},
        coverage_family=family, contrast_set=f'{action}-{value_index}',
        split=('train_candidate' if value_index < 3 else 'development' if value_index == 3 else 'held_out'),
        training_eligible=False, reference_review='Astra-authored parameterized reference; non-independent review',
        expected_verdict='complete', parameters={'action':action,'value':value,'form':form},
        semantic_dimensions=['source ownership','parameter conservation','stage/Goal separation','terminal evidence'],
        forbidden_outcomes=['unbound or early effect','wrong parameter','unsupported completion'],
        acceptable_variation='Meaning-equivalent role outputs need separately reviewed replay branches; exact text is not a model-quality oracle.')
    case['provenance'].update(authoring_method='GPT-6 Astra authored 60 contrasts; deterministic 4 actions × 5 values × 5 language forms expansion',
        independent_inference_per_case=False, training_eligible=False)
    case['initial_planner'] = 'deep' if conditional or family in {'normal_deep','plan_missing_parameter','plan_wrong_parameter','plan_foreign_goal','plan_unknown_capability','multi_goal','multi_goal_omission','early_work'} else 'fast'
    # Use the existing provider-owned catalog, including duration semantics.
    common = json.loads((ROOT/'benchmarks/datasets/fast_planner_daily_life/catalogs/common_v1.json').read_text())['capabilities']
    case['catalog'] = [c for c in common if c['capability_id'] in {'chromie.weather.lookup','soridormi.blink_eyes','soridormi.walk_forward'}]
    # Controlled, reduced contracts retain paired Soridormi nod/shake count bounds
    # (configs/skills/open_duck_mini_v2_skills.json at 284273bc). Not registry/robot proof.
    for gesture in ('nod', 'shake'):
        catalog_entry = copy.deepcopy(next(c for c in common if c['capability_id'] == 'soridormi.blink_eyes'))
        catalog_entry.update(capability_id=CAPABILITIES[gesture], description=f'Perform the requested {gesture} head gesture an exact number of times.')
        catalog_entry['input_schema']['properties']['count'].update(minimum=2, maximum=8)
        catalog_entry['exclusive_group'] = 'body.head_pose'
        catalog_entry['resource_claims'] = ['body.head_pose']
        case['catalog'].append(catalog_entry)
        case['provider_schemas'][CAPABILITIES[gesture]] = copy.deepcopy(case['provider_schemas']['soridormi.blink_eyes'])
        case['provider_outputs'][CAPABILITIES[gesture]] = {'completed':True}
    case['provider_schemas']['soridormi.walk_forward'] = copy.deepcopy(case['provider_schemas']['soridormi.blink_eyes'])
    case['provider_outputs']['soridormi.walk_forward'] = {'completed':True}
    gi = case['model_steps'][0]['response']
    responsibility = gi['responsibilities'][0]
    responsibility.update(outcome=text.rstrip('.。'), source_evidence=source_evidence(text),
        binding_items={binding:bound_value, **({'location':location} if conditional else {})})
    ga = case['model_steps'][1]['response']
    bindings = [{'name':binding,'entity_type':binding,'value':str(bound_value),'confidence':1.0}]
    if action == 'walk':
        direction = '向前' if zh else 'forward'
        responsibility['binding_items']['direction'] = direction
        bindings.append({'name':'direction','entity_type':'direction','value':direction,'confidence':1.0})
    if conditional:
        bindings.append({'name':'location','entity_type':'location','value':location,'confidence':1.0})
    bindings.sort(key=lambda item: list(responsibility['binding_items']).index(item['name']))
    if ga.get('new_goals'):
        ga['new_goals'][0]['bindings'] = bindings
    if delayed:
        prior = case['initial_goal_resolution']['new_goals'][0]
        prior.update(description=original+' Ready at 2099-09-04T19:00:00+08:00; never earlier.',
            source_text=original+' Ready at 2099-09-04T19:00:00+08:00; never earlier.')
        readiness = prior['object']['bindings']['ready_at']
        prior['object']['bindings'] = {**{b['name']:b for b in bindings}, 'ready_at':readiness}
    for step in case['model_steps']:
        step.pop('request', None)
        role = step['name'].split('-')[0]
        if role in {'fast','deep'}:
            source_step_name = step['name']
            role = case['initial_planner'] if step['name'].endswith('initial') else role
            step['name'] = role + '-' + step['name'].split('-',1)[1]
            raw = step['response']
            raw.setdefault('social_fixture_text', case.get('social_cognition', {}).get(source_step_name, ''))
            raw['goal_summary'] = 'Honor the admitted action, parameter, and any condition or readiness.'
            for work in raw['steps']:
                if work['capability_id'] == 'soridormi.blink_eyes':
                    work.update(capability_id=capability, args={argument:value}, expected_outcome='The requested action and exact parameter are completed.')
                elif work['capability_id'] == 'chromie.weather.lookup':
                    work['args']['location'] = location
            if family == 'conditional_dry' and not zh and raw['social_fixture_text']:
                raw['social_fixture_text'] = 'No rain is forecast, so I will not perform the requested action.'
                raw['goal_outcomes']['${goal}']['social_fixture_text'] = raw['social_fixture_text']
            if zh and raw['social_fixture_text']:
                raw['social_fixture_text'] = '我会保留任务，等到指定时间再执行。' if delayed else '预报没有雨，因此这次无需执行该动作。'
                raw['goal_outcomes']['${goal}']['social_fixture_text'] = raw['social_fixture_text']
        step['role'] = role
    case['expected_provider_calls'] = [
        {'capability':'chromie.weather.lookup','args':{'location':location}}
    ] if conditional else []
    if family != 'conditional_dry':
        case['expected_provider_calls'].append({'capability':capability,'args':{argument:value}})

    if family.startswith('provider_') or family in {'duplicate_outcome','stale_outcome','foreign_goal_outcome','cancel_timer','terminal_timer'}:
        case['probe'] = family
    if family == 'provider_failed': case['provider_status'] = 'failed'
    if family == 'provider_refused': case['provider_status'] = 'refused'
    if family == 'provider_invalid_output': case['provider_outputs'][capability] = {'completed':'not a boolean'}
    if family in {'cancel_timer','terminal_timer'}:
        case['model_steps'] = case['model_steps'][:3]
    if family == 'cancel_timer':
        followup = '取消刚才安排的任务。' if zh else 'Cancel that scheduled task.'
        case['followup'] = {'sid':sid+'-cancel','text':followup,'language':language}
        cancelled = copy.deepcopy(gi)
        cancelled['responsibilities'][0].update(outcome=followup.rstrip('.。'), relationship='cancel',
            binding_items={}, source_evidence=source_evidence(followup))
        association = GoalAssociationModelOutput.model_validate({'confidence':1.0, 'associations':[{
            'relationship':'cancel','source_responsibility_refs':['r1'],'target_goal_ids':['scheduled-blink'],
            'confidence':1.0,'reason_summary':'Cancel the explicitly referenced scheduled Goal.'}]}).model_dump(mode='json')
        case['model_steps'] += [{'name':'gi-cancel','role':'gi','response':cancelled}, {'name':'ga-cancel','role':'ga','response':association}]
    if family == 'early_work':
        raw = json.loads((SEEDS/'workflow-normal.json').read_text())['model_steps'][2]['response']
        raw['steps'][0].update(capability_id=capability,args={argument:value})
        case['model_steps'][2]['response'] = raw
        reject(case, 'deep')
    if family.startswith('gi_'):
        if family == 'gi_forbidden_how': responsibility['capability_id'] = capability
        if family == 'gi_duplicate_ref': gi['responsibilities'].append(copy.deepcopy(responsibility))
        if family == 'gi_bad_source': responsibility['source_evidence']['source_end_token_ref'] = 't9999'
        if family == 'gi_unknown_binding': responsibility['binding_items']['invented_owner_field'] = 'unsupported'
        reject(case,'gi')
    if family.startswith('ga_'):
        if family == 'ga_missing_source': ga['new_goals'][0]['source_responsibility_refs'] = []
        if family == 'ga_foreign_source': ga['new_goals'][0]['source_responsibility_refs'] = ['r-foreign']
        if family == 'ga_duplicate_mapping': ga['new_goals'].append(copy.deepcopy(ga['new_goals'][0]))
        reject(case,'ga')
    if family.startswith('plan_'):
        raw = case['model_steps'][2]['response']
        if family == 'plan_wrong_parameter': raw['steps'][0]['args'][argument] = value + 1
        if family == 'plan_missing_parameter': raw['steps'][0]['args'].pop(argument)
        if family == 'plan_foreign_goal': raw['steps'][0]['source_goal_ids'] = ['foreign_goal']
        if family == 'plan_unknown_capability': raw['steps'][0]['capability_id'] = 'undeclared.action'
        if family == 'plan_unknown_capability': case['allow_nonexecuting_rejection'] = True
        reject(case,'deep')
    if family == 'acquisition_false_completion':
        raw = case['model_steps'][2]['response']
        for sat in (raw['goal_satisfaction'],raw['goal_outcomes']['${goal}']['satisfaction']):
            sat.update(score=1.0, status='exact', satisfied_goal_ids=['${goal}'], unmet_goal_ids=[], unmet_requirements=[])
        reject(case,'deep')
    if family in {'multi_goal','multi_goal_omission'}:
        second_action = 'walk' if action == 'blink' else 'blink'
        second_value = VALUES[second_action][value_index]
        second = action_text(second_action,second_value,form)
        text = original+' '+second
        case['input']['text'] = text
        responsibility.update(outcome=original.rstrip('.。'), source_evidence=source_evidence(text,end=len(original)))
        other = copy.deepcopy(responsibility)
        second_binding = 'duration' if second_action == 'walk' else 'count'
        second_bound = f'{second_value}秒' if zh else f'{second_value} seconds'
        second_bound = second_value if second_action == 'blink' else second_bound
        other.update(local_ref='r2',outcome=second.rstrip('.。'), source_evidence=source_evidence(text,start=len(original)+1), binding_items={second_binding:second_bound})
        if second_action == 'walk': other['binding_items']['direction'] = '向前' if zh else 'forward'
        gi['responsibilities'].append(other)
        extra = copy.deepcopy(ga['new_goals'][0])
        extra.update(source_responsibility_refs=['r2'], bindings=[{'name':second_binding,'entity_type':second_binding,'value':str(second_bound),'confidence':1.0}])
        if second_action == 'walk': extra['bindings'].append({'name':'direction','entity_type':'direction','value':other['binding_items']['direction'],'confidence':1.0})
        ga['new_goals'].append(extra)
        raw = case['model_steps'][2]['response']
        work = copy.deepcopy(raw['steps'][0])
        second_capability = 'soridormi.blink_eyes' if second_action == 'blink' else 'soridormi.walk_forward'
        work.update(step_id='second-action', capability_id=second_capability,
            args={('count' if second_action == 'blink' else 'duration_s'):second_value}, source_goal_ids=['${goal2}'])
        raw['steps'].append(work)
        extra_outcome = json.loads(json.dumps(raw['goal_outcomes']['${goal}']).replace('${goal}','${goal2}'))
        extra_outcome['step_ids'] = ['second-action']
        raw['goal_outcomes']['${goal2}'] = extra_outcome
        raw['goal_satisfaction']['satisfied_goal_ids'].append('${goal2}')
        case['expected_provider_calls'].append({'capability':second_capability,'args':work['args']})
        if family == 'multi_goal_omission':
            del raw['goal_outcomes']['${goal2}']
            reject(case,'deep')
    for index, step in enumerate(case['model_steps']):
        if step['role'] == 'gi':
            step['required_prompt_fragments'] = [case.get('followup',case['input'])['text'] if step['name'] == 'gi-cancel' else case['input']['text']]
        elif step['role'] in {'fast','deep'}:
            step['required_prompt_fragments'] = ['${goal}'] + (['${goal2}'] if family in {'multi_goal','multi_goal_omission'} else [])
        step['fixture_kind'] = (
            'fault_injection' if case.get('expected_rejection') and index == len(case['model_steps'])-1 else
            'authored_reference'
        )
        step['training_eligible'] = False
    return _separate_interaction(case)


def _speech_plan(raw, text, *, clarify=False):
    raw.update(disposition='clarify' if clarify else 'respond', steps=[], social_fixture_text=text)
    outcome = raw['goal_outcomes']['${goal}']
    outcome.update(disposition=raw['disposition'], step_ids=[], social_fixture_text=text)
    if clarify:
        raw['coverage'] = outcome['coverage'] = 'partial'
        raw['unresolved'] = outcome['unresolved'] = ['The requested time or referent is not determined.']
        for sat in (raw['goal_satisfaction'],outcome['satisfaction']):
            sat.update(score=0.0, status='unsatisfied', satisfied_goal_ids=[], unmet_goal_ids=['${goal}'],
                unmet_requirements=['The user must supply the missing time or referent.'])
    return raw


def extended_case(family, action, value_index, form):
    """Additional authored state/authority contrasts; references precede execution."""
    base = 'multi_goal' if family == 'plan_conflicting_resource' else 'normal_deep' if family.startswith('plan_') or family in {'speech_deep','mixed_action_speech'} else 'normal_fast'
    case = reference_case(base, action, value_index, form)
    old_id = case['id']
    case = json.loads(json.dumps(case).replace(old_id, old_id.replace(base,family)))
    case.update(coverage_family=family)
    gi, ga, raw = [step['response'] for step in case['model_steps']]
    responsibility = gi['responsibilities'][0]
    value = VALUES[action][value_index]
    argument = 'duration_s' if action == 'walk' else 'count'
    cap = CAPABILITIES[action]
    zh = form in {2,3}
    original = case['input']['text']
    temporal = family in {'new_readiness_gap','relative_readiness','new_timer_cancellation','new_timer_terminal'} or family.startswith('readiness_')
    if temporal:
        instant = '2099-09-04T19:00:00+08:00'
        scope = instant
        if family in {'relative_readiness','readiness_missing_clock','readiness_foreign_source'}:
            scope = '五分钟后' if zh else 'in five minutes'
            instant = '2026-09-04T00:05:00+00:00'
            # Controlled clock is 2026-09-04T00:00Z. Receipt is a trusted Gateway
            # fact; it provides an elapsed-time origin, not the user's local zone.
            case['input']['context'] = {'user_turn_envelope':{'received_at':'2026-09-04T00:00:00+00:00'}}
        text = original.rstrip('.。') + ('，在'+scope+'执行。' if zh else ' '+('at ' if scope == instant else '')+scope+'.')
        case['input']['text'] = text
        responsibility.update(outcome=text.rstrip('.。'), source_evidence=source_evidence(text))
        responsibility['binding_items']['ready_at'] = instant
        if scope != instant: responsibility['binding_items']['time_scope'] = scope
        if family == 'readiness_missing_zone': responsibility['binding_items']['ready_at'] = '2099-09-04T19:00:00'
        if family == 'readiness_invalid_date': responsibility['binding_items']['ready_at'] = '2099-02-30T19:00:00+08:00'
        if family == 'readiness_missing_clock': case['input'].pop('context')
        if family == 'readiness_foreign_source': responsibility['binding_items']['time_scope'] = 'at a time never stated'
        ga['new_goals'][0]['bindings'] = [{'name':key,'entity_type':key,'value':str(val),'confidence':1.0} for key,val in responsibility['binding_items'].items()]
        if family.startswith('readiness_'):
            reject(case,'gi')
        else:
            from datetime import datetime
            wait = json.loads((SEEDS/'workflow-delayed.json').read_text())['model_steps'][2]
            wait.pop('request',None)
            wait.update(role='fast')
            wait['response']['time_conditions'][0]['due_at_ms'] = int(datetime.fromisoformat(instant).timestamp()*1000)
            if zh:
                wait['response']['social_fixture_text'] = wait['response']['goal_outcomes']['${goal}']['social_fixture_text'] = '我会等到指定时间再执行。'
            case['model_steps'] = case['model_steps'][:2] + [wait]
            case.update(family='delayed', initial_goal_resolution=None, expected_ready_at=instant,
                scope='New admitted request: primary GI → GA → wait → restart → due wake → actual controlled Runtime.')
            if family in {'new_timer_cancellation','new_timer_terminal'}:
                case['probe'] = 'cancel_timer' if family == 'new_timer_cancellation' else 'terminal_timer'
                if family == 'new_timer_cancellation':
                    followup = '取消刚才安排的任务。' if zh else 'Cancel that scheduled task.'
                    case['followup'] = {'sid':case['id']+'-cancel','text':followup,'language':case['input']['language']}
                    cancelled = copy.deepcopy(gi)
                    cancelled['responsibilities'][0].update(outcome=followup.rstrip('.。'), relationship='cancel',
                        target_goal_ids=['${goal}'], binding_items={}, source_evidence=source_evidence(followup))
                    association = GoalAssociationModelOutput.model_validate({'confidence':1.0,'associations':[{
                        'relationship':'cancel','source_responsibility_refs':['r1'],'target_goal_ids':['${goal}'],
                        'confidence':1.0,'reason_summary':'Cancel the explicitly referenced newly scheduled Goal.'}]}).model_dump(mode='json')
                    case['model_steps'] += [{'name':'gi-cancel','role':'gi','response':cancelled},{'name':'ga-cancel','role':'ga','response':association}]
            else:
                case['model_steps'].append({'name':'fast-due','role':'fast','response':raw})
    elif family in {'ambiguous_readiness','gi_depth_resolved','gi_depth_unresolved'}:
        if family == 'ambiguous_readiness':
            scope = '明天七点' if zh else 'tomorrow at seven'
            text = original.rstrip('.。') + ('，'+scope+'执行。' if zh else ' '+scope+'.')
            case['input']['text'] = text
            responsibility.update(outcome=text.rstrip('.。'), source_evidence=source_evidence(text))
            responsibility['binding_items']['time_scope'] = scope
            ga['new_goals'][0]['bindings'].append({'name':'time_scope','entity_type':'time_scope','value':scope,'confidence':1.0})
            unresolved = 'The requested local calendar time lacks a timezone and AM/PM.'
        elif family == 'gi_depth_unresolved':
            text = ('对那个做这个动作：' if zh else 'Do this action to that one: ') + original
            case['input']['text'] = text
            responsibility.update(outcome=text.rstrip('.。'), source_evidence=source_evidence(text))
            unresolved = 'The referent of that one is absent from the supplied context.'
        else:
            unresolved = 'Primary cognition is uncertain whether the explicit quantity denotes the requested action parameter.'
        gi['unresolved'] = [unresolved]
        deeper = copy.deepcopy(gi)
        if family == 'gi_depth_resolved': deeper['unresolved'] = []
        else:
            _speech_plan(raw, '请说明具体时间和时区。' if family == 'ambiguous_readiness' and zh else 'Please specify the time, timezone and AM or PM.' if family == 'ambiguous_readiness' else '你指的是哪个对象？' if zh else 'Which one do you mean?', clarify=True)
            case.update(probe='clarification', expected_goal_status='open', expected_provider_calls=[])
        case['model_steps'].insert(1,{'name':'gi-deep','role':'gi','response':deeper})
    elif family in {'speech_fast','speech_deep','speech_exact_quote','mixed_action_speech'}:
        names = {'blink':('眨眼','blinking'), 'walk':('向前走','walking forward'), 'nod':('点头','nodding'), 'shake':('摇头','shaking your head')}
        descriptions = {'blink':('眨眼是短暂闭上再睁开眼睛。','Blinking means briefly closing and reopening the eyes.'),
            'walk':('向前走是朝面向的方向移动。','Walking forward means moving in the direction you face.'),
            'nod':('点头是上下移动头部。','Nodding means moving the head up and down.'),
            'shake':('摇头是左右移动头部。','Shaking your head means moving the head from side to side.')}
        quote = f'今天练习{names[action][0]}，编号{value}。' if zh else f'Today we practice {names[action][1]}, item {value}.'
        reply = descriptions[action][0 if zh else 1]
        asks = f'请说“{reply}”' if zh else f'Please say "{reply}"'
        if family == 'speech_exact_quote':
            asks = f'请原样说出“{quote}”' if zh else f'Say exactly "{quote}"'
            reply = quote
        elif family != 'mixed_action_speech':
            reply = quote
            asks = f'请说“{quote}”' if zh else f'Please say "{quote}"'
        if family == 'mixed_action_speech':
            text = original+' '+asks
            case['input']['text'] = text
            responsibility.update(source_evidence=source_evidence(text,end=len(original)))
            other = copy.deepcopy(responsibility)
            other.update(local_ref='r2', outcome=asks, output_mode='speech',binding_items={'proposition':reply},source_evidence=source_evidence(text,start=len(original)+1))
            gi['responsibilities'].append(other)
            extra = copy.deepcopy(ga['new_goals'][0])
            extra.update(source_responsibility_refs=['r2'],output_mode='speech',bindings=[{'name':'proposition','entity_type':'proposition','value':reply,'confidence':1.0}])
            ga['new_goals'].append(extra)
            extra_outcome = copy.deepcopy(raw['goal_outcomes']['${goal}'])
            extra_outcome.update(disposition='respond',step_ids=[],social_fixture_text=reply)
            extra_outcome['satisfaction']['satisfied_goal_ids'] = ['${goal2}']
            raw['goal_outcomes']['${goal2}'] = extra_outcome
            raw['goal_satisfaction']['satisfied_goal_ids'].append('${goal2}')
            raw['social_fixture_text'] = reply
            raw['disposition'] = 'mixed'
        else:
            case['input']['text'] = asks
            output_mode = 'speech'
            speech_bindings = {'proposition':reply}
            responsibility.update(outcome=asks, output_mode=output_mode,binding_items=speech_bindings,source_evidence=source_evidence(asks))
            ga['new_goals'][0].update(output_mode=output_mode,bindings=[{'name':key,'entity_type':key,'value':str(val),'confidence':1.0} for key,val in speech_bindings.items()])
            _speech_plan(raw,reply)
            case['expected_provider_calls'] = []
        case['expected_speech'] = reply
    elif family in {'provider_timed_out','provider_cancelled'}:
        case.update(probe=family, provider_status=family.removeprefix('provider_'))
    elif family in {'runtime_disabled_provider','confirmation_denied','confirmation_granted','cancel_after_completion'}:
        case['probe'] = family
        if family.startswith('confirmation_'):
            next(c for c in case['catalog'] if c['capability_id']==cap)['requires_confirmation'] = True
            raw['user_confirmation_required'] = True
            raw['social_fixture_text'] = ('确认执行这个动作吗？' if zh else 'Do you confirm this action?')
    elif family.startswith('plan_'):
        work = raw['steps'][0]
        if family == 'plan_duplicate_step': raw['steps'].append(copy.deepcopy(work))
        if family == 'plan_missing_outcome':
            if form in {1,3}: raw.pop('goal_outcomes')
            else: raw['goal_outcomes'] = {}
        if family == 'plan_false_satisfaction': _speech_plan(raw,'Done.')
        if family == 'plan_invalid_argument_type': work['args'][argument] = 'not-a-number'
        if family == 'plan_unknown_argument':
            work['args']['unowned_argument'] = 1
            case['allow_nonexecuting_rejection'] = True
        if family == 'plan_missing_timing': work.pop('timing')
        if family == 'plan_conflicting_resource':
            for step in raw['steps']:
                step['timing'] = 'parallel'
                entry = next(c for c in case['catalog'] if c['capability_id'] == step['capability_id'])
                entry['can_run_parallel'] = True
                entry['resource_claims'] = ['body.primary_motion']
                entry['exclusive_group'] = 'body.primary_motion'
            raw['parameter_resolutions'] = [{'step_id':step['step_id'],'parameter':name,'strategy':'user_supplied',
                'value':number,'confidence':1.0,'blocking':False,'rationale':'Preserve the explicit action parameter.',
                'source_goal_ids':step['source_goal_ids']} for step in raw['steps'] for name,number in step['args'].items()]
        reject(case,'deep')
        if family == 'plan_conflicting_resource':
            case['allow_nonexecuting_rejection'] = True
            case['expected_validation_feedback'] = 'parallel_resource_claim_conflict'
    elif family.startswith('ga_'):
        if family == 'ga_binding_mutation': ga['new_goals'][0]['bindings'][0]['value'] = '999'
        if family == 'ga_forbidden_how': ga['new_goals'][0]['capability_id'] = cap
        if family == 'ga_unknown_target': ga['new_goals'][0]['supersedes_goal_ids'] = ['foreign-goal']
        reject(case,'ga')
    else:
        raise ValueError(f'Unimplemented authored family: {family}')
    for index,step in enumerate(case['model_steps']):
        step.pop('request',None)
        step['required_prompt_fragments'] = [case['followup']['text'] if step['name']=='gi-cancel' else case['input']['text']] if step['role']=='gi' else ['${goal}'] if step['role'] in {'fast','deep'} else []
        step['fixture_kind'] = 'fault_injection' if case.get('expected_rejection') and index==len(case['model_steps'])-1 else 'authored_reference'
        step['training_eligible'] = False
    return _separate_interaction(case)


def reject(case, role):
    case['probe'] = case['coverage_family']
    case['expected_rejection'] = role
    if case['expected_verdict'] != 'known_contract_gap': case['expected_verdict'] = 'expected_rejection'
    case['model_steps'] = case['model_steps'][:{'gi':1,'ga':2,'deep':3,'fast':3}[role]]


def cases():
    for family in FAMILIES:
        for action in VALUES:
            for value_index in range(5):
                for form in range(5):
                    yield reference_case(family,action,value_index,form)


def freeze_capture(capture_root: Path, output: Path):
    """Publish reviewed authoring captures without deleting failed scenarios."""
    output.mkdir(parents=True, exist_ok=False)
    artifacts = output/'artifacts'
    artifacts.mkdir()
    identities = {}
    missing = []
    for path in sorted(capture_root.glob('workflow-*/case.json')):
        case = json.loads(path.read_text())
        for step in case['model_steps']:
            if 'request' not in step:
                step['request_unavailable'] = 'Production stopped before rendering/invoking this planned model step; retain its authored expected response.'
                missing.append({'case':case['id'],'step':step['name']})
                continue
            request = step['request']
            def artifact(value):
                raw = encoded(value)
                digest = hashlib.sha256(raw).hexdigest()
                target = artifacts/f'{digest}.json'
                if not target.exists(): target.write_bytes(raw)
                return {'$artifact':digest}
            request['format'] = artifact(request['format'])
            for message in request['messages']:
                if message['role'] == 'system': message['content'] = artifact(message['content'])
        raw = (json.dumps(case,ensure_ascii=False,indent=2)+'\n').encode()
        filename = case['id']+'.json'
        (output/filename).write_bytes(raw)
        identities[filename] = hashlib.sha256(raw).hexdigest()
    manifest = {'schema_version':2,'count':len(identities),'families':list(FAMILIES),
        'author_model':'gpt-6-astra','authoring_method':'60 authored contrasts, expanded over 4 actions × 5 values × 5 language forms',
        'independent_review':False,'independent_inference_per_case':False,'training_eligible':False,
        'model_ability_evaluated':False,'splits':{'train_candidate':3600,'development':1200,'held_out':1200},
        'contrast_split_rule':'All languages and fault/positive relatives for one action/value stay together.',
        'case_sha256':identities, 'unrendered_requests':missing,
        'artifact_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(artifacts.glob('*.json'))}}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest
