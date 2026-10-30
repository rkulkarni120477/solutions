"""Run one job in a process that the supervisor can stop on cancellation."""
import sys
from .worker import process

if __name__ == '__main__':
    process(sys.argv[1])
