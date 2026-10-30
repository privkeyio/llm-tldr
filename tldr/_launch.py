"""Start Python subprocesses without letting the working directory shadow modules."""

import sys

# Python 3.10 has no -P: drop the '' entry -c adds before importing anything else.
_BOOTSTRAP = (
    "import sys; sys.path.pop(0); sys.argv.pop(0); import runpy; "
    "runpy.run_module(sys.argv[0], run_name='__main__', alter_sys=True)"
)


def python_module_argv(module: str, *args: str) -> list[str]:
    if sys.version_info >= (3, 11):
        return [sys.executable, "-P", "-m", module, *args]
    return [sys.executable, "-c", _BOOTSTRAP, module, *args]
