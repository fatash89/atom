import signal
import time
from typing import Callable


class TimedOutException(Exception):
    """
    Raised when a timeout happens
    """

    pass


def alarm_handler(signum, frame):
    """
    Handle SIGALRM signals in response to a timeout event
    """
    raise TimedOutException()


def exec_with_deadline(func: Callable, timeout: float = 0.0):
    """
    Execute a function within a time limit

    Args:
        func: A callable to execute
        timeout: Time limit in seconds

    Returns:
        Whatever func returns

    Raises:
        TimedOutException: If execution reaches time limit
    """

    def wrapper(*args, **kwargs):
        # Note the original handler state so we can restore it later
        old_handler = signal.signal(signal.SIGALRM, alarm_handler)

        # Set alarm using a real time timer that accepts floats as a timeout.
        # The alternative, signal.alarm, only accepts int seconds as a timeout.
        signal.setitimer(signal.ITIMER_REAL, timeout)

        try:
            # Execute the function. If this function runs longer than timeout, a
            # SIGALRM signal is sent to this process. The signal is handled
            # using alarm_handler, which raises a TimedOutException.
            result = func(*args, **kwargs)

        except Exception as e:
            # Either the function took too long to execute (raising a
            # TimedOutException) or the function errored out before the time
            # limit (raising any other Exception).
            raise e

        finally:
            # Always restore the old signal handler and remove the alarm
            signal.signal(signal.SIGALRM, old_handler)
            signal.setitimer(signal.ITIMER_REAL, 0)

        return result

    return wrapper


if __name__ == "__main__":

    def command_normal():
        """Run for 1 second"""
        for _ in range(1):
            time.sleep(1)

        return "Normal command returned"

    def command_timeout():
        """Run for 5 seconds (longer than timeout)"""
        for _ in range(5):
            time.sleep(1)

        return "Ran timeout command"

    def command_error():
        """Raise an error after 1 second"""
        for _ in range(1):
            time.sleep(1)

        raise RuntimeError

    def run_command(command):
        try:
            print(exec_with_deadline(command, timeout=3.1)())
        except TimedOutException:
            print("Timed out")
        except Exception:
            print("Errored out")
        else:
            print("Normal")

    run_command(command_normal)  # Normal command returned, Normal
    run_command(command_error)  # Errored out
    run_command(command_timeout)  # Timed out
