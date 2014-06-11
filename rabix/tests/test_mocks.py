import os
import tempfile
from nose.tools import nottest, assert_equals

from rabix.common.protocol import from_url, Outputs, BaseJob
from rabix.common.util import rnd_name
from rabix.runtime.graph import JobGraph
from rabix.runtime.runners import RUNNER_MAP


def load(path):
    with open(path) as fp:
        return fp.read()


def save(val, job_id):
    result = tempfile.mktemp(dir='.')
    with open(result, 'w') as fp:
        fp.write(unicode(val))
    return os.path.join('..', job_id, result) if job_id else result


def get_inp(d, inp, unpack=False, cast=None):
    val = map(load, d.get('$inputs', {}).get(inp, []))
    if cast:
        val = map(cast, val)
    if unpack:
        val = val[0]
    return val


def generator(job):
    return Outputs({'generated': save(1, job.job_id)})


def incrementor(job):
    args = job.args
    num = get_inp(args, 'to_increment', True, int) or 0
    return Outputs({'incremented': save(num + 1, job.job_id)})


def two_step_increment(job):
    args = job.args
    if args.get('$step', 0) == 0:
        num = get_inp(args, 'to_increment', True, int) or 0
        return BaseJob(args={'the_number': num+1, '$step': 1})
    else:
        num = args.get('the_number')
        return Outputs({'incremented': save(num + 1, job.job_id)})


@nottest
def test_pipeline(pipeline_url, expected_result, output_id):
    prefix = 'x-test-%s' % rnd_name(5)  # Be warned, all dirs with this prefix will be rm -rf on success
    pipeline = from_url(pipeline_url)
    graph = JobGraph.from_pipeline(pipeline, job_prefix=prefix)
    graph.simple_run(RUNNER_MAP, {'initial': 'data:,1'})
    out = graph.get_outputs()[output_id][0]
    with open(os.path.abspath('not_a_dir/'+out)) as fp:
        assert_equals(fp.read(), expected_result)
    os.system('rm -rf %s.*' % prefix)


def test_mock_pipeline():
    test_pipeline(os.path.join(os.path.dirname(__file__), 'apps/mock.pipeline.json'), '4', 'incremented')


def test_mock_pipeline_remote_ref():
    test_pipeline(os.path.join(os.path.dirname(__file__), 'apps/mock.pipeline.remote_ref.json'), '4', 'incremented')