import subprocess
import shlex


def run(args):
    if isinstance(args, str):
        args = shlex.split(args)
    p = subprocess.check_output(args)
    return p.decode()

result = run('/usr/bin/ls -al')

print(result)
