# setup.py
from setuptools import setup

setup(
    name='autoparser',
    version='0.1.0',
    description='Dataclass‑based argparse bridge with recursive subparser support',
    long_description='''\
Light‑weight argparse generator based on dataclasses and typing.Annotated,
with full nesting/subparser support and type‑safe dispatch.
''',
    author='Matthew Krafczyk',
    author_email='krafczyk.matthew@gmail.com',
    url='https://github.com/krafczyk/autoparser',  # adjust or remove
    py_modules=['autoparser'],
    python_requires='>=3.8',
    install_requires=[
        # no dependencies outside the stdlib
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
)

