import subprocess
import shlex


def run(args):
    if not isinstance(args, str):
        args = ' '.join(args)
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    return p.stdout.decode()

result = run(('/usr/bin/ls', '-al'))

print(result)
