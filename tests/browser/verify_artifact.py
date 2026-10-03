"""Optional developer-only verifier of an already generated artifact.

No npm install/build is required by the application. This helper uses an
existing Node Playwright installation when PLAYGROUND_NODE/NODE_PATH are set.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from playground.computation.evaluator import compile_computations, execute
from playground.computation.validate import prepare_inputs
from playground.ir.serialization import load_ir, to_mapping
from playground.validation.browser import alternative_values, discover_chromium


def verify_output(folder):
    folder = Path(folder).resolve()
    ir = compile_computations(load_ir((folder / 'explanation_ir.json').read_text(encoding='utf-8')))
    probes = []
    for index, control in enumerate(ir.lesson_spec.controls):
        for value in alternative_values(to_mapping(control)):
            if value == control.default:
                continue
            probes.append({'control_index':index, 'kind':control.control_type, 'value':value,
                           'expected':execute(ir, prepare_inputs(ir, {control.id:value}))[0]})
    payload = {'artifact':str(folder / 'index.html'), 'executable':str(discover_chromium()[0]),
               'baseline':execute(ir, prepare_inputs(ir, strict=True))[0], 'probes':probes,
               'presets':[execute(ir, prepare_inputs(ir, e.setup))[0] for e in ir.lesson_spec.guided_explorations]}
    result = subprocess.run([os.environ['PLAYGROUND_NODE'], str(Path(__file__).with_name('node_verify.cjs'))],
                            input=json.dumps(payload), capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise ValueError('Browser verification failed: ' + result.stderr.strip())
    return json.loads(result.stdout)


if __name__ == '__main__':
    print(json.dumps(verify_output(sys.argv[1])))
