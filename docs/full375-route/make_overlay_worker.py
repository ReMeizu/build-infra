"""Source-only transformation of the exact original worker; never compile here."""
import ast
import hashlib
import importlib.util
from pathlib import Path

PARENT_SHA = '196b46fc755f5ef77eeca02dc81c448f46f3f70daf095f3997624ec2583bc9be'
J2_HELPER_SHA = 'fc49a990999915506986d7655266b59f593acb931c655d88d66f56abb2141294'
HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / 'free-hosted-route'


def once(code, old, new):
    if code.count(old) != 1:
        raise ValueError('exact original worker transformation context required')
    return code.replace(old, new, 1)


def transformed_worker(body):
    if hashlib.sha256(body).hexdigest() != PARENT_SHA:
        raise ValueError('exact original worker bytes required')
    helper = PARENT / 'make_j2_successor.py'
    if hashlib.sha256(helper.read_bytes()).hexdigest() != J2_HELPER_SHA:
        raise ValueError('exact reviewed two-job transformation helper required')
    spec = importlib.util.spec_from_file_location('reviewed_j2_transform', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    code = module.transformed_worker(body.decode())
    code = once(code, '    from free_hosted_resource import admit\n',
                '    from overlay_io import admit, prepared_source, retain_output, source_after\n')
    start = "    source = out / 'native-source'\n"
    end = '    rust_layouts = []\n'
    if code.count(start) != 1 or code.count(end) != 1:
        raise ValueError('exact original source-copy block required')
    before, tail = code.split(start)
    old, after = tail.split(end, 1)
    if "shutil.copyfile(p, dst)" not in old or "RAM source copy differs" not in old:
        raise ValueError('reviewed original whole-source copy block required')
    code = before + '    original, source = prepared_source(controller, out, inputs)\n' + end + after
    code = once(code,
                "'path':str((native_out/relative).relative_to(out))",
                "'path':retain_output(native_out/relative, out, source)")
    code = once(code, "'path':str(p.relative_to(out))",
                "'path':retain_output(p, out, source)")
    code = once(code, "'path': str(p.relative_to(out))",
                "'path': retain_output(p, out, source)")
    code = once(code, "    (out / 'GN_RESULT.json').write_text",
                "    source_after(controller, out, inputs)\n    (out / 'GN_RESULT.json').write_text")
    code = once(code,
                '    from overlay_io import admit, prepared_source, retain_output, source_after\n',
                '    from overlay_io import admit, prepared_source, retain_output, source_after\n    from native_target_witness import capture as capture_target, complete as complete_targets\n')
    code = once(code,
                "            data = json.loads(subprocess.run(command, cwd=source, env=env,\n                capture_output=True, text=True, check=True).stdout)\n            outputs.extend(gn_output_target(source, native_out, x) for x in gn_target_outputs(data,label))",
                "            described = subprocess.run(command, cwd=source, env=env,\n                capture_output=True, text=True, check=True)\n            data = json.loads(described.stdout)\n            relative_outputs = [gn_output_target(source, native_out, x) for x in gn_target_outputs(data,label)]\n            outputs.extend(relative_outputs)\n            capture_target(out, sha(manifest), label, command, described.stdout, relative_outputs)")
    code = once(code,
                "            _milestone=out/'NATIVE_LIBRARIES_RESULT.pending.json'",
                "            complete_targets(out, sha(manifest), native_libraries, source, native_out)\n            _milestone=out/'NATIVE_LIBRARIES_RESULT.pending.json'")
    # The source, argument, target, SDK, ELF/ext4 and failure checks stay intact.
    ast.parse(code)
    return code
