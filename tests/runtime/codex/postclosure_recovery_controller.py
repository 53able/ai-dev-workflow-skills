"""Recovery Root stdin dispatcher; synchronous reviewed operators, one fixed environment.

No model/native process starts on import. The external Root owns stdin. Each
request still requires its exact separately released command and caller digest.
No command creation, claim override, retry, shell evaluation or environment
rewriting. A failed operation terminates this dispatcher. All producer-owned
native processes close before another Root request can be read.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SOURCE / 'tests/runtime/codex'))
import postclosure_recovery as core
import postclosure_recovery_operator as operator


def diagnostic(error):
    """Keep cause/source positions; expose only these source-owned messages."""
    reasons = {'bounded complete Root request required', 'Root request object required',
               'unique bounded Root request ID required', 'unsupported Root operation',
               'Root command outside current C', 'Root environment drift'}
    chain, seen = [], set()
    while error is not None and id(error) not in seen and len(chain) < 8:
        seen.add(id(error))
        entry = {'exception_type': type(error).__name__, 'frames': [
            {'file': frame.f_code.co_filename, 'function': frame.f_code.co_name, 'line': line}
            for frame, line in list(traceback.walk_tb(error.__traceback__))[-16:]]}
        if type(error) is core.Hold and error.args and type(error.args[0]) is str and error.args[0] in reasons:
            entry['reason'] = error.args[0]
        chain.append(entry)
        error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    return {'chain': chain}


def serve(input_stream, output_stream, *, lookup=operator.produce_lookup,
          execute=operator.run_released):
    environment_hash = core.canonical_hash(dict(os.environ))
    core.require(not any(os.environ.get(key) is not None
                         for key in core.PYTHON_ENVIRONMENT if key != 'PATH'),
                 'Root dispatcher requires unmodified test interpreter environment')
    seen = set()

    def emit(value):
        output_stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
        output_stream.flush()

    emit({'state': 'READY', 'environment_sha256': environment_hash,
          'controller_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    while True:
        line = input_stream.readline(65537)
        if not line:
            return 0
        request_id = None
        try:
            core.require(len(line) <= 65536 and line.endswith(b'\n'), 'bounded complete Root request required')
            request = core.decode(line)
            core.require(type(request) is dict, 'Root request object required')
            request_id = request.get('id')
            core.require(type(request_id) is str and 0 < len(request_id) <= 64 and
                         request_id not in seen, 'unique bounded Root request ID required')
            seen.add(request_id)
            if request.get('operation') == 'stop':
                core.fields(request, 'id operation')
                emit({'id': request_id, 'state': 'STOPPED'})
                return 0
            core.fields(request, 'id operation command')
            core.require(request['operation'] in ('lookup', 'execute'), 'unsupported Root operation')
            command = request['command']
            core.ref_shape(command)
            core.require(Path(command['path']).is_relative_to(core.CONTROL_ROOT), 'Root command outside current C')
            core.require(core.canonical_hash(dict(os.environ)) == environment_hash, 'Root environment drift')
            raw = (lookup if request['operation'] == 'lookup' else execute)(command, command['sha256'])
            core.require(core.canonical_hash(dict(os.environ)) == environment_hash, 'Root environment drift')
            if request['operation'] == 'lookup':
                failure = raw['native_facts']['failure']
                result = {'USER': raw['USER'], 'candidate': raw['native_facts']['invariant_candidate']}
            else:
                failure = raw['failure']
                result = {'accounting': raw['accounting'], 'business_PASS': False}
            emit({'id': request_id, 'state': 'COMPLETED' if failure is None else 'FAILED',
                  'failure': failure, **result})
            if failure is not None:
                return 1
        except BaseException as error:
            emit({'id': request_id, 'state': 'FAILED', 'exception_type': type(error).__name__,
                  'diagnostic': diagnostic(error)})
            return 1


if __name__ == '__main__':
    raise SystemExit(serve(sys.stdin.buffer, sys.stdout))
