import subprocess
import shlex


def run(args):
    if isinstance(args, str):
        args = shlex.split(args)
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    return p.stdout.decode()

result = run('/usr/bin/ls -al')

print(result)
