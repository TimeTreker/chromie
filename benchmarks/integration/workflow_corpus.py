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
)
VALUES = {'blink':(1,2,3,5,10), 'walk':(0.1,1,2,15,30)}


def source_evidence(text, start=0, end=None):
    tokens = [t for t in _source_tokens(text) if t['start'] >= start and t['end'] <= (end or len(text))]
    return {'source_start_token_ref':tokens[0]['ref'], 'source_end_token_ref':tokens[-1]['ref']}


def action_text(action, value, form):
    number = str(value)
    en = f'blink {number} times' if action == 'blink' else f'walk forward for {number} seconds'
    zh = f'眨眼{number}次' if action == 'blink' else f'向前走{number}秒'
    return (en.capitalize()+'.', f'Please {en}.', zh+'。', '请'+zh+'。', '请 '+en+'。')[form]


def reference_case(family, action, value_index, form):
    """Assemble authored primary results, never fit an oracle to a runtime verdict."""
    delayed = family in {'retained_timer','cancel_timer','terminal_timer','early_work'}
    conditional = family in {'conditional_rain','conditional_dry','acquisition_false_completion'}
    seed = 'delayed' if delayed else 'conditional-dry' if family == 'conditional_dry' else 'conditional-rain' if conditional else 'cancellation' if family == 'cancellation' else 'normal'
    case = json.loads((SEEDS/f'workflow-{seed}.json').read_text())
    value = VALUES[action][value_index]
    zh = form in {2,3}
    language = 'zh-CN' if zh else 'en-US' if form in {0,1} else 'auto'
    capability = 'soridormi.blink_eyes' if action == 'blink' else 'soridormi.walk_forward'
    argument = 'count' if action == 'blink' else 'duration_s'
    binding = 'count' if action == 'blink' else 'duration'
    bound_value = value if action == 'blink' else f'{value}秒' if zh else f'{value} seconds'
    original = action_text(action, value, form)
    text = original
    location = ('Hangzhou','Beijing','Shanghai','Shenzhen','Chengdu')[value_index]
    if conditional:
        text = f'如果{location}预报有雨，就{original}' if zh else f'If rain is forecast in {location}, {original}'
    if delayed:
        text = '继续之前安排的任务。' if zh else 'Continue the previously scheduled task.'
    if family == 'new_readiness_gap':
        text = original.rstrip('.。') + ('，在2099-09-04T19:00:00+08:00执行。' if zh else ' at 2099-09-04T19:00:00+08:00.')
    sid = f'workflow-{family}-{action}-{value_index}-{form}'
    case.update(id=sid, input={'sid':sid,'text':text,'language':language},
        coverage_family=family, contrast_set=f'{action}-{value_index}',
        split=('train_candidate' if value_index < 3 else 'development' if value_index == 3 else 'held_out'),
        training_eligible=False, reference_review='Astra-authored parameterized reference; non-independent review',
        expected_verdict='complete', parameters={'action':action,'value':value,'form':form},
        semantic_dimensions=['source ownership','parameter conservation','stage/Goal separation','terminal evidence'],
        forbidden_outcomes=['unbound or early effect','wrong parameter','unsupported completion'],
        acceptable_variation='Meaning-equivalent role outputs need separately reviewed replay branches; exact text is not a model-quality oracle.')
    case['provenance'].update(authoring_method='GPT-6 Astra authored 30 contrasts; deterministic 2 actions × 5 values × 5 language forms expansion',
        independent_inference_per_case=False, training_eligible=False)
    case['initial_planner'] = 'deep' if conditional or family in {'normal_deep','plan_missing_parameter','plan_wrong_parameter','plan_foreign_goal','plan_unknown_capability','multi_goal','multi_goal_omission','early_work'} else 'fast'
    # Use the existing provider-owned catalog, including duration semantics.
    common = json.loads((ROOT/'benchmarks/datasets/fast_planner_daily_life/catalogs/common_v1.json').read_text())['capabilities']
    case['catalog'] = [c for c in common if c['capability_id'] in {'chromie.weather.lookup','soridormi.blink_eyes','soridormi.walk_forward'}]
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
            role = case['initial_planner'] if step['name'].endswith('initial') else role
            step['name'] = role + '-' + step['name'].split('-',1)[1]
            raw = step['response']
            raw['goal_summary'] = 'Honor the admitted action, parameter, and any condition or readiness.'
            for work in raw['steps']:
                if work['capability_id'] == 'soridormi.blink_eyes':
                    work.update(capability_id=capability, args={argument:value}, expected_outcome='The requested action and exact parameter are completed.')
                elif work['capability_id'] == 'chromie.weather.lookup':
                    work['args']['location'] = location
            if zh and raw['response_text']:
                raw['response_text'] = '我会保留任务，等到指定时间再执行。' if delayed else '预报没有雨，因此这次无需执行该动作。'
                raw['goal_outcomes']['${goal}']['response_text'] = raw['response_text']
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
    if family.startswith('gi_') or family == 'new_readiness_gap':
        if family == 'gi_forbidden_how': responsibility['capability_id'] = capability
        if family == 'gi_duplicate_ref': gi['responsibilities'].append(copy.deepcopy(responsibility))
        if family == 'gi_bad_source': responsibility['source_evidence']['source_end_token_ref'] = 't9999'
        if family == 'gi_unknown_binding': responsibility['binding_items']['invented_owner_field'] = 'unsupported'
        if family == 'new_readiness_gap':
            responsibility['binding_items']['ready_at'] = '2099-09-04T19:00:00+08:00'
            case['expected_verdict'] = 'known_contract_gap'
            case['known_issue'] = 60
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
            'desired_unrepresentable_result' if family == 'new_readiness_gap' else
            'fault_injection' if case.get('expected_rejection') and index == len(case['model_steps'])-1 else
            'authored_reference'
        )
        step['training_eligible'] = False
    return case


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
        'author_model':'gpt-6-astra','authoring_method':'30 authored contrasts, expanded over 2 actions × 5 values × 5 language forms',
        'independent_review':False,'independent_inference_per_case':False,'training_eligible':False,
        'model_ability_evaluated':False,'splits':{'train_candidate':900,'development':300,'held_out':300},
        'contrast_split_rule':'All languages and fault/positive relatives for one action/value stay together.',
        'case_sha256':identities, 'unrendered_requests':missing,
        'artifact_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(artifacts.glob('*.json'))}}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest
