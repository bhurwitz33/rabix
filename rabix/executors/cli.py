import docopt
import sys
import logging
import six
import collections
from rabix import __version__ as version
from rabix.executors.runner import DockerRunner, NativeRunner
from rabix.cliche.adapter import Adapter, from_url
from rabix.common.util import set_log_level


TEMPLATE_JOB = {
    'app': 'http://example.com/app.json',
    'inputs': {},
    'platform': 'http://example.org/my_platform/v1',
    'allocatedResources': {
        "cpu": 4,
        "mem": 5000,
        "ports": [],
        "diskSpace": 20000,
        "network": False
    }
}

USAGE = '''
Usage:
    rabix <tool> [-v...] [-hcI] [-d <dir>] [-i <inp>] [-- {inputs}...]
    rabix --version

    Options:
  -d --dir=<dir>       Working directory for the task. If not provided one will
                       be auto generated in the current dir.
  -h --help            Show this help message. In conjunction with tool,
                       it will print inputs you can provide for the job.

  -I --install         Only install referenced tools. Do not run anything.
  -i --inp-file=<inp>  Inputs
  -c --print-cli       Only print calculated command line. Do not run anything.
  -v --verbose         Verbosity. More Vs more output.
     --version         Print version and exit.
'''

TOOL_TEMPLATE = '''
Usage:
  tool {inputs}
'''


def update_dict(dct, new_dct):
    for key, val in six.iteritems(new_dct):
        t = dct
        if '.' in key:
            for k in key.split('.'):
                if k == key.split('.')[-1]:
                    if isinstance(val, collections.Mapping):
                        t = t.setdefault(k, {})
                        update_dict(t, new_dct[key])
                    else:
                        t[k] = val
                else:
                    if not isinstance(t.get(k), collections.Mapping):
                        t[k] = {}
                    t = t.setdefault(k, {})
        else:
            if isinstance(val, collections.Mapping):
                t = t.setdefault(key, {})
                update_dict(t, new_dct[key])
            else:
                t[key] = val


def make_tool_usage_string(tool, template=TOOL_TEMPLATE, inp={}):

    def required(req, arg, inputs):
        inp = inputs.keys()
        if req and (arg not in inp):
            return True
        return False

    inputs = tool.get('inputs', {}).get('properties')
    usage_str = []
    param_str = []
    for k, v in inputs.items():
        if v.get('type') == 'file':
            arg = '--%s=<file>' % k
            usage_str.append(arg if required(v.get('required'), k, inp)
                             else '[%s]' % arg)
        elif v.get('type') == 'array':
            if ((v.get('items').get('type') == 'file' or v.get(
                    'items').get('type') == 'directory')):
                arg = '--%s=<file>...' % k
                usage_str.append(arg if required(v.get('required'), k, inp)
                                 else '[%s]' % arg)
            else:
                arg = '--%s=<array_%s_separator(%s)>...' % (k, v.get(
                    'items').get('type'), v.get('adapter').get(
                        'itemSeparator'))
                param_str.append(arg if required(v.get('required'), k, inp)
                                 else '[%s]' % arg)
        else:
            arg = '--%s=<%s>' % (k, v.get('type'))
            param_str.append(arg if required(v.get('required'), k, inp)
                             else '[%s]' % arg)
    usage_str.extend(param_str)
    return template.format(inputs=' '.join(usage_str))


def resolve(k, v, nval, inp):
    if isinstance(nval, list):
        if v.get('type') != 'array':
            raise Exception('Too many values')
        inp[k] = []
        for nv in nval:
            if (v['items']['type'] == 'file' or v['items'][
                    'type'] == 'directory'):
                inp[k].append({'path': nv})
            else:
                inp[k].append(nv)
    else:
        if (v['type'] == 'file' or v['type'] == 'directory'):
            inp[k] = {'path': nval}
        else:
            inp[k] = nval


def get_inputs(tool, args):
    inp = {}
    inputs = tool.get('inputs', {}).get('properties')
    for k, v in six.iteritems(inputs):
        nval = args.get('--' + k) or args.get(k)
        if nval:
            resolve(k, v, nval, inp)
    return {'inputs': inp}


def update_paths(job, inputs):
    for inp in inputs['inputs'].keys():
        job['inputs'][inp] = inputs['inputs'][inp]
    return job


def get_tool(args):
    if args['<tool>']:
        return from_url(args['<tool>'])


def dry_run_parse(args=None):
    args = args or sys.argv[1:]
    args = args + ['an_input']
    usage = USAGE.format(inputs='<inputs>')
    try:
        return docopt.docopt(usage, args, version=version, help=False)
    except docopt.DocoptExit:
        return


def main():
    logging.basicConfig(level=logging.WARN)
    if len(sys.argv) == 1:
        print(USAGE)
        return

    usage = USAGE.format(inputs='<inputs>')
    tool_usage = usage

    if len(sys.argv) == 2 and \
            (sys.argv[1] == '--help' or sys.argv[1] == '-h'):
        print(USAGE)
        return

    dry_run_args = dry_run_parse()
    if not dry_run_args:
        print(USAGE)
        return

    if not (dry_run_args['<tool>']):
        print('You have to specify a tool, with --tool option')
        print(usage)
        return

    tool = get_tool(dry_run_args)
    if not tool:
        print("Couldn't find tool.")
        return

    runner = DockerRunner(tool)

    if dry_run_args['--install']:
        runner.install()
        print("Install successful.")
        return

    try:
        args = docopt.docopt(usage, version=version, help=False)
        job = TEMPLATE_JOB
        set_log_level(dry_run_args['--verbose'])

        if args['--inp-file']:
            input_file = from_url(args.get('--inp-file'))
            update_dict(job['inputs'], get_inputs(tool, input_file)['inputs'])

        tool_inputs_usage = make_tool_usage_string(
            tool, template=TOOL_TEMPLATE, inp=job['inputs'])
        tool_usage = make_tool_usage_string(tool, USAGE, job['inputs'])

        tool_inputs = docopt.docopt(tool_inputs_usage, args['<inputs>'])

        if args['--help']:
            print(tool_usage)
            return

        inp = get_inputs(tool, tool_inputs)
        job = update_paths(job, inp)

        if args['--print-cli']:
            adapter = Adapter(tool)
            print(adapter.cmd_line(job))
            return

        runner.run_job(job, job_id=args.get('--dir'))

    except docopt.DocoptExit:
        print(tool_usage)
        return


if __name__ == '__main__':
    main()
