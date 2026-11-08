"""Hosted composition of shared Processor SDK operations; no filesystem store."""
from __future__ import annotations

import json

from osii.model_endpoints import endpoint_from_environment
from osii.processor_sdk import (ProcessorClient, ProcessorDescriptor, ProcessorKind, SynthesisRequest,
    EnrichmentRequest, SynthesisResponse, EnrichmentResponse)
from osii.processors.text import (LocalExtractivePreviewSynthesizer, LocalStatsKeywordsEnricher,
    chat_synthesizer_descriptor, synthesis_prompt, model_synthesis_response)

BUILTINS = {p.descriptor.name: p for p in (LocalExtractivePreviewSynthesizer(), LocalStatsKeywordsEnricher())}
MODEL_SYNTHESIS = chat_synthesizer_descriptor()
MAX_INPUT_CHARS = 200_000


class ProcessorError(ValueError):
    """Safe operator diagnostics, without processor bodies or model credentials."""


def configured_urls(store, settings) -> list[str]:
    return validate_urls(store.setting('processor_endpoints', {'urls': list(settings.processor_urls)})['urls'])


def validate_urls(urls: list[str]) -> list[str]:
    if len(urls) > 16:
        raise ValueError('Configure at most 16 Processor API endpoints')
    result = []
    for value in urls:
        endpoint = endpoint_from_environment('chat', environment={'OSII_CHAT_BASE_URL': value})
        if not endpoint.base_url:
            raise ValueError('Processor endpoint must have an HTTP(S) address')
        result.append(endpoint.base_url)
    return list(dict.fromkeys(result))


def catalog(store, settings) -> list[dict]:
    rows = []
    descriptors = [(p.descriptor, '') for p in BUILTINS.values()] + [(MODEL_SYNTHESIS, '')]
    for url in configured_urls(store, settings):
        try:
            descriptor = ProcessorClient(url, timeout=3).descriptor()
            descriptors.append((descriptor, url))
        except Exception:
            rows.append({'id': url, 'display_name': url, 'kind': 'unavailable', 'available': False,
                         'detail': 'Processor descriptor could not be read', 'base_url': url})
    names = {}
    for descriptor, url in descriptors:
        name = descriptor.name
        if descriptor.kind not in {ProcessorKind.SYNTHESIZER, ProcessorKind.ENRICHER}:
            continue
        required = dict(descriptor.model_requirements)
        if name == MODEL_SYNTHESIS.name and not url:
            required = {'chat': 'required'}
        available = 'object' in descriptor.capabilities.scope_types
        detail = '' if available else 'This processor does not support individual documents'
        for capability, requirement in required.items():
            if requirement == 'required' and not store.configuration().get(capability + '_model'):
                available, detail = False, f'Select a {capability} model in Models first'
        row = {'id': name, 'display_name': descriptor.display_name, 'kind': descriptor.kind.value,
               'description': descriptor.description, 'available': available, 'detail': detail,
               'base_url': url, 'descriptor': descriptor.model_dump(mode='json'),
               'model_requirements': required}
        if name in names:
            row['available'], row['detail'] = False, 'Duplicate processor name; configure unique processor names'
            names[name]['available'], names[name]['detail'] = False, row['detail']
        names[name] = row
        rows.append(row)
    return rows


def resolve(rows: list[dict], name: str | None, kind: str) -> dict | None:
    if not name:
        return None
    matches = [row for row in rows if row.get('id') == name and row.get('kind') == kind]
    if len(matches) != 1 or not matches[0]['available']:
        raise ValueError(f'The selected {kind} is unavailable. Check processor connections and model selection.')
    return matches[0]


def bounded_config(config: dict, selection: dict | None = None) -> dict:
    if len(json.dumps(config)) > 16_000:
        raise ValueError('Processor configuration exceeds 16,000 characters')
    schema = (selection or {}).get('descriptor', {}).get('config_schema', {})
    properties = schema.get('properties', {})
    if schema.get('additionalProperties') is False and set(config) - set(properties):
        raise ValueError('Processor configuration contains unsupported settings')
    if set(schema.get('required', [])) - set(config):
        raise ValueError('Required processor settings are missing')
    import math
    for name, value in config.items():
        field = properties.get(name, {})
        kind = field.get('type')
        valid = {'string': isinstance(value, str), 'boolean': isinstance(value, bool),
                 'integer': type(value) is int, 'number': type(value) in (int, float),
                 'array': isinstance(value, list), 'object': isinstance(value, dict)}
        if kind in valid and not valid[kind]:
            raise ValueError(f'Invalid setting type: {name}')
        if type(value) in (int, float) and (not math.isfinite(value) or value < field.get('minimum', -math.inf) or value > field.get('maximum', math.inf)):
            raise ValueError(f'Setting is outside its allowed range: {name}')
        if 'enum' in field and value not in field['enum']:
            raise ValueError(f'Unsupported option for setting: {name}')
    return config


