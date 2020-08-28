"""
Module that takes care of executing input/scripts by injecting them inside the interpreter

IMPORTANT NOTE:
    This module is NOT executing any potentially malicious code, e.g. the one being scanned by aura.
    It is intended to inject helper scripts that parse AST information or other kind of info from the source code.
    This allows aura to process both Py2k and Py3k source code as it injects the parsers into the appropriate
    interpreter that is able to parse the target source code.
"""

import os
import subprocess
from shutil import which
from typing import List

import rapidjson as json

from . import config
from .exceptions import PythonExecutorError


LOGGER = config.get_logger(__name__)


def run_with_interpreters(*, metadata=None, **kwargs):
    """
    Proxy to execute_interpreter
    Iterates over defined interpreter until one that runs the input/script is found

    Return a 3-tuple with the following elements:
    - JSON decoded output of the executed script
    - name of the interpreter as defined in aura config
    - path/command to the interpreter as defined in aura config

    In case an interpreter that is able to execute the input script was not found, all tuple elements are set to None
    """
    if metadata and metadata.get("interpreter_path"):
        return execute_interpreter(
            interpreter=metadata["interpreter_path"],
            **kwargs
        )

    interpreters = list(config.CFG["interpreters"].items())
    executor_exception = None

    for name, interpreter in interpreters:
        # If interpreter is not directly an executable, find out it's location via `witch` lookup
        if not os.path.isfile(interpreter):
            interpreter = which(interpreter)

        try:
            output = execute_interpreter(interpreter=interpreter, **kwargs)
            if output is not None:
                if metadata is not None:
                    metadata["interpreter_name"] = name
                    metadata["interpreter_path"] = interpreter

                return output
        except PythonExecutorError as exc:
            executor_exception = exc
            continue

    if executor_exception is not None:
        raise executor_exception


def execute_interpreter(*, command: List[str], interpreter: str, stdin=None):
    """
    Run script/command inside the defined interpreter and retrieve the JSON encoded output

    :param command: command/path to script to execute
    :param interpreter: command/path to the Python interpreter used for execution
    :param stdin: stdin to pass to the execute program
    :return: json decoded stdout
    """

    full_args = [interpreter] + command
    proc = subprocess.run(
        args=full_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        input=stdin
    )
    if proc.returncode == 0:
        payload = None
        try:
            payload = proc.stdout
            return json.loads(payload)
        except json.JSONDecodeError:
            LOGGER.exception(f"Error decoding interpreter JSON: {repr(payload)}")
            new_exception = PythonExecutorError("Error decoding python interpreter JSON")
            new_exception.stdout = payload
            new_exception.stderr = proc.stderr
            raise new_exception
    else:
        exc = PythonExecutorError(f"Interpreter exited with non-zero status code: {proc.returncode}")
        exc.stderr = proc.stderr
        exc.stdout = proc.stdout
        raise exc