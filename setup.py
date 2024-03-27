"""setup.py"""
from os.path import dirname, join, abspath
from setuptools import setup, find_packages

__DESCRIPTION = """This unofficial Python API provides access to \
the conversational capabilities of Anthropic's Claude AI \
through a simple chat messaging interface."""

with open(
    join(abspath(dirname(__file__)), "README.md"),
    "r",
    encoding="utf-8",
    errors="ignore",
) as fp:
    __LONG_DESCRIPTION = fp.read().lstrip().rstrip()

setup(
    name="unofficial-claude-api",
    version="0.3.1",
    author="st1vms",
    author_email="stefano.maria.salvatore@gmail.com",
    description=__DESCRIPTION,
    long_description=__LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    url="https://github.com/st1vms/unofficial-claude-api",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
    install_requires=[
        "requests",
        "selgym",
        "curl_cffi",
        "tzlocal",
        "brotli",
    ],
)
