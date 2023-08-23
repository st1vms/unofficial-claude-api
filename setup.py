from setuptools import setup, find_packages
from os.path import dirname, join, abspath

__DESCRIPTION = """Unofficial Claude2 API supporting direct HTTP chat creation/deletion/retrieval, \
message attachments and auto session gathering using Firefox with geckodriver. \
"""

with open(join(abspath(dirname(__file__)), "README.md"), "r") as fp:
    __LONG_DESCRIPTION = fp.read().lstrip().rstrip()

setup(
    name="unofficial-claude2-api",
    version="0.1.2",
    author="st1vms",
    author_email="stefano.maria.salvatore@gmail.com",
    description=__DESCRIPTION,
    long_description=__LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    url="https://github.com/st1vms/unofficial-claude2-api",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
    install_requires=[
        "requests",
        "selenium",
        "screeninfo",
        "tzlocal",
    ],
)