def validate_response(response, request, selection):
    expected = selection['descriptor']
    if response.request_id != request.request_id or response.processor.name != expected['name'] or response.processor.version != expected['version'] or response.processor.kind.value != selection['kind']:
        raise ProcessorError('Processor returned a mismatched request or identity')
    if len(response.model_dump_json()) > 4_000_000:
        raise ProcessorError('Processor output exceeds the 4 MiB hosted limit')
    allowed = {doc.file_id for doc in request.scope.documents}
    refs = response.citations if isinstance(response, SynthesisResponse) else []
    lengths = {doc.file_id: len(doc.text or '') for doc in request.scope.documents}
    for ref in refs:
        if ref.file_id and ref.file_id not in allowed:
            raise ProcessorError('Processor cited a document outside the requested scope')
        if ref.file_id and ((ref.char_start is not None and ref.char_start > lengths[ref.file_id]) or
                            (ref.char_end is not None and ref.char_end > lengths[ref.file_id]) or
                            (ref.char_start is not None and ref.char_end is not None and ref.char_start > ref.char_end)):
            raise ProcessorError('Processor citation falls outside the supplied text')
    def check_refs(value):
        if isinstance(value, dict):
            if value.get('file_id') and (not isinstance(value['file_id'], str) or value['file_id'] not in allowed):
                raise ProcessorError('Processor artifact referenced a document outside its requested scope')
            for child in value.values():
                check_refs(child)
        elif isinstance(value, list):
            for child in value:
                check_refs(child)
    if isinstance(response, EnrichmentResponse):
        for artifact in response.artifacts:
            check_refs(artifact.model_dump(mode='json'))
    return response


def invoke(store, settings, provider, selection: dict, request, *, job_id: str, worker: str):
    if sum(len(doc.text or '') for doc in request.scope.documents) > MAX_INPUT_CHARS:
        raise ProcessorError('Document exceeds the 200,000-character processor input limit')
    name, url = selection['id'], selection['base_url']
    if url:
        descriptor = ProcessorClient(url, timeout=3).descriptor()
        if descriptor.model_dump(mode='json') != selection['descriptor']:
            raise ProcessorError('Processor descriptor changed. Stage a new plan with the current processor.')
        from osii.server.processor_gateway import grant
        with grant(store, settings, selection, job_id, worker) as context:
            request.model_context = context
            client = ProcessorClient(url, timeout=180)
            response = client.synthesize(request) if selection['kind'] == 'synthesizer' else client.enrich(request)
    elif name in BUILTINS:
        processor = BUILTINS[name]
        response = processor.synthesize(request) if selection['kind'] == 'synthesizer' else processor.enrich(request)
    elif name == MODEL_SYNTHESIS.name:
        model = store.configuration()['chat_model']
        content, usage = provider.chat(model, [{'role': 'user', 'content': synthesis_prompt(request)}],
            max_tokens=max(256, min(int(request.config.get('max_tokens', 1200)), 4000)),
            **({"temperature": float(request.config["temperature"])} if "temperature" in request.config else {}))
        response = model_synthesis_response(request, MODEL_SYNTHESIS, content, model, {'usage': usage})
    else:
        raise ProcessorError('Unsupported processor selection')
    return validate_response(response, request, selection)


def derived_outputs(store, settings, provider, job: dict, worker: str, index: int, item: dict,
                    document: dict, *, report) -> None:
    from osii.persistence.postgres import now, identifier
    from osii.processor_sdk import DocumentInput, ScopeInput
    import hashlib
    payload = job['payload']
    records = store.extraction_records(document['file_id'])
    if not records or not document['text'].strip():
        raise ProcessorError('No primary extracted text is available for synthesis/enrichment')
    fingerprint = {'text_sha256': hashlib.sha256(document['text'].encode()).hexdigest(), 'extraction_id': records[0]['id']}
    if item.get('processing_input') and item['processing_input'] != fingerprint:
        raise ProcessorError('Primary text changed since a completed step. Stage a new plan to keep outputs consistent.')
    item['processing_input'] = fingerprint
    scope = ScopeInput(scope_type='object', scope_id=document['file_id'], documents=[DocumentInput(
        file_id=document['file_id'], filename=document['filename'], media_type=document['media_type'],
        text=document['text'], segments=records[0]['response'].get('segments', []),
        metadata={'source_relpath': document['source_relpath'], 'extraction_id': records[0]['id']})])
    for kind, selection_key, request_type in [('synthesis', 'synthesizer', SynthesisRequest), ('enrichment', 'enricher', EnrichmentRequest)]:
        selection = payload.get(selection_key)
        if not selection:
            continue
        previous = store.processing_output(job['id'], index, kind)
        if previous:
            if previous['payload'].get('input_extraction_id') != fingerprint['extraction_id']:
                raise ProcessorError('Previously saved output used a different extraction. Stage a new plan.')
            item.setdefault('steps', {})[kind] = 'done'
            continue
        item['current_step'] = kind
        store.update_processing_item(job['id'], worker, index, item)
        report(f'{kind} started: {item["path"]} · {selection["display_name"]}')
        request = request_type(request_id=identifier(), scope=scope, expert_context=payload.get('expert_context') or None,
                               config=payload.get(selection_key + '_config', {}))
        response = invoke(store, settings, provider, selection, request, job_id=job['id'], worker=worker)
        # PostgreSQL JSONB cannot represent NUL; derived output is not canonical evidence.
        data = json.loads(response.model_dump_json().replace('\\u0000', '\\ufffd'))
        item.setdefault('steps', {})[kind] = 'done'
        store.commit_processing_output(document['file_id'], kind, {
            'response': data, 'processor_kind': selection['kind'], 'created_at': now().isoformat(),
            'input_extraction_id': fingerprint['extraction_id'], 'input_text_sha256': fingerprint['text_sha256'],
            'run_id': job['id'], 'config': request.config, 'expert_context': request.expert_context,
        }, jid=job['id'], worker=worker, index=index, item=item)
        report(f'{kind} saved: {item["path"]}')
